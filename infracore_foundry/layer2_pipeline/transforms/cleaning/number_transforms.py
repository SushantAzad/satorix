"""Numeric cleaning transforms for Indian financial data."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

from layer2_pipeline.core.context import ExecutionContext
from layer2_pipeline.transforms.base import BaseTransform, TransformError
from layer2_pipeline.transforms.registry import register

# Indian currency symbols and formatting
_CURRENCY_PATTERN = re.compile(r"[₹$€£¥,\s]")
_LAKH_CRORE_PATTERN = re.compile(
    r"([\d,]+\.?\d*)\s*(cr(?:ore)?|lakh|lac|k|m|b)?",
    re.IGNORECASE,
)

_MULTIPLIERS = {
    "crore": 1e7,
    "cr": 1e7,
    "lakh": 1e5,
    "lac": 1e5,
    "k": 1e3,
    "m": 1e6,
    "b": 1e9,
}


def _parse_indian_number(s: str) -> float | None:
    """Parse '1,23,456.78' or '5.2 Crore' → float rupees."""
    if not isinstance(s, str):
        return None
    s = _CURRENCY_PATTERN.sub("", s).strip()
    m = _LAKH_CRORE_PATTERN.fullmatch(s)
    if not m:
        return None
    num_str, suffix = m.group(1), (m.group(2) or "").lower()
    try:
        num = float(num_str.replace(",", ""))
    except ValueError:
        return None
    multiplier = _MULTIPLIERS.get(suffix, 1.0)
    return num * multiplier


class ParseIndianNumber(BaseTransform):
    """
    Convert Indian-formatted number strings to float.
    Handles: '1,23,456', '5.2 Crore', '₹10 Lakh', '1.5Cr'
    """

    transform_type = "parse_indian_number"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        cols = config.get("columns", [])
        df = df.copy()
        for col in cols:
            if col not in df.columns:
                context.warn(f"parse_indian_number: column {col!r} not found")
                continue
            df[col] = df[col].apply(
                lambda v: _parse_indian_number(str(v)) if pd.notna(v) else None
            )
        return df

    @classmethod
    def validate_config(cls, config: dict) -> list[str]:
        if not config.get("columns"):
            return ["parse_indian_number: 'columns' is required"]
        return []


class RemoveCurrencySymbol(BaseTransform):
    """Strip currency symbols and thousand-separators, leaving a clean numeric string."""

    transform_type = "remove_currency_symbol"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        cols = config.get("columns", [])
        df = df.copy()
        for col in cols:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace(r"[₹$€£¥,\s]", "", regex=True)
        return df


class ParseCroreToRupees(BaseTransform):
    """Convert crore-valued column to rupees (multiply by 1e7)."""

    transform_type = "parse_crore_to_rupees"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        cols = config.get("columns", [])
        df = df.copy()
        for col in cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce") * 1e7
        return df


class ClipOutliers(BaseTransform):
    """Clip numeric values to [lower, upper] percentile or absolute bounds."""

    transform_type = "clip_outliers"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        cols = config.get("columns", [])
        lower = config.get("lower")
        upper = config.get("upper")
        use_percentile = config.get("use_percentile", False)
        df = df.copy()
        for col in cols:
            if col not in df.columns:
                continue
            series = pd.to_numeric(df[col], errors="coerce")
            if use_percentile:
                lo = series.quantile(lower) if lower is not None else None
                hi = series.quantile(upper) if upper is not None else None
            else:
                lo, hi = lower, upper
            df[col] = series.clip(lower=lo, upper=hi)
        return df


class RoundDecimals(BaseTransform):
    """Round numeric columns to N decimal places."""

    transform_type = "round_decimals"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        cols = config.get("columns", [])
        decimals = config.get("decimals", 2)
        df = df.copy()
        for col in cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").round(decimals)
        return df


register(ParseIndianNumber())
register(RemoveCurrencySymbol())
register(ParseCroreToRupees())
register(ClipOutliers())
register(RoundDecimals())
