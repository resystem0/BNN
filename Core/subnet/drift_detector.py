"""
subnet/drift_detector.py
Semantic drift detection for domain miners.

A miner exhibits "semantic drift" when its corpus diverges from the
knowledge domain its node_id declares. This happens if a miner swaps
in off-domain documents (accidentally or to game retrieval scores).

Detection method:
  1. Maintain a rolling buffer of (query_embedding, chunk_embeddings)
     pairs observed during validator challenges.
  2. Each epoch, compute the mean cosine similarity between the query
     embeddings and the node's *expected domain centroid* (computed once
     from nodes.yaml domain tags and a reference corpus of seed sentences).
  3. If the similarity drops below DRIFT_THRESHOLD for DRIFT_WINDOW_EPOCHS
     consecutive epochs, the miner is flagged as drifted.
  4. Flag is cleared when similarity recovers above DRIFT_RECOVERY_THRESHOLD.

Gate criterion (Phase 3):
  Validator must flag drift > 0.28 cosine drop within 2 epochs of corpus swap.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple

import bittensor as bt
import numpy as np

from config.subnet_config import SubnetConfig


# ---------------------------------------------------------------------------
# Domain centroid registry
# ---------------------------------------------------------------------------

# Seed sentences used to build expected domain centroids.
# Each list represents the semantic "centre" of a domain.
# In production these are embedded once at startup via the Embedder.
DOMAIN_SEED_SENTENCES: Dict[str, List[str]] = {
    "physics": [
        "quantum mechanics describes the behavior of particles at the atomic scale",
        "general relativity explains gravitation as spacetime curvature",
        "thermodynamics governs energy transfer and entropy in physical systems",
        "electromagnetism unifies electric and magnetic forces through Maxwell's equations",
        "particle physics studies the fundamental constituents of matter",
    ],
    "computer_science": [
        "algorithms and data structures are the foundation of efficient computation",
        "machine learning enables systems to learn from data without explicit programming",
        "cryptographic protocols secure communication over untrusted networks",
        "distributed systems coordinate computation across multiple machines",
        "quantum computing uses quantum mechanical phenomena to perform computation",
    ],
    "biology": [
        "DNA encodes the genetic instructions for development and reproduction",
        "evolution by natural selection shapes the diversity of life",
        "cellular metabolism converts nutrients into energy and biomolecules",
        "neuroscience studies the structure and function of the nervous system",
        "ecology examines interactions between organisms and their environment",
    ],
    "astronomy": [
        "cosmology studies the origin and evolution of the universe",
        "stellar astrophysics describes the life cycle of stars",
        "dark matter and dark energy constitute most of the universe's content",
        "exoplanet detection reveals planetary systems beyond our solar system",
        "gravitational waves carry information about extreme cosmic events",
    ],
    "chemistry": [
        "chemical bonding determines the structure and properties of molecules",
        "reaction kinetics describes the rates and mechanisms of chemical reactions",
        "thermochemistry relates heat flow to chemical transformations",
        "organic chemistry studies carbon-based compounds and their reactions",
        "catalysis accelerates chemical reactions without being consumed",
    ],
    "mathematics": [
        "probability theory provides a framework for reasoning under uncertainty",
        "linear algebra describes vector spaces and linear transformations",
        "game theory models strategic interactions between rational agents",
        "information theory quantifies the transmission of data",
        "statistics enables inference about populations from sample data",
    ],
    "philosophy": [
        "epistemology examines the nature and limits of human knowledge",
        "philosophy of mind addresses consciousness and mental representation",
        "ethics reasons about moral values duties and the good life",
        "metaphysics investigates the fundamental nature of reality and existence",
        "logic provides formal rules for valid inference and argumentation",
    ],
}


def compute_domain_centroid(
    domain: str,
    embedder,
) -> Optional[np.ndarray]:
    """
    Embed the seed sentences for a domain and return their mean as the centroid.
    Returns None if the domain has no seeds.
    """
    seeds = DOMAIN_SEED_SENTENCES.get(domain)
    if not seeds:
        bt.logging.warning(f"DriftDetector: no seed sentences for domain={domain!r}")
        return None
    embeddings = embedder.embed(seeds)
    arr = np.array(embeddings, dtype=np.float32)
    centroid = arr.mean(axis=0)
    norm = np.linalg.norm(centroid)
    return centroid / norm if norm > 0 else centroid


# ---------------------------------------------------------------------------
# Per-epoch drift observation
# ---------------------------------------------------------------------------

@dataclass
class DriftObservation:
    uid: int
    epoch: int
    node_id: str
    domain: str
    mean_cosine_to_centroid: float      # how aligned chunks are with domain centroid
    query_chunk_cosine: float           # retrieval quality (existing signal)
    drifted: bool = False
    timestamp: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# DriftWindow
# ---------------------------------------------------------------------------

class DriftWindow:
    """Rolling buffer of DriftObservations for a single uid."""

    def __init__(self, uid: int, node_id: str, domain: str, window: int = 10):
        self.uid = uid
        self.node_id = node_id
        self.domain = domain
        self._obs: Deque[DriftObservation] = deque(maxlen=window)

    def push(self, obs: DriftObservation) -> None:
        self._obs.append(obs)

    def __len__(self) -> int:
        return len(self._obs)

    def recent_cosines(self) -> List[float]:
        return [o.mean_cosine_to_centroid for o in self._obs]

    def mean_cosine(self) -> float:
        vals = self.recent_cosines()
        return float(np.mean(vals)) if vals else 1.0

    def consecutive_below(self, threshold: float) -> int:
        count = 0
        for obs in reversed(self._obs):
            if obs.mean_cosine_to_centroid < threshold:
                count += 1
            else:
                break
        return count

    def drop_from_baseline(self, baseline: float) -> float:
        """How far mean cosine has fallen from a known-good baseline."""
        return max(0.0, baseline - self.mean_cosine())


# ---------------------------------------------------------------------------
# DriftDetector
# ---------------------------------------------------------------------------

class DriftDetector:
    """
    Tracks semantic drift for all registered domain miners.

    Used by the validator epoch loop:

        detector = DriftDetector(embedder, cfg)
        detector.register_node("quantum_mechanics", "physics")

        # After each challenge response:
        obs = detector.observe(
            uid=3,
            epoch=42,
            node_id="quantum_mechanics",
            chunk_embeddings=resp.chunk_embeddings,
            query_embedding=query_emb,
        )

        # Each epoch:
        flagged = detector.evaluate_epoch(epoch=42)
        for uid, obs in flagged:
            bt.logging.warning(f"Drift detected: uid={uid}")
    """

    def __init__(self, embedder, cfg: Optional[SubnetConfig] = None):
        self.embedder = embedder
        self.cfg = cfg or SubnetConfig()

        # node_id → domain centroid vector
        self._centroids: Dict[str, np.ndarray] = {}
        # node_id → known-good baseline cosine (first 3 epochs average)
        self._baselines: Dict[str, float] = {}
        # uid → DriftWindow
        self._windows: Dict[int, DriftWindow] = {}
        # uid → currently flagged
        self._flagged: Dict[int, bool] = {}

    # ── Setup ─────────────────────────────────────────────────────────

    def register_node(self, node_id: str, domain: str) -> None:
        """Pre-compute and cache the domain centroid for a node."""
        if node_id in self._centroids:
            return
        centroid = compute_domain_centroid(domain, self.embedder)
        if centroid is not None:
            self._centroids[node_id] = centroid
            bt.logging.debug(
                f"DriftDetector: centroid registered for node={node_id} domain={domain}"
            )

    def register_uid(self, uid: int, node_id: str, domain: str) -> None:
        if uid not in self._windows:
            self._windows[uid] = DriftWindow(
                uid=uid,
                node_id=node_id,
                domain=domain,
                window=self.cfg.DRIFT_WINDOW_EPOCHS,
            )
        self.register_node(node_id, domain)

    # ── Observation ───────────────────────────────────────────────────

    def _cosine_to_centroid(
        self,
        chunk_embeddings: List[List[float]],
        centroid: np.ndarray,
    ) -> float:
        """Mean cosine similarity of chunk embeddings to domain centroid."""
        if not chunk_embeddings:
            return 0.0
        arr = np.array(chunk_embeddings, dtype=np.float32)
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        normed = arr / norms
        sims = normed @ centroid
        return float(sims.mean())

    def _query_chunk_cosine(
        self,
        query_embedding: List[float],
        chunk_embeddings: List[List[float]],
    ) -> float:
        if not chunk_embeddings or not query_embedding:
            return 0.0
        q = np.array(query_embedding, dtype=np.float32)
        q_norm = np.linalg.norm(q)
        if q_norm == 0:
            return 0.0
        q = q / q_norm
        arr = np.array(chunk_embeddings, dtype=np.float32)
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        normed = arr / norms
        return float((normed @ q).mean())

    def observe(
        self,
        uid: int,
        epoch: int,
        node_id: str,
        domain: str,
        chunk_embeddings: List[List[float]],
        query_embedding: List[float],
    ) -> DriftObservation:
        """
        Record one challenge observation for a uid.
        Call this after every KnowledgeQuery challenge response.
        """
        self.register_uid(uid, node_id, domain)

        centroid = self._centroids.get(node_id)
        if centroid is not None:
            cosine_to_centroid = self._cosine_to_centroid(chunk_embeddings, centroid)
        else:
            cosine_to_centroid = 1.0   # unknown domain — don't penalise

        qc_cosine = self._query_chunk_cosine(query_embedding, chunk_embeddings)

        obs = DriftObservation(
            uid=uid,
            epoch=epoch,
            node_id=node_id,
            domain=domain,
            mean_cosine_to_centroid=cosine_to_centroid,
            query_chunk_cosine=qc_cosine,
        )
        self._windows[uid].push(obs)

        # Update baseline from first DRIFT_BASELINE_EPOCHS observations
        window = self._windows[uid]
        if node_id not in self._baselines and len(window) >= self.cfg.DRIFT_BASELINE_EPOCHS:
            self._baselines[node_id] = window.mean_cosine()
            bt.logging.debug(
                f"DriftDetector: baseline set for node={node_id} "
                f"cosine={self._baselines[node_id]:.4f}"
            )

        return obs

    # ── Epoch evaluation ──────────────────────────────────────────────

    def evaluate_epoch(
        self, epoch: int
    ) -> List[Tuple[int, DriftObservation]]:
        """
        Evaluate all uid windows for drift. Returns list of (uid, latest_obs)
        for miners newly flagged this epoch.

        A miner is flagged when EITHER:
          (a) consecutive_below(DRIFT_THRESHOLD) >= DRIFT_CONSECUTIVE_EPOCHS
          (b) drop_from_baseline > DRIFT_DROP_THRESHOLD (hard drop check)
        """
        cfg = self.cfg
        newly_flagged: List[Tuple[int, DriftObservation]] = []

        for uid, window in self._windows.items():
            if not window._obs:
                continue

            latest = window._obs[-1]
            consecutive = window.consecutive_below(cfg.DRIFT_THRESHOLD)
            baseline = self._baselines.get(window.node_id, 1.0)
            drop = window.drop_from_baseline(baseline)

            is_drifted = (
                consecutive >= cfg.DRIFT_CONSECUTIVE_EPOCHS
                or drop > cfg.DRIFT_DROP_THRESHOLD
            )

            was_flagged = self._flagged.get(uid, False)

            if is_drifted and not was_flagged:
                self._flagged[uid] = True
                latest.drifted = True
                newly_flagged.append((uid, latest))
                bt.logging.warning(
                    f"DriftDetector: DRIFT FLAGGED uid={uid} "
                    f"node={window.node_id} domain={window.domain} "
                    f"epoch={epoch} consecutive={consecutive} "
                    f"drop={drop:.4f} cosine={window.mean_cosine():.4f}"
                )

            elif not is_drifted and was_flagged:
                # Recovery
                self._flagged[uid] = False
                bt.logging.info(
                    f"DriftDetector: drift CLEARED uid={uid} "
                    f"node={window.node_id} cosine={window.mean_cosine():.4f}"
                )

        return newly_flagged

    # ── Accessors ─────────────────────────────────────────────────────

    def is_flagged(self, uid: int) -> bool:
        return self._flagged.get(uid, False)

    def flagged_uids(self) -> List[int]:
        return [uid for uid, f in self._flagged.items() if f]

    def cosine_score(self, uid: int) -> Optional[float]:
        window = self._windows.get(uid)
        return window.mean_cosine() if window else None

    def stats(self) -> Dict:
        return {
            "tracked_uids": len(self._windows),
            "flagged_uids": len(self.flagged_uids()),
            "baselines_set": len(self._baselines),
            "centroids_loaded": len(self._centroids),
        }
