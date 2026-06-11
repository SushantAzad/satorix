"""
CSV/TSV connector for local, network, and URL-based CSV files.
Handles encoding detection, BOM, Indian number formats, delimiter auto-detection.
"""

import hashlib
import io
import logging
import os
import re
import time
from typing import Optional

import chardet
import httpx
import pandas as pd

from layer1_ingestion.connectors.base_connector import (
    BaseConnector, ConnectionTestResult, SchemaDetectionResult,
    ExtractionConfig, IncrementalConfig,
    ConnectionError, ExtractionError,
)

logger = logging.getLogger(__name__)

# Indian number format: 1,24,500 or 12,34,567
INDIAN_NUMBER_PATTERN = re.compile(r"^-?\d{1,2}(?:,\d{2})*(?:,\d{3})(?:\.\d+)?$")


def _normalize_indian_number(value: str) -> str:
    """Convert Indian number format (1,24,500) to standard integer/float."""
    if isinstance(value, str) and INDIAN_NUMBER_PATTERN.match(value.strip()):
        return value.replace(",", "")
    return value


def _detect_encoding(file_path: str) -> str:
    """Detect file encoding using chardet, handling BOM."""
    with open(file_path, "rb") as f:
        raw = f.read(min(os.path.getsize(file_path), 100000))

    # Check for BOM markers
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if raw.startswith(b"\xff\xfe"):
        return "utf-16-le"
    if raw.startswith(b"\xfe\xff"):
        return "utf-16-be"

    result = chardet.detect(raw)
    encoding = result.get("encoding", "utf-8")
    confidence = result.get("confidence", 0)
    logger.debug(
        "Detected encoding: %s (confidence=%.2f)", encoding, confidence
    )
    return encoding or "utf-8"


def _detect_delimiter(file_path: str, encoding: str) -> str:
    """Auto-detect CSV delimiter by analyzing the first few lines."""
    with open(file_path, "r", encoding=encoding, errors="replace") as f:
        sample = ""
        for i, line in enumerate(f):
            if i >= 20:
                break
            sample += line

    candidates = {",": 0, "\t": 0, ";": 0, "|": 0}
    for char in candidates:
        candidates[char] = sample.count(char)

    best = max(candidates, key=candidates.get)
    if candidates[best] == 0:
        return ","  # default
    logger.debug("Detected delimiter: %r (count=%d)", best, candidates[best])
    return best


def _get_file_content(file_path: str, config: dict) -> tuple[io.StringIO, str]:
    """
    Get file content from local path, network path, or URL.
    Returns a StringIO buffer and the detected encoding.
    """
    if file_path.startswith(("http://", "https://")):
        response = httpx.get(file_path, follow_redirects=True, timeout=60)
        response.raise_for_status()
        raw = response.content
        detected = chardet.detect(raw[:100000])
        encoding = config.get("encoding") or detected.get("encoding", "utf-8")
        text = raw.decode(encoding, errors="replace")
        return io.StringIO(text), encoding

    encoding = config.get("encoding") or _detect_encoding(file_path)
    with open(file_path, "r", encoding=encoding, errors="replace") as f:
        text = f.read()
    return io.StringIO(text), encoding


class CSVConnector(BaseConnector):
    """Connector for CSV and TSV files from local, network, or URL sources."""

    REQUIRED_CONFIG_FIELDS = ["file_path"]

    def __init__(self, source_id: str, config: dict) -> None:
        super().__init__(source_id, config)
        self.file_path: str = config.get("file_path", "")
        self.delimiter: Optional[str] = config.get("delimiter")
        self.encoding: Optional[str] = config.get("encoding")
        self.has_header: bool = config.get("has_header", True)
        self.skip_rows: int = config.get("skip_rows", 0)

    def test_connection(self) -> ConnectionTestResult:
        """Check if the CSV file exists and is readable."""
        start = time.perf_counter()
        try:
            if self.file_path.startswith(("http://", "https://")):
                resp = httpx.head(self.file_path, follow_redirects=True, timeout=10)
                resp.raise_for_status()
                elapsed = (time.perf_counter() - start) * 1000
                return ConnectionTestResult(
                    success=True,
                    message=f"URL reachable (status={resp.status_code})",
                    response_time_ms=elapsed,
                )
            else:
                if not os.path.exists(self.file_path):
                    elapsed = (time.perf_counter() - start) * 1000
                    return ConnectionTestResult(
                        success=False,
                        message=f"File not found: {self.file_path}",
                        response_time_ms=elapsed,
                        error="FileNotFoundError",
                    )
                if not os.access(self.file_path, os.R_OK):
                    elapsed = (time.perf_counter() - start) * 1000
                    return ConnectionTestResult(
                        success=False,
                        message=f"File not readable: {self.file_path}",
                        response_time_ms=elapsed,
                        error="PermissionError",
                    )
                file_size = os.path.getsize(self.file_path)
                elapsed = (time.perf_counter() - start) * 1000
                return ConnectionTestResult(
                    success=True,
                    message=f"File accessible ({file_size:,} bytes)",
                    response_time_ms=elapsed,
                )
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=False,
                message=str(e),
                response_time_ms=elapsed,
                error=type(e).__name__,
            )

    def extract_schema(self) -> SchemaDetectionResult:
        """Read first 1000 rows to detect schema and Indian identifiers."""
        with self._timed_operation("schema_detection"):
            buffer, encoding = _get_file_content(self.file_path, self.config)
            delimiter = self.delimiter
            if delimiter is None and not self.file_path.startswith(("http://", "https://")):
                delimiter = _detect_delimiter(self.file_path, encoding)
            delimiter = delimiter or ","

            df = pd.read_csv(
                buffer,
                delimiter=delimiter,
                header=0 if self.has_header else None,
                skiprows=self.skip_rows,
                nrows=1000,
                on_bad_lines="warn",
            )

            columns = []
            for col in df.columns:
                col_info = {
                    "name": str(col),
                    "type": str(df[col].dtype),
                    "nullable": bool(df[col].isnull().any()),
                    "sample_values": df[col].dropna().head(5).tolist(),
                }
                columns.append(col_info)

            # Detect Indian identifiers
            indian_ids: dict[str, str] = {}
            try:
                from layer1_ingestion.schema.indian_identifiers import detect_identifier_columns
                indian_ids = detect_identifier_columns(df)
            except ImportError:
                pass

            timestamp_cols = [
                str(col) for col in df.columns
                if df[col].dtype == "object"
                and pd.to_datetime(df[col], errors="coerce").notna().mean() > 0.8
            ]

            return SchemaDetectionResult(
                columns=columns,
                total_columns=len(df.columns),
                indian_identifiers=indian_ids,
                timestamp_columns=timestamp_cols,
                record_count_estimate=None,
            )

    def extract_full(self, config: ExtractionConfig) -> pd.DataFrame:
        """Extract the entire CSV file."""
        start = time.perf_counter()
        errors = 0
        try:
            self.logger.info(
                "extraction_start",
                extra={"source_id": self.source_id, "file": self.file_path},
            )

            buffer, encoding = _get_file_content(self.file_path, self.config)
            delimiter = self.delimiter
            if delimiter is None and not self.file_path.startswith(("http://", "https://")):
                delimiter = _detect_delimiter(self.file_path, encoding)
            delimiter = delimiter or ","

            df = pd.read_csv(
                buffer,
                delimiter=delimiter,
                header=0 if self.has_header else None,
                skiprows=self.skip_rows,
                on_bad_lines="warn",
                dtype=str,  # Read all as string to avoid premature conversion
            )

            # Normalize Indian number format columns
            for col in df.columns:
                sample = df[col].dropna().head(100)
                if sample.apply(lambda v: bool(INDIAN_NUMBER_PATTERN.match(str(v).strip()))).mean() > 0.5:
                    df[col] = df[col].apply(
                        lambda v: _normalize_indian_number(str(v)) if pd.notna(v) else v
                    )
                    try:
                        df[col] = pd.to_numeric(df[col], errors="coerce")
                    except Exception:
                        pass

            duration = time.perf_counter() - start
            self.log_extraction(len(df), duration, errors)
            return df

        except Exception as e:
            duration = time.perf_counter() - start
            self.log_extraction(0, duration, 1)
            raise ExtractionError(
                self.source_id,
                f"CSV extraction failed: {str(e)}",
                context={"file_path": self.file_path},
            ) from e

    def extract_incremental(self, config: IncrementalConfig) -> pd.DataFrame:
        """
        For files: compare checksum against stored checksum.
        If changed, extract full and flag as modified.
        """
        current_checksum = self._compute_file_checksum()

        if config.last_extracted_id == current_checksum:
            self.logger.info(
                "File unchanged (checksum match), skipping extraction",
                extra={"source_id": self.source_id, "checksum": current_checksum},
            )
            return pd.DataFrame()

        self.logger.info(
            "File changed, performing full extraction",
            extra={
                "source_id": self.source_id,
                "old_checksum": config.last_extracted_id,
                "new_checksum": current_checksum,
            },
        )
        df = self.extract_full(config)
        return df

    def get_record_count(self) -> int:
        """Count lines in the CSV file (excluding header)."""
        if self.file_path.startswith(("http://", "https://")):
            buffer, _ = _get_file_content(self.file_path, self.config)
            text = buffer.getvalue()
            lines = text.strip().split("\n")
            return max(0, len(lines) - (1 if self.has_header else 0))
        else:
            encoding = self.encoding or _detect_encoding(self.file_path)
            count = 0
            with open(self.file_path, "r", encoding=encoding, errors="replace") as f:
                for _ in f:
                    count += 1
            header_offset = 1 if self.has_header else 0
            return max(0, count - header_offset - self.skip_rows)

    def _compute_file_checksum(self) -> str:
        """Compute SHA-256 checksum of the file content."""
        if self.file_path.startswith(("http://", "https://")):
            resp = httpx.get(self.file_path, follow_redirects=True, timeout=60)
            resp.raise_for_status()
            return hashlib.sha256(resp.content).hexdigest()
        else:
            sha256 = hashlib.sha256()
            with open(self.file_path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    sha256.update(chunk)
            return sha256.hexdigest()
