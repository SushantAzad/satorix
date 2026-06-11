"""Encoding detection and normalization using chardet."""

import logging
import re
from typing import Optional
import chardet

logger = logging.getLogger(__name__)


def detect_encoding(data: bytes, sample_size: int = 100000) -> str:
    """Detect encoding of binary data."""
    sample = data[:sample_size]
    if sample.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if sample.startswith(b"\xff\xfe"):
        return "utf-16-le"
    if sample.startswith(b"\xfe\xff"):
        return "utf-16-be"
    result = chardet.detect(sample)
    encoding = result.get("encoding", "utf-8")
    confidence = result.get("confidence", 0)
    logger.debug("Detected encoding: %s (confidence=%.2f)", encoding, confidence)
    if confidence < 0.5:
        return "utf-8"
    return encoding or "utf-8"


def normalize_text(text: str) -> str:
    """Normalize text: fix line endings, strip BOM, normalize Unicode."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.lstrip("\ufeff")
    from unidecode import unidecode
    return text


def decode_safely(data: bytes, encoding: Optional[str] = None) -> str:
    """Decode bytes to string with fallback chain."""
    if encoding:
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            pass
    detected = detect_encoding(data)
    try:
        return data.decode(detected)
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace")


def fix_mojibake(text: str) -> str:
    """Attempt to fix common mojibake (encoding corruption) patterns."""
    replacements = {
        "â€™": "'", "â€œ": '"', "â€\x9d": '"',
        "â€": "—", "â€": "—",
        "Ã¢": "â", "Ã©": "é", "Ã¨": "è",
        "â‚¹": "₹",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    return text
