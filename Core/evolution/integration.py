"""
evolution/integration.py
Node integration: smoothly introduces accepted NodeProposals into the
live knowledge graph.

Three-phase integration lifecycle after ACCEPTED:
  1. Foreshadow   — narrative miners receive a "foreshadowing notice" so
                    they can begin referencing the incoming node obliquely
                    before it is fully traversable (bridge window opens)
  2. Edge ramp    — the new node's edges start at MIN_EDGE_WEIGHT and
                    linearly increase to 1.0 over EDGE_RAMP_BLOCKS
  3. Go-live      — once ramp completes the node is marked LIVE and
                    enters normal scoring / emission cycles
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import bittensor as bt

from config.subnet_config import SubnetConfig
from evolution.proposal import NodeProposal, ProposalStatus
from subnet.graph_store import GraphStore


# ---------------------------------------------------------------------------
# Integration state
# ---------------------------------------------------------------------------

@dataclass
class IntegrationState:
    proposal_id: str
    node_id: str
    adjacency: List[str]

    accepted_at_block: int
    foreshadow_block: int       # block at which foreshadowing notices go out
    bridge_open_block: int      # block at which node first appears in routing
    ramp_complete_block: int    # block at which edge weight reaches 1.0

    current_edge_weight: float = 0.0
    foreshadowed: bool = False
    bridge_open: bool = False
    live: bool = False

    created_at: float = field(default_factory=time.time)

    def edge_weight_at(self, current_block: int, min_weight: float = 0.05) -> float:
        """
        Linear ramp from min_weight at bridge_open_block to 1.0 at
        ramp_complete_block.
        """
        if current_block < self.bridge_open_block:
            return 0.0
        if current_block >= self.ramp_complete_block:
            return 1.0
        span = max(self.ramp_complete_block - self.bridge_open_block, 1)
        progress = (current_block - self.bridge_open_block) / span
        return min_weight + (1.0 - min_weight) * progress


# ---------------------------------------------------------------------------
# ForeshadowingNotice
# ---------------------------------------------------------------------------

@dataclass
class ForeshadowingNotice:
    """
    Sent to narrative miners so they can hint at the incoming node before
    it becomes traversable. The notice is injected into the persona system
    prompt via SubnetConfig.FORESHADOW_INJECTION_KEY.
    """
    node_id: str
    domain: str
    persona: str
    description: str
    goes_live_at_block: int
    issued_at: float = field(default_factory=time.time)

    def persona_hint(self) -> str:
        """Short hint string safe to inject into a narrative system prompt."""
        return (
            f"[UPCOMING: A new node '{self.node_id}' ({self.domain}) will soon "
            f"become traversable. You may allude to it obliquely when relevant.]"
        )


# ---------------------------------------------------------------------------
# IntegrationManager
# ---------------------------------------------------------------------------

class IntegrationManager:
    """
    Drives the integration of accepted proposals into the live graph.

    Called once per epoch by the validator. Performs:
      - Foreshadowing notice dispatch (epoch ≥ foreshadow_block)
      - Graph edge insertion at bridge-open (epoch ≥ bridge_open_block)
      - Edge weight ramp update each epoch
      - Go-live transition (epoch ≥ ramp_complete_block)
    """

    def __init__(
        self,
        graph_store: GraphStore,
        cfg: Optional[SubnetConfig] = None,
    ):
        self.graph_store = graph_store
        self.cfg = cfg or SubnetConfig()

        # proposal_id → IntegrationState
        self._states: Dict[str, IntegrationState] = {}
        # node_id → ForeshadowingNotice (for query by narrative miners)
        self._notices: Dict[str, ForeshadowingNotice] = {}

    # ── State construction ────────────────────────────────────────────

    def enqueue(self, proposal: NodeProposal, accepted_at_block: int) -> IntegrationState:
        """
        Create an IntegrationState for a newly accepted proposal and
        transition it to INTEGRATING.
        """
        cfg = self.cfg
        foreshadow_block  = accepted_at_block + cfg.FORESHADOW_OFFSET_BLOCKS
        bridge_open_block = accepted_at_block + cfg.BRIDGE_OPEN_OFFSET_BLOCKS
        ramp_complete_block = bridge_open_block + cfg.EDGE_RAMP_BLOCKS

        state = IntegrationState(
            proposal_id=proposal.proposal_id,
            node_id=proposal.node_id,
            adjacency=list(proposal.adjacency),
            accepted_at_block=accepted_at_block,
            foreshadow_block=foreshadow_block,
            bridge_open_block=bridge_open_block,
            ramp_complete_block=ramp_complete_block,
        )
        self._states[proposal.proposal_id] = state
        proposal.status = ProposalStatus.INTEGRATING
        proposal.integration_starts_at_block = accepted_at_block

        bt.logging.info(
            f"Integration enqueued: node={proposal.node_id} "
            f"foreshadow@{foreshadow_block} "
            f"bridge@{bridge_open_block} "
            f"live@{ramp_complete_block}"
        )
        return state

    # ── Foreshadowing ─────────────────────────────────────────────────

    def _issue_foreshadowing(self, state: IntegrationState, proposal: NodeProposal) -> None:
        notice = ForeshadowingNotice(
            node_id=proposal.node_id,
            domain=proposal.domain,
            persona=proposal.persona,
            description=proposal.description,
            goes_live_at_block=state.bridge_open_block,
        )
        self._notices[proposal.node_id] = notice
        state.foreshadowed = True

        bt.logging.info(
            f"Foreshadowing issued for node={proposal.node_id}: "
            f"\"{notice.persona_hint()}\""
        )

    def get_foreshadowing_notice(self, node_id: str) -> Optional[ForeshadowingNotice]:
        """Called by narrative miners when assembling prompts."""
        return self._notices.get(node_id)

    def active_notices(self) -> List[ForeshadowingNotice]:
        return list(self._notices.values())

    # ── Bridge / graph insertion ──────────────────────────────────────

    def _open_bridge(self, state: IntegrationState, proposal: NodeProposal) -> None:
        """
        Insert the node and its ramped edges into the live GraphStore.
        Edges start at MIN_EDGE_WEIGHT so they don't immediately dominate routing.
        """
        self.graph_store.add_node(
            node_id=proposal.node_id,
            domain=proposal.domain,
            persona=proposal.persona,
            uid=proposal.proposer_uid,
        )

        min_w = self.cfg.INTEGRATION_MIN_EDGE_WEIGHT
        for dst in state.adjacency:
            if self.graph_store.get_node(dst) is not None:
                self.graph_store.add_edge(proposal.node_id, dst, weight=min_w)
                bt.logging.debug(
                    f"Integration: edge {proposal.node_id} → {dst} opened at w={min_w}"
                )

        state.bridge_open = True
        state.current_edge_weight = min_w
        bt.logging.info(
            f"Bridge opened for node={proposal.node_id} "
            f"with {len(state.adjacency)} edges at w={min_w}"
        )

    # ── Edge ramp ─────────────────────────────────────────────────────

    def _ramp_edges(self, state: IntegrationState, current_block: int) -> None:
        """Update edge weights to their current ramp value."""
        new_weight = state.edge_weight_at(
            current_block,
            min_weight=self.cfg.INTEGRATION_MIN_EDGE_WEIGHT,
        )
        if abs(new_weight - state.current_edge_weight) < 1e-4:
            return

        delta = new_weight - state.current_edge_weight
        for dst in state.adjacency:
            self.graph_store.update_weight(state.node_id, dst, delta)

        state.current_edge_weight = new_weight
        bt.logging.debug(
            f"Edge ramp: node={state.node_id} weight={new_weight:.4f} "
            f"(block={current_block})"
        )

    # ── Go-live ───────────────────────────────────────────────────────

    def _go_live(self, state: IntegrationState, proposal: NodeProposal) -> None:
        # Final edge weight pass to ensure exactly 1.0
        for dst in state.adjacency:
            edge = self.graph_store.get_edge(state.node_id, dst)
            if edge:
                delta = 1.0 - edge.weight
                if abs(delta) > 1e-6:
                    self.graph_store.update_weight(state.node_id, dst, delta)

        state.live = True
        proposal.status = ProposalStatus.LIVE

        # Remove foreshadowing notice — node is now traversable
        self._notices.pop(state.node_id, None)

        bt.logging.success(
            f"Node LIVE: {state.node_id} | "
            f"edges={len(state.adjacency)} | "
            f"ramp_took={state.ramp_complete_block - state.bridge_open_block} blocks"
        )

    # ── Epoch driver ──────────────────────────────────────────────────

    def process_epoch(
        self,
        proposals_by_id: Dict[str, NodeProposal],
        current_block: int,
    ) -> List[IntegrationState]:
        """
        Drive all in-flight integrations forward by one epoch.
        Returns list of states that transitioned to LIVE this epoch.
        """
        went_live: List[IntegrationState] = []

        for pid, state in list(self._states.items()):
            if state.live:
                continue

            proposal = proposals_by_id.get(pid)
            if proposal is None:
                bt.logging.warning(f"IntegrationManager: no proposal found for {pid}")
                continue

            # Phase 1: foreshadow
            if not state.foreshadowed and current_block >= state.foreshadow_block:
                self._issue_foreshadowing(state, proposal)

            # Phase 2: open bridge
            if not state.bridge_open and current_block >= state.bridge_open_block:
                self._open_bridge(state, proposal)

            # Phase 3: ramp edges
            if state.bridge_open and not state.live:
                self._ramp_edges(state, current_block)

            # Phase 4: go-live
            if not state.live and current_block >= state.ramp_complete_block:
                self._go_live(state, proposal)
                went_live.append(state)

        return went_live

    def pending_states(self) -> List[IntegrationState]:
        return [s for s in self._states.values() if not s.live]

    def stats(self) -> Dict:
        return {
            "total": len(self._states),
            "pending": len(self.pending_states()),
            "live": sum(1 for s in self._states.values() if s.live),
            "active_notices": len(self._notices),
        }
