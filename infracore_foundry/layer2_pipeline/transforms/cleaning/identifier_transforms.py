"""
Indian business identifier normalization transforms.
CIN, GSTIN, PAN, DIN, IFSC — validate format, uppercase, remove junk chars.
"""

from __future__ import annotations

import re
from typing import Any, Optional

import pandas as pd

from layer2_pipeline.core.context import ExecutionContext
from layer2_pipeline.transforms.base import BaseTransform, TransformError
from layer2_pipeline.transforms.registry import register

# --- Format patterns ---
_CIN_PATTERN = re.compile(
    r"^([LUu])(\d{5})([A-Z]{2})(\d{4})([A-Z]{3})(\d{6})$"
)
_GSTIN_PATTERN = re.compile(
    r"^\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}Z[A-Z\d]{1}$"
)
_PAN_PATTERN = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$")
_DIN_PATTERN = re.compile(r"^\d{8}$")
_IFSC_PATTERN = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")

# GSTIN checksum table
_GSTIN_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_GSTIN_CHAR_MAP = {c: i for i, c in enumerate(_GSTIN_CHARS)}


def _gstin_checksum_valid(gstin: str) -> bool:
    """Luhn-like checksum for GSTIN's last character."""
    if len(gstin) != 15:
        return False
    factor = 2
    total = 0
    for ch in reversed(gstin[:-1]):
        val = _GSTIN_CHAR_MAP.get(ch, 0) * factor
        total += val // 36 + val % 36
        factor = 1 if factor == 2 else 2
    check = (36 - total % 36) % 36
    expected = _GSTIN_CHARS[check]
    return gstin[-1] == expected


def _normalize(value: Any, pattern: re.Pattern, strip_chars: str = r"[^A-Z0-9]") -> Optional[str]:
    if not isinstance(value, str) or not value.strip():
        return None
    cleaned = re.sub(strip_chars, "", value.upper())
    return cleaned if pattern.match(cleaned) else None


class NormalizeCIN(BaseTransform):
    """
    Normalize Corporate Identification Numbers (CIN).
    Format: [LU]NNNNNSSYYYYTTTNNNNNN (21 chars)
    """

    transform_type = "normalize_cin"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        col = config["column"]
        if col not in df.columns:
            raise TransformError(f"normalize_cin: column {col!r} not found")
        df = df.copy()
        invalid_count = 0

        def _process(val: Any) -> Optional[str]:
            nonlocal invalid_count
            normalized = _normalize(val, _CIN_PATTERN)
            if normalized is None and pd.notna(val) and str(val).strip():
                invalid_count += 1
            return normalized  # Always None for invalid — never propagate garbage

        df[col] = df[col].apply(_process)
        if invalid_count > 0:
            context.warn(f"normalize_cin ({step_id}): {invalid_count} invalid CIN value(s) replaced with null")
        return df


class NormalizeGSTIN(BaseTransform):
    """
    Normalize GSTIN (15 chars) with optional checksum validation.
    First 2 digits must match state code; last char is checksum.
    """

    transform_type = "normalize_gstin"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        col = config["column"]
        validate_checksum = config.get("validate_checksum", True)
        if col not in df.columns:
            raise TransformError(f"normalize_gstin: column {col!r} not found")
        df = df.copy()

        def _process(val: Any) -> Optional[str]:
            cleaned = _normalize(val, _GSTIN_PATTERN)
            if cleaned is None:
                return None
            if validate_checksum and not _gstin_checksum_valid(cleaned):
                return None
            return cleaned

        df[col] = df[col].apply(_process)
        return df


class NormalizePAN(BaseTransform):
    """
    Normalize Permanent Account Numbers (PAN).
    Format: AAAAA9999A (10 chars, 5 alpha + 4 numeric + 1 alpha)
    """

    transform_type = "normalize_pan"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        col = config["column"]
        if col not in df.columns:
            raise TransformError(f"normalize_pan: column {col!r} not found")
        df = df.copy()
        df[col] = df[col].apply(lambda v: _normalize(v, _PAN_PATTERN))
        return df


class NormalizeDIN(BaseTransform):
    """
    Normalize Director Identification Numbers (DIN).
    Format: 8 digits, zero-padded.
    """

    transform_type = "normalize_din"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        col = config["column"]
        if col not in df.columns:
            raise TransformError(f"normalize_din: column {col!r} not found")
        df = df.copy()

        def _process(val: Any) -> Optional[str]:
            if pd.isna(val):
                return None
            digits = re.sub(r"\D", "", str(val))
            if not digits:
                return None
            padded = digits.zfill(8)
            return padded if _DIN_PATTERN.match(padded) else None

        df[col] = df[col].apply(_process)
        return df


class NormalizeIFSC(BaseTransform):
    """
    Normalize IFSC codes (11 chars: 4 alpha bank code + 0 + 6 alphanumeric branch).
    """

    transform_type = "normalize_ifsc"

    def apply(self, df: pd.DataFrame, config: dict, context: ExecutionContext, step_id: str) -> pd.DataFrame:
        col = config["column"]
        if col not in df.columns:
            raise TransformError(f"normalize_ifsc: column {col!r} not found")
        df = df.copy()
        df[col] = df[col].apply(lambda v: _normalize(v, _IFSC_PATTERN))
        return df


register(NormalizeCIN())
register(NormalizeGSTIN())
register(NormalizePAN())
register(NormalizeDIN())
register(NormalizeIFSC())
