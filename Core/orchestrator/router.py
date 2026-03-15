"""
orchestrator/router.py
Entry-node ranking and narrative-miner resolution for the orchestrator.

The Router answers two questions:
  1. Given a query embedding, which graph node is the best entry point?
  2. Given a destination node_id, which miner UID should generate the narrative?

It relies on the GraphStore for graph topology and the live metagraph for
miner registration status.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import bittensor as bt

from config.subnet_config import ENTRY_COSINE_FLOOR, SubnetConfig
from subnet.graph_store import GraphStore


def _cosine(a: List[float], b: List[float]) -> float:
    """Cosine similarity between two equal-length vectors."""
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class Router:
    """
    Resolves entry nodes and narrative miners.

    Domain-miner domain centroids are fetched from their registered manifests
    (cached in the graph store) and compared against the query embedding to
    find the best-matching entry node.
    """

    def __init__(
        self,
        graph_store: GraphStore,
        metagraph: bt.metagraph,
        cfg: Optional[SubnetConfig] = None,
    ):
        self.graph_store = graph_store
        self.metagraph = metagraph
        self.cfg = cfg or SubnetConfig()

    def rank_entry_nodes(
        self,
        query_embedding: List[float],
        top_k: int = 3,
    ) -> List[str]:
        """
        Return up to top_k node_ids ranked by domain similarity to the query.

        Only nodes with a registered miner UID and a similarity score above
        ENTRY_COSINE_FLOOR are considered.  Falls back to all live nodes if
        none pass the floor.
        """
        node_ids = self.graph_store.all_node_ids()
        if not node_ids:
            raise RuntimeError("GraphStore has no nodes; cannot route entry.")

        scored: List[Tuple[float, str]] = []
        for node_id in node_ids:
            node = self.graph_store.get_node(node_id)
            if node is None or node.uid is None:
                continue
            # Use domain centroid stored on the node (populated at startup)
            centroid = getattr(node, "centroid", None)
            if centroid:
                sim = _cosine(query_embedding, centroid)
            else:
                sim = 0.0
            if sim >= ENTRY_COSINE_FLOOR:
                scored.append((sim, node_id))

        if not scored:
            # Fallback: return nodes with registered UIDs, unsorted
            scored = [(0.0, n) for n in node_ids
                      if self.graph_store.get_node(n) and
                      self.graph_store.get_node(n).uid is not None]

        if not scored:
            # Last resort: return first available node
            return [node_ids[0]]

        scored.sort(key=lambda x: -x[0])
        return [node_id for _, node_id in scored[:top_k]]

    def resolve_narrative_miner(self, node_id: str) -> Optional[int]:
        """
        Return the Bittensor UID of the narrative miner registered to node_id,
        or None if no miner is registered.
        """
        node = self.graph_store.get_node(node_id)
        if node is None:
            return None
        return node.uid
