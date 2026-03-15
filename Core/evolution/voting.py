"""
evolution/voting.py
Ballot tally, quorum checking, and bond-return logic for NodeProposals.

Voting is stake-weighted: a validator's vote counts proportionally to its
stake on the subnet. Quorum requires both a minimum participation threshold
(% of total stake that voted) and a minimum approval ratio among contested
votes (for + against).

Vote lifecycle:
  1. Proposal enters VOTING status when submitted
  2. Validators call cast_vote() during the voting window
  3. tally() is called each epoch by the validator loop
  4. If voting_closes_at_block is reached:
       - quorum met + approved  → ACCEPTED  (bond held for integration)
       - quorum met + rejected  → REJECTED  (bond returned immediately)
       - quorum not met         → REJECTED  (bond returned, low interest)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

import bittensor as bt

from config.subnet_config import SubnetConfig
from evolution.proposal import NodeProposal, ProposalStatus


# ---------------------------------------------------------------------------
# Vote dataclass
# ---------------------------------------------------------------------------

class VoteChoice(str, Enum):
    FOR     = "for"
    AGAINST = "against"
    ABSTAIN = "abstain"


@dataclass
class Vote:
    proposal_id: str
    voter_hotkey: str
    voter_uid: int
    choice: VoteChoice
    stake_weight: float          # validator's stake at time of vote
    cast_at_block: int
    cast_at: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# TallyResult
# ---------------------------------------------------------------------------

@dataclass
class TallyResult:
    proposal_id: str
    epoch_block: int

    votes_for: float       = 0.0
    votes_against: float   = 0.0
    votes_abstain: float   = 0.0
    total_stake_voted: float = 0.0
    total_stake_network: float = 0.0

    quorum_met: bool       = False
    approved: bool         = False
    outcome: Optional[ProposalStatus] = None   # ACCEPTED | REJECTED | None (still open)

    @property
    def participation_ratio(self) -> float:
        if self.total_stake_network == 0:
            return 0.0
        return self.total_stake_voted / self.total_stake_network

    @property
    def approval_ratio(self) -> float:
        contested = self.votes_for + self.votes_against
        if contested == 0:
            return 0.0
        return self.votes_for / contested

    def summary(self) -> str:
        return (
            f"proposal={self.proposal_id} "
            f"for={self.votes_for:.3f} against={self.votes_against:.3f} "
            f"abstain={self.votes_abstain:.3f} "
            f"participation={self.participation_ratio:.1%} "
            f"approval={self.approval_ratio:.1%} "
            f"outcome={self.outcome}"
        )


# ---------------------------------------------------------------------------
# BondReturn
# ---------------------------------------------------------------------------

class BondReturn:
    """
    Handles returning the proposal bond to the proposer on rejection.
    In production this calls a custom refund extrinsic; here we model
    it as a transfer from the escrow address back to the proposer coldkey.
    """

    def __init__(self, subtensor: bt.subtensor, cfg: SubnetConfig):
        self.subtensor = subtensor
        self.cfg = cfg

    def return_bond(
        self,
        proposal: NodeProposal,
        escrow_wallet: bt.wallet,
    ) -> bool:
        """
        Transfer bond_amount TAO from escrow back to proposer coldkey.
        Returns True on success.
        """
        try:
            # Look up proposer coldkey address from metagraph or on-chain
            # For now we use the proposer_hotkey as a proxy;
            # in production you'd resolve the associated coldkey.
            dest = proposal.proposer_hotkey
            amount = bt.Balance.from_tao(proposal.bond_amount)

            success, msg = self.subtensor.transfer(
                wallet=escrow_wallet,
                dest=dest,
                amount=amount,
                wait_for_inclusion=True,
            )
            if success:
                bt.logging.success(
                    f"Bond returned: {proposal.bond_amount} TAO → {dest[:8]}... "
                    f"(proposal={proposal.proposal_id})"
                )
            else:
                bt.logging.error(f"Bond return failed: {msg}")
            return success

        except Exception as exc:
            bt.logging.error(f"BondReturn exception: {exc}", exc_info=True)
            return False


# ---------------------------------------------------------------------------
# VotingEngine
# ---------------------------------------------------------------------------

class VotingEngine:
    """
    Manages the full voting lifecycle for all active proposals.

    One VotingEngine instance lives on each validator and is driven by
    the epoch loop. Votes are cast by validators when they observe a
    new proposal on-chain.
    """

    def __init__(
        self,
        subtensor: bt.subtensor,
        metagraph: bt.metagraph,
        escrow_wallet: bt.wallet,
        cfg: Optional[SubnetConfig] = None,
    ):
        self.subtensor     = subtensor
        self.metagraph     = metagraph
        self.escrow_wallet = escrow_wallet
        self.cfg           = cfg or SubnetConfig()
        self.bond_return   = BondReturn(subtensor, self.cfg)

        # proposal_id → list of votes cast
        self._votes: Dict[str, List[Vote]] = {}
        # proposal_id → set of hotkeys that already voted (dedup)
        self._voted: Dict[str, set] = {}

    # ── Casting votes ─────────────────────────────────────────────────

    def cast_vote(
        self,
        proposal: NodeProposal,
        voter_hotkey: str,
        choice: VoteChoice,
        current_block: int,
    ) -> bool:
        """
        Record a vote. Returns False if the voter already voted on this
        proposal or the voting window is closed.
        """
        pid = proposal.proposal_id

        if proposal.status not in (ProposalStatus.SUBMITTED, ProposalStatus.VOTING):
            bt.logging.warning(f"cast_vote: proposal {pid} is not in voting state")
            return False

        if proposal.voting_closes_at_block and current_block > proposal.voting_closes_at_block:
            bt.logging.warning(f"cast_vote: voting window closed for {pid}")
            return False

        self._voted.setdefault(pid, set())
        if voter_hotkey in self._voted[pid]:
            bt.logging.debug(f"cast_vote: {voter_hotkey[:8]}... already voted on {pid}")
            return False

        # Resolve stake weight
        stake = 0.0
        if voter_hotkey in self.metagraph.hotkeys:
            uid = self.metagraph.hotkeys.index(voter_hotkey)
            stake = float(self.metagraph.S[uid])

        if stake < self.cfg.MIN_VALIDATOR_STAKE_TO_VOTE:
            bt.logging.debug(
                f"cast_vote: {voter_hotkey[:8]}... stake={stake:.2f} below minimum"
            )
            return False

        vote = Vote(
            proposal_id=pid,
            voter_hotkey=voter_hotkey,
            voter_uid=self.metagraph.hotkeys.index(voter_hotkey)
                      if voter_hotkey in self.metagraph.hotkeys else -1,
            choice=choice,
            stake_weight=stake,
            cast_at_block=current_block,
        )
        self._votes.setdefault(pid, []).append(vote)
        self._voted[pid].add(voter_hotkey)

        # Transition proposal to VOTING if still SUBMITTED
        if proposal.status == ProposalStatus.SUBMITTED:
            proposal.status = ProposalStatus.VOTING

        bt.logging.info(
            f"Vote cast: {voter_hotkey[:8]}... {choice.value} on {pid} "
            f"(stake={stake:.2f})"
        )
        return True

    # ── Tallying ──────────────────────────────────────────────────────

    def _total_network_stake(self) -> float:
        return float(self.metagraph.S.sum())

    def tally(
        self,
        proposal: NodeProposal,
        current_block: int,
    ) -> TallyResult:
        """
        Compute the current tally for a proposal.
        Does NOT mutate proposal status — call finalise() for that.
        """
        pid = proposal.proposal_id
        votes = self._votes.get(pid, [])

        result = TallyResult(
            proposal_id=pid,
            epoch_block=current_block,
            total_stake_network=self._total_network_stake(),
        )

        for vote in votes:
            result.total_stake_voted += vote.stake_weight
            if vote.choice == VoteChoice.FOR:
                result.votes_for += vote.stake_weight
            elif vote.choice == VoteChoice.AGAINST:
                result.votes_against += vote.stake_weight
            else:
                result.votes_abstain += vote.stake_weight

        # Sync tally back onto proposal object
        proposal.votes_for     = result.votes_for
        proposal.votes_against = result.votes_against
        proposal.votes_abstain = result.votes_abstain

        result.quorum_met = (
            result.participation_ratio >= self.cfg.VOTE_QUORUM_PARTICIPATION
        )
        result.approved = (
            result.approval_ratio >= self.cfg.VOTE_APPROVAL_THRESHOLD
        )

        # Determine outcome only if window is closed
        if (
            proposal.voting_closes_at_block
            and current_block >= proposal.voting_closes_at_block
        ):
            if result.quorum_met and result.approved:
                result.outcome = ProposalStatus.ACCEPTED
            else:
                result.outcome = ProposalStatus.REJECTED

        return result

    def finalise(
        self,
        proposal: NodeProposal,
        result: TallyResult,
    ) -> ProposalStatus:
        """
        Apply the tally outcome to the proposal and trigger bond return
        if rejected. Returns the new ProposalStatus.
        """
        if result.outcome is None:
            return proposal.status   # window still open

        if result.outcome == ProposalStatus.ACCEPTED:
            proposal.status = ProposalStatus.ACCEPTED
            bt.logging.success(
                f"Proposal ACCEPTED: {proposal.proposal_id} | {result.summary()}"
            )

        elif result.outcome == ProposalStatus.REJECTED:
            proposal.status = ProposalStatus.REJECTED
            bt.logging.warning(
                f"Proposal REJECTED: {proposal.proposal_id} | {result.summary()}"
            )
            returned = self.bond_return.return_bond(proposal, self.escrow_wallet)
            if returned:
                proposal.status = ProposalStatus.BOND_RETURNED

        return proposal.status

    def process_epoch(
        self,
        proposals: List[NodeProposal],
        current_block: int,
    ) -> List[Tuple[NodeProposal, TallyResult]]:
        """
        Convenience method: tally + finalise all active proposals.
        Returns list of (proposal, tally_result) for audit logging.
        """
        results = []
        for proposal in proposals:
            if not proposal.is_active:
                continue
            result = self.tally(proposal, current_block)
            self.finalise(proposal, result)
            bt.logging.info(f"Voting tally: {result.summary()}")
            results.append((proposal, result))
        return results

    def votes_for_proposal(self, proposal_id: str) -> List[Vote]:
        return list(self._votes.get(proposal_id, []))

    def voter_count(self, proposal_id: str) -> int:
        return len(self._voted.get(proposal_id, set()))
