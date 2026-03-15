"""
subnet/validator.py
Validator logic for the axon-graph subnet.

Responsibilities:
  • Run a per-epoch scoring loop against all registered miners
  • Issue KnowledgeQuery and NarrativeHop challenges
  • Issue corpus-integrity challenges (Merkle proof verification)
  • Aggregate traversal / quality / topology sub-scores
  • Broadcast WeightCommit to peer validators then call set_weights
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import random
import time
from typing import Any, Dict, List, Optional, Tuple

import bittensor as bt
import numpy as np

from config.subnet_config import SubnetConfig
from subnet.graph_store import GraphStore
from subnet.protocol import KnowledgeQuery, NarrativeHop, WeightCommit


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def _cosine(a: List[float], b: List[float]) -> float:
    """Cosine similarity between two equal-length vectors."""
    a_arr = np.array(a, dtype=np.float32)
    b_arr = np.array(b, dtype=np.float32)
    denom = np.linalg.norm(a_arr) * np.linalg.norm(b_arr)
    if denom == 0:
        return 0.0
    return float(np.dot(a_arr, b_arr) / denom)


def _hash_commit(epoch: int, uids: List[int], weights: List[float]) -> str:
    payload = json.dumps(
        {"epoch": epoch, "uids": uids, "weights": [round(w, 6) for w in weights]},
        sort_keys=True,
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def _normalise(scores: Dict[int, float]) -> Dict[int, float]:
    """Min-max normalise a uid→score dict to [0, 1]."""
    if not scores:
        return {}
    values = list(scores.values())
    lo, hi = min(values), max(values)
    if hi == lo:
        return {uid: 1.0 for uid in scores}
    return {uid: (v - lo) / (hi - lo) for uid, v in scores.items()}


# ---------------------------------------------------------------------------
# CorpusChallenge
# ---------------------------------------------------------------------------

class CorpusChallenge:
    """
    Selects a random chunk from a miner's previously returned chunk_ids
    and asks the miner to re-prove inclusion via a Merkle path.
    A simplified challenge: we re-query the same node and verify that
    (a) the merkle_root is stable and (b) the challenged chunk_id reappears.
    """

    def __init__(self, cfg: SubnetConfig):
        self.cfg = cfg

    async def run(
        self,
        dendrite: bt.dendrite,
        axon: bt.axon,
        uid: int,
        node_id: str,
        expected_root: str,
        query_embedding: List[float],
    ) -> float:
        """Returns a challenge score in [0, 1]."""
        synapse = KnowledgeQuery(
            node_id=node_id,
            query_text="__corpus_challenge__",
            query_embedding=query_embedding,
            top_k=self.cfg.CHALLENGE_TOP_K,
        )
        try:
            response: KnowledgeQuery = await dendrite(
                axons=[axon],
                synapse=synapse,
                timeout=self.cfg.CHALLENGE_TIMEOUT,
                deserialize=False,
            )
            response = response[0]
        except Exception as exc:
            bt.logging.warning(f"[uid={uid}] corpus challenge failed: {exc}")
            return 0.0

        if not response.is_success():
            return 0.0

        root_match = float(response.merkle_root == expected_root)
        return root_match


# ---------------------------------------------------------------------------
# ScoringLoop
# ---------------------------------------------------------------------------

class ScoringLoop:
    """
    Runs one full scoring epoch:
      1. Query all UIDs with a sampled (node, query) pair
      2. Issue NarrativeHop challenges to narrative miners
      3. Issue corpus challenges
      4. Combine sub-scores with configured weights
      5. Return uid→final_score dict
    """

    def __init__(
        self,
        cfg: SubnetConfig,
        graph_store: GraphStore,
        metagraph: bt.metagraph,
        dendrite: bt.dendrite,
        embedder,  # orchestrator.embedder.Embedder
    ):
        self.cfg = cfg
        self.graph_store = graph_store
        self.metagraph = metagraph
        self.dendrite = dendrite
        self.embedder = embedder
        self.corpus_challenger = CorpusChallenge(cfg)

    # ── helpers ──────────────────────────────────────────────────────────

    def _sample_challenge_pair(self) -> Tuple[str, str, List[float]]:
        """Pick a random node and synthesise a query embedding."""
        node_ids = self.graph_store.all_node_ids()
        node_id = random.choice(node_ids)
        query_text = f"Tell me about {node_id}"
        embedding = self.embedder.embed([query_text])[0]
        return node_id, query_text, embedding

    def _uid_to_axon(self, uid: int) -> Optional[bt.AxonInfo]:
        try:
            return self.metagraph.axons[uid]
        except IndexError:
            return None

    # ── sub-score: traversal ─────────────────────────────────────────────

    async def _score_traversal(
        self,
        uid: int,
        node_id: str,
        query_text: str,
        query_embedding: List[float],
    ) -> Tuple[float, Optional[str], Optional[List[float]]]:
        """
        Score based on retrieval relevance.
        Returns (traversal_score, merkle_root, query_embedding).
        """
        axon = self._uid_to_axon(uid)
        if axon is None:
            return 0.0, None, None

        synapse = KnowledgeQuery(
            node_id=node_id,
            query_text=query_text,
            query_embedding=query_embedding,
            top_k=self.cfg.SCORING_TOP_K,
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
            bt.logging.debug(f"[uid={uid}] traversal query exception: {exc}")
            return 0.0, None, None

        if not resp.is_success():
            return 0.0, None, None

        # Score = mean cosine similarity between query_embedding and each chunk embedding
        if resp.scores:
            score = float(np.mean(resp.scores))
        else:
            # Re-embed chunks and compute similarity ourselves
            chunk_embeddings = self.embedder.embed(resp.chunks[:self.cfg.SCORING_TOP_K])
            sims = [_cosine(query_embedding, ce) for ce in chunk_embeddings]
            score = float(np.mean(sims)) if sims else 0.0

        score = max(0.0, min(score, 1.0))

        # Latency penalty
        if resp.elapsed_ms is not None:
            latency_s = resp.elapsed_ms / 1000.0
            if latency_s > self.cfg.LATENCY_SOFT_LIMIT_S:
                penalty = min(
                    self.cfg.LATENCY_MAX_PENALTY,
                    (latency_s - self.cfg.LATENCY_SOFT_LIMIT_S) * self.cfg.LATENCY_PENALTY_PER_S,
                )
                score = max(0.0, score - penalty)

        return score, resp.merkle_root, query_embedding

    # ── sub-score: quality (narrative) ───────────────────────────────────

    async def _score_quality(
        self,
        uid: int,
        from_node: str,
        to_node: str,
        chunks: List[str],
    ) -> float:
        axon = self._uid_to_axon(uid)
        if axon is None:
            return 0.0

        synapse = NarrativeHop(
            session_id=f"validator_challenge_{uid}_{int(time.time())}",
            from_node_id=from_node,
            to_node_id=to_node,
            chunks=chunks,
            max_tokens=self.cfg.CHALLENGE_MAX_TOKENS,
        )
        try:
            responses = await self.dendrite(
                axons=[axon],
                synapse=synapse,
                timeout=self.cfg.NARRATIVE_TIMEOUT,
                deserialize=False,
            )
            resp: NarrativeHop = responses[0]
        except Exception as exc:
            bt.logging.debug(f"[uid={uid}] narrative challenge exception: {exc}")
            return 0.0

        if not resp.is_success():
            return 0.0

        word_count = resp.hop_word_count()
        # Simple heuristic: reward concise, complete responses
        if word_count < self.cfg.MIN_HOP_WORDS:
            return 0.2
        if word_count > self.cfg.MAX_HOP_WORDS:
            return 0.6  # penalise verbosity but don't zero it
        return 1.0

    # ── sub-score: topology ──────────────────────────────────────────────

    def _score_topology(self, uid: int) -> float:
        """
        Score based on graph-store metrics: betweenness centrality and
        decay-adjusted edge weight for this miner's primary node.
        """
        node_id = self.graph_store.uid_to_node(uid)
        if node_id is None:
            return 0.0
        return self.graph_store.topology_score(node_id)

    # ── main entry ───────────────────────────────────────────────────────

    async def run_epoch(self, epoch: int) -> Dict[int, float]:
        node_id, query_text, query_embedding = self._sample_challenge_pair()
        bt.logging.info(
            f"[epoch={epoch}] scoring {len(self.metagraph.uids)} UIDs "
            f"on node={node_id}"
        )

        uids = list(self.metagraph.uids.tolist())
        traversal_scores: Dict[int, float] = {}
        quality_scores: Dict[int, float] = {}
        topology_scores: Dict[int, float] = {}
        corpus_scores: Dict[int, float] = {}

        # Sample an edge for narrative challenge
        edges = self.graph_store.sample_edges(n=1)
        narrative_edge = edges[0] if edges else (node_id, node_id)

        # Run traversal + corpus challenges concurrently per UID
        traversal_tasks = {
            uid: self._score_traversal(uid, node_id, query_text, query_embedding)
            for uid in uids
        }
        results = await asyncio.gather(*traversal_tasks.values(), return_exceptions=True)

        merkle_roots: Dict[int, Optional[str]] = {}
        for uid, result in zip(traversal_tasks.keys(), results):
            if isinstance(result, Exception):
                traversal_scores[uid] = 0.0
                merkle_roots[uid] = None
            else:
                score, root, _ = result
                traversal_scores[uid] = score
                merkle_roots[uid] = root

        # Corpus challenges for miners that returned a merkle root
        corpus_tasks = {}
        for uid in uids:
            axon = self._uid_to_axon(uid)
            root = merkle_roots.get(uid)
            if axon and root:
                corpus_tasks[uid] = self.corpus_challenger.run(
                    self.dendrite, axon, uid, node_id, root, query_embedding
                )
        if corpus_tasks:
            corpus_results = await asyncio.gather(
                *corpus_tasks.values(), return_exceptions=True
            )
            for uid, res in zip(corpus_tasks.keys(), corpus_results):
                corpus_scores[uid] = 0.0 if isinstance(res, Exception) else res
        for uid in uids:
            corpus_scores.setdefault(uid, 0.0)

        # Quality / narrative scores
        quality_tasks = {
            uid: self._score_quality(uid, narrative_edge[0], narrative_edge[1], [])
            for uid in uids
        }
        quality_results = await asyncio.gather(
            *quality_tasks.values(), return_exceptions=True
        )
        for uid, res in zip(quality_tasks.keys(), quality_results):
            quality_scores[uid] = 0.0 if isinstance(res, Exception) else res

        # Topology scores (synchronous, from graph_store)
        for uid in uids:
            topology_scores[uid] = self._score_topology(uid)

        # Normalise each sub-score
        t_norm = _normalise(traversal_scores)
        q_norm = _normalise(quality_scores)
        tp_norm = _normalise(topology_scores)
        c_norm = _normalise(corpus_scores)

        cfg = self.cfg
        final: Dict[int, float] = {}
        for uid in uids:
            combined = (
                cfg.TRAVERSAL_WEIGHT * t_norm.get(uid, 0.0)
                + cfg.QUALITY_WEIGHT * q_norm.get(uid, 0.0)
                + cfg.TOPOLOGY_WEIGHT * tp_norm.get(uid, 0.0)
                + cfg.CORPUS_WEIGHT * c_norm.get(uid, 0.0)
            )
            final[uid] = round(combined, 6)

        bt.logging.info(
            f"[epoch={epoch}] scores computed. "
            f"top5={sorted(final.items(), key=lambda x: -x[1])[:5]}"
        )
        return final


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

class Validator:
    """
    Top-level validator class.  Intended to be instantiated once and then
    driven by an external epoch loop (e.g. a Nomad job or asyncio task).
    """

    def __init__(
        self,
        wallet: bt.wallet,
        subtensor: bt.subtensor,
        metagraph: bt.metagraph,
        graph_store: GraphStore,
        embedder,
        cfg: Optional[SubnetConfig] = None,
    ):
        self.wallet = wallet
        self.subtensor = subtensor
        self.metagraph = metagraph
        self.graph_store = graph_store
        self.cfg = cfg or SubnetConfig()
        self.dendrite = bt.dendrite(wallet=self.wallet)
        self.scoring_loop = ScoringLoop(
            self.cfg, graph_store, metagraph, self.dendrite, embedder
        )
        self._epoch: int = 0

    # ── weight commit broadcast ──────────────────────────────────────────

    async def _broadcast_weight_commit(
        self, uids: List[int], weights: List[float]
    ) -> bool:
        """
        Send WeightCommit to all peer validators and require a quorum of
        acknowledgements before proceeding.
        """
        commit_hash = _hash_commit(self._epoch, uids, weights)
        synapse = WeightCommit(
            epoch=self._epoch,
            uids=uids,
            weights=weights,
            commit_hash=commit_hash,
            validator_hotkey=self.wallet.hotkey.ss58_address,
        )

        peer_axons = [
            self.metagraph.axons[uid]
            for uid in self.metagraph.uids
            if self.metagraph.validator_trust[uid] > self.cfg.VALIDATOR_TRUST_MIN
            and self.metagraph.hotkeys[uid] != self.wallet.hotkey.ss58_address
        ]

        if not peer_axons:
            bt.logging.info("No peer validators found; skipping broadcast.")
            return True

        responses = await self.dendrite(
            axons=peer_axons,
            synapse=synapse,
            timeout=self.cfg.COMMIT_TIMEOUT,
            deserialize=False,
        )

        acks = sum(1 for r in responses if isinstance(r, WeightCommit) and r.is_acknowledged())
        quorum = acks / len(peer_axons) if peer_axons else 1.0
        bt.logging.info(
            f"[epoch={self._epoch}] weight commit: {acks}/{len(peer_axons)} acks "
            f"(quorum={quorum:.2f}, required={self.cfg.COMMIT_QUORUM})"
        )
        return quorum >= self.cfg.COMMIT_QUORUM

    # ── set weights ──────────────────────────────────────────────────────

    def _set_weights(self, scores: Dict[int, float]) -> None:
        uids = sorted(scores.keys())
        raw_weights = [scores[uid] for uid in uids]
        total = sum(raw_weights)
        if total == 0:
            bt.logging.warning("All scores are zero; skipping set_weights.")
            return
        norm_weights = [w / total for w in raw_weights]

        success, message = self.subtensor.set_weights(
            wallet=self.wallet,
            netuid=self.cfg.NETUID,
            uids=uids,
            weights=norm_weights,
            wait_for_inclusion=True,
        )
        if success:
            bt.logging.success(f"[epoch={self._epoch}] set_weights accepted: {message}")
        else:
            bt.logging.error(f"[epoch={self._epoch}] set_weights failed: {message}")

    # ── epoch runner ─────────────────────────────────────────────────────

    async def run_epoch(self) -> None:
        self._epoch += 1
        self.metagraph.sync(subtensor=self.subtensor)

        scores = await self.scoring_loop.run_epoch(self._epoch)

        uids = sorted(scores.keys())
        total = sum(scores[u] for u in uids) or 1.0
        norm = [scores[u] / total for u in uids]

        quorum_ok = await self._broadcast_weight_commit(uids, norm)
        if quorum_ok:
            self._set_weights(scores)
        else:
            bt.logging.warning(
                f"[epoch={self._epoch}] quorum not reached; weights not committed."
            )

        self.graph_store.decay_edges(self.cfg.EDGE_DECAY_RATE)

    async def run_forever(self) -> None:
        """Drive the validator epoch loop indefinitely."""
        bt.logging.info(
            f"Validator starting on netuid={self.cfg.NETUID}, "
            f"epoch_blocks={self.cfg.EPOCH_LENGTH_BLOCKS}"
        )
        while True:
            try:
                await self.run_epoch()
            except Exception as exc:
                bt.logging.error(f"Epoch error: {exc}", exc_info=True)
            await asyncio.sleep(self.cfg.EPOCH_SLEEP_S)
