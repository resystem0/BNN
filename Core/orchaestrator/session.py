"""
orchestrator/session.py
OrchestratorSession — manages the full lifecycle of one user traversal session.

For each session the orchestrator:
  1. Resolves an entry node from the user query (via Router)
  2. Fetches grounding chunks from the domain miner at that node (KnowledgeQuery)
  3. Generates the opening narrative hop (NarrativeHop)
  4. On each subsequent hop: repeats steps 2–3 for the new node
  5. Tracks path state, accumulated narrative, and safety ticks
"""

from __future__ import annotations

import enum
import time
import uuid
from typing import Any, Dict, List, Optional

import bittensor as bt

from config.subnet_config import SubnetConfig
from orchestrator.embedder import Embedder
from orchestrator.router import Router
from orchestrator.safety_guard import PathSafetyGuard
from subnet.graph_store import GraphStore
from subnet.protocol import KnowledgeQuery, NarrativeHop


class SessionState(str, enum.Enum):
    CREATED = "created"
    ACTIVE = "active"
    TERMINAL = "terminal"
    ERROR = "error"


class OrchestratorSession:
    """
    Stateful session object.  One instance per active user traversal.

    All public async methods are safe to call from FastAPI route handlers.
    """

    def __init__(
        self,
        session_id: str,
        graph_store: GraphStore,
        embedder: Embedder,
        router: Router,
        safety_guard: PathSafetyGuard,
        wallet: bt.wallet,
        subtensor: bt.subtensor,
        metagraph: bt.metagraph,
        cfg: Optional[SubnetConfig] = None,
    ):
        self.session_id = session_id
        self.graph_store = graph_store
        self.embedder = embedder
        self.router = router
        self.safety_guard = safety_guard
        self.wallet = wallet
        self.subtensor = subtensor
        self.metagraph = metagraph
        self.cfg = cfg or SubnetConfig()

        self.dendrite = bt.dendrite(wallet=wallet)

        # Mutable session state
        self.state: SessionState = SessionState.CREATED
        self.path: List[str] = []
        self.narrative_so_far: str = ""
        self.persona: str = "neutral"
        self.max_hops: int = self.cfg.DEFAULT_MAX_HOPS
        self._hop_count: int = 0
        self._created_at: float = time.time()

    # ── convenience properties ───────────────────────────────────────

    @property
    def current_node_id(self) -> Optional[str]:
        return self.path[-1] if self.path else None

    @property
    def hop_count(self) -> int:
        return self._hop_count

    # ── internal helpers ─────────────────────────────────────────────

    def _uid_for_node(self, node_id: str) -> Optional[int]:
        """Find the registered miner UID for a given node_id."""
        node = self.graph_store.get_node(node_id)
        if node and node.uid is not None:
            return node.uid
        return None

    def _axon_for_uid(self, uid: int) -> Optional[bt.AxonInfo]:
        try:
            return self.metagraph.axons[uid]
        except (IndexError, AttributeError):
            return None

    async def _fetch_chunks(
        self, node_id: str, query_text: str, query_embedding: List[float]
    ) -> tuple[List[str], List[str], Optional[str]]:
        """
        Send KnowledgeQuery to the domain miner for node_id.
        Returns (chunks, chunk_ids, merkle_root).
        Falls back to empty lists on failure.
        """
        uid = self._uid_for_node(node_id)
        if uid is None:
            bt.logging.warning(f"[session={self.session_id}] no miner UID for node={node_id}")
            return [], [], None

        axon = self._axon_for_uid(uid)
        if axon is None:
            return [], [], None

        synapse = KnowledgeQuery(
            node_id=node_id,
            query_text=query_text,
            query_embedding=query_embedding,
            top_k=self.cfg.SESSION_RETRIEVAL_TOP_K,
            session_id=self.session_id,
        )

        try:
            responses = await self.dendrite(
                axons=[axon],
                synapse=synapse,
                timeout=self.cfg.QUERY_TIMEOUT,
                deserialize=False,
            )
            resp: KnowledgeQuery = responses[0]
        except Exception as exc:
            bt.logging.error(
                f"[session={self.session_id}] KnowledgeQuery failed for node={node_id}: {exc}"
            )
            return [], [], None

        if not resp.is_success():
            return [], [], None

        # Log traversal to graph store
        if self.current_node_id and self.current_node_id != node_id:
            self.graph_store.record_traversal(self.current_node_id, node_id)

        return resp.chunks or [], resp.chunk_ids or [], resp.merkle_root

    async def _generate_hop(
        self,
        from_node_id: str,
        to_node_id: str,
        chunks: List[str],
    ) -> tuple[str, str]:
        """
        Send NarrativeHop to a narrative miner.
        Returns (hop_text, finish_reason).
        Falls back to a placeholder string on failure.
        """
        # Narrative miners are selected by the router; use the to_node's narrative miner
        narrative_uid = self.router.resolve_narrative_miner(to_node_id)
        if narrative_uid is None:
            # Fallback: use from_node miner if it has narrative capability
            narrative_uid = self._uid_for_node(from_node_id)

        axon = self._axon_for_uid(narrative_uid) if narrative_uid is not None else None

        synapse = NarrativeHop(
            session_id=self.session_id,
            from_node_id=from_node_id,
            to_node_id=to_node_id,
            path_so_far=list(self.path),
            chunks=chunks,
            prior_narrative=self.narrative_so_far,
            persona=self.persona,
            max_tokens=self.cfg.SESSION_MAX_TOKENS,
        )

        if axon is None:
            bt.logging.warning(
                f"[session={self.session_id}] no narrative axon for {from_node_id}→{to_node_id}"
            )
            fallback = (
                f"Continuing from {from_node_id}, we arrive at {to_node_id}, "
                "where new perspectives await."
            )
            return fallback, "stop"

        try:
            responses = await self.dendrite(
                axons=[axon],
                synapse=synapse,
                timeout=self.cfg.NARRATIVE_TIMEOUT,
                deserialize=False,
            )
            resp: NarrativeHop = responses[0]
        except Exception as exc:
            bt.logging.error(
                f"[session={self.session_id}] NarrativeHop failed: {exc}"
            )
            return f"[error generating hop {from_node_id}→{to_node_id}]", "safety"

        if not resp.is_success():
            return f"[hop generation incomplete for {from_node_id}→{to_node_id}]", "safety"

        return resp.hop_text or "", resp.finish_reason or "stop"

    def _available_next(self, node_id: str) -> List[str]:
        """Return node_ids reachable from node_id, respecting safety guard."""
        nbrs = self.graph_store.neighbours(node_id, top_k=self.cfg.MAX_NEXT_NODES)
        candidates = [n for n, _ in nbrs]
        safe = self.safety_guard.filter_candidates(self.path, candidates)
        return safe

    # ── public API ───────────────────────────────────────────────────

    async def enter(
        self,
        query: str,
        persona: str = "neutral",
        max_hops: int = 5,
        entry_node_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Initialise the session and generate the entry narrative.
        Returns a dict consumed by the gateway's EnterResponse.
        """
        self.persona = persona
        self.max_hops = max_hops

        # Embed query
        query_embedding = self.embedder.embed([query])[0]

        # Resolve entry node
        if entry_node_id:
            resolved = entry_node_id
        else:
            resolved = self.router.rank_entry_nodes(query_embedding, top_k=1)[0]

        self.path = [resolved]
        self.state = SessionState.ACTIVE

        # Fetch grounding chunks at the entry node
        chunks, _, _ = await self._fetch_chunks(resolved, query, query_embedding)

        # Generate the opening narrative hop (self-loop: from=to=entry)
        hop_text, _ = await self._generate_hop(
            from_node_id=resolved,
            to_node_id=resolved,
            chunks=chunks,
        )
        self.narrative_so_far = hop_text

        # Safety guard tick
        self.safety_guard.tick(self.path, hop_text)

        bt.logging.info(
            f"[session={self.session_id}] entered at node={resolved} | "
            f"persona={persona} | max_hops={max_hops}"
        )

        return {
            "entry_node_id": resolved,
            "entry_narrative": hop_text,
            "available_next_nodes": self._available_next(resolved),
        }

    async def hop(self, to_node_id: str) -> Dict[str, Any]:
        """
        Advance the session by one hop to to_node_id.
        Raises ValueError if to_node_id is not a valid next node.
        Returns a dict consumed by the gateway's HopResponse.
        """
        if self.state != SessionState.ACTIVE:
            raise ValueError(f"Session is not active (state={self.state})")

        from_node_id = self.current_node_id
        available = self._available_next(from_node_id)
        if to_node_id not in available:
            raise ValueError(
                f"'{to_node_id}' is not reachable from '{from_node_id}'. "
                f"Available: {available}"
            )

        # Embed the accumulated narrative as the "query" for chunk retrieval
        query_embedding = self.embedder.embed([self.narrative_so_far[-512:]])[0]
        chunks, _, _ = await self._fetch_chunks(to_node_id, self.narrative_so_far[-512:], query_embedding)

        hop_text, finish_reason = await self._generate_hop(
            from_node_id=from_node_id,
            to_node_id=to_node_id,
            chunks=chunks,
        )

        self.path.append(to_node_id)
        self.narrative_so_far = (self.narrative_so_far + "\n\n" + hop_text).strip()
        self._hop_count += 1

        # Safety guard tick — may reroute or bridge on safety concern
        safe_hop = self.safety_guard.tick(self.path, hop_text)
        if safe_hop and safe_hop != hop_text:
            hop_text = safe_hop

        # Terminal check
        next_nodes = self._available_next(to_node_id)
        if self._hop_count >= self.max_hops or not next_nodes:
            self.state = SessionState.TERMINAL
            bt.logging.info(
                f"[session={self.session_id}] reached terminal at node={to_node_id} "
                f"after {self._hop_count} hops"
            )

        # Log quality to graph store
        word_count = len(hop_text.split())
        quality = min(1.0, word_count / max(self.cfg.MAX_HOP_WORDS, 1))
        self.graph_store.log_traversal(self.session_id, self.path, quality)

        return {
            "from_node_id": from_node_id,
            "to_node_id": to_node_id,
            "hop_text": hop_text,
            "available_next_nodes": next_nodes,
        }
