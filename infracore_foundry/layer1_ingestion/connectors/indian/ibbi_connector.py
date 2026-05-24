"""
IBBI (Insolvency and Bankruptcy Board of India) connector.

Extracts CIRP (Corporate Insolvency Resolution Process) cases, corporate
debtor data, Resolution Professional assignments, and liquidation proceedings
from IBBI public data sources.

This is one of the most valuable data sources for the platform — CIRP cases
are public record and directly feed the graph's InsolvencyProceeding nodes.

Data sources:
  1. IBBI public website data (scraped/parsed)
  2. NCLT cause list and order database (public)
  3. Sandbox.co.in IBBI dataset (if available)

config keys:
  sandbox_api_key   : str
  mode              : "bulk" | "api"  default "bulk"
  data_dir          : str   path to pre-downloaded IBBI CSV/Excel files
  year_from         : int   default 2016 (CIRP started Aug 2016)
  year_to           : int   default current year
  include_personal  : bool  include personal insolvency — default False
"""

import logging
import os
import time
from datetime import datetime, timezone
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

# IBBI public data API (they publish quarterly datasets)
_IBBI_DATA_URL = "https://ibbi.gov.in/api/public"
_SANDBOX_BASE = "https://api.sandbox.co.in"


class IBBIConnector(BaseConnector):
    """IBBI insolvency proceedings connector."""

    REQUIRED_CONFIG_FIELDS: list[str] = []

    def __init__(self, source_id: str, config: dict) -> None:
        super().__init__(source_id, config)
        settings = get_settings()
        self.sandbox_api_key: str = config.get("sandbox_api_key", "") or settings.sandbox_api_key
        self.mode: str = config.get("mode", "bulk")
        self.data_dir: str = config.get("data_dir", "/tmp/ibbi_data")
        self.year_from: int = int(config.get("year_from", 2016))
        self.year_to: int = int(config.get("year_to", datetime.now().year))
        self.include_personal: bool = bool(config.get("include_personal", False))

    def _fetch_ibbi_public_data(self) -> list[dict]:
        """
        Fetch IBBI quarterly CIRP data from public endpoints.
        IBBI publishes case-level data as downloadable reports.
        """
        records: list[dict] = []

        # IBBI provides downloadable datasets quarterly
        endpoints = [
            "/data/corporateinsolvency/outstanding",
            "/data/corporateinsolvency/closed",
        ]
        headers = {"Accept": "application/json", "User-Agent": "Mozilla/5.0"}

        for endpoint in endpoints:
            try:
                resp = httpx.get(
                    f"{_IBBI_DATA_URL}{endpoint}",
                    headers=headers,
                    timeout=30,
                    follow_redirects=True,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    cases = data if isinstance(data, list) else data.get("data", data.get("cases", []))
                    for case in cases:
                        records.append(self._normalize_cirp_case(case))
            except Exception as exc:
                logger.warning("IBBI endpoint %s failed: %s", endpoint, exc)

        return records

    def _load_from_files(self) -> list[dict]:
        """Load pre-downloaded IBBI Excel/CSV files from data_dir."""
        records: list[dict] = []
        if not os.path.isdir(self.data_dir):
            logger.warning("IBBI data_dir not found: %s", self.data_dir)
            return records

        for fname in os.listdir(self.data_dir):
            fpath = os.path.join(self.data_dir, fname)
            ext = fname.rsplit(".", 1)[-1].lower()
            try:
                if ext in ("xlsx", "xls"):
                    df = pd.read_excel(fpath, dtype=str)
                elif ext == "csv":
                    df = pd.read_csv(fpath, dtype=str, encoding="utf-8", errors="replace")
                else:
                    continue
                for _, row in df.iterrows():
                    records.append(self._normalize_row(row.to_dict(), fname))
            except Exception as exc:
                logger.warning("Failed to parse IBBI file %s: %s", fname, exc)

        return records

    def _normalize_cirp_case(self, case: dict) -> dict:
        """Normalize IBBI API response to standard schema."""
        return {
            "cirp_id": case.get("cirp_id") or case.get("id") or case.get("case_number", ""),
            "corporate_debtor_name": case.get("corporate_debtor") or case.get("company_name", ""),
            "cin": case.get("cin", ""),
            "nclt_bench": case.get("nclt_bench") or case.get("bench", ""),
            "admission_date": case.get("admission_date") or case.get("date_of_admission", ""),
            "resolution_professional": case.get("rp_name") or case.get("resolution_professional", ""),
            "ip_registration": case.get("ip_reg") or case.get("ip_registration_number", ""),
            "status": case.get("status", ""),
            "closure_type": case.get("closure_type") or case.get("outcome", ""),
            "closure_date": case.get("closure_date") or case.get("date_of_closure", ""),
            "resolution_applicant": case.get("resolution_applicant", ""),
            "industry": case.get("industry") or case.get("sector", ""),
            "claim_amount_cr": case.get("total_claims") or case.get("claim_amount", ""),
            "data_source": "ibbi_api",
        }

    def _normalize_row(self, row: dict, source_file: str) -> dict:
        """Normalize a row from an IBBI Excel/CSV file."""
        # Try multiple column name variants (IBBI changes formats frequently)
        def pick(keys: list[str]) -> str:
            for k in keys:
                for col, val in row.items():
                    if k.lower() in str(col).lower() and val and str(val) != "nan":
                        return str(val).strip()
            return ""

        return {
            "cirp_id": pick(["cirp", "case no", "case number", "id"]),
            "corporate_debtor_name": pick(["corporate debtor", "company name", "debtor"]),
            "cin": pick(["cin", "company identification"]),
            "nclt_bench": pick(["nclt", "bench", "tribunal"]),
            "admission_date": pick(["admission date", "date of admission", "filing date"]),
            "resolution_professional": pick(["resolution professional", "rp name", "ip name"]),
            "ip_registration": pick(["ip reg", "registration number", "ip no"]),
            "status": pick(["status", "stage", "current status"]),
            "closure_type": pick(["closure", "outcome", "resolution"]),
            "closure_date": pick(["closure date", "date of order", "closing date"]),
            "resolution_applicant": pick(["resolution applicant", "acquirer", "buyer"]),
            "industry": pick(["industry", "sector", "classification"]),
            "claim_amount_cr": pick(["claim", "amount", "total claim"]),
            "data_source": source_file,
        }

    def test_connection(self) -> ConnectionTestResult:
        start = time.perf_counter()
        if self.mode == "bulk" and os.path.isdir(self.data_dir):
            files = [f for f in os.listdir(self.data_dir) if f.endswith((".xlsx", ".csv", ".xls"))]
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=bool(files),
                message=f"IBBI bulk mode: {len(files)} data file(s) in {self.data_dir}",
                response_time_ms=elapsed,
            )
        try:
            resp = httpx.get(
                f"{_IBBI_DATA_URL}/data/corporateinsolvency/outstanding",
                headers={"Accept": "application/json"},
                timeout=15,
                follow_redirects=True,
            )
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=resp.status_code < 400,
                message=f"IBBI API status: {resp.status_code}",
                response_time_ms=elapsed,
            )
        except Exception as exc:
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=False, message=str(exc),
                response_time_ms=elapsed, error=type(exc).__name__,
            )

    def extract_schema(self) -> SchemaDetectionResult:
        with self._timed_operation("ibbi_schema_detection"):
            columns = [
                {"name": "cirp_id", "type": "string", "nullable": False, "sample_values": []},
                {"name": "corporate_debtor_name", "type": "string", "nullable": False, "sample_values": []},
                {"name": "cin", "type": "string", "nullable": True, "sample_values": []},
                {"name": "nclt_bench", "type": "string", "nullable": True, "sample_values": ["Mumbai", "Delhi"]},
                {"name": "admission_date", "type": "string", "nullable": True, "sample_values": []},
                {"name": "resolution_professional", "type": "string", "nullable": True, "sample_values": []},
                {"name": "ip_registration", "type": "string", "nullable": True, "sample_values": []},
                {"name": "status", "type": "string", "nullable": True, "sample_values": ["Ongoing","Closed-RA","Closed-Liquidation"]},
                {"name": "closure_type", "type": "string", "nullable": True, "sample_values": []},
                {"name": "closure_date", "type": "string", "nullable": True, "sample_values": []},
                {"name": "resolution_applicant", "type": "string", "nullable": True, "sample_values": []},
                {"name": "industry", "type": "string", "nullable": True, "sample_values": []},
                {"name": "claim_amount_cr", "type": "string", "nullable": True, "sample_values": []},
                {"name": "data_source", "type": "string", "nullable": False, "sample_values": []},
            ]
            return SchemaDetectionResult(
                columns=columns,
                total_columns=len(columns),
                detected_primary_key="cirp_id",
                timestamp_columns=["admission_date", "closure_date"],
                indian_identifiers={"cin": "CIN"},
            )

    def extract_full(self, config: ExtractionConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            if self.mode == "bulk":
                records = self._load_from_files()
            else:
                records = self._fetch_ibbi_public_data()
            df = pd.DataFrame(records) if records else pd.DataFrame()
            # Filter out personal insolvency if not wanted
            if not self.include_personal and "status" in df.columns:
                df = df[~df.get("corporate_debtor_name", pd.Series()).str.contains(
                    r"\bHUF\b|proprietor|individual", case=False, na=False
                )]
            self.log_extraction(len(df), time.perf_counter() - start, 0)
            return df
        except Exception as exc:
            self.log_extraction(0, time.perf_counter() - start, 1)
            raise ExtractionError(self.source_id, f"IBBI extraction failed: {exc}") from exc

    def extract_incremental(self, config: IncrementalConfig) -> pd.DataFrame:
        # IBBI publishes quarterly data; full refresh is appropriate
        return self.extract_full(config)

    def get_record_count(self) -> int:
        if self.mode == "bulk" and os.path.isdir(self.data_dir):
            return sum(
                1 for f in os.listdir(self.data_dir)
                if f.endswith((".xlsx", ".csv", ".xls"))
            )
        return 0
