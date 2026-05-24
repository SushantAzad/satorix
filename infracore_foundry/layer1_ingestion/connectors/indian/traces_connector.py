"""
TRACES (TDS Reconciliation Analysis and Correction Enabling System) connector.

TRACES is the CBDT (Central Board of Direct Taxes) portal for TDS/TCS
data. It provides:
  - TDS/TCS certificate data (Form 16, 16A, 16B, 16C, 27D)
  - Challan status for TDS payments
  - Default summaries for deductors
  - Justification reports

This is critical for due diligence on Indian companies:
  - Check if a company is regular in TDS deductions/deposits
  - Verify salary/payment patterns to directors
  - Cross-reference TDS with income tax return filings

Data sources:
  1. Sandbox.co.in TRACES API (requires PAN + deductor credentials)
  2. Bulk export files downloaded from TRACES portal
  3. Form 26AS data (summarized TDS view)

config keys:
  sandbox_api_key   : str
  mode              : "sandbox" | "bulk"  default "bulk"
  data_dir          : str   path to TRACES export files
  deductor_tan      : str   TAN of the deductor company
  pan_list          : list  PANs of deductees to check TDS
  assessment_year   : str   e.g. "2024-25"
  form_type         : str   "16" | "16A" | "26AS" | "all"  default "all"
  max_records       : int   default 10000
"""

import logging
import os
import time
from datetime import datetime
from typing import Optional

import httpx
import pandas as pd

from layer1_ingestion.connectors.base_connector import (
    AuthenticationError,
    BaseConnector,
    ConnectionTestResult,
    ExtractionConfig,
    ExtractionError,
    IncrementalConfig,
    SchemaDetectionResult,
)
from layer1_ingestion.core.config import get_settings

logger = logging.getLogger(__name__)

_SANDBOX_BASE = "https://api.sandbox.co.in"


class TRACESConnector(BaseConnector):
    """TRACES TDS/TCS data connector."""

    REQUIRED_CONFIG_FIELDS: list[str] = []

    def __init__(self, source_id: str, config: dict) -> None:
        super().__init__(source_id, config)
        settings = get_settings()
        self.sandbox_api_key: str = config.get("sandbox_api_key", "") or settings.sandbox_api_key
        self.mode: str = config.get("mode", "bulk")
        self.data_dir: str = config.get("data_dir", "/tmp/traces_data")
        self.deductor_tan: str = config.get("deductor_tan", "").upper()
        self.pan_list: list = config.get("pan_list", [])
        self.assessment_year: str = config.get("assessment_year", "")
        self.form_type: str = config.get("form_type", "all")
        self.max_records: int = int(config.get("max_records", 10000))

    def _sandbox_headers(self) -> dict:
        return {
            "x-api-key": self.sandbox_api_key,
            "Content-Type": "application/json",
        }

    def _fetch_form26as_sandbox(self, pan: str) -> Optional[dict]:
        try:
            resp = httpx.get(
                f"{_SANDBOX_BASE}/income-tax/26as",
                headers=self._sandbox_headers(),
                params={"pan": pan, "ay": self.assessment_year or "2024-25"},
                timeout=20,
            )
            if resp.status_code == 401:
                raise AuthenticationError(self.source_id, "Invalid Sandbox.co.in API key")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json().get("data", {})
        except AuthenticationError:
            raise
        except Exception as exc:
            logger.debug("TRACES Form26AS fetch failed for %s: %s", pan, exc)
            return None

    def _load_from_files(self) -> list[dict]:
        records: list[dict] = []
        if not os.path.isdir(self.data_dir):
            return records
        for fname in os.listdir(self.data_dir):
            fpath = os.path.join(self.data_dir, fname)
            ext = fname.rsplit(".", 1)[-1].lower()
            try:
                if ext in ("xlsx", "xls"):
                    df = pd.read_excel(fpath, dtype=str)
                elif ext == "csv":
                    df = pd.read_csv(fpath, dtype=str, encoding="utf-8", errors="replace")
                elif ext == "txt":
                    # TRACES fixed-width text reports
                    df = pd.read_fwf(fpath, dtype=str)
                else:
                    continue
                df = df.dropna(how="all")
                for _, row in df.iterrows():
                    records.append(self._normalize_row(row.to_dict(), fname))
            except Exception as exc:
                logger.warning("Failed to parse TRACES file %s: %s", fname, exc)
        return records

    def _normalize_26as(self, pan: str, data: dict) -> list[dict]:
        records: list[dict] = []
        # Form 26AS has multiple parts: A (TDS on Salary), B (TDS on Non-Salary), C (TCS), etc.
        for part_key in ("partA", "partB", "partC", "part_a", "part_b", "tds_entries", "data"):
            entries = data.get(part_key, [])
            if isinstance(entries, list):
                for entry in entries:
                    records.append({
                        "pan": pan,
                        "deductor_tan": entry.get("tan") or entry.get("deductor_tan", ""),
                        "deductor_name": entry.get("deductor_name") or entry.get("name", ""),
                        "section": entry.get("section") or entry.get("tds_section", ""),
                        "transaction_date": entry.get("date") or entry.get("transaction_date", ""),
                        "amount_paid": entry.get("amount_paid") or entry.get("amount", ""),
                        "tds_deducted": entry.get("tds_deducted") or entry.get("tds", ""),
                        "tds_deposited": entry.get("tds_deposited", ""),
                        "certificate_number": entry.get("certificate_number") or entry.get("cert_no", ""),
                        "assessment_year": self.assessment_year,
                        "form_type": "26AS",
                        "remarks": entry.get("remarks", ""),
                    })
        return records

    def _normalize_row(self, row: dict, source_file: str) -> dict:
        def pick(keys: list[str]) -> str:
            for k in keys:
                for col, val in row.items():
                    if k.lower() in str(col).lower() and val and str(val) not in ("nan", ""):
                        return str(val).strip()
            return ""

        return {
            "pan": pick(["pan", "deductee pan"]),
            "deductor_tan": pick(["tan", "deductor tan"]) or self.deductor_tan,
            "deductor_name": pick(["deductor name", "name of deductor"]),
            "section": pick(["section", "nature of payment"]),
            "transaction_date": pick(["date", "transaction date", "challan date"]),
            "amount_paid": pick(["amount paid", "payment amount", "total amount"]),
            "tds_deducted": pick(["tds deducted", "tax deducted", "tds"]),
            "tds_deposited": pick(["tds deposited", "tax deposited", "challan amount"]),
            "certificate_number": pick(["certificate", "cert no"]),
            "assessment_year": pick(["assessment year", "ay"]) or self.assessment_year,
            "form_type": pick(["form type", "form"]) or source_file.split("_")[0].upper(),
            "remarks": pick(["remarks", "status"]),
        }

    def test_connection(self) -> ConnectionTestResult:
        start = time.perf_counter()
        if self.mode == "bulk":
            files = [f for f in os.listdir(self.data_dir) if f.endswith((".xlsx", ".csv", ".txt"))] if os.path.isdir(self.data_dir) else []
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=bool(files),
                message=f"TRACES bulk mode: {len(files)} file(s) in {self.data_dir}",
                response_time_ms=elapsed,
            )
        try:
            resp = httpx.get(
                f"{_SANDBOX_BASE}/income-tax/26as",
                headers=self._sandbox_headers(),
                params={"pan": "AAACN5014H", "ay": "2024-25"},
                timeout=15,
            )
            if resp.status_code == 401:
                raise AuthenticationError(self.source_id, "Invalid Sandbox.co.in API key")
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=resp.status_code < 400,
                message=f"TRACES Sandbox API status: {resp.status_code}",
                response_time_ms=elapsed,
            )
        except AuthenticationError:
            raise
        except Exception as exc:
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=False, message=str(exc),
                response_time_ms=elapsed, error=type(exc).__name__,
            )

    def extract_schema(self) -> SchemaDetectionResult:
        with self._timed_operation("traces_schema_detection"):
            columns = [
                {"name": "pan", "type": "string", "nullable": False, "sample_values": []},
                {"name": "deductor_tan", "type": "string", "nullable": True, "sample_values": []},
                {"name": "deductor_name", "type": "string", "nullable": True, "sample_values": []},
                {"name": "section", "type": "string", "nullable": True, "sample_values": ["192","194A","194C","194J"]},
                {"name": "transaction_date", "type": "string", "nullable": True, "sample_values": []},
                {"name": "amount_paid", "type": "string", "nullable": True, "sample_values": []},
                {"name": "tds_deducted", "type": "string", "nullable": True, "sample_values": []},
                {"name": "tds_deposited", "type": "string", "nullable": True, "sample_values": []},
                {"name": "certificate_number", "type": "string", "nullable": True, "sample_values": []},
                {"name": "assessment_year", "type": "string", "nullable": True, "sample_values": ["2024-25"]},
                {"name": "form_type", "type": "string", "nullable": True, "sample_values": ["16","16A","26AS"]},
                {"name": "remarks", "type": "string", "nullable": True, "sample_values": []},
            ]
            return SchemaDetectionResult(
                columns=columns,
                total_columns=len(columns),
                detected_primary_key="certificate_number",
                timestamp_columns=["transaction_date"],
                indian_identifiers={"pan": "PAN", "deductor_tan": "TAN"},
            )

    def extract_full(self, config: ExtractionConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            if self.mode == "bulk":
                records = self._load_from_files()
            else:
                records = []
                for pan in self.pan_list[: self.max_records]:
                    data = self._fetch_form26as_sandbox(pan)
                    if data:
                        records.extend(self._normalize_26as(pan, data))
                    time.sleep(0.2)

            df = pd.DataFrame(records) if records else pd.DataFrame()
            if self.form_type != "all" and not df.empty and "form_type" in df.columns:
                df = df[df["form_type"].str.contains(self.form_type, case=False, na=False)]
            self.log_extraction(len(df), time.perf_counter() - start, 0)
            return df
        except Exception as exc:
            self.log_extraction(0, time.perf_counter() - start, 1)
            raise ExtractionError(self.source_id, f"TRACES extraction failed: {exc}") from exc

    def extract_incremental(self, config: IncrementalConfig) -> pd.DataFrame:
        return self.extract_full(config)

    def get_record_count(self) -> int:
        return len(self.pan_list)
