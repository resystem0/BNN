"""
subnet/protocol.py
Synapse dataclasses for the axon-graph subnet.
Defines the three core message types that flow between orchestrator,
validators, and miners: KnowledgeQuery, NarrativeHop, WeightCommit.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import bittensor as bt
from pydantic import Field, field_validator


# ---------------------------------------------------------------------------
# KnowledgeQuery
# ---------------------------------------------------------------------------

class KnowledgeQuery(bt.Synapse):
    """
    Sent by the orchestrator to a *domain miner* to retrieve relevant
    document chunks for a given concept node and query embedding.

    Request fields  (orchestrator → miner)
    ────────────────────────────────────────
    node_id         : canonical node identifier in the knowledge graph
    query_text      : raw natural-language query from the end user
    query_embedding : pre-computed sentence-transformer vector (list[float])
    top_k           : number of chunks to return (default 5)
    session_id      : opaque session handle for multi-hop correlation

    Response fields  (miner → orchestrator)
    ─────────────────────────────────────────
    chunks          : retrieved text chunks ordered by relevance
    chunk_ids       : stable content-addressed IDs (used for Merkle proof)
    scores          : cosine similarity scores parallel to chunks
    merkle_root     : root of the chunk Merkle tree for corpus challenge
    miner_hotkey    : hotkey of the responding miner (filled by miner)
    elapsed_ms      : server-side retrieval latency
    """

    # ── request ──────────────────────────────────────────────────────────
    node_id: str = Field(..., description="Knowledge graph node identifier")
    query_text: str = Field(..., description="Raw user query")
    query_embedding: List[float] = Field(
        default_factory=list,
        description="Pre-computed query embedding vector",
    )
    top_k: int = Field(default=5, ge=1, le=50)
    session_id: Optional[str] = Field(default=None)

    # ── response ─────────────────────────────────────────────────────────
    chunks: Optional[List[str]] = Field(default=None)
    chunk_ids: Optional[List[str]] = Field(default=None)
    scores: Optional[List[float]] = Field(default=None)
    merkle_root: Optional[str] = Field(default=None)
    miner_hotkey: Optional[str] = Field(default=None)
    elapsed_ms: Optional[float] = Field(default=None)

    @field_validator("top_k")
    @classmethod
    def _clamp_top_k(cls, v: int) -> int:
        return max(1, min(v, 50))

    def is_success(self) -> bool:
        return (
            self.chunks is not None
            and len(self.chunks) > 0
            and self.merkle_root is not None
        )


# ---------------------------------------------------------------------------
# NarrativeHop
# ---------------------------------------------------------------------------

class NarrativeHop(bt.Synapse):
    """
    Sent by the orchestrator to a *narrative miner* to generate one hop
    of the story that bridges two adjacent knowledge-graph nodes.

    Request fields  (orchestrator → miner)
    ────────────────────────────────────────
    session_id      : session this hop belongs to
    from_node_id    : source node in this hop
    to_node_id      : destination node in this hop
    path_so_far     : ordered list of node_ids traversed so far
    chunks          : document chunks retrieved from the domain miner
    prior_narrative : concatenated narrative text produced in earlier hops
    persona         : narrative persona / tone instruction
    max_tokens      : generation budget (default 512)

    Response fields  (miner → orchestrator)
    ─────────────────────────────────────────
    hop_text        : generated narrative paragraph(s) for this hop
    finish_reason   : "stop" | "length" | "safety"
    token_count     : actual tokens generated
    miner_hotkey    : hotkey of the responding miner
    elapsed_ms      : server-side generation latency
    """

    # ── request ──────────────────────────────────────────────────────────
    session_id: str = Field(..., description="Opaque session identifier")
    from_node_id: str = Field(..., description="Source graph node")
    to_node_id: str = Field(..., description="Destination graph node")
    path_so_far: List[str] = Field(default_factory=list)
    chunks: List[str] = Field(
        default_factory=list,
        description="Relevant document chunks for grounding",
    )
    prior_narrative: str = Field(
        default="",
        description="Accumulated story text from previous hops",
    )
    persona: str = Field(
        default="neutral",
        description="Narrative persona or tone instruction",
    )
    max_tokens: int = Field(default=512, ge=64, le=2048)

    # ── response ─────────────────────────────────────────────────────────
    hop_text: Optional[str] = Field(default=None)
    finish_reason: Optional[str] = Field(default=None)
    token_count: Optional[int] = Field(default=None)
    miner_hotkey: Optional[str] = Field(default=None)
    elapsed_ms: Optional[float] = Field(default=None)

    def is_success(self) -> bool:
        return (
            self.hop_text is not None
            and len(self.hop_text.strip()) > 0
            and self.finish_reason in ("stop", "length")
        )

    def hop_word_count(self) -> int:
        if not self.hop_text:
            return 0
        return len(self.hop_text.split())


# ---------------------------------------------------------------------------
# WeightCommit
# ---------------------------------------------------------------------------

class WeightCommit(bt.Synapse):
    """
    Internal synapse used by the validator to broadcast a weight-commit
    message to peer validators for Byzantine-fault-tolerant agreement
    before calling ``subtensor.set_weights``.

    This synapse is *not* sent to miners; it flows validator → validator.

    Request fields  (initiating validator → peer validator)
    ─────────────────────────────────────────────────────────
    epoch           : subnet epoch number this commit belongs to
    uids            : ordered list of miner UIDs being scored
    weights         : raw float scores parallel to uids (pre-normalised)
    score_breakdown : per-uid dict with sub-scores for audit trail
    commit_hash     : SHA-256(epoch || uids || weights) for integrity check
    validator_hotkey: hotkey of the initiating validator

    Response fields  (peer validator → initiating validator)
    ──────────────────────────────────────────────────────────
    ack             : True if peer accepts the commit as valid
    peer_hotkey     : hotkey of the responding peer
    peer_commit_hash: peer's own independent hash for cross-check
    disagreement_uids: UIDs where peer's scores differ significantly
    """

    # ── request ──────────────────────────────────────────────────────────
    epoch: int = Field(..., ge=0, description="Subnet epoch index")
    uids: List[int] = Field(..., description="Miner UIDs being scored")
    weights: List[float] = Field(..., description="Normalised weight per UID")
    score_breakdown: Dict[str, Any] = Field(
        default_factory=dict,
        description="Per-uid audit dict: {uid: {traversal, quality, topology}}",
    )
    commit_hash: str = Field(..., description="SHA-256 integrity hash")
    validator_hotkey: str = Field(..., description="Initiating validator hotkey")
    timestamp: float = Field(default_factory=time.time)

    # ── response ─────────────────────────────────────────────────────────
    ack: Optional[bool] = Field(default=None)
    peer_hotkey: Optional[str] = Field(default=None)
    peer_commit_hash: Optional[str] = Field(default=None)
    disagreement_uids: Optional[List[int]] = Field(default=None)

    @field_validator("weights")
    @classmethod
    def _weights_sum_to_one(cls, v: List[float]) -> List[float]:
        """Soft validation: warn if weights deviate significantly from 1.0."""
        if v:
            total = sum(v)
            if not (0.98 <= total <= 1.02):
                bt.logging.warning(
                    f"WeightCommit: weights sum to {total:.4f}, expected ~1.0"
                )
        return v

    def uid_weight_map(self) -> Dict[int, float]:
        return dict(zip(self.uids, self.weights))

    def is_acknowledged(self) -> bool:
        return self.ack is True and self.peer_hotkey is not None
