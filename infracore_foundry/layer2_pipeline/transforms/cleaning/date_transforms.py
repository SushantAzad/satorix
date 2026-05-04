"""
Date/time cleaning transforms for Indian data sources.
Handles all 8 common Indian date formats plus financial year computation.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Optional

import pandas as pd

from layer2_pipeline.core.context import ExecutionContext
from layer2_pipeline.transforms.base import BaseTransform, TransformError
from layer2_pipeline.transforms.registry import register

# Indian date formats in descending specificity order
_INDIAN_DATE_FORMATS = [
    "%d-%m-%Y",        # 31-12-2023
    "%d/%m/%Y",        # 31/12/2023
    "%d.%m.%Y",        # 31.12.2023
    "%d-%b-%Y",        # 31-Dec-2023
    "%d %b %Y",        # 31 Dec 2023
    "%d %B %Y",        # 31 December 2023
    "%Y-%m-%d",        # 2023-12-31 (ISO — common in DB exports)
    "%d-%m-%y",        # 31-12-23
    "%d/%m/%y",        # 31/12/23
    "%d%m%Y",          # 31122023 (MCA21 compact)
    "%Y%m%d",          # 20231231 (SEBI compact)
]

# MCA21 uses DD/MM/YYYY or DDMMYYYY
_MCA21_COMPACT = re.compile(r"^(\d{2})(\d{2})(\d{4})$")


def _parse_single(value: str) -> Optional[pd.Timestamp]:
    """Try all Indian date formats and return the first successful parse."""
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()

    # Handle MCA21 compact: 31122023
    m = _MCA21_COMPACT.match(value)
    if m:
        value = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    for fmt in _INDIAN_DATE_FORMATS:
        try:
            return pd.Timestamp(value, tz=None)
        except Exception:
            pass
        try:
            return pd.Timestamp(pd.to_datetime(value, format=fmt))
        except Exception:
            pass

    # Last resort: pandas inference
    try:
        return pd.Timestamp(pd.to_datetime(value, dayfirst=True, infer_datetime_format=True))
    except Exception:
        return None


def _financial_year(dt: pd.Timestamp) -> Optional[str]:
    """Return 'FY2024-25' string for a date."""
    if pd.isna(dt):
        return None
    year = dt.year
    month = dt.month
    if month >= 4:
        return f"FY{year}-{str(year + 1)[2:]}"
    else:
        return f"FY{year - 1}-{str(year)[2:]}"


class ParseIndianDate(BaseTransform):
    """
    Parse Indian date strings across all 8+ common formats.
    Output column dtype is datetime64[ns].
    """

    transform_type = "parse_indian_date"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        cols = config.get("columns", [])
        output_format = config.get("output_format")  # e.g. "%Y-%m-%d" for string output
        df = df.copy()

        for col in cols:
            if col not in df.columns:
                context.warn(f"parse_indian_date: column {col!r} not found")
                continue

            parsed = df[col].apply(lambda v: _parse_single(str(v)) if pd.notna(v) else pd.NaT)
            failed = parsed.isna() & df[col].notna()
            fail_count = failed.sum()
            if fail_count > 0:
                context.warn(f"parse_indian_date: {fail_count} values in {col!r} could not be parsed")
                for idx in df[failed].index[:5]:
                    context.add_failed_record(
                        step_id=step_id,
                        error_type="transform",
                        error_subtype="date_parse_failure",
                        error_message=f"Cannot parse date: {df.at[idx, col]!r}",
                        severity="warning",
                        original_record={col: df.at[idx, col]},
                    )

            if output_format:
                df[col] = parsed.dt.strftime(output_format)
            else:
                df[col] = parsed

        return df

    @classmethod
    def validate_config(cls, config: dict) -> list[str]:
        if not config.get("columns"):
            return ["parse_indian_date: 'columns' is required"]
        return []


class ComputeFinancialYear(BaseTransform):
    """
    Add a financial year string column (e.g. 'FY2024-25') derived from a date column.
    Indian financial year: April 1 – March 31.
    """

    transform_type = "compute_financial_year"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        source_col = config["source_column"]
        target_col = config.get("target_column", "financial_year")
        if source_col not in df.columns:
            raise TransformError(f"compute_financial_year: column {source_col!r} not found")
        df = df.copy()
        series = pd.to_datetime(df[source_col], errors="coerce")
        df[target_col] = series.apply(_financial_year)
        return df

    @classmethod
    def validate_config(cls, config: dict) -> list[str]:
        if not config.get("source_column"):
            return ["compute_financial_year: 'source_column' is required"]
        return []


class ComputeAge(BaseTransform):
    """Compute age in years from a date column (as of today)."""

    transform_type = "compute_age"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        source_col = config["source_column"]
        target_col = config.get("target_column", "age_years")
        if source_col not in df.columns:
            raise TransformError(f"compute_age: column {source_col!r} not found")
        df = df.copy()
        today = pd.Timestamp.now()
        dob = pd.to_datetime(df[source_col], errors="coerce")
        df[target_col] = ((today - dob).dt.days / 365.25).round(0).astype("Int64")
        return df


class DateDifference(BaseTransform):
    """Compute signed difference in days between two date columns."""

    transform_type = "date_difference"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        start_col = config["start_column"]
        end_col = config["end_column"]
        target_col = config.get("target_column", "days_diff")
        unit = config.get("unit", "days")  # days | months | years
        for col in (start_col, end_col):
            if col not in df.columns:
                raise TransformError(f"date_difference: column {col!r} not found")
        df = df.copy()
        start = pd.to_datetime(df[start_col], errors="coerce")
        end = pd.to_datetime(df[end_col], errors="coerce")
        diff_days = (end - start).dt.days
        if unit == "days":
            df[target_col] = diff_days
        elif unit == "months":
            df[target_col] = (diff_days / 30.44).round(1)
        elif unit == "years":
            df[target_col] = (diff_days / 365.25).round(2)
        return df


_PARSE_DATE = ParseIndianDate()
register(_PARSE_DATE)
register(ComputeFinancialYear())
register(ComputeAge())
register(DateDifference())


def DATE_NORMALIZE_TRANSFORM(df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
    col = config.get("column")
    on_fail = config.get("on_fail", "null")
    cfg = {"columns": [col]} if col else config
    result = _PARSE_DATE.apply(df, cfg, context, step_id)
    if on_fail == "null" and col and col in result.columns:
        pass  # NaT already fills unparseable values
    return result
