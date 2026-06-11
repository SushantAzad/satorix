"""Column type inference engine."""

import logging
import re
from typing import Optional
import pandas as pd

logger = logging.getLogger(__name__)


class TypeInferrer:
    """Infer the best data type for DataFrame columns."""

    def infer_types(self, df: pd.DataFrame) -> dict[str, str]:
        """Return {column_name: best_type} for all columns."""
        result = {}
        for col in df.columns:
            result[col] = self._infer_column_type(df[col])
        return result

    def _infer_column_type(self, series: pd.Series) -> str:
        if pd.api.types.is_numeric_dtype(series):
            if pd.api.types.is_integer_dtype(series):
                return "integer"
            return "float"
        if pd.api.types.is_datetime64_any_dtype(series):
            return "datetime"
        if pd.api.types.is_bool_dtype(series):
            return "boolean"

        sample = series.dropna().astype(str).head(500)
        if len(sample) == 0:
            return "unknown"

        # Check boolean
        bool_vals = {"true", "false", "yes", "no", "1", "0", "y", "n"}
        if sample.str.lower().isin(bool_vals).mean() > 0.9:
            return "boolean"

        # Check integer
        int_parsed = pd.to_numeric(sample, errors="coerce")
        if int_parsed.notna().mean() > 0.9:
            if (int_parsed == int_parsed.astype(int)).all():
                return "integer"
            return "float"

        # Check date
        date_parsed = pd.to_datetime(sample, errors="coerce", dayfirst=True)
        if date_parsed.notna().mean() > 0.8:
            return "datetime"

        # Check email
        if sample.str.match(r"^[^@]+@[^@]+\.[^@]+$").mean() > 0.8:
            return "email"

        # Check URL
        if sample.str.match(r"^https?://").mean() > 0.8:
            return "url"

        avg_len = sample.str.len().mean()
        if avg_len > 200:
            return "text"

        return "string"

    def apply_types(self, df: pd.DataFrame, type_map: dict[str, str]) -> pd.DataFrame:
        """Apply inferred types to DataFrame columns."""
        df = df.copy()
        for col, dtype in type_map.items():
            if col not in df.columns:
                continue
            try:
                if dtype == "integer":
                    df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
                elif dtype == "float":
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                elif dtype == "datetime":
                    df[col] = pd.to_datetime(df[col], errors="coerce", dayfirst=True)
                elif dtype == "boolean":
                    df[col] = df[col].astype(str).str.lower().map(
                        {"true": True, "false": False, "yes": True, "no": False, "1": True, "0": False}
                    )
            except Exception as e:
                logger.warning("Failed to convert column %s to %s: %s", col, dtype, e)
        return df
