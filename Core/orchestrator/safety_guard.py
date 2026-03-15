"""
orchestrator/safety_guard.py
Content-safety filtering for player traversal paths and narrative text.

PathSafetyGuard is called on every hop to:
  1. Filter next-node candidates (remove nodes that would create cycles
     or violate path length limits).
  2. Check generated hop text for policy violations (placeholder; integrate
     a real moderation API in production).
  3. Optionally return a sanitised replacement passage on violation.
"""

from __future__ import annotations

from typing import List, Optional


class PathSafetyGuard:
    """
    Stateless safety guard for traversal paths and narrative text.

    Args:
        max_revisits:   Maximum number of times a node may appear in the path.
                        Default 1 — no revisits allowed.
        min_hop_words:  Minimum word count to pass the text length check.
        max_hop_words:  Maximum word count to pass the text length check.
    """

    def __init__(
        self,
        max_revisits: int = 1,
        min_hop_words: int = 30,
        max_hop_words: int = 400,
    ):
        self.max_revisits = max_revisits
        self.min_hop_words = min_hop_words
        self.max_hop_words = max_hop_words

    def filter_candidates(
        self,
        current_path: List[str],
        candidates: List[str],
    ) -> List[str]:
        """
        Remove candidate node_ids that would violate path constraints.

        Filtered out:
          - Nodes already visited >= max_revisits times in current_path
        """
        from collections import Counter
        visit_counts = Counter(current_path)
        return [c for c in candidates if visit_counts[c] < self.max_revisits]

    def tick(
        self,
        path: List[str],
        hop_text: str,
    ) -> Optional[str]:
        """
        Called after each hop is generated.  Returns None if the text passes
        safety checks, or a sanitised replacement string on violation.

        Current checks:
          - Minimum word count (empty / too-short passages indicate a failure)
          - Maximum word count (extremely verbose responses are truncated)

        Production: integrate a moderation API call here.
        """
        words = hop_text.split()

        if len(words) < self.min_hop_words:
            return (
                "The journey continues, bridging ideas across the knowledge "
                "landscape toward new horizons of understanding."
            )

        if len(words) > self.max_hop_words:
            # Hard-truncate at sentence boundary closest to max_hop_words
            truncated = " ".join(words[: self.max_hop_words])
            last_period = truncated.rfind(".")
            if last_period > len(truncated) // 2:
                truncated = truncated[: last_period + 1]
            return truncated

        return None
