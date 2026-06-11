"""
SAP export file connector — parses SAP IDOC flat files, SAP CSV exports,
and structured text from common SAP transaction exports (FB60, FB70, VA01, XK01).

Large Indian manufacturers, FMCG companies, and PSUs use SAP but rarely
allow live API access. The standard data-sharing pattern is scheduled
exports dropped to an SFTP server or shared folder.

Supported file formats:
  1. IDOC flat file (fixed-width, CONTROL + DATA records)
  2. SAP CSV/XLS export (with SAP header row, configurable delimiter)
  3. ALV grid export (text layout with column ruler separator line)
  4. SAP BEx / Webi export (headerless numeric exports)

config keys:
  file_path         : str   path to a local file OR an SFTP-mounted path
  format            : "idoc" | "csv" | "alv" | "bex"  — default: auto-detect
  encoding          : str   default "utf-8"; common SAP: "cp1252", "utf-16"
  delimiter         : str   for CSV exports — default "\t" (SAP exports use tab)
  skip_rows         : int   header rows to skip — default 0 (auto for ALV)
  idoc_type         : str   expected IDOC type e.g. "DEBMAS06" for customer master
  currency_columns  : list  column names containing SAP currency amounts (divide by 100)
  date_columns      : list  column names with SAP date format YYYYMMDD
  files_dir         : str   directory to scan for matching export files (batch mode)
  file_pattern      : str   glob pattern for batch mode e.g. "DEBMAS*.txt"
"""

import glob
import io
import logging
import os
import re
import time
from typing import Optional

import pandas as pd

from layer1_ingestion.connectors.base_connector import (
    BaseConnector,
    ConnectionTestResult,
    ExtractionConfig,
    ExtractionError,
    IncrementalConfig,
    SchemaDetectionResult,
)

logger = logging.getLogger(__name__)


def _parse_sap_date(series: pd.Series) -> pd.Series:
    """Convert SAP YYYYMMDD date strings to datetime."""
    return pd.to_datetime(series, format="%Y%m%d", errors="coerce")


def _parse_sap_amount(series: pd.Series) -> pd.Series:
    """SAP stores monetary values as integers scaled ×100 in some exports."""
    return pd.to_numeric(series, errors="coerce") / 100.0


class SAPConnector(BaseConnector):
    """SAP export file parser — IDOC, CSV, ALV, and BEx formats."""

    REQUIRED_CONFIG_FIELDS: list[str] = []

    def __init__(self, source_id: str, config: dict) -> None:
        super().__init__(source_id, config)
        self.file_path: str = config.get("file_path", "")
        self.format: str = config.get("format", "auto")
        self.encoding: str = config.get("encoding", "utf-8")
        self.delimiter: str = config.get("delimiter", "\t")
        self.skip_rows: int = int(config.get("skip_rows", 0))
        self.idoc_type: str = config.get("idoc_type", "")
        self.currency_columns: list = config.get("currency_columns", [])
        self.date_columns: list = config.get("date_columns", [])
        self.files_dir: str = config.get("files_dir", "")
        self.file_pattern: str = config.get("file_pattern", "*.txt")

    def _resolve_files(self) -> list[str]:
        if self.file_path and os.path.isfile(self.file_path):
            return [self.file_path]
        if self.files_dir:
            pattern = os.path.join(self.files_dir, self.file_pattern)
            return sorted(glob.glob(pattern))
        return []

    def _detect_format(self, content: str) -> str:
        """Auto-detect SAP export format from first few lines."""
        head = content[:500]
        if re.search(r"^EDI_DC[0-9]+\s", head, re.MULTILINE):
            return "idoc"
        if "\t" in head and re.search(r"\d{8}", head):
            return "csv"
        if re.search(r"[-]{5,}", head):
            return "alv"
        return "csv"

    def _parse_idoc(self, content: str) -> pd.DataFrame:
        """Parse SAP IDOC flat file into a DataFrame of segment records."""
        records: list[dict] = []
        current_idoc: dict = {}
        for line in content.splitlines():
            if not line.strip():
                continue
            record_type = line[:3].strip()
            if record_type == "EDI":
                if current_idoc:
                    records.append(current_idoc)
                current_idoc = {
                    "record_type": "CONTROL",
                    "idoc_number": line[14:28].strip(),
                    "idoc_type": line[48:68].strip(),
                    "sender": line[83:99].strip(),
                    "receiver": line[99:115].strip(),
                    "creation_date": line[115:123].strip(),
                }
            elif len(line) >= 63:
                segment: dict = {
                    "record_type": "DATA",
                    "idoc_number": line[14:28].strip(),
                    "segment_type": line[48:62].strip(),
                    "data": line[63:].rstrip(),
                }
                segment.update(current_idoc)
                records.append(segment)

        if current_idoc and current_idoc not in records:
            records.append(current_idoc)

        return pd.DataFrame(records)

    def _parse_alv(self, content: str) -> pd.DataFrame:
        """Parse SAP ALV grid text export — column widths inferred from ruler line."""
        lines = content.splitlines()
        ruler_idx = next(
            (i for i, l in enumerate(lines) if re.match(r"^[-| ]+$", l) and len(l) > 20),
            None,
        )
        if ruler_idx is None:
            return pd.read_csv(io.StringIO(content), sep="\t", encoding=self.encoding)

        header_line = lines[ruler_idx - 1] if ruler_idx > 0 else ""
        ruler = lines[ruler_idx]
        # Compute column positions from ruler
        col_positions: list[int] = [0]
        for i, ch in enumerate(ruler):
            if ch == " " and i > 0 and ruler[i - 1] == "-":
                col_positions.append(i + 1)
        col_positions.append(len(ruler))

        def split_fixed(line: str) -> list[str]:
            return [
                line[col_positions[i]: col_positions[i + 1]].strip()
                for i in range(len(col_positions) - 1)
            ]

        headers = split_fixed(header_line)
        data_lines = lines[ruler_idx + 1:]
        rows = [split_fixed(l) for l in data_lines if l.strip() and not re.match(r"^[-| ]+$", l)]
        return pd.DataFrame(rows, columns=headers if headers else None)

    def _parse_csv(self, content: str) -> pd.DataFrame:
        """Parse SAP CSV/tab export, skipping configurable header rows."""
        return pd.read_csv(
            io.StringIO(content),
            sep=self.delimiter,
            skiprows=self.skip_rows,
            encoding=self.encoding,
            dtype=str,
            on_bad_lines="warn",
        )

    def _parse_file(self, path: str) -> pd.DataFrame:
        with open(path, encoding=self.encoding, errors="replace") as f:
            content = f.read()

        fmt = self.format if self.format != "auto" else self._detect_format(content)
        if fmt == "idoc":
            df = self._parse_idoc(content)
        elif fmt == "alv":
            df = self._parse_alv(content)
        else:
            df = self._parse_csv(content)

        # Post-process SAP-specific column types
        for col in self.date_columns:
            if col in df.columns:
                df[col] = _parse_sap_date(df[col])
        for col in self.currency_columns:
            if col in df.columns:
                df[col] = _parse_sap_amount(df[col])

        df["_source_file"] = os.path.basename(path)
        return df

    def test_connection(self) -> ConnectionTestResult:
        start = time.perf_counter()
        files = self._resolve_files()
        elapsed = (time.perf_counter() - start) * 1000
        if not files:
            return ConnectionTestResult(
                success=False,
                message=f"No SAP export files found at path={self.file_path!r} or dir={self.files_dir!r}",
                response_time_ms=elapsed,
            )
        total_size = sum(os.path.getsize(f) for f in files)
        return ConnectionTestResult(
            success=True,
            message=f"{len(files)} SAP export file(s) found ({total_size:,} bytes total)",
            response_time_ms=elapsed,
        )

    def extract_schema(self) -> SchemaDetectionResult:
        with self._timed_operation("sap_schema_detection"):
            files = self._resolve_files()
            if not files:
                return SchemaDetectionResult(columns=[], total_columns=0)
            df = self._parse_file(files[0])
            columns = [
                {
                    "name": str(c),
                    "type": str(df[c].dtype),
                    "nullable": bool(df[c].isnull().any()),
                    "sample_values": df[c].dropna().head(3).tolist(),
                }
                for c in df.columns
            ]
            return SchemaDetectionResult(
                columns=columns,
                total_columns=len(columns),
                timestamp_columns=[c["name"] for c in columns if "date" in c["name"].lower()],
                record_count_estimate=len(df),
            )

    def extract_full(self, config: ExtractionConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            files = self._resolve_files()
            if not files:
                return pd.DataFrame()
            chunks = [self._parse_file(f) for f in files]
            df = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()
            self.log_extraction(len(df), time.perf_counter() - start, 0)
            return df
        except Exception as exc:
            self.log_extraction(0, time.perf_counter() - start, 1)
            raise ExtractionError(
                self.source_id, f"SAP file parsing failed: {exc}"
            ) from exc

    def extract_incremental(self, config: IncrementalConfig) -> pd.DataFrame:
        """Incremental for file-based connector: only read files modified after watermark."""
        start = time.perf_counter()
        try:
            files = self._resolve_files()
            if config.last_extracted_at:
                cutoff_ts = config.last_extracted_at.timestamp()
                files = [f for f in files if os.path.getmtime(f) > cutoff_ts]
            if not files:
                return pd.DataFrame()
            chunks = [self._parse_file(f) for f in files]
            df = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()
            self.log_extraction(len(df), time.perf_counter() - start, 0)
            return df
        except Exception as exc:
            self.log_extraction(0, time.perf_counter() - start, 1)
            raise ExtractionError(
                self.source_id, f"SAP incremental failed: {exc}"
            ) from exc

    def get_record_count(self) -> int:
        files = self._resolve_files()
        if not files:
            return 0
        try:
            df = self._parse_file(files[0])
            return len(df)
        except Exception:
            return 0
