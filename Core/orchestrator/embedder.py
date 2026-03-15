"""
orchestrator/embedder.py
Thin wrapper around SentenceTransformer for embedding queries and passages.

A single shared Embedder instance is created at gateway startup and injected
into the OrchestratorSession and the Validator's ScoringLoop.
"""

from __future__ import annotations

from typing import List

import numpy as np
from sentence_transformers import SentenceTransformer

from config.subnet_config import EMBEDDING_BATCH_SIZE, EMBEDDING_DIM, EMBEDDING_MODEL


class Embedder:
    """
    Wraps a SentenceTransformer model and exposes a simple embed() method.

    Args:
        model_name: HuggingFace model ID (default: all-mpnet-base-v2, 768-dim).
        device:     "cpu", "cuda", or "mps".  None = auto-detect.
    """

    def __init__(
        self,
        model_name: str = EMBEDDING_MODEL,
        device: str | None = None,
    ):
        self._model = SentenceTransformer(model_name, device=device)
        self._dim = EMBEDDING_DIM

    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Embed a list of strings.

        Returns a list of EMBEDDING_DIM-length float lists, one per input text.
        Embeddings are L2-normalised (cosine similarity = dot product).
        """
        if not texts:
            return []

        embeddings: np.ndarray = self._model.encode(
            texts,
            batch_size=EMBEDDING_BATCH_SIZE,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return embeddings.tolist()

    def embed_one(self, text: str) -> List[float]:
        """Convenience wrapper for single-text embedding."""
        return self.embed([text])[0]
