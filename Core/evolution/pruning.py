"""
evolution/pruning.py
Score-window evaluation, decay scheduling, and node collapse (pruning).

A node is pruned when its miner consistently underperforms across a
rolling window of epochs. Pruning is a three-phase process:

  1. Warning      — node is flagged; narrative miners receive a "collapse
                    passage" instruction so the story can gracefully
                    transition away from the node
  2. Edge decay   — outgoing edges are decayed aggressively each epoch,
                    reducing the node's influence on routing
  3. Collapse     — once the decay window expires the node is removed from
                    the graph and the miner's UID slot is freed for
                    re-registration by a better miner

Pruning is guarded by a PRUNE_QUORUM: a supermajority of validators must
agree the node is underperforming before the collapse is committed.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Deque, Dict, List, Optional

import bittensor as bt

from config.subnet_config import SubnetConfig
from subnet.graph_store import GraphStore


# ---------------------------------------------------------------------------
# Score window
# ---------------------------------------------------------------------------

@dataclass
class EpochScore:
    epoch: int
    uid: int
    node_id: str
    final_weight: float
    traversal_pool: float
    quality_pool: float
    topology_pool: float
    timestamp: float = field(default_factory=time.time)


class ScoreWindow:
    """
    Rolling window of per-epoch scores for a single miner (uid).
    Computes statistics over the window for prune-eligibility checks.
    """

    def __init__(self, uid: int, node_id: str, window_size: int = 20):
        self.uid = uid
        self.node_id = node_id
        self.window_size = window_size
        self._scores: Deque[EpochScore] = deque(maxlen=window_size)

    def push(self, score: EpochScore) -> None:
        self._scores.append(score)

    def __len__(self) -> int:
        return len(self._scores)

    @property
    def is_full(self) -> bool:
        return len(self._scores) == self.window_size

    def mean_weight(self) -> float:
        if not self._scores:
            return 0.0
        return sum(s.final_weight for s in self._scores) / len(self._scores)

    def min_weight(self) -> float:
        if not self._scores:
            return 0.0
        return min(s.final_weight for s in self._scores)

    def consecutive_below(self, threshold: float) -> int:
        """Count consecutive recent epochs where final_weight < threshold."""
        count = 0
        for score in reversed(self._scores):
            if score.final_weight < threshold:
                count += 1
            else:
                break
        return count

    def trend(self) -> float:
        """
        Linear trend of final_weight over the window.
        Negative = declining, positive = improving.
        """
        scores = list(self._scores)
        if len(scores) < 2:
            return 0.0
        n = len(scores)
        xs = list(range(n))
        ys = [s.final_weight for s in scores]
        x_mean = sum(xs) / n
        y_mean = sum(ys) / n
        num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
        den = sum((x - x_mean) ** 2 for x in xs)
        return num / den if den != 0 else 0.0


# ---------------------------------------------------------------------------
# Prune state machine
# ---------------------------------------------------------------------------

class PrunePhase(str, Enum):
    HEALTHY   = "healthy"
    WARNING   = "warning"
    DECAYING  = "decaying"
    COLLAPSED = "collapsed"


@dataclass
class PruneState:
    uid: int
    node_id: str
    phase: PrunePhase = PrunePhase.HEALTHY

    warned_at_epoch: Optional[int]   = None
    decay_started_at_epoch: Optional[int] = None
    collapsed_at_epoch: Optional[int] = None

    # Accumulated quorum votes for collapse
    collapse_votes: int  = 0
    collapse_quorum: int = 0

    collapse_passage_issued: bool = False
    created_at: float = field(default_factory=time.time)

    @property
    def is_terminal(self) -> bool:
        return self.phase == PrunePhase.COLLAPSED


# ---------------------------------------------------------------------------
# CollapsePassage
# ---------------------------------------------------------------------------

@dataclass
class CollapsePassage:
    """
    Instruction injected into narrative miner prompts to gracefully
    write the pruned node out of the story.
    """
    node_id: str
    final_epoch: int
    issued_at: float = field(default_factory=time.time)

    def persona_instruction(self) -> str:
        return (
            f"[NARRATIVE CLOSURE: The node '{self.node_id}' is being retired. "
            f"In your next hop departing from or referencing '{self.node_id}', "
            f"write a natural conclusion that allows the story to move on without "
            f"revisiting this node. Keep the closure brief and organic.]"
        )


# ---------------------------------------------------------------------------
# PruningEngine
# ---------------------------------------------------------------------------

class PruningEngine:
    """
    Evaluates miner score windows each epoch, advances prune states,
    applies aggressive edge decay to warned/decaying nodes, and
    executes graph collapse when quorum is reached.
    """

    def __init__(
        self,
        graph_store: GraphStore,
        cfg: Optional[SubnetConfig] = None,
    ):
        self.graph_store = graph_store
        self.cfg = cfg or SubnetConfig()

        self._windows: Dict[int, ScoreWindow]       = {}   # uid → ScoreWindow
        self._prune_states: Dict[int, PruneState]   = {}   # uid → PruneState
        self._passages: Dict[str, CollapsePassage]  = {}   # node_id → passage

    # ── Score ingestion ───────────────────────────────────────────────

    def push_scores(self, scores: List[EpochScore]) -> None:
        """Push a batch of epoch scores into per-uid windows."""
        for score in scores:
            uid = score.uid
            if uid not in self._windows:
                self._windows[uid] = ScoreWindow(
                    uid=uid,
                    node_id=score.node_id,
                    window_size=self.cfg.PRUNE_SCORE_WINDOW,
                )
            self._windows[uid].push(score)

    # ── Eligibility check ─────────────────────────────────────────────

    def _is_prune_eligible(self, window: ScoreWindow) -> bool:
        """
        Returns True if the miner should enter the WARNING phase.

        Conditions (all must hold):
          - Window is full (enough history to make a decision)
          - Mean weight is below PRUNE_MEAN_THRESHOLD
          - Consecutive below-threshold epochs ≥ PRUNE_CONSECUTIVE_EPOCHS
          - Declining trend (trend < 0)
        """
        if not window.is_full:
            return False
        cfg = self.cfg
        return (
            window.mean_weight() < cfg.PRUNE_MEAN_THRESHOLD
            and window.consecutive_below(cfg.PRUNE_CONSECUTIVE_THRESHOLD)
               >= cfg.PRUNE_CONSECUTIVE_EPOCHS
            and window.trend() < 0
        )

    def _is_recovered(self, window: ScoreWindow) -> bool:
        """Returns True if a warned node has recovered sufficiently."""
        return (
            window.mean_weight() >= self.cfg.PRUNE_RECOVERY_THRESHOLD
            and window.trend() >= 0
        )

    # ── Phase transitions ─────────────────────────────────────────────

    def _warn(self, uid: int, node_id: str, epoch: int) -> PruneState:
        state = self._prune_states.get(uid)
        if state is None:
            state = PruneState(uid=uid, node_id=node_id)
            self._prune_states[uid] = state
        state.phase = PrunePhase.WARNING
        state.warned_at_epoch = epoch
        bt.logging.warning(
            f"PruningEngine: uid={uid} node={node_id} → WARNING at epoch={epoch}"
        )
        return state

    def _begin_decay(self, state: PruneState, epoch: int) -> None:
        state.phase = PrunePhase.DECAYING
        state.decay_started_at_epoch = epoch

        # Issue collapse passage to narrative miners
        passage = CollapsePassage(node_id=state.node_id, final_epoch=epoch + self.cfg.PRUNE_DECAY_EPOCHS)
        self._passages[state.node_id] = passage
        state.collapse_passage_issued = True

        bt.logging.warning(
            f"PruningEngine: uid={state.uid} node={state.node_id} "
            f"→ DECAYING at epoch={epoch}. Collapse passage issued."
        )

    def _apply_decay(self, state: PruneState) -> None:
        """Apply aggressive edge decay to a decaying node."""
        node = self.graph_store.get_node(state.node_id)
        if node is None:
            return
        nbrs = self.graph_store.neighbours(state.node_id)
        for dst, _ in nbrs:
            self.graph_store.update_weight(
                state.node_id, dst,
                delta=-self.cfg.PRUNE_AGGRESSIVE_DECAY_RATE,
            )

    def _collapse(self, state: PruneState, epoch: int) -> None:
        """
        Remove the node's edges from the graph.
        The node record itself is kept for audit trail; its edges go to zero
        so it disappears from routing naturally.
        """
        node = self.graph_store.get_node(state.node_id)
        if node:
            nbrs = self.graph_store.neighbours(state.node_id)
            for dst, w in nbrs:
                self.graph_store.update_weight(state.node_id, dst, delta=-w)

        state.phase = PrunePhase.COLLAPSED
        state.collapsed_at_epoch = epoch
        self._passages.pop(state.node_id, None)

        bt.logging.warning(
            f"PruningEngine: uid={state.uid} node={state.node_id} "
            f"COLLAPSED at epoch={epoch}"
        )

    def _recover(self, state: PruneState) -> None:
        state.phase = PrunePhase.HEALTHY
        state.warned_at_epoch = None
        state.decay_started_at_epoch = None
        self._passages.pop(state.node_id, None)
        bt.logging.info(
            f"PruningEngine: uid={state.uid} node={state.node_id} → RECOVERED"
        )

    # ── Epoch driver ──────────────────────────────────────────────────

    def process_epoch(self, epoch: int) -> List[PruneState]:
        """
        Advance all prune states by one epoch.
        Returns list of states that transitioned to COLLAPSED this epoch.
        """
        collapsed: List[PruneState] = []

        for uid, window in self._windows.items():
            state = self._prune_states.get(uid)

            # ── HEALTHY ──────────────────────────────────────────────
            if state is None or state.phase == PrunePhase.HEALTHY:
                if self._is_prune_eligible(window):
                    state = self._warn(uid, window.node_id, epoch)

            # ── WARNING ──────────────────────────────────────────────
            elif state.phase == PrunePhase.WARNING:
                if self._is_recovered(window):
                    self._recover(state)
                elif (
                    state.warned_at_epoch is not None
                    and epoch - state.warned_at_epoch >= self.cfg.PRUNE_WARNING_EPOCHS
                ):
                    self._begin_decay(state, epoch)

            # ── DECAYING ─────────────────────────────────────────────
            elif state.phase == PrunePhase.DECAYING:
                if self._is_recovered(window):
                    self._recover(state)
                    continue

                self._apply_decay(state)

                if (
                    state.decay_started_at_epoch is not None
                    and epoch - state.decay_started_at_epoch >= self.cfg.PRUNE_DECAY_EPOCHS
                ):
                    self._collapse(state, epoch)
                    collapsed.append(state)

        return collapsed

    # ── Quorum vote for collapse ──────────────────────────────────────

    def vote_collapse(self, uid: int, quorum_required: int) -> bool:
        """
        Cast a validator vote for collapsing uid.
        Returns True when quorum is reached.
        """
        state = self._prune_states.get(uid)
        if state is None or state.phase != PrunePhase.DECAYING:
            return False
        state.collapse_votes += 1
        state.collapse_quorum = quorum_required
        return state.collapse_votes >= quorum_required

    # ── Accessors ─────────────────────────────────────────────────────

    def get_passage(self, node_id: str) -> Optional[CollapsePassage]:
        """Called by narrative miners when assembling prompts."""
        return self._passages.get(node_id)

    def active_passages(self) -> List[CollapsePassage]:
        return list(self._passages.values())

    def prune_state(self, uid: int) -> Optional[PruneState]:
        return self._prune_states.get(uid)

    def warned_uids(self) -> List[int]:
        return [
            uid for uid, s in self._prune_states.items()
            if s.phase in (PrunePhase.WARNING, PrunePhase.DECAYING)
        ]

    def stats(self) -> Dict:
        phases: Dict[str, int] = {}
        for s in self._prune_states.values():
            phases[s.phase.value] = phases.get(s.phase.value, 0) + 1
        return {
            "tracked_uids": len(self._windows),
            "prune_states": phases,
            "active_passages": len(self._passages),
        }
