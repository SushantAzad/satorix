"""
Deduplication engine: exact key dedup, fuzzy dedup, and cross-batch dedup.
Fuzzy matching uses rapidfuzz for performance on large DataFrames.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Any, Optional

import pandas as pd

logger = logging.getLogger(__name__)

try:
    from rapidfuzz import fuzz, process as rfuzz_process
    _HAS_RAPIDFUZZ = True
except ImportError:
    _HAS_RAPIDFUZZ = False
    logger.warning("rapidfuzz not installed; fuzzy deduplication will be disabled")


@dataclass
class DedupResult:
    total_input: int
    total_output: int
    duplicates_removed: int
    groups_merged: int


class ExactDeduplicator:
    """
    Deduplicate rows with identical values on a set of key columns.
    When merge_strategy='latest', the row with the highest value in sort_col is kept.
    """

    def __init__(self, key_columns: list[str], sort_column: Optional[str] = None, keep: str = "first") -> None:
        self.key_columns = key_columns
        self.sort_column = sort_column
        self.keep = keep

    def deduplicate(self, df: pd.DataFrame) -> tuple[pd.DataFrame, DedupResult]:
        n_in = len(df)

        if self.sort_column and self.sort_column in df.columns:
            df = df.sort_values(self.sort_column, ascending=False)

        result = df.drop_duplicates(subset=self.key_columns, keep=self.keep).reset_index(drop=True)
        n_out = len(result)

        return result, DedupResult(
            total_input=n_in,
            total_output=n_out,
            duplicates_removed=n_in - n_out,
            groups_merged=n_in - n_out,
        )


class FuzzyDeduplicator:
    """
    Fuzzy deduplication using token_sort_ratio from rapidfuzz.
    Groups records where the match_column similarity exceeds threshold.
    The canonical record in each group is the one with the highest sort_column value.

    Complexity: O(n²) in the worst case — use blocking to reduce candidates first.
    For n > 10,000 records, enable blocking_column to partition the search space.
    """

    def __init__(
        self,
        match_column: str,
        threshold: float = 85.0,
        key_column: Optional[str] = None,
        sort_column: Optional[str] = None,
        blocking_column: Optional[str] = None,
    ) -> None:
        if not _HAS_RAPIDFUZZ:
            raise RuntimeError("rapidfuzz must be installed for fuzzy deduplication")
        self.match_column = match_column
        self.threshold = threshold
        self.key_column = key_column
        self.sort_column = sort_column
        self.blocking_column = blocking_column

    def deduplicate(self, df: pd.DataFrame) -> tuple[pd.DataFrame, DedupResult]:
        n_in = len(df)
        if n_in == 0:
            return df, DedupResult(0, 0, 0, 0)

        if self.blocking_column and self.blocking_column in df.columns:
            blocks = df.groupby(self.blocking_column)
            parts = [self._dedup_block(block_df) for _, block_df in blocks]
            result = pd.concat(parts, ignore_index=True)
        else:
            result = self._dedup_block(df)

        n_out = len(result)
        return result, DedupResult(
            total_input=n_in,
            total_output=n_out,
            duplicates_removed=n_in - n_out,
            groups_merged=n_in - n_out,
        )

    def _dedup_block(self, df: pd.DataFrame) -> pd.DataFrame:
        if len(df) <= 1:
            return df

        if self.sort_column and self.sort_column in df.columns:
            df = df.sort_values(self.sort_column, ascending=False).reset_index(drop=True)

        values = df[self.match_column].astype(str).tolist()
        canonical_indices: set[int] = set()
        merged_indices: set[int] = set()

        for i, val in enumerate(values):
            if i in merged_indices:
                continue
            canonical_indices.add(i)
            for j in range(i + 1, len(values)):
                if j in merged_indices:
                    continue
                score = fuzz.token_sort_ratio(val, values[j])
                if score >= self.threshold:
                    merged_indices.add(j)
                    logger.debug("Fuzzy merge: %r ≈ %r (score=%.1f)", val, values[j], score)

        return df.iloc[sorted(canonical_indices)].reset_index(drop=True)


class CrossBatchDeduplicator:
    """
    Detect records already ingested in a previous batch using a bloom-filter-like
    fingerprint approach. Fingerprint = SHA-256(key column values joined).
    """

    def __init__(self, key_columns: list[str]) -> None:
        self.key_columns = key_columns

    def compute_fingerprints(self, df: pd.DataFrame) -> pd.Series:
        """Return a Series of hex fingerprints, one per row."""
        def _fp(row: pd.Series) -> str:
            content = "|".join(str(row.get(c, "")) for c in self.key_columns)
            return hashlib.sha256(content.encode()).hexdigest()[:16]

        return df.apply(_fp, axis=1)

    def filter_new(self, df: pd.DataFrame, seen_fingerprints: set[str]) -> tuple[pd.DataFrame, int]:
        """Return only rows whose fingerprint is NOT in seen_fingerprints."""
        fps = self.compute_fingerprints(df)
        is_new = ~fps.isin(seen_fingerprints)
        new_df = df[is_new].reset_index(drop=True)
        duplicate_count = int((~is_new).sum())
        return new_df, duplicate_count
