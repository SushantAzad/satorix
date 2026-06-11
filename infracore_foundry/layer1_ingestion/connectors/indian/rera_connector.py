"""
RERA (Real Estate Regulatory Authority) connector.

Extracts real estate project registrations, promoter details, and project
status from state RERA portals. Essential for the Project entity type in the
graph — every RERA-registered project has a promoter company (linkable via CIN)
and registered agents.

Each Indian state has its own RERA portal. This connector uses:
  1. Sandbox.co.in RERA API (aggregated, multi-state)
  2. State-specific RERA APIs (Maharashtra MahaRERA, Karnataka K-RERA, etc.)

MahaRERA is the most complete and has the best API coverage.

config keys:
  sandbox_api_key   : str
  mode              : "sandbox" | "maharera" | "bulk"
  state             : str   state code e.g. "MH", "KA", "DL", "TN"
  project_ids       : list  specific RERA project registration numbers
  promoter_cins     : list  CINs of promoter companies to find all their projects
  data_dir          : str   path to bulk-downloaded RERA files
  project_type      : str   "residential" | "commercial" | "all"  default "all"
  max_records       : int   default 5000
"""

import logging
import os
import time
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
_MAHARERA_API = "https://maharera.maharashtra.gov.in/api/public"

# RERA state portal base URLs (public APIs where available)
_STATE_RERA_APIS = {
    "MH": "https://maharera.maharashtra.gov.in/api/public",
    "KA": "https://rera.karnataka.gov.in/api/v1",
    "DL": "https://rera.delhi.gov.in/api",
    "TN": "https://www.tnrera.in/api",
    "GJ": "https://gujrera.gujarat.gov.in/api",
    "HR": "https://hrera.in/api",
    "UP": "https://up-rera.in/api",
    "WB": "https://hira.wb.gov.in/api",
    "TS": "https://tsrera.telangana.gov.in/api",
    "RJ": "https://rera.rajasthan.gov.in/api",
}


class RERAConnector(BaseConnector):
    """RERA real estate project registry connector."""

    REQUIRED_CONFIG_FIELDS: list[str] = []

    def __init__(self, source_id: str, config: dict) -> None:
        super().__init__(source_id, config)
        settings = get_settings()
        self.sandbox_api_key: str = config.get("sandbox_api_key", "") or settings.sandbox_api_key
        self.mode: str = config.get("mode", "sandbox")
        self.state: str = config.get("state", "MH").upper()
        self.project_ids: list = config.get("project_ids", [])
        self.promoter_cins: list = config.get("promoter_cins", [])
        self.data_dir: str = config.get("data_dir", "/tmp/rera_data")
        self.project_type: str = config.get("project_type", "all")
        self.max_records: int = int(config.get("max_records", 5000))

    def _sandbox_headers(self) -> dict:
        return {
            "x-api-key": self.sandbox_api_key,
            "Content-Type": "application/json",
        }

    def _fetch_sandbox_project(self, project_id: str) -> Optional[dict]:
        try:
            resp = httpx.get(
                f"{_SANDBOX_BASE}/rera/mh/projects/{project_id}",
                headers=self._sandbox_headers(),
                timeout=15,
            )
            if resp.status_code == 401:
                raise AuthenticationError(self.source_id, "Invalid Sandbox.co.in API key")
            resp.raise_for_status()
            return resp.json().get("data", {})
        except AuthenticationError:
            raise
        except Exception as exc:
            logger.debug("RERA project %s fetch failed: %s", project_id, exc)
            return None

    def _fetch_maharera_public(self) -> list[dict]:
        """Fetch from MahaRERA public search API."""
        records: list[dict] = []
        page = 1
        headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
        while len(records) < self.max_records:
            try:
                resp = httpx.get(
                    f"{_MAHARERA_API}/projects",
                    headers=headers,
                    params={"page": page, "limit": 100, "status": "REGISTERED"},
                    timeout=20,
                )
                resp.raise_for_status()
                data = resp.json()
                projects = data.get("projects", data.get("data", []))
                if not projects:
                    break
                for p in projects:
                    records.append(self._normalize_project(p))
                if len(projects) < 100:
                    break
                page += 1
            except Exception as exc:
                logger.warning("MahaRERA page %d failed: %s", page, exc)
                break
        return records

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
                else:
                    continue
                for _, row in df.iterrows():
                    records.append(self._normalize_row(row.to_dict()))
            except Exception as exc:
                logger.warning("Failed to parse RERA file %s: %s", fname, exc)
        return records

    def _normalize_project(self, p: dict) -> dict:
        return {
            "rera_id": p.get("rera_id") or p.get("project_id") or p.get("registration_number", ""),
            "project_name": p.get("project_name") or p.get("name", ""),
            "promoter_name": p.get("promoter_name") or p.get("developer_name", ""),
            "promoter_cin": p.get("cin", ""),
            "state": p.get("state", self.state),
            "district": p.get("district", ""),
            "pin_code": p.get("pin_code") or p.get("pincode", ""),
            "project_type": p.get("project_type") or p.get("type", ""),
            "registration_date": p.get("registration_date") or p.get("reg_date", ""),
            "expiry_date": p.get("expiry_date") or p.get("exp_date", ""),
            "status": p.get("status", ""),
            "total_units": p.get("total_units") or p.get("sanctioned_units", ""),
            "units_sold": p.get("units_sold") or p.get("sold_units", ""),
            "expected_completion": p.get("expected_completion") or p.get("completion_date", ""),
            "actual_completion": p.get("actual_completion", ""),
            "is_delayed": str(p.get("is_delayed", "")),
        }

    def _normalize_row(self, row: dict) -> dict:
        def pick(keys: list[str]) -> str:
            for k in keys:
                for col, val in row.items():
                    if k.lower() in str(col).lower() and val and str(val) not in ("nan", ""):
                        return str(val).strip()
            return ""
        return {
            "rera_id": pick(["rera", "registration no", "project id"]),
            "project_name": pick(["project name", "name"]),
            "promoter_name": pick(["promoter", "developer", "builder"]),
            "promoter_cin": pick(["cin"]),
            "state": pick(["state"]) or self.state,
            "district": pick(["district"]),
            "pin_code": pick(["pin", "pincode", "postal"]),
            "project_type": pick(["type", "category"]),
            "registration_date": pick(["registration date", "reg date"]),
            "expiry_date": pick(["expiry", "expiry date"]),
            "status": pick(["status"]),
            "total_units": pick(["total units", "sanctioned"]),
            "units_sold": pick(["sold", "units sold", "booked"]),
            "expected_completion": pick(["expected completion", "completion date"]),
            "actual_completion": pick(["actual completion", "completion"]),
            "is_delayed": pick(["delayed", "delay"]),
        }

    def test_connection(self) -> ConnectionTestResult:
        start = time.perf_counter()
        if self.mode == "bulk":
            files = [f for f in os.listdir(self.data_dir) if f.endswith((".xlsx", ".csv"))] if os.path.isdir(self.data_dir) else []
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=bool(files),
                message=f"RERA bulk mode: {len(files)} file(s) in {self.data_dir}",
                response_time_ms=elapsed,
            )
        try:
            resp = httpx.get(
                f"{_MAHARERA_API}/projects",
                headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
                params={"page": 1, "limit": 1},
                timeout=15,
            )
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=resp.status_code < 400,
                message=f"MahaRERA API status: {resp.status_code}",
                response_time_ms=elapsed,
            )
        except Exception as exc:
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=False, message=str(exc),
                response_time_ms=elapsed, error=type(exc).__name__,
            )

    def extract_schema(self) -> SchemaDetectionResult:
        with self._timed_operation("rera_schema_detection"):
            columns = [
                {"name": "rera_id", "type": "string", "nullable": False, "sample_values": []},
                {"name": "project_name", "type": "string", "nullable": False, "sample_values": []},
                {"name": "promoter_name", "type": "string", "nullable": True, "sample_values": []},
                {"name": "promoter_cin", "type": "string", "nullable": True, "sample_values": []},
                {"name": "state", "type": "string", "nullable": False, "sample_values": ["MH","KA","DL"]},
                {"name": "district", "type": "string", "nullable": True, "sample_values": []},
                {"name": "pin_code", "type": "string", "nullable": True, "sample_values": []},
                {"name": "project_type", "type": "string", "nullable": True, "sample_values": ["Residential","Commercial"]},
                {"name": "registration_date", "type": "string", "nullable": True, "sample_values": []},
                {"name": "expiry_date", "type": "string", "nullable": True, "sample_values": []},
                {"name": "status", "type": "string", "nullable": True, "sample_values": ["REGISTERED","REVOKED","LAPSED"]},
                {"name": "total_units", "type": "string", "nullable": True, "sample_values": []},
                {"name": "units_sold", "type": "string", "nullable": True, "sample_values": []},
                {"name": "expected_completion", "type": "string", "nullable": True, "sample_values": []},
                {"name": "is_delayed", "type": "string", "nullable": True, "sample_values": []},
            ]
            return SchemaDetectionResult(
                columns=columns,
                total_columns=len(columns),
                detected_primary_key="rera_id",
                timestamp_columns=["registration_date", "expiry_date", "expected_completion"],
                indian_identifiers={"rera_id": "RERA", "promoter_cin": "CIN"},
            )

    def extract_full(self, config: ExtractionConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            if self.mode == "bulk":
                records = self._load_from_files()
            elif self.mode == "sandbox" and self.project_ids:
                records = [
                    self._normalize_project(r)
                    for pid in self.project_ids
                    if (r := self._fetch_sandbox_project(pid)) is not None
                ]
            else:
                records = self._fetch_maharera_public()

            df = pd.DataFrame(records) if records else pd.DataFrame()
            if self.project_type != "all" and not df.empty and "project_type" in df.columns:
                df = df[df["project_type"].str.lower() == self.project_type.lower()]
            self.log_extraction(len(df), time.perf_counter() - start, 0)
            return df
        except Exception as exc:
            self.log_extraction(0, time.perf_counter() - start, 1)
            raise ExtractionError(self.source_id, f"RERA extraction failed: {exc}") from exc

    def extract_incremental(self, config: IncrementalConfig) -> pd.DataFrame:
        return self.extract_full(config)

    def get_record_count(self) -> int:
        return len(self.project_ids) or 0
