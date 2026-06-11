"""Data quality profiling: statistical distribution analysis."""

import pandas as pd
from typing import Any


def compute_distribution(series: pd.Series) -> dict:
    """Compute distribution statistics for a column."""
    result: dict[str, Any] = {}
    non_null = series.dropna()
    if len(non_null) == 0:
        return {"min": None, "max": None, "mean": None, "top_values": []}

    if pd.api.types.is_numeric_dtype(non_null):
        result["min"] = float(non_null.min())
        result["max"] = float(non_null.max())
        result["mean"] = round(float(non_null.mean()), 4)
        result["median"] = round(float(non_null.median()), 4)
        result["std"] = round(float(non_null.std()), 4) if len(non_null) > 1 else 0.0
        result["q25"] = float(non_null.quantile(0.25))
        result["q75"] = float(non_null.quantile(0.75))
    else:
        result["min"] = str(non_null.min()) if len(non_null) > 0 else None
        result["max"] = str(non_null.max()) if len(non_null) > 0 else None
        result["mean"] = None

    # Top values
    value_counts = non_null.value_counts().head(10)
    result["top_values"] = [(str(v), int(c)) for v, c in value_counts.items()]
    return result


def compute_dataframe_distribution(df: pd.DataFrame) -> dict[str, dict]:
    return {str(col): compute_distribution(df[col]) for col in df.columns}
