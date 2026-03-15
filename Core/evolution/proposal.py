"""
evolution/proposal.py
NodeProposal dataclass and on-chain submission logic.

A NodeProposal is how new knowledge-graph nodes (and their associated miners)
enter the subnet. The proposer bonds TAO, submits metadata on-chain via
subtensor commitments, and the proposal enters the voting window defined in
evolution/voting.py.

Lifecycle:
  DRAFT → SUBMITTED → VOTING → ACCEPTED | REJECTED → (ACCEPTED) INTEGRATING → LIVE
                                                      (REJECTED) BOND_RETURNED
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import bittensor as bt

from config.subnet_config import SubnetConfig


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ProposalStatus(str, Enum):
    DRAFT        = "draft"
    SUBMITTED    = "submitted"
    VOTING       = "voting"
    ACCEPTED     = "accepted"
    REJECTED     = "rejected"
    INTEGRATING  = "integrating"
    LIVE         = "live"
    BOND_RETURNED = "bond_returned"


class ProposalType(str, Enum):
    ADD_NODE    = "add_node"     # introduce a new graph node
    REMOVE_NODE = "remove_node"  # deprecate an existing node
    ADD_EDGE    = "add_edge"     # add a directed edge between existing nodes
    UPDATE_META = "update_meta"  # change persona / domain metadata for a node


# ---------------------------------------------------------------------------
# NodeProposal dataclass
# ---------------------------------------------------------------------------

@dataclass
class NodeProposal:
    """
    Represents a single evolution proposal.

    Fields marked *on-chain* are hashed and committed to subtensor.
    Fields marked *off-chain* are stored locally and referenced by proposal_id.
    """

    # ── identity ─────────────────────────────────────────────────────────
    proposal_id: str                        # SHA-256 of canonical payload
    proposal_type: ProposalType

    # ── proposer ─────────────────────────────────────────────────────────
    proposer_hotkey: str
    proposer_uid: int
    bond_amount: float                      # TAO bonded by proposer

    # ── node metadata (on-chain) ─────────────────────────────────────────
    node_id: str                            # proposed canonical node identifier
    domain: str                             # knowledge domain tag
    persona: str = "neutral"               # narrative persona
    adjacency: List[str] = field(default_factory=list)  # proposed edges (dst node_ids)

    # ── miner binding ────────────────────────────────────────────────────
    miner_hotkey: Optional[str] = None      # hotkey that will serve this node
    corpus_manifest_cid: Optional[str] = None  # IPFS CID of the corpus manifest

    # ── lifecycle ────────────────────────────────────────────────────────
    status: ProposalStatus = ProposalStatus.DRAFT
    submitted_at_block: Optional[int] = None
    voting_closes_at_block: Optional[int] = None
    accepted_at_block: Optional[int] = None
    integration_starts_at_block: Optional[int] = None

    # ── vote tallies (populated during voting) ───────────────────────────
    votes_for: float = 0.0                  # stake-weighted yes votes
    votes_against: float = 0.0
    votes_abstain: float = 0.0

    # ── metadata (off-chain) ─────────────────────────────────────────────
    description: str = ""
    tags: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    # ── helpers ──────────────────────────────────────────────────────────

    @classmethod
    def compute_id(
        cls,
        proposal_type: ProposalType,
        node_id: str,
        proposer_hotkey: str,
        timestamp: float,
    ) -> str:
        payload = json.dumps(
            {
                "type": proposal_type.value,
                "node_id": node_id,
                "proposer": proposer_hotkey,
                "ts": round(timestamp, 3),
            },
            sort_keys=True,
        ).encode()
        return hashlib.sha256(payload).hexdigest()[:32]

    def canonical_payload(self) -> Dict[str, Any]:
        """Minimal on-chain payload — kept small to fit subtensor commitment."""
        return {
            "id": self.proposal_id,
            "type": self.proposal_type.value,
            "node_id": self.node_id,
            "domain": self.domain,
            "persona": self.persona,
            "adjacency": sorted(self.adjacency),
            "miner_hotkey": self.miner_hotkey or "",
            "corpus_cid": self.corpus_manifest_cid or "",
            "bond": round(self.bond_amount, 6),
            "proposer": self.proposer_hotkey,
        }

    def commitment_hash(self) -> str:
        payload = json.dumps(self.canonical_payload(), sort_keys=True).encode()
        return hashlib.sha256(payload).hexdigest()

    @property
    def is_active(self) -> bool:
        return self.status in (ProposalStatus.SUBMITTED, ProposalStatus.VOTING)

    @property
    def total_votes(self) -> float:
        return self.votes_for + self.votes_against + self.votes_abstain

    @property
    def approval_ratio(self) -> float:
        contested = self.votes_for + self.votes_against
        return self.votes_for / contested if contested > 0 else 0.0


# ---------------------------------------------------------------------------
# ProposalSubmitter
# ---------------------------------------------------------------------------

class ProposalSubmitter:
    """
    Handles building, validating, and submitting NodeProposals on-chain.

    On-chain submission uses subtensor's ``commit`` extrinsic to store the
    commitment hash (not the full payload) in the subnet's on-chain storage.
    Full proposal metadata is pinned to IPFS and referenced by CID.
    """

    def __init__(
        self,
        wallet: bt.wallet,
        subtensor: bt.subtensor,
        metagraph: bt.metagraph,
        cfg: Optional[SubnetConfig] = None,
    ):
        self.wallet = wallet
        self.subtensor = subtensor
        self.metagraph = metagraph
        self.cfg = cfg or SubnetConfig()
        self._submitted: Dict[str, NodeProposal] = {}

    # ── validation ───────────────────────────────────────────────────

    def _validate(self, proposal: NodeProposal) -> None:
        """Raise ValueError if the proposal is malformed or violates policy."""
        if not proposal.node_id:
            raise ValueError("node_id must not be empty")
        if not proposal.domain:
            raise ValueError("domain must not be empty")
        if proposal.bond_amount < self.cfg.MIN_PROPOSAL_BOND:
            raise ValueError(
                f"bond_amount {proposal.bond_amount} TAO is below minimum "
                f"{self.cfg.MIN_PROPOSAL_BOND} TAO"
            )
        if proposal.proposal_type == ProposalType.ADD_NODE and not proposal.miner_hotkey:
            raise ValueError("ADD_NODE proposal must specify a miner_hotkey")
        if len(proposal.adjacency) > self.cfg.MAX_PROPOSAL_ADJACENCY:
            raise ValueError(
                f"adjacency list length {len(proposal.adjacency)} exceeds "
                f"maximum {self.cfg.MAX_PROPOSAL_ADJACENCY}"
            )

        hotkey = self.wallet.hotkey.ss58_address
        if hotkey not in self.metagraph.hotkeys:
            raise ValueError(f"proposer hotkey {hotkey!r} is not registered on the subnet")

    # ── bond ─────────────────────────────────────────────────────────

    def _lock_bond(self, amount: float) -> bool:
        """
        Transfer bond from the proposer's coldkey to the subnet's bond escrow.
        Returns True on success.

        In production this calls a custom extrinsic; here we use a transfer
        to the well-known escrow address defined in subnet_config.
        """
        try:
            success, err = self.subtensor.transfer(
                wallet=self.wallet,
                dest=self.cfg.BOND_ESCROW_ADDRESS,
                amount=bt.Balance.from_tao(amount),
                wait_for_inclusion=True,
            )
            if not success:
                bt.logging.error(f"Bond transfer failed: {err}")
            return success
        except Exception as exc:
            bt.logging.error(f"Bond lock exception: {exc}", exc_info=True)
            return False

    # ── on-chain commitment ──────────────────────────────────────────

    def _commit_on_chain(self, proposal: NodeProposal) -> bool:
        """
        Write the commitment hash to subtensor storage via the ``commit``
        extrinsic.  The full payload is expected to be on IPFS already.
        """
        commitment = proposal.commitment_hash()
        try:
            success = self.subtensor.commit(
                wallet=self.wallet,
                netuid=self.cfg.NETUID,
                data=commitment,
            )
            return bool(success)
        except Exception as exc:
            bt.logging.error(f"On-chain commitment failed: {exc}", exc_info=True)
            return False

    # ── public API ───────────────────────────────────────────────────

    def build(
        self,
        proposal_type: ProposalType,
        node_id: str,
        domain: str,
        persona: str = "neutral",
        adjacency: Optional[List[str]] = None,
        miner_hotkey: Optional[str] = None,
        corpus_manifest_cid: Optional[str] = None,
        bond_amount: Optional[float] = None,
        description: str = "",
        tags: Optional[List[str]] = None,
    ) -> NodeProposal:
        """Construct a NodeProposal (status=DRAFT) without submitting."""
        hotkey = self.wallet.hotkey.ss58_address
        uid = (
            self.metagraph.hotkeys.index(hotkey)
            if hotkey in self.metagraph.hotkeys
            else -1
        )
        now = time.time()
        proposal_id = NodeProposal.compute_id(proposal_type, node_id, hotkey, now)

        return NodeProposal(
            proposal_id=proposal_id,
            proposal_type=proposal_type,
            proposer_hotkey=hotkey,
            proposer_uid=uid,
            bond_amount=bond_amount or self.cfg.DEFAULT_PROPOSAL_BOND,
            node_id=node_id,
            domain=domain,
            persona=persona,
            adjacency=adjacency or [],
            miner_hotkey=miner_hotkey,
            corpus_manifest_cid=corpus_manifest_cid,
            description=description,
            tags=tags or [],
            created_at=now,
        )

    def submit(self, proposal: NodeProposal) -> NodeProposal:
        """
        Validate → lock bond → commit on-chain → mark SUBMITTED.
        Returns the updated proposal. Raises on failure.
        """
        self._validate(proposal)

        bt.logging.info(
            f"Submitting proposal id={proposal.proposal_id} "
            f"type={proposal.proposal_type.value} node={proposal.node_id}"
        )

        # Lock bond
        if not self._lock_bond(proposal.bond_amount):
            raise RuntimeError("Failed to lock proposal bond on-chain")

        # Commit hash
        current_block = self.subtensor.get_current_block()
        if not self._commit_on_chain(proposal):
            raise RuntimeError("Failed to commit proposal hash to subtensor")

        proposal.status = ProposalStatus.SUBMITTED
        proposal.submitted_at_block = current_block
        proposal.voting_closes_at_block = (
            current_block + self.cfg.VOTING_WINDOW_BLOCKS
        )

        self._submitted[proposal.proposal_id] = proposal
        bt.logging.success(
            f"Proposal {proposal.proposal_id} submitted at block={current_block}. "
            f"Voting closes at block={proposal.voting_closes_at_block}."
        )
        return proposal

    def get(self, proposal_id: str) -> Optional[NodeProposal]:
        return self._submitted.get(proposal_id)

    def all_active(self) -> List[NodeProposal]:
        return [p for p in self._submitted.values() if p.is_active]

    def update_status(self, proposal_id: str, status: ProposalStatus) -> None:
        if proposal_id in self._submitted:
            self._submitted[proposal_id].status = status
