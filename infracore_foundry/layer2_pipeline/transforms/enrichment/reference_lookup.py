"""
Reference data enrichment transforms.
Bundles curated lookup tables for PIN codes, IFSC, states, NIC industry codes.
These are embedded rather than queried from an external source to avoid
network dependency at transform time.
"""

from __future__ import annotations

import csv
import io
import logging
from functools import lru_cache
from typing import Any, Optional

import pandas as pd

from layer2_pipeline.core.context import ExecutionContext
from layer2_pipeline.transforms.base import BaseTransform, TransformError
from layer2_pipeline.transforms.registry import register

logger = logging.getLogger(__name__)

# ── Embedded PIN Code → State/District lookup (sample — full table loaded from CSV) ──
# In production, mount the full India PIN Code CSV at /data/reference/pin_codes.csv
_PIN_SAMPLE: dict[str, dict] = {
    "400001": {"state": "Maharashtra", "district": "Mumbai", "city": "Mumbai"},
    "110001": {"state": "Delhi", "district": "New Delhi", "city": "New Delhi"},
    "560001": {"state": "Karnataka", "district": "Bengaluru Urban", "city": "Bengaluru"},
    "600001": {"state": "Tamil Nadu", "district": "Chennai", "city": "Chennai"},
    "500001": {"state": "Telangana", "district": "Hyderabad", "city": "Hyderabad"},
    "700001": {"state": "West Bengal", "district": "Kolkata", "city": "Kolkata"},
    "380001": {"state": "Gujarat", "district": "Ahmedabad", "city": "Ahmedabad"},
    "302001": {"state": "Rajasthan", "district": "Jaipur", "city": "Jaipur"},
    "226001": {"state": "Uttar Pradesh", "district": "Lucknow", "city": "Lucknow"},
    "411001": {"state": "Maharashtra", "district": "Pune", "city": "Pune"},
}

# NIC 2008 industry code → description (top-level sections only)
_NIC_CODES: dict[str, str] = {
    "A": "Agriculture, Forestry and Fishing",
    "B": "Mining and Quarrying",
    "C": "Manufacturing",
    "D": "Electricity, Gas, Steam and Air Conditioning Supply",
    "E": "Water Supply; Sewerage, Waste Management",
    "F": "Construction",
    "G": "Wholesale and Retail Trade",
    "H": "Transportation and Storage",
    "I": "Accommodation and Food Service Activities",
    "J": "Information and Communication",
    "K": "Financial and Insurance Activities",
    "L": "Real Estate Activities",
    "M": "Professional, Scientific and Technical Activities",
    "N": "Administrative and Support Service Activities",
    "O": "Public Administration and Defence",
    "P": "Education",
    "Q": "Human Health and Social Work Activities",
    "R": "Arts, Entertainment and Recreation",
    "S": "Other Service Activities",
    "T": "Activities of Households as Employers",
    "U": "Activities of Extraterritorial Organisations",
}

_PIN_REFERENCE_PATH = "/data/reference/pin_codes.csv"
_IFSC_REFERENCE_PATH = "/data/reference/ifsc_codes.csv"


@lru_cache(maxsize=1)
def _load_pin_reference() -> dict[str, dict]:
    """Load PIN code reference from CSV if available; fall back to sample."""
    try:
        df = pd.read_csv(_PIN_REFERENCE_PATH, dtype=str)
        return {
            str(row["pincode"]).zfill(6): {
                "state": row.get("state_name", ""),
                "district": row.get("district", ""),
                "city": row.get("office_name", ""),
            }
            for _, row in df.iterrows()
        }
    except FileNotFoundError:
        logger.debug("PIN code reference CSV not found at %s; using sample data", _PIN_REFERENCE_PATH)
        return _PIN_SAMPLE


@lru_cache(maxsize=1)
def _load_ifsc_reference() -> dict[str, dict]:
    """Load IFSC reference from CSV if available."""
    try:
        df = pd.read_csv(_IFSC_REFERENCE_PATH, dtype=str)
        return {
            str(row["IFSC"]): {
                "bank": row.get("BANK", ""),
                "branch": row.get("BRANCH", ""),
                "city": row.get("CITY", ""),
                "state": row.get("STATE", ""),
            }
            for _, row in df.iterrows()
        }
    except FileNotFoundError:
        logger.debug("IFSC reference CSV not found at %s; returning empty", _IFSC_REFERENCE_PATH)
        return {}


class PINCodeLookup(BaseTransform):
    """
    Enrich PIN codes with state/district/city from the India PIN Code database.
    config: pin_column (str), add_columns (list: state|district|city)
    """

    transform_type = "pin_code_lookup"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        pin_col = config["pin_column"]
        add_cols = config.get("add_columns", ["state", "district", "city"])
        if pin_col not in df.columns:
            raise TransformError(f"pin_code_lookup: column {pin_col!r} not found")

        ref = _load_pin_reference()
        df = df.copy()

        for target_col in add_cols:
            df[target_col] = df[pin_col].apply(
                lambda v: ref.get(str(v).zfill(6), {}).get(target_col) if pd.notna(v) else None
            )

        matched = df[add_cols[0]].notna().sum() if add_cols else 0
        context.warn(
            f"pin_code_lookup: matched {matched}/{len(df)} PINs"
        ) if matched < len(df) else None

        return df


class IFSCLookup(BaseTransform):
    """
    Enrich IFSC codes with bank/branch/city/state details.
    config: ifsc_column (str), add_columns (list: bank|branch|city|state)
    """

    transform_type = "ifsc_lookup"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        ifsc_col = config["ifsc_column"]
        add_cols = config.get("add_columns", ["bank", "branch", "city", "state"])
        if ifsc_col not in df.columns:
            raise TransformError(f"ifsc_lookup: column {ifsc_col!r} not found")

        ref = _load_ifsc_reference()
        df = df.copy()

        for target_col in add_cols:
            df[target_col] = df[ifsc_col].apply(
                lambda v: ref.get(str(v).upper().strip(), {}).get(target_col) if pd.notna(v) else None
            )
        return df


class StateLookup(BaseTransform):
    """
    Enrich state names with additional metadata: state_code, zone, capital.
    config: state_column (str)
    """

    _STATE_META = {
        "Andhra Pradesh": {"state_code": "AP", "zone": "South", "capital": "Amaravati"},
        "Arunachal Pradesh": {"state_code": "AR", "zone": "Northeast", "capital": "Itanagar"},
        "Assam": {"state_code": "AS", "zone": "Northeast", "capital": "Dispur"},
        "Bihar": {"state_code": "BR", "zone": "East", "capital": "Patna"},
        "Chhattisgarh": {"state_code": "CG", "zone": "Central", "capital": "Raipur"},
        "Goa": {"state_code": "GA", "zone": "West", "capital": "Panaji"},
        "Gujarat": {"state_code": "GJ", "zone": "West", "capital": "Gandhinagar"},
        "Haryana": {"state_code": "HR", "zone": "North", "capital": "Chandigarh"},
        "Himachal Pradesh": {"state_code": "HP", "zone": "North", "capital": "Shimla"},
        "Jharkhand": {"state_code": "JH", "zone": "East", "capital": "Ranchi"},
        "Karnataka": {"state_code": "KA", "zone": "South", "capital": "Bengaluru"},
        "Kerala": {"state_code": "KL", "zone": "South", "capital": "Thiruvananthapuram"},
        "Madhya Pradesh": {"state_code": "MP", "zone": "Central", "capital": "Bhopal"},
        "Maharashtra": {"state_code": "MH", "zone": "West", "capital": "Mumbai"},
        "Manipur": {"state_code": "MN", "zone": "Northeast", "capital": "Imphal"},
        "Meghalaya": {"state_code": "ML", "zone": "Northeast", "capital": "Shillong"},
        "Mizoram": {"state_code": "MZ", "zone": "Northeast", "capital": "Aizawl"},
        "Nagaland": {"state_code": "NL", "zone": "Northeast", "capital": "Kohima"},
        "Odisha": {"state_code": "OD", "zone": "East", "capital": "Bhubaneswar"},
        "Punjab": {"state_code": "PB", "zone": "North", "capital": "Chandigarh"},
        "Rajasthan": {"state_code": "RJ", "zone": "North", "capital": "Jaipur"},
        "Sikkim": {"state_code": "SK", "zone": "Northeast", "capital": "Gangtok"},
        "Tamil Nadu": {"state_code": "TN", "zone": "South", "capital": "Chennai"},
        "Telangana": {"state_code": "TS", "zone": "South", "capital": "Hyderabad"},
        "Tripura": {"state_code": "TR", "zone": "Northeast", "capital": "Agartala"},
        "Uttar Pradesh": {"state_code": "UP", "zone": "North", "capital": "Lucknow"},
        "Uttarakhand": {"state_code": "UK", "zone": "North", "capital": "Dehradun"},
        "West Bengal": {"state_code": "WB", "zone": "East", "capital": "Kolkata"},
        "Delhi": {"state_code": "DL", "zone": "North", "capital": "New Delhi"},
    }

    transform_type = "state_lookup"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        state_col = config["state_column"]
        add_cols = config.get("add_columns", ["state_code", "zone"])
        if state_col not in df.columns:
            raise TransformError(f"state_lookup: column {state_col!r} not found")
        df = df.copy()
        for target_col in add_cols:
            df[target_col] = df[state_col].apply(
                lambda v: self._STATE_META.get(str(v), {}).get(target_col) if pd.notna(v) else None
            )
        return df


class NICCodeLookup(BaseTransform):
    """
    Map NIC (National Industrial Classification) section letter to description.
    config: nic_column (str), target_column (str)
    """

    transform_type = "nic_code_lookup"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        nic_col = config["nic_column"]
        target_col = config.get("target_column", "industry_description")
        if nic_col not in df.columns:
            raise TransformError(f"nic_code_lookup: column {nic_col!r} not found")
        df = df.copy()
        df[target_col] = df[nic_col].apply(
            lambda v: _NIC_CODES.get(str(v).strip().upper()[:1]) if pd.notna(v) else None
        )
        return df


register(PINCodeLookup())
register(IFSCLookup())
register(StateLookup())
register(NICCodeLookup())
