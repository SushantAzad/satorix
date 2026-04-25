"""
3-phase entity resolution:
  Phase 1 — Blocking: partition candidates by cheap shared attribute (PIN, name prefix, phonetic)
  Phase 2 — Comparison: compute similarity scores using rapidfuzz metrics
  Phase 3 — Classification: auto-merge (>= 0.95), flag for review (0.75–0.95), discard (< 0.50)

Writes DedupGroup records to the database via the context caller (not directly).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd

logger = logging.getLogger(__name__)

try:
    from rapidfuzz import fuzz
    _HAS_RAPIDFUZZ = True
except ImportError:
    _HAS_RAPIDFUZZ = False
    logger.warning("rapidfuzz not installed — entity resolution disabled")


@dataclass
class EntityPair:
    idx_a: int
    idx_b: int
    record_a: dict
    record_b: dict
    score: float
    merge_strategy: str = "auto"   # auto | manual
    decision: str = "unknown"      # merge | review | discard


@dataclass
class ResolutionResult:
    canonical_groups: list[list[int]]        # list of groups; each group = list of row indices
    requires_review: list[list[int]]
    discarded_pairs: int
    total_comparisons: int


class EntityResolver:
    """
    Resolve duplicate entities within a DataFrame using configurable feature weights.

    Usage:
        resolver = EntityResolver(
            name_column="company_name",
            key_columns=["cin"],
            blocking_column="pin_code",
            weights={"name": 0.5, "address": 0.3, "pan": 0.2},
        )
        result = resolver.resolve(df)
    """

    AUTO_MERGE_THRESHOLD = 0.95
    REVIEW_THRESHOLD = 0.75
    DISCARD_THRESHOLD = 0.50

    def __init__(
        self,
        name_column: str,
        key_columns: list[str] | None = None,
        blocking_column: str | None = None,
        address_column: str | None = None,
        weights: dict[str, float] | None = None,
    ) -> None:
        if not _HAS_RAPIDFUZZ:
            raise RuntimeError("rapidfuzz must be installed for entity resolution")
        self.name_column = name_column
        self.key_columns = key_columns or []
        self.blocking_column = blocking_column
        self.address_column = address_column
        self.weights = weights or {"name": 1.0}

    def resolve(self, df: pd.DataFrame) -> ResolutionResult:
        if len(df) == 0:
            return ResolutionResult([], [], 0, 0)

        blocks = self._build_blocks(df)
        canonical_groups: list[list[int]] = []
        review_groups: list[list[int]] = []
        total_comparisons = 0
        discarded = 0

        # Union-Find for group merging
        parent: dict[int, int] = {i: i for i in range(len(df))}

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x: int, y: int) -> None:
            parent[find(x)] = find(y)

        review_pairs: list[tuple[int, int]] = []

        for block_indices in blocks:
            if len(block_indices) < 2:
                continue
            for i in range(len(block_indices)):
                for j in range(i + 1, len(block_indices)):
                    idx_a, idx_b = block_indices[i], block_indices[j]
                    total_comparisons += 1

                    # Skip if already in the same group
                    if find(idx_a) == find(idx_b):
                        continue

                    score = self._compute_score(df.iloc[idx_a], df.iloc[idx_b])

                    if score >= self.AUTO_MERGE_THRESHOLD:
                        union(idx_a, idx_b)
                    elif score >= self.REVIEW_THRESHOLD:
                        review_pairs.append((idx_a, idx_b))
                    elif score < self.DISCARD_THRESHOLD:
                        discarded += 1

        # Collect canonical groups
        from collections import defaultdict
        group_map: dict[int, list[int]] = defaultdict(list)
        for i in range(len(df)):
            group_map[find(i)].append(i)

        for group in group_map.values():
            if len(group) > 1:
                canonical_groups.append(group)

        # Collect review groups
        for a, b in review_pairs:
            review_groups.append([a, b])

        return ResolutionResult(
            canonical_groups=canonical_groups,
            requires_review=review_groups,
            discarded_pairs=discarded,
            total_comparisons=total_comparisons,
        )

    def _build_blocks(self, df: pd.DataFrame) -> list[list[int]]:
        """
        Partition the DataFrame into blocks to reduce O(n²) comparisons.
        Strategies (applied in order of availability):
          1. Shared blocking_column value (e.g. PIN code)
          2. First 3 chars of name_column (name prefix blocking)
        """
        if self.blocking_column and self.blocking_column in df.columns:
            groups = df.groupby(self.blocking_column, dropna=False)
            return [list(g.index) for _, g in groups if len(g) >= 2]

        # Name prefix blocking
        prefix_map: dict[str, list[int]] = {}
        for idx, row in df.iterrows():
            name = str(row.get(self.name_column, "")).upper()[:3]
            prefix_map.setdefault(name, []).append(idx)
        return [v for v in prefix_map.values() if len(v) >= 2]

    def _compute_score(self, row_a: pd.Series, row_b: pd.Series) -> float:
        """Weighted similarity score across configured feature columns."""
        total_weight = sum(self.weights.values())
        if total_weight == 0:
            return 0.0

        score = 0.0

        if "name" in self.weights:
            name_a = str(row_a.get(self.name_column, ""))
            name_b = str(row_b.get(self.name_column, ""))
            sim = (
                0.5 * fuzz.token_sort_ratio(name_a, name_b) / 100.0
                + 0.5 * fuzz.jaro_winkler_similarity(name_a, name_b)
            )
            score += self.weights["name"] * sim

        if "address" in self.weights and self.address_column:
            addr_a = str(row_a.get(self.address_column, ""))
            addr_b = str(row_b.get(self.address_column, ""))
            sim = fuzz.token_set_ratio(addr_a, addr_b) / 100.0
            score += self.weights["address"] * sim

        # Exact key match bonus (PAN, CIN, etc.)
        for key_col in self.key_columns:
            if "key" in self.weights:
                val_a = str(row_a.get(key_col, "")).strip()
                val_b = str(row_b.get(key_col, "")).strip()
                if val_a and val_b and val_a == val_b:
                    # Exact key match overrides everything
                    return 1.0
                elif val_a and val_b and val_a != val_b:
                    # Definitive non-match on unique key
                    return 0.0

        return score / total_weight
