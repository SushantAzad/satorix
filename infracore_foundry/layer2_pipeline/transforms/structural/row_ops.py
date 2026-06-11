"""Row-level structural transforms: filter, deduplicate, sort, number."""

from __future__ import annotations

from typing import Any

import pandas as pd

from layer2_pipeline.core.context import ExecutionContext
from layer2_pipeline.transforms.base import BaseTransform, TransformError
from layer2_pipeline.transforms.registry import register


class FilterRows(BaseTransform):
    """
    Keep rows matching a pandas query expression.
    config: expression (str) — e.g. "status == 'active' and amount > 0"
    """

    transform_type = "filter_rows"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        expression = config.get("expression")
        if not expression:
            raise TransformError("filter_rows: 'expression' is required")
        try:
            result = df.query(expression)
        except Exception as exc:
            raise TransformError(f"filter_rows: query failed {expression!r}: {exc}") from exc
        dropped = len(df) - len(result)
        if dropped > 0:
            context.warn(f"filter_rows step {step_id}: dropped {dropped} rows")
        return result.reset_index(drop=True)

    @classmethod
    def validate_config(cls, config: dict) -> list[str]:
        if not config.get("expression"):
            return ["filter_rows: 'expression' is required"]
        return []


class DropNullRows(BaseTransform):
    """Drop rows where ANY or ALL of the specified columns are null."""

    transform_type = "drop_null_rows"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        cols = config.get("columns")
        how = config.get("how", "any")  # any | all
        if how not in ("any", "all"):
            raise TransformError("drop_null_rows: 'how' must be 'any' or 'all'")
        result = df.dropna(subset=cols, how=how)
        dropped = len(df) - len(result)
        if dropped > 0:
            context.warn(f"drop_null_rows: dropped {dropped} rows with null in {cols or 'any column'}")
        return result.reset_index(drop=True)


class DeduplicateRows(BaseTransform):
    """
    Deduplicate rows by key columns.
    keep: first | last | none (drop all duplicates)
    """

    transform_type = "deduplicate_rows"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        key_cols = config.get("key_columns")
        keep = config.get("keep", "first")
        if keep not in ("first", "last", "none", False):
            raise TransformError("deduplicate_rows: 'keep' must be first|last|none")
        keep_val = False if keep == "none" else keep
        result = df.drop_duplicates(subset=key_cols, keep=keep_val)
        dropped = len(df) - len(result)
        if dropped > 0:
            context.warn(f"deduplicate_rows: removed {dropped} duplicate rows on {key_cols or 'all columns'}")
        return result.reset_index(drop=True)


class SortRows(BaseTransform):
    """Sort rows by one or more columns."""

    transform_type = "sort_rows"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        cols = config.get("columns", [])
        ascending = config.get("ascending", True)
        if not cols:
            raise TransformError("sort_rows: 'columns' list is required")
        missing = [c for c in cols if c not in df.columns]
        if missing:
            raise TransformError(f"sort_rows: columns not found: {missing}")
        if isinstance(ascending, bool):
            ascending_list = [ascending] * len(cols)
        else:
            ascending_list = ascending
        return df.sort_values(by=cols, ascending=ascending_list, na_position="last").reset_index(drop=True)


class AddRowNumber(BaseTransform):
    """Add a sequential row number column (1-based by default)."""

    transform_type = "add_row_number"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        target_col = config.get("target_column", "row_number")
        start = config.get("start", 1)
        df = df.copy()
        df[target_col] = range(start, start + len(df))
        return df


class SampleRows(BaseTransform):
    """Sample N rows or a fraction of rows (useful in testing/preview mode)."""

    transform_type = "sample_rows"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        n = config.get("n")
        frac = config.get("frac")
        random_state = config.get("random_state", 42)
        if n is None and frac is None:
            raise TransformError("sample_rows: either 'n' or 'frac' is required")
        kwargs = {"random_state": random_state}
        if n is not None:
            kwargs["n"] = min(n, len(df))
        else:
            kwargs["frac"] = frac
        return df.sample(**kwargs).reset_index(drop=True)


register(FilterRows())
register(DropNullRows())
register(DeduplicateRows())
register(SortRows())
register(AddRowNumber())
register(SampleRows())
