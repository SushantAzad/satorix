"""Data quality profiling: completeness analysis."""

import pandas as pd

NULL_REPRESENTATIONS = ["", "NULL", "null", "None", "none", "N/A", "n/a", "NA", "na", "#N/A", "-", "--", ".", "NaN"]


def compute_completeness(series: pd.Series) -> dict:
    """Compute completeness metrics for a single column."""
    total = len(series)
    if total == 0:
        return {"score": 0.0, "null_count": 0, "null_representation": None}

    null_count = series.isnull().sum()
    # Also count string null representations
    str_nulls = 0
    null_repr = None
    if series.dtype == "object":
        for rep in NULL_REPRESENTATIONS:
            matches = (series.astype(str).str.strip() == rep).sum()
            if matches > 0:
                str_nulls += matches
                if null_repr is None:
                    null_repr = rep

    total_missing = null_count + str_nulls
    score = 1.0 - (total_missing / total) if total > 0 else 0.0
    return {"score": round(score, 4), "null_count": int(total_missing), "null_representation": null_repr}


def compute_dataframe_completeness(df: pd.DataFrame) -> dict[str, dict]:
    """Compute completeness for all columns."""
    return {str(col): compute_completeness(df[col]) for col in df.columns}
