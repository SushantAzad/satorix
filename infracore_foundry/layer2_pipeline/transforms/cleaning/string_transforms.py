"""String cleaning transforms."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from layer2_pipeline.core.context import ExecutionContext
from layer2_pipeline.transforms.base import BaseTransform, TransformError
from layer2_pipeline.transforms.registry import register


class TrimWhitespace(BaseTransform):
    """Strip leading/trailing whitespace and collapse internal runs."""

    transform_type = "trim_whitespace"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        cols = config.get("columns") or [c for c in df.columns if pd.api.types.is_string_dtype(df[c])]
        df = df.copy()
        for col in cols:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
                if config.get("collapse_internal", False):
                    df[col] = df[col].str.replace(r"\s+", " ", regex=True)
        return df


class NormalizeCase(BaseTransform):
    """Normalize string case: upper | lower | title."""

    transform_type = "normalize_case"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        cols = config.get("columns", [])
        mode = config.get("mode", "upper").lower()
        if mode not in ("upper", "lower", "title"):
            raise TransformError(f"Invalid mode {mode!r}; expected upper|lower|title")
        df = df.copy()
        for col in cols:
            if col not in df.columns:
                context.warn(f"NormalizeCase: column {col!r} not in DataFrame")
                continue
            s = df[col].astype(str)
            df[col] = getattr(s.str, mode)()
        return df

    @classmethod
    def validate_config(cls, config: dict) -> list[str]:
        errors = []
        if not config.get("columns"):
            errors.append("normalize_case: 'columns' is required")
        if config.get("mode", "upper") not in ("upper", "lower", "title"):
            errors.append("normalize_case: 'mode' must be upper|lower|title")
        return errors


class RegexExtract(BaseTransform):
    """Extract first capture group of a regex into a new or the same column."""

    transform_type = "regex_extract"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        source_col = config["source_column"]
        pattern = config["pattern"]
        target_col = config.get("target_column", source_col)
        if source_col not in df.columns:
            raise TransformError(f"regex_extract: source column {source_col!r} not found")
        df = df.copy()
        df[target_col] = df[source_col].astype(str).str.extract(pattern, expand=False)
        return df

    @classmethod
    def validate_config(cls, config: dict) -> list[str]:
        errors = []
        if not config.get("source_column"):
            errors.append("regex_extract: 'source_column' is required")
        if not config.get("pattern"):
            errors.append("regex_extract: 'pattern' is required")
        return errors


class RegexReplace(BaseTransform):
    """Replace regex matches in a column."""

    transform_type = "regex_replace"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        col = config["column"]
        pattern = config["pattern"]
        replacement = config.get("replacement", "")
        if col not in df.columns:
            raise TransformError(f"regex_replace: column {col!r} not found")
        df = df.copy()
        df[col] = df[col].astype(str).str.replace(pattern, replacement, regex=True)
        return df

    @classmethod
    def validate_config(cls, config: dict) -> list[str]:
        errors = []
        if not config.get("column"):
            errors.append("regex_replace: 'column' is required")
        if not config.get("pattern"):
            errors.append("regex_replace: 'pattern' is required")
        return errors


class FillNullString(BaseTransform):
    """Replace null/empty string values with a default."""

    transform_type = "fill_null_string"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        cols = config.get("columns") or list(df.columns)
        default = config.get("default", "")
        df = df.copy()
        for col in cols:
            if col in df.columns:
                df[col] = df[col].fillna(default)
                df[col] = df[col].replace("", default)
        return df


class RemoveSpecialCharacters(BaseTransform):
    """Remove characters not matching a whitelist pattern."""

    transform_type = "remove_special_characters"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        cols = config.get("columns", [])
        keep_pattern = config.get("keep_pattern", r"[^a-zA-Z0-9 ]")
        replacement = config.get("replacement", "")
        df = df.copy()
        for col in cols:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace(keep_pattern, replacement, regex=True)
        return df


# Register all instances
register(TrimWhitespace())
register(NormalizeCase())
register(RegexExtract())
register(RegexReplace())
register(FillNullString())
register(RemoveSpecialCharacters())
