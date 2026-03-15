"""
subnet/emissions.py
Emission pool math for the axon-graph subnet.

Bittensor distributes a fixed TAO emission per block across all miners
weighted by the scores set via set_weights. This module computes the
*per-epoch allocation* each miner receives from three named pools:

  Traversal pool  — rewards miners whose chunks were actually retrieved
                    during live user sessions (proven usage signal)
  Quality pool    — rewards narrative miners for coherent, well-sized hops
                    (validator-challenged quality signal)
  Topology pool   — rewards miners that occupy high-betweenness graph
                    positions, incentivising a well-connected graph

The three pool scores are combined into a single normalised weight vector
that is handed to the validator's set_weights call.

Pool split is controlled by SubnetConfig:
  TRAVERSAL_WEIGHT + QUALITY_WEIGHT + TOPOLOGY_WEIGHT == 1.0
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import bittensor as bt
import numpy as np

from config.subnet_config import SubnetConfig


# ---------------------------------------------------------------------------
# Per-miner score snapshot
# ---------------------------------------------------------------------------

@dataclass
class MinerScoreSnapshot:
    uid: int
    epoch: int

    # Raw sub-scores (before pool normalisation), each in [0, ∞)
    traversal_raw: float = 0.0      # weighted sum of retrieval cosine scores
    quality_raw: float = 0.0        # narrative quality heuristic
    topology_raw: float = 0.0       # betweenness + edge-weight blend
    corpus_raw: float = 0.0         # Merkle challenge pass rate

    # Normalised pool contributions (set by EmissionCalculator)
    traversal_pool: float = 0.0
    quality_pool: float = 0.0
    topology_pool: float = 0.0

    # Final combined weight (sum of pool contributions)
    final_weight: float = 0.0

    # Metadata
    node_id: Optional[str] = None
    hotkey: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict:
        return {
            "uid": self.uid,
            "epoch": self.epoch,
            "traversal_raw": round(self.traversal_raw, 6),
            "quality_raw": round(self.quality_raw, 6),
            "topology_raw": round(self.topology_raw, 6),
            "corpus_raw": round(self.corpus_raw, 6),
            "traversal_pool": round(self.traversal_pool, 6),
            "quality_pool": round(self.quality_pool, 6),
            "topology_pool": round(self.topology_pool, 6),
            "final_weight": round(self.final_weight, 6),
            "node_id": self.node_id,
            "hotkey": self.hotkey,
        }


# ---------------------------------------------------------------------------
# Pool normalisers
# ---------------------------------------------------------------------------

def _softmax(values: List[float], temperature: float = 1.0) -> List[float]:
    """Temperature-scaled softmax over a list of floats."""
    if not values:
        return []
    arr = np.array(values, dtype=np.float64) / max(temperature, 1e-8)
    arr -= arr.max()          # numerical stability
    exp = np.exp(arr)
    return (exp / exp.sum()).tolist()


def _linear_normalise(values: List[float]) -> List[float]:
    """Min-max normalise to [0, 1]."""
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi == lo:
        return [1.0] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


def _rank_normalise(values: List[float]) -> List[float]:
    """
    Convert raw scores to rank-based weights.
    Highest score gets weight N, lowest gets 1, then linearly normalise.
    Reduces the impact of outlier scores.
    """
    if not values:
        return []
    n = len(values)
    indexed = sorted(enumerate(values), key=lambda x: x[1])
    rank_weights = [0.0] * n
    for rank, (idx, _) in enumerate(indexed):
        rank_weights[idx] = float(rank + 1)
    total = sum(rank_weights)
    return [w / total for w in rank_weights]


# ---------------------------------------------------------------------------
# Traversal pool
# ---------------------------------------------------------------------------

class TraversalPool:
    """
    Allocates the traversal pool across miners.

    Score inputs:
      - retrieval_scores: per-uid cosine similarity averaged over challenges
      - session_hit_counts: how many live sessions actually queried each uid
        (populated from graph_store traversal log)

    Formula:
      traversal_score(uid) = retrieval_score(uid)
                           * log1p(session_hits(uid)) / log1p(max_hits)
                           * corpus_pass_rate(uid)

    This rewards miners that are both high-quality AND actually used.
    """

    def __init__(self, cfg: SubnetConfig):
        self.cfg = cfg

    def compute(
        self,
        uids: List[int],
        retrieval_scores: Dict[int, float],
        session_hits: Dict[int, int],
        corpus_scores: Dict[int, float],
    ) -> Dict[int, float]:
        if not uids:
            return {}

        max_hits = max(session_hits.values(), default=1)
        raw: Dict[int, float] = {}

        for uid in uids:
            ret   = retrieval_scores.get(uid, 0.0)
            hits  = session_hits.get(uid, 0)
            corpus = corpus_scores.get(uid, 0.0)

            # Usage-weighted retrieval quality
            usage_factor = math.log1p(hits) / math.log1p(max(max_hits, 1))
            score = ret * (
                self.cfg.TRAVERSAL_USAGE_WEIGHT * usage_factor
                + (1.0 - self.cfg.TRAVERSAL_USAGE_WEIGHT)
            ) * corpus
            raw[uid] = max(0.0, score)

        # Rank-normalise to reduce outlier dominance
        uid_list = list(raw.keys())
        normed = _rank_normalise([raw[u] for u in uid_list])
        return dict(zip(uid_list, normed))


# ---------------------------------------------------------------------------
# Quality pool
# ---------------------------------------------------------------------------

class QualityPool:
    """
    Allocates the quality pool across narrative miners.

    Score inputs:
      - coherence_scores: validator-issued narrative quality scores [0, 1]
      - word_count_scores: normalised hop word-count adherence [0, 1]
      - finish_reason_scores: 1.0 if "stop", 0.5 if "length", 0.0 if "safety"

    Formula:
      quality_score(uid) = 0.5 * coherence
                         + 0.3 * word_count_adherence
                         + 0.2 * finish_reason

    Domain miners that receive no narrative challenges get quality_score = 0
    (they earn only via traversal + topology pools).
    """

    def __init__(self, cfg: SubnetConfig):
        self.cfg = cfg

    def compute(
        self,
        uids: List[int],
        coherence_scores: Dict[int, float],
        word_count_scores: Dict[int, float],
        finish_reason_scores: Dict[int, float],
    ) -> Dict[int, float]:
        if not uids:
            return {}

        raw: Dict[int, float] = {}
        for uid in uids:
            coh   = coherence_scores.get(uid, 0.0)
            wc    = word_count_scores.get(uid, 0.0)
            fin   = finish_reason_scores.get(uid, 0.0)

            score = (
                self.cfg.QUALITY_COHERENCE_WEIGHT  * coh
                + self.cfg.QUALITY_WORDCOUNT_WEIGHT  * wc
                + self.cfg.QUALITY_FINISH_WEIGHT     * fin
            )
            raw[uid] = max(0.0, score)

        uid_list = list(raw.keys())
        normed = _linear_normalise([raw[u] for u in uid_list])
        return dict(zip(uid_list, normed))


# ---------------------------------------------------------------------------
# Topology pool
# ---------------------------------------------------------------------------

class TopologyPool:
    """
    Allocates the topology pool to incentivise a well-connected graph.

    Score inputs:
      - betweenness: normalised betweenness centrality per node [0, 1]
      - edge_weight_sums: sum of outgoing edge weights per node

    Formula:
      topology_score(uid) = α * betweenness(node)
                          + β * log1p(edge_weight_sum) / log1p(max_ew)

    where α = TOPOLOGY_BETWEENNESS_WEIGHT, β = 1 - α.

    Miners on isolated or weakly-connected nodes are incentivised to
    accept more edges (via evolution proposals).
    """

    def __init__(self, cfg: SubnetConfig):
        self.cfg = cfg

    def compute(
        self,
        uids: List[int],
        betweenness: Dict[int, float],
        edge_weight_sums: Dict[int, float],
    ) -> Dict[int, float]:
        if not uids:
            return {}

        max_ew = max(edge_weight_sums.values(), default=1.0)
        raw: Dict[int, float] = {}

        for uid in uids:
            bc = betweenness.get(uid, 0.0)
            ew = edge_weight_sums.get(uid, 0.0)
            ew_norm = math.log1p(ew) / math.log1p(max(max_ew, 1.0))

            score = (
                self.cfg.TOPOLOGY_BETWEENNESS_WEIGHT * bc
                + (1.0 - self.cfg.TOPOLOGY_BETWEENNESS_WEIGHT) * ew_norm
            )
            raw[uid] = max(0.0, score)

        uid_list = list(raw.keys())
        # Softmax for topology: we want a smooth distribution, not winner-take-all
        normed = _softmax(
            [raw[u] for u in uid_list],
            temperature=self.cfg.TOPOLOGY_SOFTMAX_TEMP,
        )
        return dict(zip(uid_list, normed))


# ---------------------------------------------------------------------------
# EmissionCalculator
# ---------------------------------------------------------------------------

class EmissionCalculator:
    """
    Combines the three pools into a final normalised weight vector.

    Usage (called by the validator once per epoch):

        calc = EmissionCalculator(cfg)
        snapshots = calc.compute(
            epoch=42,
            uids=[0, 1, 2, ...],
            retrieval_scores={...},
            session_hits={...},
            corpus_scores={...},
            coherence_scores={...},
            word_count_scores={...},
            finish_reason_scores={...},
            betweenness={...},
            edge_weight_sums={...},
            uid_to_node={...},
            uid_to_hotkey={...},
        )
        weights = {s.uid: s.final_weight for s in snapshots}
    """

    def __init__(self, cfg: Optional[SubnetConfig] = None):
        self.cfg = cfg or SubnetConfig()
        self.traversal_pool = TraversalPool(self.cfg)
        self.quality_pool   = QualityPool(self.cfg)
        self.topology_pool  = TopologyPool(self.cfg)

    def compute(
        self,
        epoch: int,
        uids: List[int],
        # Traversal pool inputs
        retrieval_scores: Dict[int, float],
        session_hits: Dict[int, int],
        corpus_scores: Dict[int, float],
        # Quality pool inputs
        coherence_scores: Dict[int, float],
        word_count_scores: Dict[int, float],
        finish_reason_scores: Dict[int, float],
        # Topology pool inputs
        betweenness: Dict[int, float],
        edge_weight_sums: Dict[int, float],
        # Metadata
        uid_to_node: Optional[Dict[int, str]] = None,
        uid_to_hotkey: Optional[Dict[int, str]] = None,
    ) -> List[MinerScoreSnapshot]:

        t_pool  = self.traversal_pool.compute(uids, retrieval_scores, session_hits, corpus_scores)
        q_pool  = self.quality_pool.compute(uids, coherence_scores, word_count_scores, finish_reason_scores)
        tp_pool = self.topology_pool.compute(uids, betweenness, edge_weight_sums)

        cfg = self.cfg
        snapshots: List[MinerScoreSnapshot] = []

        for uid in uids:
            t  = t_pool.get(uid, 0.0)
            q  = q_pool.get(uid, 0.0)
            tp = tp_pool.get(uid, 0.0)

            combined = (
                cfg.TRAVERSAL_WEIGHT * t
                + cfg.QUALITY_WEIGHT   * q
                + cfg.TOPOLOGY_WEIGHT  * tp
            )

            snap = MinerScoreSnapshot(
                uid=uid,
                epoch=epoch,
                traversal_raw=retrieval_scores.get(uid, 0.0),
                quality_raw=coherence_scores.get(uid, 0.0),
                topology_raw=betweenness.get(uid, 0.0),
                corpus_raw=corpus_scores.get(uid, 0.0),
                traversal_pool=t,
                quality_pool=q,
                topology_pool=tp,
                final_weight=combined,
                node_id=(uid_to_node or {}).get(uid),
                hotkey=(uid_to_hotkey or {}).get(uid),
            )
            snapshots.append(snap)

        # Re-normalise final weights to sum to 1.0
        total = sum(s.final_weight for s in snapshots) or 1.0
        for s in snapshots:
            s.final_weight = round(s.final_weight / total, 8)

        bt.logging.info(
            f"[epoch={epoch}] emission calc: "
            f"top5={sorted([(s.uid, s.final_weight) for s in snapshots], key=lambda x: -x[1])[:5]}"
        )
        return snapshots

    def weight_vector(
        self, snapshots: List[MinerScoreSnapshot]
    ) -> Tuple[List[int], List[float]]:
        """Return (uids, weights) lists ready for subtensor.set_weights."""
        uids    = [s.uid for s in snapshots]
        weights = [s.final_weight for s in snapshots]
        return uids, weights

    def audit_log(self, snapshots: List[MinerScoreSnapshot]) -> List[Dict]:
        return [s.to_dict() for s in snapshots]
