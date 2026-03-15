"""
subnet/graph_store.py
Persistent knowledge-graph store backed by KùzuDB.

Responsibilities:
  • Maintain directed, weighted edges between concept nodes
  • Log traversal events and update edge weights
  • Apply exponential decay to edge weights each epoch
  • Compute betweenness centrality and topology scores
  • Provide neighbour / path queries used by the orchestrator router
"""

from __future__ import annotations

import math
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Set, Tuple

import bittensor as bt

try:
    import kuzu
    _KUZU_AVAILABLE = True
except ImportError:
    _KUZU_AVAILABLE = False
    bt.logging.warning("kuzu not installed; GraphStore will run in-memory only.")


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Node:
    node_id: str
    domain: str
    persona: str = "neutral"
    uid: Optional[int] = None          # registered miner UID, if any
    created_at: float = field(default_factory=time.time)


@dataclass
class Edge:
    src: str
    dst: str
    weight: float = 1.0
    traversal_count: int = 0
    last_traversed: float = field(default_factory=time.time)
    created_at: float = field(default_factory=time.time)


@dataclass
class TraversalLog:
    session_id: str
    path: List[str]
    quality_score: float
    timestamp: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# In-memory graph (used standalone or as write-through cache over KùzuDB)
# ---------------------------------------------------------------------------

class _MemoryGraph:
    """
    Pure in-memory graph with adjacency lists.
    Thread-safe via a single RWLock pattern (threading.Lock for writes,
    unlocked reads with copy-on-read for critical sections).
    """

    def __init__(self):
        self._nodes: Dict[str, Node] = {}
        self._edges: Dict[Tuple[str, str], Edge] = {}
        self._adj: Dict[str, Set[str]] = defaultdict(set)   # src → {dst}
        self._rev: Dict[str, Set[str]] = defaultdict(set)   # dst → {src}
        self._uid_map: Dict[int, str] = {}                  # uid → node_id
        self._lock = threading.Lock()

    # ── nodes ─────────────────────────────────────────────────────────

    def add_node(self, node: Node) -> None:
        with self._lock:
            self._nodes[node.node_id] = node
            if node.uid is not None:
                self._uid_map[node.uid] = node.node_id

    def get_node(self, node_id: str) -> Optional[Node]:
        return self._nodes.get(node_id)

    def all_node_ids(self) -> List[str]:
        return list(self._nodes.keys())

    def uid_to_node(self, uid: int) -> Optional[str]:
        return self._uid_map.get(uid)

    # ── edges ─────────────────────────────────────────────────────────

    def add_edge(self, src: str, dst: str, weight: float = 1.0) -> None:
        with self._lock:
            key = (src, dst)
            if key in self._edges:
                self._edges[key].weight = max(self._edges[key].weight, weight)
            else:
                self._edges[key] = Edge(src=src, dst=dst, weight=weight)
            self._adj[src].add(dst)
            self._rev[dst].add(src)

    def get_edge(self, src: str, dst: str) -> Optional[Edge]:
        return self._edges.get((src, dst))

    def update_weight(self, src: str, dst: str, delta: float) -> None:
        with self._lock:
            key = (src, dst)
            if key in self._edges:
                self._edges[key].weight = max(0.0, self._edges[key].weight + delta)

    def record_traversal(self, src: str, dst: str) -> None:
        with self._lock:
            key = (src, dst)
            if key in self._edges:
                e = self._edges[key]
                e.traversal_count += 1
                e.last_traversed = time.time()
                e.weight = min(e.weight * 1.05, 10.0)  # slight boost per traversal

    def decay_all(self, rate: float) -> None:
        """Multiply all edge weights by (1 - rate). Remove edges that fall below threshold."""
        PRUNE_THRESHOLD = 0.01
        with self._lock:
            to_remove = []
            for key, edge in self._edges.items():
                edge.weight *= (1.0 - rate)
                if edge.weight < PRUNE_THRESHOLD:
                    to_remove.append(key)
            for key in to_remove:
                src, dst = key
                self._edges.pop(key)
                self._adj[src].discard(dst)
                self._rev[dst].discard(src)

    def neighbours(self, node_id: str) -> List[Tuple[str, float]]:
        """Return [(dst, weight), ...] sorted by descending weight."""
        nbrs = []
        for dst in self._adj.get(node_id, []):
            edge = self._edges.get((node_id, dst))
            if edge:
                nbrs.append((dst, edge.weight))
        return sorted(nbrs, key=lambda x: -x[1])

    def sample_edges(self, n: int = 1) -> List[Tuple[str, str]]:
        import random
        keys = list(self._edges.keys())
        if not keys:
            return []
        return random.sample(keys, min(n, len(keys)))

    def all_edges(self) -> Iterator[Edge]:
        return iter(self._edges.values())

    # ── BFS shortest path ─────────────────────────────────────────────

    def bfs_path(self, start: str, end: str) -> Optional[List[str]]:
        if start not in self._nodes or end not in self._nodes:
            return None
        visited: Set[str] = {start}
        queue: deque[List[str]] = deque([[start]])
        while queue:
            path = queue.popleft()
            node = path[-1]
            if node == end:
                return path
            for nbr, _ in self.neighbours(node):
                if nbr not in visited:
                    visited.add(nbr)
                    queue.append(path + [nbr])
        return None

    # ── Betweenness centrality (approximate, Brandes) ─────────────────

    def betweenness(self) -> Dict[str, float]:
        """
        Approximate betweenness centrality via Brandes' algorithm.
        Runs in O(VE) which is acceptable for graphs up to ~500 nodes.
        """
        nodes = list(self._nodes.keys())
        cb: Dict[str, float] = {n: 0.0 for n in nodes}

        for s in nodes:
            stack: List[str] = []
            pred: Dict[str, List[str]] = {n: [] for n in nodes}
            sigma: Dict[str, float] = {n: 0.0 for n in nodes}
            dist: Dict[str, int] = {n: -1 for n in nodes}
            sigma[s] = 1.0
            dist[s] = 0
            q: deque[str] = deque([s])
            while q:
                v = q.popleft()
                stack.append(v)
                for w, _ in self.neighbours(v):
                    if dist[w] < 0:
                        q.append(w)
                        dist[w] = dist[v] + 1
                    if dist[w] == dist[v] + 1:
                        sigma[w] += sigma[v]
                        pred[w].append(v)
            delta: Dict[str, float] = {n: 0.0 for n in nodes}
            while stack:
                w = stack.pop()
                for v in pred[w]:
                    if sigma[w] != 0:
                        delta[v] += (sigma[v] / sigma[w]) * (1.0 + delta[w])
                if w != s:
                    cb[w] += delta[w]

        # Normalise
        n = len(nodes)
        norm = (n - 1) * (n - 2) if n > 2 else 1.0
        return {node: val / norm for node, val in cb.items()}


# ---------------------------------------------------------------------------
# GraphStore (public API)
# ---------------------------------------------------------------------------

class GraphStore:
    """
    Public interface for the axon-graph knowledge graph.
    Wraps _MemoryGraph and (optionally) persists to KùzuDB.
    """

    def __init__(self, db_path: Optional[str] = None):
        self._mem = _MemoryGraph()
        self._db = None
        self._betweenness_cache: Dict[str, float] = {}
        self._betweenness_stale: bool = True
        self._lock = threading.Lock()

        if db_path and _KUZU_AVAILABLE:
            try:
                self._db = kuzu.Database(db_path)
                self._conn = kuzu.Connection(self._db)
                self._init_schema()
                bt.logging.info(f"GraphStore: KùzuDB opened at {db_path}")
            except Exception as exc:
                bt.logging.warning(f"GraphStore: KùzuDB init failed ({exc}); using memory only.")
                self._db = None

    # ── schema ────────────────────────────────────────────────────────

    def _init_schema(self) -> None:
        if self._conn is None:
            return
        self._conn.execute(
            "CREATE NODE TABLE IF NOT EXISTS Node(id STRING, domain STRING, "
            "persona STRING, uid INT64, created_at DOUBLE, PRIMARY KEY (id))"
        )
        self._conn.execute(
            "CREATE REL TABLE IF NOT EXISTS Edge(FROM Node TO Node, "
            "weight DOUBLE, traversal_count INT64, last_traversed DOUBLE)"
        )

    # ── node operations ──────────────────────────────────────────────

    def add_node(self, node_id: str, domain: str, persona: str = "neutral", uid: Optional[int] = None) -> None:
        node = Node(node_id=node_id, domain=domain, persona=persona, uid=uid)
        self._mem.add_node(node)
        self._betweenness_stale = True

        if self._db:
            try:
                self._conn.execute(
                    "MERGE (n:Node {id: $id}) SET n.domain = $domain, "
                    "n.persona = $persona, n.uid = $uid, n.created_at = $ts",
                    {"id": node_id, "domain": domain, "persona": persona,
                     "uid": uid if uid is not None else -1, "ts": time.time()},
                )
            except Exception as exc:
                bt.logging.debug(f"GraphStore.add_node DB error: {exc}")

    def get_node(self, node_id: str) -> Optional[Node]:
        return self._mem.get_node(node_id)

    def all_node_ids(self) -> List[str]:
        return self._mem.all_node_ids()

    def uid_to_node(self, uid: int) -> Optional[str]:
        return self._mem.uid_to_node(uid)

    # ── edge operations ──────────────────────────────────────────────

    def get_edge(self, src: str, dst: str) -> Optional[Edge]:
        return self._mem.get_edge(src, dst)

    def update_weight(self, src: str, dst: str, delta: float) -> None:
        self._mem.update_weight(src, dst, delta)
        self._betweenness_stale = True

    def add_edge(self, src: str, dst: str, weight: float = 1.0) -> None:
        self._mem.add_edge(src, dst, weight)
        self._betweenness_stale = True

        if self._db:
            try:
                self._conn.execute(
                    "MATCH (s:Node {id: $src}), (d:Node {id: $dst}) "
                    "MERGE (s)-[e:Edge]->(d) SET e.weight = $w, "
                    "e.traversal_count = 0, e.last_traversed = $ts",
                    {"src": src, "dst": dst, "w": weight, "ts": time.time()},
                )
            except Exception as exc:
                bt.logging.debug(f"GraphStore.add_edge DB error: {exc}")

    def record_traversal(self, src: str, dst: str) -> None:
        self._mem.record_traversal(src, dst)
        self._betweenness_stale = True

    def decay_edges(self, rate: float) -> None:
        """Apply exponential decay. Called by the validator after each epoch."""
        self._mem.decay_all(rate)
        self._betweenness_stale = True
        bt.logging.debug(f"GraphStore: edge decay applied (rate={rate})")

    def sample_edges(self, n: int = 1) -> List[Tuple[str, str]]:
        return self._mem.sample_edges(n)

    # ── traversal log ─────────────────────────────────────────────────

    def log_traversal(self, session_id: str, path: List[str], quality: float) -> None:
        for i in range(len(path) - 1):
            self.record_traversal(path[i], path[i + 1])

    # ── queries ──────────────────────────────────────────────────────

    def neighbours(self, node_id: str, top_k: int = 10) -> List[Tuple[str, float]]:
        return self._mem.neighbours(node_id)[:top_k]

    def bfs_path(self, start: str, end: str) -> Optional[List[str]]:
        return self._mem.bfs_path(start, end)

    # ── betweenness & topology score ─────────────────────────────────

    def _refresh_betweenness(self) -> None:
        with self._lock:
            if self._betweenness_stale:
                self._betweenness_cache = self._mem.betweenness()
                self._betweenness_stale = False

    def betweenness(self, node_id: str) -> float:
        self._refresh_betweenness()
        return self._betweenness_cache.get(node_id, 0.0)

    def topology_score(self, node_id: str) -> float:
        """
        Combine betweenness centrality and the sum of outgoing edge weights
        into a single topology score in [0, 1].
        """
        bc = self.betweenness(node_id)

        nbrs = self._mem.neighbours(node_id)
        edge_weight_sum = sum(w for _, w in nbrs)
        # Soft-cap edge weight contribution via log
        ew_score = math.log1p(edge_weight_sum) / math.log1p(50.0)  # normalise to ~[0,1]

        # Blend 60% betweenness + 40% edge weight
        score = 0.6 * min(bc, 1.0) + 0.4 * min(ew_score, 1.0)
        return round(score, 6)

    # ── bulk load ────────────────────────────────────────────────────

    def load_from_dict(self, data: Dict) -> None:
        """
        Bootstrap from a dict like:
          {"nodes": [{"id": ..., "domain": ..., "persona": ..., "uid": ...}],
           "edges": [{"src": ..., "dst": ..., "weight": ...}]}
        """
        for n in data.get("nodes", []):
            self.add_node(n["id"], n.get("domain", ""), n.get("persona", "neutral"), n.get("uid"))
        for e in data.get("edges", []):
            self.add_edge(e["src"], e["dst"], e.get("weight", 1.0))
        bt.logging.info(
            f"GraphStore loaded {len(data.get('nodes', []))} nodes, "
            f"{len(data.get('edges', []))} edges."
        )

    # ── debug helpers ─────────────────────────────────────────────────

    def stats(self) -> Dict:
        nodes = self._mem.all_node_ids()
        edges = list(self._mem.all_edges())
        weights = [e.weight for e in edges]
        return {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "avg_edge_weight": round(sum(weights) / max(len(weights), 1), 4),
            "max_edge_weight": round(max(weights, default=0.0), 4),
        }
