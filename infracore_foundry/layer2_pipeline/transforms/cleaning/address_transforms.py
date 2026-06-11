"""
Indian address cleaning transforms.
Handles PIN codes, state normalization, city normalization, address parsing.
"""

from __future__ import annotations

import re
from typing import Any, Optional

import pandas as pd

from layer2_pipeline.core.context import ExecutionContext
from layer2_pipeline.transforms.base import BaseTransform, TransformError
from layer2_pipeline.transforms.registry import register

_PIN_PATTERN = re.compile(r"\b([1-9][0-9]{5})\b")

# Canonical state names keyed by known variants (lowercase)
_STATE_ALIASES: dict[str, str] = {
    "andhra pradesh": "Andhra Pradesh",
    "ap": "Andhra Pradesh",
    "arunachal pradesh": "Arunachal Pradesh",
    "assam": "Assam",
    "bihar": "Bihar",
    "chhattisgarh": "Chhattisgarh",
    "chattisgarh": "Chhattisgarh",
    "goa": "Goa",
    "gujarat": "Gujarat",
    "guj": "Gujarat",
    "haryana": "Haryana",
    "himachal pradesh": "Himachal Pradesh",
    "hp": "Himachal Pradesh",
    "jharkhand": "Jharkhand",
    "karnataka": "Karnataka",
    "ktk": "Karnataka",
    "kerala": "Kerala",
    "madhya pradesh": "Madhya Pradesh",
    "mp": "Madhya Pradesh",
    "maharashtra": "Maharashtra",
    "mh": "Maharashtra",
    "manipur": "Manipur",
    "meghalaya": "Meghalaya",
    "mizoram": "Mizoram",
    "nagaland": "Nagaland",
    "odisha": "Odisha",
    "orissa": "Odisha",
    "punjab": "Punjab",
    "rajasthan": "Rajasthan",
    "raj": "Rajasthan",
    "sikkim": "Sikkim",
    "tamil nadu": "Tamil Nadu",
    "tn": "Tamil Nadu",
    "tamilnadu": "Tamil Nadu",
    "telangana": "Telangana",
    "ts": "Telangana",
    "tripura": "Tripura",
    "uttar pradesh": "Uttar Pradesh",
    "up": "Uttar Pradesh",
    "uttarakhand": "Uttarakhand",
    "west bengal": "West Bengal",
    "wb": "West Bengal",
    # UTs
    "delhi": "Delhi",
    "nct": "Delhi",
    "new delhi": "Delhi",
    "chandigarh": "Chandigarh",
    "jammu and kashmir": "Jammu & Kashmir",
    "j&k": "Jammu & Kashmir",
    "ladakh": "Ladakh",
    "puducherry": "Puducherry",
    "pondicherry": "Puducherry",
    "andaman and nicobar": "Andaman & Nicobar Islands",
    "lakshadweep": "Lakshadweep",
    "dadra and nagar haveli": "Dadra & Nagar Haveli and Daman & Diu",
    "daman and diu": "Dadra & Nagar Haveli and Daman & Diu",
}

# Common city name normalizations
_CITY_ALIASES: dict[str, str] = {
    "bombay": "Mumbai",
    "calcutta": "Kolkata",
    "madras": "Chennai",
    "bangalore": "Bengaluru",
    "bengaluru": "Bengaluru",
    "hyderabad": "Hyderabad",
    "new delhi": "New Delhi",
    "delhi": "Delhi",
    "pune": "Pune",
    "poona": "Pune",
    "ahmedabad": "Ahmedabad",
    "amdavad": "Ahmedabad",
    "surat": "Surat",
    "jaipur": "Jaipur",
    "lucknow": "Lucknow",
    "kanpur": "Kanpur",
    "nagpur": "Nagpur",
    "visakhapatnam": "Visakhapatnam",
    "vizag": "Visakhapatnam",
    "bhopal": "Bhopal",
    "patna": "Patna",
    "vadodara": "Vadodara",
    "baroda": "Vadodara",
    "ludhiana": "Ludhiana",
    "agra": "Agra",
    "nashik": "Nashik",
    "nasik": "Nashik",
    "faridabad": "Faridabad",
    "meerut": "Meerut",
    "rajkot": "Rajkot",
    "varanasi": "Varanasi",
    "banaras": "Varanasi",
    "srinagar": "Srinagar",
    "aurangabad": "Aurangabad",
    "dhanbad": "Dhanbad",
    "amritsar": "Amritsar",
    "navi mumbai": "Navi Mumbai",
    "thane": "Thane",
    "coimbatore": "Coimbatore",
    "indore": "Indore",
    "kochi": "Kochi",
    "cochin": "Kochi",
    "guwahati": "Guwahati",
}


class ExtractPINCode(BaseTransform):
    """Extract 6-digit Indian PIN code from an address string into a new column."""

    transform_type = "extract_pin_code"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        source_col = config["source_column"]
        target_col = config.get("target_column", "pin_code")
        if source_col not in df.columns:
            raise TransformError(f"extract_pin_code: column {source_col!r} not found")
        df = df.copy()

        def _extract(val: Any) -> Optional[str]:
            if not isinstance(val, str):
                return None
            m = _PIN_PATTERN.search(val)
            return m.group(1) if m else None

        df[target_col] = df[source_col].apply(_extract)
        return df


class NormalizeState(BaseTransform):
    """Normalize Indian state names to canonical form."""

    transform_type = "normalize_state"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        col = config["column"]
        if col not in df.columns:
            raise TransformError(f"normalize_state: column {col!r} not found")
        df = df.copy()
        df[col] = df[col].apply(
            lambda v: _STATE_ALIASES.get(str(v).strip().lower(), str(v).strip()) if pd.notna(v) else v
        )
        return df


class NormalizeCity(BaseTransform):
    """Normalize Indian city names to canonical form (e.g. Bombay → Mumbai)."""

    transform_type = "normalize_city"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        col = config["column"]
        if col not in df.columns:
            raise TransformError(f"normalize_city: column {col!r} not found")
        df = df.copy()
        df[col] = df[col].apply(
            lambda v: _CITY_ALIASES.get(str(v).strip().lower(), str(v).strip().title()) if pd.notna(v) else v
        )
        return df


class SplitAddressComponents(BaseTransform):
    """
    Attempt to split a single address string into components:
    street, area, city, state, pin_code.
    Heuristic: PIN at end, state before PIN, rest is street/city.
    """

    transform_type = "split_address_components"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        source_col = config["source_column"]
        prefix = config.get("prefix", "addr_")
        if source_col not in df.columns:
            raise TransformError(f"split_address_components: column {source_col!r} not found")
        df = df.copy()

        def _split(val: Any) -> dict:
            result = {"pin_code": None, "state": None, "city": None, "street": None}
            if not isinstance(val, str):
                return result
            # Extract PIN
            m = _PIN_PATTERN.search(val)
            if m:
                result["pin_code"] = m.group(1)
                val = val[:m.start()].strip().rstrip(",")
            # Split by comma — last part often state, second-to-last city
            parts = [p.strip() for p in val.split(",") if p.strip()]
            if len(parts) >= 2:
                state_candidate = parts[-1].strip().lower()
                result["state"] = _STATE_ALIASES.get(state_candidate, parts[-1].strip())
                city_candidate = parts[-2].strip().lower()
                result["city"] = _CITY_ALIASES.get(city_candidate, parts[-2].strip().title())
                result["street"] = ", ".join(parts[:-2])
            elif parts:
                result["street"] = parts[0]
            return result

        parsed = df[source_col].apply(_split)
        for key in ("pin_code", "state", "city", "street"):
            df[f"{prefix}{key}"] = parsed.apply(lambda d: d[key])

        return df


register(ExtractPINCode())
register(NormalizeState())
register(NormalizeCity())
register(SplitAddressComponents())
