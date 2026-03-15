"""
miners/domain/corpus.py

Two classes:

  CorpusLoader   — ingests .txt/.md files from a directory, splits them into
                   overlapping chunks, embeds each chunk, and computes the
                   domain centroid embedding.

  MerkleProver   — builds a binary Merkle tree over chunk hashes and serves
                   inclusion proofs in response to validator chunk challenges.

Design notes:

  - CorpusLoader is called once at miner startup. It is intentionally
    synchronous and blocking — we want startup to wait until the corpus is
    fully loaded before the axon starts accepting queries.

  - Embeddings are computed in batches and cached to disk as a .npy file
    alongside the corpus directory. On restart, if the cache is fresh
    (same file mtimes), loading takes <1s instead of ~30s.

  - MerkleProver uses SHA-256 throughout. The root hash it computes must
    match the corpus_root_hash in the miner's on-chain manifest, or
    validators will flag a corpus integrity failure.

  - The Merkle tree is a complete binary tree padded with the last leaf.
    Proof paths are left/right sibling hashes from leaf to root.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import pickle
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
from sentence_transformers import SentenceTransformer

from config.subnet_config import (
    CHUNK_MAX_TOKENS,
    CHUNK_OVERLAP_TOKENS,
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_DIM,
)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class Chunk:
    id:         str          # "{source_stem}_{index:04d}"
    source_id:  str          # original filename stem
    text:       str          # chunk plaintext
    hash:       str          # SHA-256 hex of text (utf-8 encoded)
    embedding:  list[float]  # EMBEDDING_DIM floats
    char_start: int          # character offset in source document
    char_end:   int


# ---------------------------------------------------------------------------
# CorpusLoader
# ---------------------------------------------------------------------------

class CorpusLoader:
    """
    Loads a domain corpus from a directory, chunks it, embeds it, and
    exposes the chunks + centroid for the domain miner.

    Args:
        corpus_dir: Path to directory containing .txt and/or .md files.
        embedder:   A loaded SentenceTransformer instance.
        cache:      Whether to read/write an embedding cache.

    After load():
        self.chunks   — list[Chunk], one entry per text segment
        self.centroid — np.ndarray shape (EMBEDDING_DIM,), mean of all embeddings
    """

    def __init__(
        self,
        corpus_dir: Path,
        embedder:   SentenceTransformer,
        cache:      bool = True,
    ):
        self.corpus_dir = corpus_dir
        self.embedder   = embedder
        self.cache      = cache
        self.chunks:    list[Chunk] = []
        self.centroid:  np.ndarray  = np.zeros(EMBEDDING_DIM)
        self._cache_path = corpus_dir / ".embedding_cache.pkl"

    def load(self) -> list[dict]:
        """
        Main entry point. Returns chunks as list[dict] suitable for
        inserting into Chroma (serialisable, no numpy).
        """
        t0 = time.monotonic()

        # 1. Gather source files
        source_files = sorted(
            p for p in self.corpus_dir.rglob("*")
            if p.suffix in {".txt", ".md"} and not p.name.startswith(".")
        )
        if not source_files:
            raise FileNotFoundError(
                f"No .txt or .md files found in {self.corpus_dir}"
            )

        # 2. Check cache validity
        if self.cache and self._cache_valid(source_files):
            self._load_cache()
        else:
            self._ingest(source_files)
            if self.cache:
                self._save_cache()

        elapsed = time.monotonic() - t0
        print(
            f"[corpus] Loaded {len(self.chunks)} chunks from "
            f"{len(source_files)} files in {elapsed:.1f}s"
        )

        return [self._chunk_to_dict(c) for c in self.chunks]

    # -----------------------------------------------------------------------
    # Ingestion
    # -----------------------------------------------------------------------

    def _ingest(self, source_files: list[Path]):
        raw_texts: list[str]  = []
        meta:      list[dict] = []

        for path in source_files:
            text = path.read_text(encoding="utf-8", errors="replace")
            segments = self._split(text)
            stem = path.stem
            for i, (seg, start, end) in enumerate(segments):
                raw_texts.append(seg)
                meta.append({
                    "id":         f"{stem}_{i:04d}",
                    "source_id":  stem,
                    "char_start": start,
                    "char_end":   end,
                })

        # Embed in batches
        all_embeddings = self._embed_batched(raw_texts)

        self.chunks = []
        for text, emb, m in zip(raw_texts, all_embeddings, meta):
            self.chunks.append(Chunk(
                id         = m["id"],
                source_id  = m["source_id"],
                text       = text,
                hash       = _sha256(text),
                embedding  = emb.tolist(),
                char_start = m["char_start"],
                char_end   = m["char_end"],
            ))

        self.centroid = all_embeddings.mean(axis=0)

    def _split(self, text: str) -> list[tuple[str, int, int]]:
        """
        Naive token-approximate chunker.

        We approximate tokens as words (1 word ≈ 1.3 tokens on average).
        This avoids a tokenizer dependency while staying reasonably close
        to the token budget. For production, swap with tiktoken or the
        model's own tokenizer.

        Returns list of (chunk_text, char_start, char_end).
        """
        words = text.split()
        if not words:
            return []

        # Convert token limits to approximate word counts
        max_words     = int(CHUNK_MAX_TOKENS / 1.3)
        overlap_words = int(CHUNK_OVERLAP_TOKENS / 1.3)
        stride        = max(1, max_words - overlap_words)

        segments = []
        word_positions = _word_positions(text)   # list of (word, char_start, char_end)

        i = 0
        while i < len(words):
            end_idx = min(i + max_words, len(words))
            chunk_words = words[i:end_idx]
            chunk_text  = " ".join(chunk_words)

            char_start = word_positions[i][1]
            char_end   = word_positions[end_idx - 1][2]

            segments.append((chunk_text, char_start, char_end))
            i += stride

        return segments

    def _embed_batched(self, texts: list[str]) -> np.ndarray:
        """Embed a list of texts in batches. Returns (N, DIM) array."""
        all_embs = []
        for i in range(0, len(texts), EMBEDDING_BATCH_SIZE):
            batch = texts[i : i + EMBEDDING_BATCH_SIZE]
            embs  = self.embedder.encode(
                batch,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            all_embs.append(embs)
        return np.vstack(all_embs).astype(np.float32)

    # -----------------------------------------------------------------------
    # Cache
    # -----------------------------------------------------------------------

    def _cache_valid(self, source_files: list[Path]) -> bool:
        """True if cache exists and is newer than all source files."""
        if not self._cache_path.exists():
            return False
        cache_mtime = self._cache_path.stat().st_mtime
        return all(f.stat().st_mtime <= cache_mtime for f in source_files)

    def _load_cache(self):
        with open(self._cache_path, "rb") as f:
            data = pickle.load(f)
        self.chunks   = data["chunks"]
        self.centroid = data["centroid"]
        print(f"[corpus] Loaded {len(self.chunks)} chunks from cache.")

    def _save_cache(self):
        with open(self._cache_path, "wb") as f:
            pickle.dump({"chunks": self.chunks, "centroid": self.centroid}, f)

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _chunk_to_dict(c: Chunk) -> dict:
        return {
            "id":        c.id,
            "source_id": c.source_id,
            "text":      c.text,
            "hash":      c.hash,
            "embedding": c.embedding,
        }


# ---------------------------------------------------------------------------
# MerkleProver
# ---------------------------------------------------------------------------

class MerkleProver:
    """
    Builds a binary Merkle tree over the SHA-256 hashes of all corpus chunks
    and serves inclusion proofs for individual chunks.

    The tree is constructed bottom-up:
      - Leaves: SHA-256(chunk.text) for each chunk, in load order.
      - Internal nodes: SHA-256(left_child_hash + right_child_hash).
      - Odd number of leaves: last leaf is duplicated to make the tree complete.

    The root_hash must match the corpus_root_hash in the miner's manifest.
    If it doesn't, the miner's manifest is stale and needs refreshing.

    Proof format returned to validators:
        {
            "chunk_hash":   str,          # SHA-256 of the chunk text
            "chunk_text":   str,          # plaintext (for re-hashing)
            "leaf_index":   int,          # position in the leaf array
            "siblings":     list[str],    # sibling hashes leaf→root
            "directions":   list[str],    # "left" or "right" per sibling
            "root_hash":    str,
        }

    Verification (validator side):
        current = SHA-256(chunk_text)
        for sibling, direction in zip(siblings, directions):
            if direction == "left":
                current = SHA-256(sibling + current)
            else:
                current = SHA-256(current + sibling)
        assert current == root_hash
    """

    def __init__(self, chunks: list[dict]):
        """
        Args:
            chunks: list of chunk dicts, each with at least "hash" and "text".
                    Order matters — must be the same order as at manifest time.
        """
        self.n_chunks  = len(chunks)
        self._hash_to_chunk: dict[str, dict] = {c["hash"]: c for c in chunks}
        self._leaves:  list[str] = [c["hash"] for c in chunks]
        self._tree:    list[list[str]] = []
        self.root_hash: str = ""
        self._build()

    # -----------------------------------------------------------------------
    # Build
    # -----------------------------------------------------------------------

    def _build(self):
        """
        Constructs the tree level by level from leaves upward.
        self._tree[0] = leaves
        self._tree[-1] = [root_hash]
        """
        if not self._leaves:
            self.root_hash = _sha256("")
            return

        level = list(self._leaves)

        # Pad to even length at each level
        if len(level) % 2 == 1:
            level.append(level[-1])

        self._tree = [level]

        while len(level) > 1:
            next_level = []
            for i in range(0, len(level), 2):
                combined   = level[i] + level[i + 1]
                next_level.append(_sha256(combined))
            if len(next_level) % 2 == 1 and len(next_level) > 1:
                next_level.append(next_level[-1])
            self._tree.append(next_level)
            level = next_level

        self.root_hash = self._tree[-1][0]

    # -----------------------------------------------------------------------
    # Prove
    # -----------------------------------------------------------------------

    def prove(self, chunk_hash: str) -> Optional[dict]:
        """
        Returns an inclusion proof for the chunk identified by chunk_hash,
        or None if the hash is not in this corpus.
        """
        if chunk_hash not in self._hash_to_chunk:
            return None

        chunk      = self._hash_to_chunk[chunk_hash]
        leaf_index = self._leaves.index(chunk_hash)

        siblings:   list[str] = []
        directions: list[str] = []

        idx = leaf_index
        for level in self._tree[:-1]:  # exclude root level
            # Pad level to even if needed (mirrors _build logic)
            padded = list(level)
            if len(padded) % 2 == 1:
                padded.append(padded[-1])

            if idx % 2 == 0:
                # Current node is left child; sibling is right
                sibling_idx = idx + 1
                directions.append("right")
            else:
                # Current node is right child; sibling is left
                sibling_idx = idx - 1
                directions.append("left")

            siblings.append(padded[sibling_idx])
            idx = idx // 2

        return {
            "chunk_hash":   chunk_hash,
            "chunk_text":   chunk["text"],
            "leaf_index":   leaf_index,
            "siblings":     siblings,
            "directions":   directions,
            "root_hash":    self.root_hash,
            "n_chunks":     self.n_chunks,
        }

    def verify(self, proof: dict) -> bool:
        """
        Verifies a proof dict against this tree's root_hash.
        Used in tests and by the validator's local verification helper.
        """
        current = _sha256(proof["chunk_text"])
        for sibling, direction in zip(proof["siblings"], proof["directions"]):
            if direction == "left":
                current = _sha256(sibling + current)
            else:
                current = _sha256(current + sibling)
        return current == self.root_hash


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _sha256(text: str) -> str:
    """Return the hex SHA-256 digest of a UTF-8 string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _word_positions(text: str) -> list[tuple[str, int, int]]:
    """
    Returns a list of (word, char_start, char_end) for each whitespace-
    separated token in text. Used by the chunker to track character offsets.
    """
    positions = []
    i = 0
    for word in text.split():
        start = text.index(word, i)
        end   = start + len(word)
        positions.append((word, start, end))
        i = end
    return positions


def merkle_root(chunk_hashes: list[str]) -> str:
    """
    Compute the Merkle root of a list of hex SHA-256 chunk hashes.
    Convenience wrapper used by scripts/register_miner.py.
    """
    if not chunk_hashes:
        return _sha256("")
    level = list(chunk_hashes)
    if len(level) % 2 == 1:
        level.append(level[-1])
    while len(level) > 1:
        next_level = [
            _sha256(level[i] + level[i + 1])
            for i in range(0, len(level), 2)
        ]
        if len(next_level) % 2 == 1 and len(next_level) > 1:
            next_level.append(next_level[-1])
        level = next_level
    return level[0]


def compute_corpus_root_hash(corpus_dir: Path) -> str:
    """
    Standalone helper used by scripts/register_miner.py to compute the
    root hash before the full CorpusLoader is initialised.
    Requires only the chunk texts in load order (no embeddings).
    """
    source_files = sorted(
        p for p in corpus_dir.rglob("*")
        if p.suffix in {".txt", ".md"} and not p.name.startswith(".")
    )
    leaves = []
    for path in source_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        for word_count_start in range(
            0,
            len(text.split()),
            max(1, int(CHUNK_MAX_TOKENS / 1.3) - int(CHUNK_OVERLAP_TOKENS / 1.3))
        ):
            chunk = " ".join(
                text.split()[
                    word_count_start : word_count_start + int(CHUNK_MAX_TOKENS / 1.3)
                ]
            )
            if chunk.strip():
                leaves.append(_sha256(chunk))

    if not leaves:
        return _sha256("")

    # Build minimal tree to get root
    level = leaves[:]
    if len(level) % 2 == 1:
        level.append(level[-1])
    while len(level) > 1:
        next_level = [
            _sha256(level[i] + level[i + 1])
            for i in range(0, len(level), 2)
        ]
        if len(next_level) % 2 == 1 and len(next_level) > 1:
            next_level.append(next_level[-1])
        level = next_level
    return level[0]
