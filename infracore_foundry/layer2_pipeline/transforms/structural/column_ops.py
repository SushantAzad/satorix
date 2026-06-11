"""Column-level structural transforms: rename, drop, add, split, concat."""

from __future__ import annotations

from typing import Any

import pandas as pd

from layer2_pipeline.core.context import ExecutionContext
from layer2_pipeline.transforms.base import BaseTransform, TransformError
from layer2_pipeline.transforms.registry import register


class RenameColumns(BaseTransform):
    """Rename one or more columns via a mapping dict."""

    transform_type = "rename_columns"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        mapping: dict[str, str] = config.get("mapping", {})
        if not mapping:
            raise TransformError("rename_columns: 'mapping' is required and must be non-empty")
        missing = [k for k in mapping if k not in df.columns]
        if missing and not config.get("ignore_missing", False):
            raise TransformError(f"rename_columns: columns not found: {missing}")
        actual_mapping = {k: v for k, v in mapping.items() if k in df.columns}
        return df.rename(columns=actual_mapping)

    @classmethod
    def validate_config(cls, config: dict) -> list[str]:
        if not config.get("mapping"):
            return ["rename_columns: 'mapping' dict is required"]
        return []


class DropColumns(BaseTransform):
    """Drop specified columns; optionally silently ignore missing ones."""

    transform_type = "drop_columns"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        cols = config.get("columns", [])
        ignore_missing = config.get("ignore_missing", True)
        to_drop = [c for c in cols if c in df.columns]
        missing = [c for c in cols if c not in df.columns]
        if missing and not ignore_missing:
            raise TransformError(f"drop_columns: columns not found: {missing}")
        return df.drop(columns=to_drop)

    @classmethod
    def validate_config(cls, config: dict) -> list[str]:
        if not config.get("columns"):
            return ["drop_columns: 'columns' list is required"]
        return []


class SelectColumns(BaseTransform):
    """Keep only specified columns in the given order."""

    transform_type = "select_columns"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        cols = config.get("columns", [])
        missing = [c for c in cols if c not in df.columns]
        if missing:
            raise TransformError(f"select_columns: columns not found: {missing}")
        return df[cols]


class AddComputedColumn(BaseTransform):
    """
    Add a column computed from a simple expression evaluated against other columns.
    Uses pandas eval — safe subset only (no builtins, no arbitrary Python).
    """

    transform_type = "add_computed_column"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        target_col = config["target_column"]
        expression = config["expression"]
        df = df.copy()
        try:
            df[target_col] = df.eval(expression)
        except Exception as exc:
            raise TransformError(f"add_computed_column: eval failed for {expression!r}: {exc}") from exc
        return df

    @classmethod
    def validate_config(cls, config: dict) -> list[str]:
        errors = []
        if not config.get("target_column"):
            errors.append("add_computed_column: 'target_column' is required")
        if not config.get("expression"):
            errors.append("add_computed_column: 'expression' is required")
        return errors


class AddConstantColumn(BaseTransform):
    """Add a column with a fixed constant value."""

    transform_type = "add_constant_column"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        target_col = config["target_column"]
        value = config.get("value")
        df = df.copy()
        df[target_col] = value
        return df


class SplitColumn(BaseTransform):
    """
    Split a string column into multiple columns by a delimiter.
    config: source_column, delimiter, target_columns (list of names), max_split (int)
    """

    transform_type = "split_column"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        source_col = config["source_column"]
        delimiter = config.get("delimiter", ",")
        target_cols = config["target_columns"]
        max_split = config.get("max_split", len(target_cols) - 1)
        if source_col not in df.columns:
            raise TransformError(f"split_column: column {source_col!r} not found")
        df = df.copy()
        split_df = df[source_col].astype(str).str.split(delimiter, n=max_split, expand=True)
        for i, col in enumerate(target_cols):
            df[col] = split_df[i] if i < split_df.shape[1] else None
        return df

    @classmethod
    def validate_config(cls, config: dict) -> list[str]:
        errors = []
        if not config.get("source_column"):
            errors.append("split_column: 'source_column' is required")
        if not config.get("target_columns"):
            errors.append("split_column: 'target_columns' list is required")
        return errors


class ConcatColumns(BaseTransform):
    """Concatenate multiple columns into one with a separator."""

    transform_type = "concat_columns"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        source_cols = config["source_columns"]
        target_col = config["target_column"]
        separator = config.get("separator", " ")
        skip_nulls = config.get("skip_nulls", True)
        df = df.copy()

        def _concat(row: pd.Series) -> str:
            parts = [str(row[c]) for c in source_cols if c in row.index and (pd.notna(row[c]) or not skip_nulls)]
            return separator.join(parts)

        df[target_col] = df.apply(_concat, axis=1)
        return df

    @classmethod
    def validate_config(cls, config: dict) -> list[str]:
        errors = []
        if not config.get("source_columns"):
            errors.append("concat_columns: 'source_columns' list is required")
        if not config.get("target_column"):
            errors.append("concat_columns: 'target_column' is required")
        return errors


class CastColumn(BaseTransform):
    """Cast columns to specified dtypes."""

    transform_type = "cast_column"

    _DTYPE_MAP = {
        "string": str,
        "str": str,
        "int": "Int64",    # nullable integer
        "integer": "Int64",
        "float": float,
        "double": float,
        "bool": bool,
        "boolean": bool,
        "date": "datetime64[ns]",
        "datetime": "datetime64[ns]",
    }

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        casts: dict[str, str] = config.get("casts", {})
        df = df.copy()
        for col, dtype_str in casts.items():
            if col not in df.columns:
                context.warn(f"cast_column: column {col!r} not found")
                continue
            target_dtype = self._DTYPE_MAP.get(dtype_str.lower(), dtype_str)
            try:
                if target_dtype in ("datetime64[ns]",):
                    df[col] = pd.to_datetime(df[col], errors="coerce")
                else:
                    df[col] = df[col].astype(target_dtype, errors="ignore")
            except Exception as exc:
                context.warn(f"cast_column: failed to cast {col!r} to {dtype_str}: {exc}")
        return df


register(RenameColumns())
register(DropColumns())
register(SelectColumns())
register(AddComputedColumn())
register(AddConstantColumn())
register(SplitColumn())
register(ConcatColumns())
register(CastColumn())
