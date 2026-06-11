"""Schema detection from DataFrames."""

import logging
from typing import Any
import pandas as pd

logger = logging.getLogger(__name__)


class SchemaDetector:
    """Auto-detect schema from a DataFrame."""

    def detect(self, df: pd.DataFrame) -> dict:
        """Return a schema dict with column info."""
        schema = {"columns": [], "total_columns": len(df.columns), "total_rows": len(df)}
        for col in df.columns:
            col_info = {
                "name": str(col),
                "pandas_dtype": str(df[col].dtype),
                "inferred_type": self._infer_semantic_type(df[col]),
                "nullable": bool(df[col].isnull().any()),
                "null_count": int(df[col].isnull().sum()),
                "unique_count": int(df[col].nunique()),
                "sample_values": df[col].dropna().head(5).tolist(),
            }
            schema["columns"].append(col_info)
        try:
            from layer1_ingestion.schema.indian_identifiers import detect_identifier_columns
            schema["indian_identifiers"] = detect_identifier_columns(df)
        except ImportError:
            schema["indian_identifiers"] = {}
        return schema

    def _infer_semantic_type(self, series: pd.Series) -> str:
        if pd.api.types.is_datetime64_any_dtype(series):
            return "datetime"
        if pd.api.types.is_numeric_dtype(series):
            if pd.api.types.is_integer_dtype(series):
                return "integer"
            return "decimal"
        if pd.api.types.is_bool_dtype(series):
            return "boolean"
        sample = series.dropna().head(100).astype(str)
        if len(sample) == 0:
            return "unknown"
        date_parseable = pd.to_datetime(sample, errors="coerce").notna().mean()
        if date_parseable > 0.8:
            return "datetime"
        numeric_parseable = pd.to_numeric(sample, errors="coerce").notna().mean()
        if numeric_parseable > 0.8:
            return "numeric_string"
        avg_len = sample.str.len().mean()
        if avg_len > 200:
            return "text"
        return "string"
