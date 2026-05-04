"""
Indian-specific identifier validators and normalizers.
CIN, DIN, GSTIN, PAN, IFSC, PIN Code, Indian Mobile Number.
"""

import re
import logging
from typing import Optional
import pandas as pd

logger = logging.getLogger(__name__)

# Regex patterns
CIN_PATTERN = re.compile(r"^[UL]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}$")
DIN_PATTERN = re.compile(r"^\d{8}$")
GSTIN_PATTERN = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
PAN_PATTERN = re.compile(r"^[A-Z]{5}\d{4}[A-Z]$")
IFSC_PATTERN = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
PIN_PATTERN = re.compile(r"^[1-9]\d{5}$")
MOBILE_PATTERN = re.compile(r"^[6-9]\d{9}$")

STATE_CODES = {
    "01": "Jammu & Kashmir", "02": "Himachal Pradesh", "03": "Punjab",
    "04": "Chandigarh", "05": "Uttarakhand", "06": "Haryana",
    "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh",
    "10": "Bihar", "11": "Sikkim", "12": "Arunachal Pradesh",
    "13": "Nagaland", "14": "Manipur", "15": "Mizoram",
    "16": "Tripura", "17": "Meghalaya", "18": "Assam",
    "19": "West Bengal", "20": "Jharkhand", "21": "Odisha",
    "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat",
    "26": "Dadra & Nagar Haveli and Daman & Diu", "27": "Maharashtra",
    "28": "Andhra Pradesh", "29": "Karnataka", "30": "Goa",
    "31": "Lakshadweep", "32": "Kerala", "33": "Tamil Nadu",
    "34": "Puducherry", "35": "Andaman & Nicobar", "36": "Telangana",
    "37": "Andhra Pradesh (New)", "38": "Ladakh",
}

PAN_ENTITY_TYPES = {
    "A": "Association of Persons", "B": "Body of Individuals",
    "C": "Company", "F": "Firm/LLP", "G": "Government",
    "H": "Hindu Undivided Family", "J": "Artificial Juridical Person",
    "L": "Local Authority", "P": "Individual", "T": "Trust",
}


class CINValidator:
    @staticmethod
    def is_valid(value: str) -> bool:
        return bool(CIN_PATTERN.match(value.strip().upper()))

    @staticmethod
    def normalize(value: str) -> str:
        return value.strip().upper().replace(" ", "")

    @staticmethod
    def extract_components(value: str) -> dict:
        v = value.strip().upper()
        if not CIN_PATTERN.match(v):
            return {}
        return {
            "listing_status": "Listed" if v[0] == "L" else "Unlisted",
            "nic_code": v[1:6],
            "state_code": v[6:8],
            "year": v[8:12],
            "company_type": v[12:15],
            "sequential_number": v[15:21],
        }


class DINValidator:
    @staticmethod
    def is_valid(value: str) -> bool:
        cleaned = str(value).strip().zfill(8)
        return bool(DIN_PATTERN.match(cleaned))

    @staticmethod
    def normalize(value: str) -> str:
        return str(value).strip().zfill(8)

    @staticmethod
    def extract_components(value: str) -> dict:
        return {"din": DINValidator.normalize(value)}


class GSTINValidator:
    @staticmethod
    def is_valid(value: str) -> bool:
        v = value.strip().upper()
        if not GSTIN_PATTERN.match(v):
            return False
        return GSTINValidator._verify_checksum(v)

    @staticmethod
    def normalize(value: str) -> str:
        return value.strip().upper().replace(" ", "")

    @staticmethod
    def extract_components(value: str) -> dict:
        v = value.strip().upper()
        if not GSTIN_PATTERN.match(v):
            return {}
        state_code = v[:2]
        return {
            "state_code": state_code,
            "state_name": STATE_CODES.get(state_code, "Unknown"),
            "pan": v[2:12],
            "entity_number": v[12],
            "checksum": v[14],
        }

    @staticmethod
    def _verify_checksum(gstin: str) -> bool:
        """Verify GSTIN checksum using modified Luhn algorithm."""
        chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        total = 0
        for i, c in enumerate(gstin[:14]):
            idx = chars.index(c)
            if i % 2 != 0:
                idx *= 2
            total += idx // 36 + idx % 36
        checksum_idx = (36 - (total % 36)) % 36
        expected = chars[checksum_idx]
        return gstin[14] == expected


class PANValidator:
    @staticmethod
    def is_valid(value: str) -> bool:
        return bool(PAN_PATTERN.match(value.strip().upper()))

    @staticmethod
    def normalize(value: str) -> str:
        return value.strip().upper()

    @staticmethod
    def extract_components(value: str) -> dict:
        v = value.strip().upper()
        if not PAN_PATTERN.match(v):
            return {}
        entity_char = v[3]
        return {
            "entity_type_code": entity_char,
            "entity_type": PAN_ENTITY_TYPES.get(entity_char, "Unknown"),
            "name_initial": v[4],
        }


class IFSCValidator:
    @staticmethod
    def is_valid(value: str) -> bool:
        return bool(IFSC_PATTERN.match(value.strip().upper()))

    @staticmethod
    def normalize(value: str) -> str:
        return value.strip().upper()

    @staticmethod
    def extract_components(value: str) -> dict:
        v = value.strip().upper()
        if not IFSC_PATTERN.match(v):
            return {}
        return {
            "bank_code": v[:4],
            "reserved_zero": v[4],
            "branch_code": v[5:],
        }


class PINCodeValidator:
    @staticmethod
    def is_valid(value: str) -> bool:
        v = str(value).strip()
        if not PIN_PATTERN.match(v):
            return False
        return int(v[0]) in range(1, 9)

    @staticmethod
    def normalize(value: str) -> str:
        return str(value).strip().zfill(6)

    @staticmethod
    def extract_components(value: str) -> dict:
        v = str(value).strip()
        if not PIN_PATTERN.match(v):
            return {}
        zones = {
            "1": "Delhi, Haryana, Punjab, HP, J&K, Chandigarh",
            "2": "UP, Uttarakhand",
            "3": "Gujarat, Rajasthan, Daman & Diu, Dadra",
            "4": "Maharashtra, Goa, Chhattisgarh, MP",
            "5": "AP, Karnataka, Telangana",
            "6": "Tamil Nadu, Kerala, Puducherry, Lakshadweep",
            "7": "West Bengal, Odisha, Arunachal, Nagaland, Manipur, Mizoram, Tripura, Meghalaya, Assam, Andaman",
            "8": "Bihar, Jharkhand",
        }
        return {"postal_zone": v[0], "zone_description": zones.get(v[0], "Unknown")}


class MobileValidator:
    @staticmethod
    def is_valid(value: str) -> bool:
        cleaned = re.sub(r"[\s\-+]", "", str(value))
        if cleaned.startswith("91"):
            cleaned = cleaned[2:]
        if cleaned.startswith("0"):
            cleaned = cleaned[1:]
        return bool(MOBILE_PATTERN.match(cleaned))

    @staticmethod
    def normalize(value: str) -> str:
        cleaned = re.sub(r"[\s\-+]", "", str(value))
        if cleaned.startswith("91"):
            cleaned = cleaned[2:]
        if cleaned.startswith("0"):
            cleaned = cleaned[1:]
        return cleaned if MOBILE_PATTERN.match(cleaned) else str(value)

    @staticmethod
    def extract_components(value: str) -> dict:
        return {"mobile": MobileValidator.normalize(value)}


VALIDATORS = {
    "cin": CINValidator,
    "din": DINValidator,
    "gstin": GSTINValidator,
    "pan": PANValidator,
    "ifsc": IFSCValidator,
    "pin_code": PINCodeValidator,
    "mobile": MobileValidator,
}


def detect_identifier_columns(df: pd.DataFrame) -> dict[str, str]:
    """
    Scan every column in a DataFrame and return which Indian identifier type
    it contains based on value pattern analysis.
    Returns: {column_name: identifier_type}
    """
    result = {}
    for col in df.columns:
        if df[col].dtype != "object":
            continue
        sample = df[col].dropna().head(200).astype(str)
        if len(sample) < 5:
            continue

        best_type = None
        best_score = 0.0

        for id_type, validator in VALIDATORS.items():
            valid_count = sum(1 for v in sample if validator.is_valid(v))
            score = valid_count / len(sample)
            if score > 0.5 and score > best_score:
                best_type = id_type
                best_score = score

        if best_type:
            result[col] = best_type
            logger.debug("Column '%s' detected as %s (score=%.2f)", col, best_type, best_score)

    return result


# ── Standalone convenience validators (return (is_valid: bool, details: dict)) ──

def validate_cin(value) -> tuple[bool, dict]:
    if value is None:
        return False, {"error": "null value"}
    try:
        v = str(value).strip().upper().replace(" ", "")
        if CINValidator.is_valid(v):
            return True, CINValidator.extract_components(v)
        return False, {"error": f"does not match CIN pattern: {v!r}"}
    except Exception as exc:
        return False, {"error": str(exc)}


def validate_pan(value) -> tuple[bool, dict]:
    if value is None:
        return False, {"error": "null value"}
    try:
        v = str(value).strip().upper().replace(" ", "")
        if PANValidator.is_valid(v):
            return True, PANValidator.extract_components(v)
        return False, {"error": f"does not match PAN pattern: {v!r}"}
    except Exception as exc:
        return False, {"error": str(exc)}


def validate_din(value) -> tuple[bool, dict]:
    if value is None:
        return False, {"error": "null value"}
    try:
        v = str(value).strip()
        if DINValidator.is_valid(v):
            return True, {"din": DINValidator.normalize(v)}
        return False, {"error": f"does not match DIN pattern: {v!r}"}
    except Exception as exc:
        return False, {"error": str(exc)}


def validate_gstin(value) -> tuple[bool, dict]:
    if value is None:
        return False, {"error": "null value"}
    try:
        v = str(value).strip().upper().replace(" ", "")
        if not GSTIN_PATTERN.match(v):
            return False, {"error": f"does not match GSTIN pattern: {v!r}"}
        return True, GSTINValidator.extract_components(v)
    except Exception as exc:
        return False, {"error": str(exc)}
