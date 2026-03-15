"""
miners/domain/corpus.py
Chunk ingestion pipeline, Merkle tree builder, and Merkle proof prover.

Flow:
  1. Raw documents are split into chunks and embedded
  2. Each chunk is content-addressed (SHA-256) to produce a chunk_id
  3. A binary Merkle tree is built over all chunk_ids
  4. The Merkle root is stored and returned with every KnowledgeQuery response
  5. On corpus challenge the prover re-derives the path for a queried chunk_id
"""

from __future__ import annotations

import hashlib
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import bittensor as bt

try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    _CHROMA_AVAILABLE = True
except ImportError:
    _CHROMA_AVAILABLE = False
    bt.logging.warning("chromadb not installed; CorpusStore will be in-memory only.")


# ---------------------------------------------------------------------------
# Merkle helpers
# ---------------------------------------------------------------------------

def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


def _merkle_parent(left: str, right: str) -> str:
    return _sha256(left + right)


def _build_merkle_tree(leaves: List[str]) -> List[List[str]]:
    """
    Build a bottom-up Merkle tree from a list of leaf hashes.
    Returns a list of levels: levels[0] = leaves, levels[-1] = [root].
    Odd nodes are duplicated to ensure a complete binary tree.
    """
    if not leaves:
        return [[_sha256("")]]
    levels: List[List[str]] = [list(leaves)]
    while len(levels[-1]) > 1:
        level = levels[-1]
        if len(level) % 2 == 1:
            level = level + [level[-1]]   # duplicate last node
        parent_level = [
            _merkle_parent(level[i], level[i + 1])
            for i in range(0, len(level), 2)
        ]
        levels.append(parent_level)
    return levels


def merkle_root(leaves: List[str]) -> str:
    tree = _build_merkle_tree(leaves)
    return tree[-1][0]


def merkle_proof(leaves: List[str], target_leaf: str) -> Optional[List[Tuple[str, str]]]:
    """
    Return the Merkle proof path for target_leaf as [(sibling_hash, "left"|"right"), ...].
    Returns None if the leaf is not found.
    """
    if target_leaf not in leaves:
        return None
    tree = _build_merkle_tree(leaves)
    idx = leaves.index(target_leaf)
    proof: List[Tuple[str, str]] = []

    level = list(leaves)
    for lvl in tree[:-1]:
        if len(lvl) % 2 == 1:
            lvl = lvl + [lvl[-1]]
        if idx % 2 == 0:
            sibling = lvl[idx + 1] if idx + 1 < len(lvl) else lvl[idx]
            proof.append((sibling, "right"))
        else:
            proof.append((lvl[idx - 1], "left"))
        idx //= 2
        level = lvl

    return proof


def verify_proof(leaf: str, proof: List[Tuple[str, str]], root: str) -> bool:
    """Verify a Merkle proof path against a known root."""
    current = leaf
    for sibling, direction in proof:
        if direction == "right":
            current = _merkle_parent(current, sibling)
        else:
            current = _merkle_parent(sibling, current)
    return current == root


# ---------------------------------------------------------------------------
# Chunk dataclass
# ---------------------------------------------------------------------------

@dataclass
class Chunk:
    chunk_id: str           # SHA-256 of content
    text: str
    node_id: str
    source: str             # file path or URL
    position: int           # ordinal within source
    embedding: Optional[List[float]] = None
    created_at: float = field(default_factory=time.time)

    @classmethod
    def from_text(cls, text: str, node_id: str, source: str, position: int) -> "Chunk":
        chunk_id = _sha256(f"{node_id}:{source}:{position}:{text}")
        return cls(chunk_id=chunk_id, text=text, node_id=node_id,
                   source=source, position=position)


# ---------------------------------------------------------------------------
# Text splitter
# ---------------------------------------------------------------------------

class TextSplitter:
    """
    Splits raw text into overlapping chunks by character count.
    """

    def __init__(self, chunk_size: int = 512, overlap: int = 64):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def split(self, text: str) -> List[str]:
        text = text.strip()
        if not text:
            return []
        chunks: List[str] = []
        start = 0
        while start < len(text):
            end = start + self.chunk_size
            chunks.append(text[start:end])
            start += self.chunk_size - self.overlap
        return chunks


# ---------------------------------------------------------------------------
# CorpusStore
# ---------------------------------------------------------------------------

class CorpusStore:
    """
    Manages the document corpus for a single domain miner node.
    Stores chunks in ChromaDB (if available) and maintains the Merkle tree
    over all chunk_ids for corpus integrity challenges.
    """

    def __init__(
        self,
        node_id: str,
        persist_dir: str = "./chroma_data",
        chunk_size: int = 512,
        overlap: int = 64,
    ):
        self.node_id = node_id
        self.splitter = TextSplitter(chunk_size=chunk_size, overlap=overlap)
        self._chunks: Dict[str, Chunk] = {}          # chunk_id → Chunk
        self._ordered_ids: List[str] = []            # insertion order for Merkle
        self._merkle_root: Optional[str] = None
        self._tree_dirty: bool = False

        if _CHROMA_AVAILABLE:
            client = chromadb.PersistentClient(
                path=persist_dir,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            self._collection = client.get_or_create_collection(
                name=f"corpus_{node_id}",
                metadata={"hnsw:space": "cosine"},
            )
            bt.logging.info(
                f"CorpusStore[{node_id}]: ChromaDB collection "
                f"'{self._collection.name}' opened at {persist_dir}"
            )
        else:
            self._collection = None

    # ── ingestion ─────────────────────────────────────────────────────

    def ingest_text(
        self,
        text: str,
        source: str,
        embedder=None,
    ) -> List[str]:
        """
        Split text into chunks, embed, store in Chroma and local dict.
        Returns list of new chunk_ids.
        """
        raw_chunks = self.splitter.split(text)
        new_ids: List[str] = []

        texts_to_embed = []
        chunk_objs: List[Chunk] = []
        for i, raw in enumerate(raw_chunks):
            chunk = Chunk.from_text(raw, self.node_id, source, i)
            if chunk.chunk_id in self._chunks:
                continue
            chunk_objs.append(chunk)
            texts_to_embed.append(raw)

        if not chunk_objs:
            return []

        # Embed in batch
        if embedder is not None and texts_to_embed:
            embeddings = embedder.embed(texts_to_embed)
            for chunk, emb in zip(chunk_objs, embeddings):
                chunk.embedding = emb

        # Store
        for chunk in chunk_objs:
            self._chunks[chunk.chunk_id] = chunk
            self._ordered_ids.append(chunk.chunk_id)
            new_ids.append(chunk.chunk_id)

        if self._collection is not None and chunk_objs:
            self._collection.add(
                ids=[c.chunk_id for c in chunk_objs],
                documents=[c.text for c in chunk_objs],
                embeddings=[c.embedding for c in chunk_objs if c.embedding] or None,
                metadatas=[
                    {"node_id": c.node_id, "source": c.source, "position": c.position}
                    for c in chunk_objs
                ],
            )

        self._tree_dirty = True
        bt.logging.debug(
            f"CorpusStore[{self.node_id}]: ingested {len(new_ids)} new chunks "
            f"from '{source}'"
        )
        return new_ids

    def ingest_file(self, path: str, embedder=None) -> List[str]:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
        return self.ingest_text(text, source=path, embedder=embedder)

    # ── retrieval ─────────────────────────────────────────────────────

    def query(
        self,
        query_embedding: List[float],
        top_k: int = 5,
    ) -> Tuple[List[str], List[str], List[float]]:
        """
        Retrieve top-k chunks by cosine similarity.
        Returns (texts, chunk_ids, scores).
        Falls back to simple string-ordering if Chroma not available.
        """
        if self._collection is not None and query_embedding:
            result = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=min(top_k, max(1, self._collection.count())),
                include=["documents", "distances"],
            )
            texts = result["documents"][0]
            ids = result["ids"][0]
            # Chroma returns L2 distance; convert to cosine score approximation
            scores = [max(0.0, 1.0 - d) for d in result["distances"][0]]
            return texts, ids, scores

        # Fallback: return first top_k chunks in insertion order
        ids = self._ordered_ids[:top_k]
        texts = [self._chunks[cid].text for cid in ids]
        scores = [1.0] * len(ids)
        return texts, ids, scores

    # ── Merkle ────────────────────────────────────────────────────────

    def _rebuild_tree(self) -> None:
        self._merkle_root = merkle_root(self._ordered_ids) if self._ordered_ids else _sha256("")
        self._tree_dirty = False

    def get_merkle_root(self) -> str:
        if self._tree_dirty or self._merkle_root is None:
            self._rebuild_tree()
        return self._merkle_root  # type: ignore[return-value]

    def prove_chunk(self, chunk_id: str) -> Optional[List[Tuple[str, str]]]:
        """Return the Merkle proof path for chunk_id, or None if not found."""
        if self._tree_dirty:
            self._rebuild_tree()
        return merkle_proof(self._ordered_ids, chunk_id)

    # ── stats ─────────────────────────────────────────────────────────

    def stats(self) -> Dict:
        return {
            "node_id": self.node_id,
            "chunk_count": len(self._chunks),
            "merkle_root": self.get_merkle_root(),
            "chroma_available": self._collection is not None,
        }
