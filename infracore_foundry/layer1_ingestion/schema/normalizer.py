"""Schema normalization: column name cleaning, type standardization."""

import re
import logging
import pandas as pd
from unidecode import unidecode

logger = logging.getLogger(__name__)


class SchemaNormalizer:
    """Normalize DataFrame schemas for consistent storage."""

    COMPANY_SUFFIXES = [
        "Private Limited", "Pvt. Ltd.", "Pvt Ltd", "Private Ltd",
        "Limited", "Ltd.", "Ltd", "LLP",
    ]

    def normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize column names: lowercase, underscored, ASCII."""
        rename_map = {}
        for col in df.columns:
            clean = str(col).strip()
            clean = unidecode(clean)
            clean = re.sub(r"[^\w\s]", "", clean)
            clean = re.sub(r"\s+", "_", clean)
            clean = clean.lower().strip("_")
            if not clean:
                clean = f"column_{list(df.columns).index(col)}"
            rename_map[col] = clean
        # Deduplicate
        seen = {}
        for orig, norm in rename_map.items():
            if norm in seen.values():
                count = sum(1 for v in seen.values() if v.startswith(norm))
                rename_map[orig] = f"{norm}_{count}"
            seen[orig] = rename_map[orig]
        return df.rename(columns=rename_map)

    def normalize_company_name(self, name: str) -> tuple[str, str]:
        """Return (normalized_name, display_name). Strip suffixes for comparison."""
        display_name = name.strip()
        normalized = display_name
        for suffix in sorted(self.COMPANY_SUFFIXES, key=len, reverse=True):
            pattern = re.compile(re.escape(suffix), re.IGNORECASE)
            normalized = pattern.sub("", normalized).strip().rstrip(",").strip()
        normalized = re.sub(r"\s+", " ", normalized).upper()
        return normalized, display_name

    def normalize_dates(self, df: pd.DataFrame) -> pd.DataFrame:
        """Convert all date columns to ISO 8601 format."""
        df = df.copy()
        for col in df.columns:
            if df[col].dtype == "object":
                parsed = pd.to_datetime(df[col], errors="coerce", dayfirst=True)
                if parsed.notna().mean() > 0.7:
                    df[col] = parsed.dt.strftime("%Y-%m-%d")
        return df

    def normalize_currency(self, df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
        """Ensure currency columns are in rupees (not lakhs/crores)."""
        df = df.copy()
        for col in columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col].astype(str).str.replace(",", ""), errors="coerce")
        return df
