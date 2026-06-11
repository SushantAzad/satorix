"""Data quality profiling: uniqueness scoring."""

import pandas as pd


def compute_uniqueness(series: pd.Series) -> dict:
    """Compute uniqueness metrics for a column."""
    total = len(series.dropna())
    if total == 0:
        return {"score": 0.0, "unique_count": 0, "duplicate_count": 0}
    unique_count = series.nunique()
    duplicate_count = total - unique_count
    score = unique_count / total if total > 0 else 0.0
    return {"score": round(score, 4), "unique_count": int(unique_count), "duplicate_count": int(duplicate_count)}


def find_duplicate_rows(df: pd.DataFrame, subset: list[str] = None) -> pd.DataFrame:
    """Find and return duplicate rows."""
    duplicates = df[df.duplicated(subset=subset, keep=False)]
    return duplicates.sort_values(by=subset or list(df.columns)[:3])


def compute_dataframe_uniqueness(df: pd.DataFrame) -> dict[str, dict]:
    return {str(col): compute_uniqueness(df[col]) for col in df.columns}
