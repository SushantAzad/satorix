"""
MSME / Udyam Registration connector.

Extracts MSME (Micro, Small & Medium Enterprises) registration data from
the Udyam Registration Portal. Udyam replaced the old Udyog Aadhar system
from July 2020.

Use-cases:
  - Verify MSME status of a company (affects loan eligibility, government contracts)
  - Cross-reference Udyam number with PAN/GSTIN for entity linkage
  - Detect enterprises that registered as MSME but exceed size thresholds
  - Sector distribution analysis for portfolio companies

Udyam number format: UDYAM-XX-YY-NNNNNNN (state-category-serial)

Data sources:
  1. Sandbox.co.in MSME API (handles auth complexity)
  2. Udyam portal public lookup (https://udyamregistration.gov.in)
  3. Bulk data files from MoMSME

config keys:
  sandbox_api_key   : str   Sandbox.co.in API key
  mode              : "sandbox" | "bulk"  default "sandbox"
  data_dir          : str   path to bulk MSME data files
  udyam_numbers     : list  specific Udyam registration numbers
  pan_list          : list  PANs to look up associated Udyam registrations
  state_code        : str   2-letter state code filter
  category          : str   "micro" | "small" | "medium" | "all"  default "all"
  max_records       : int   default 5000
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

_SANDBOX_BASE = "https://api.sandbox.co.in"
_UDYAM_PUBLIC = "https://udyamregistration.gov.in/api"

_MSME_STATE_CODES = {
    "MH": "27", "DL": "07", "KA": "29", "GJ": "24", "TN": "33",
    "UP": "09", "WB": "19", "RJ": "08", "MP": "23", "TS": "36",
}


class MSMEConnector(BaseConnector):
    """MSME/Udyam registration connector."""

    REQUIRED_CONFIG_FIELDS: list[str] = []

    def __init__(self, source_id: str, config: dict) -> None:
        super().__init__(source_id, config)
        settings = get_settings()
        self.sandbox_api_key: str = config.get("sandbox_api_key", "") or settings.sandbox_api_key
        self.mode: str = config.get("mode", "sandbox")
        self.data_dir: str = config.get("data_dir", "/tmp/msme_data")
        self.udyam_numbers: list = config.get("udyam_numbers", [])
        self.pan_list: list = config.get("pan_list", [])
        self.state_code: str = config.get("state_code", "").upper()
        self.category: str = config.get("category", "all").lower()
        self.max_records: int = int(config.get("max_records", 5000))

    def _sandbox_headers(self) -> dict:
        return {
            "x-api-key": self.sandbox_api_key,
            "Content-Type": "application/json",
        }

    def _fetch_udyam_sandbox(self, udyam_number: str) -> Optional[dict]:
        try:
            resp = httpx.get(
                f"{_SANDBOX_BASE}/msme/udyam/{udyam_number}",
                headers=self._sandbox_headers(),
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
            logger.debug("MSME Udyam fetch failed for %s: %s", udyam_number, exc)
            return None

    def _fetch_by_pan_sandbox(self, pan: str) -> list[dict]:
        try:
            resp = httpx.get(
                f"{_SANDBOX_BASE}/msme/udyam/search",
                headers=self._sandbox_headers(),
                params={"pan": pan},
                timeout=20,
            )
            if resp.status_code == 401:
                raise AuthenticationError(self.source_id, "Invalid Sandbox.co.in API key")
            resp.raise_for_status()
            data = resp.json().get("data", [])
            return data if isinstance(data, list) else [data]
        except AuthenticationError:
            raise
        except Exception as exc:
            logger.debug("MSME PAN search failed for %s: %s", pan, exc)
            return []

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
                logger.warning("Failed to parse MSME file %s: %s", fname, exc)
        return records

    def _normalize_udyam(self, data: dict) -> dict:
        return {
            "udyam_number": data.get("udyam_number") or data.get("registration_number", ""),
            "enterprise_name": data.get("enterprise_name") or data.get("name", ""),
            "owner_name": data.get("owner_name") or data.get("proprietor_name", ""),
            "pan": data.get("pan", ""),
            "gstin": data.get("gstin", ""),
            "state": data.get("state", self.state_code),
            "district": data.get("district", ""),
            "pincode": data.get("pincode") or data.get("pin_code", ""),
            "enterprise_type": data.get("enterprise_type") or data.get("type", ""),
            "category": data.get("category") or data.get("msme_category", ""),
            "major_activity": data.get("major_activity") or data.get("activity", ""),
            "nic_code": data.get("nic_code") or data.get("nic", ""),
            "registration_date": data.get("registration_date") or data.get("reg_date", ""),
            "investment_plant": data.get("investment_in_plant") or data.get("plant_machinery", ""),
            "turnover": data.get("turnover") or data.get("annual_turnover", ""),
            "employment_male": data.get("employment_male") or data.get("male_employees", ""),
            "employment_female": data.get("employment_female") or data.get("female_employees", ""),
            "social_category": data.get("social_category", ""),
            "status": data.get("status", "Active"),
        }

    def _normalize_row(self, row: dict) -> dict:
        def pick(keys: list[str]) -> str:
            for k in keys:
                for col, val in row.items():
                    if k.lower() in str(col).lower() and val and str(val) not in ("nan", ""):
                        return str(val).strip()
            return ""

        return {
            "udyam_number": pick(["udyam", "registration no", "udyog"]),
            "enterprise_name": pick(["enterprise name", "name", "firm name"]),
            "owner_name": pick(["owner", "proprietor", "partner"]),
            "pan": pick(["pan"]),
            "gstin": pick(["gstin", "gst"]),
            "state": pick(["state"]) or self.state_code,
            "district": pick(["district"]),
            "pincode": pick(["pin", "pincode"]),
            "enterprise_type": pick(["enterprise type", "type", "constitution"]),
            "category": pick(["category", "class", "msme class"]),
            "major_activity": pick(["major activity", "activity", "industry"]),
            "nic_code": pick(["nic", "nic code"]),
            "registration_date": pick(["registration date", "reg date"]),
            "investment_plant": pick(["plant", "investment in plant", "machinery"]),
            "turnover": pick(["turnover", "annual turnover"]),
            "employment_male": pick(["male", "male employee"]),
            "employment_female": pick(["female", "female employee"]),
            "social_category": pick(["social", "category sc st"]),
            "status": pick(["status"]) or "Active",
        }

    def test_connection(self) -> ConnectionTestResult:
        start = time.perf_counter()
        if self.mode == "bulk":
            files = [f for f in os.listdir(self.data_dir) if f.endswith((".xlsx", ".csv"))] if os.path.isdir(self.data_dir) else []
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=bool(files),
                message=f"MSME bulk mode: {len(files)} file(s) in {self.data_dir}",
                response_time_ms=elapsed,
            )
        try:
            resp = httpx.get(
                f"{_SANDBOX_BASE}/msme/udyam/search",
                headers=self._sandbox_headers(),
                params={"pan": "AAACN5014H"},
                timeout=15,
            )
            if resp.status_code == 401:
                raise AuthenticationError(self.source_id, "Invalid Sandbox.co.in API key")
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=resp.status_code < 400,
                message=f"MSME Sandbox API status: {resp.status_code}",
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
        with self._timed_operation("msme_schema_detection"):
            columns = [
                {"name": "udyam_number", "type": "string", "nullable": False, "sample_values": ["UDYAM-MH-27-0000001"]},
                {"name": "enterprise_name", "type": "string", "nullable": False, "sample_values": []},
                {"name": "owner_name", "type": "string", "nullable": True, "sample_values": []},
                {"name": "pan", "type": "string", "nullable": True, "sample_values": []},
                {"name": "gstin", "type": "string", "nullable": True, "sample_values": []},
                {"name": "state", "type": "string", "nullable": True, "sample_values": []},
                {"name": "district", "type": "string", "nullable": True, "sample_values": []},
                {"name": "category", "type": "string", "nullable": True, "sample_values": ["Micro","Small","Medium"]},
                {"name": "major_activity", "type": "string", "nullable": True, "sample_values": ["Manufacturing","Services","Trading"]},
                {"name": "registration_date", "type": "string", "nullable": True, "sample_values": []},
                {"name": "investment_plant", "type": "string", "nullable": True, "sample_values": []},
                {"name": "turnover", "type": "string", "nullable": True, "sample_values": []},
                {"name": "employment_male", "type": "string", "nullable": True, "sample_values": []},
                {"name": "employment_female", "type": "string", "nullable": True, "sample_values": []},
                {"name": "status", "type": "string", "nullable": True, "sample_values": ["Active","Cancelled"]},
            ]
            return SchemaDetectionResult(
                columns=columns,
                total_columns=len(columns),
                detected_primary_key="udyam_number",
                timestamp_columns=["registration_date"],
                indian_identifiers={"pan": "PAN", "gstin": "GSTIN", "udyam_number": "UDYAM"},
            )

    def extract_full(self, config: ExtractionConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            if self.mode == "bulk":
                records = self._load_from_files()
            else:
                records = []
                for num in self.udyam_numbers[: self.max_records]:
                    data = self._fetch_udyam_sandbox(num)
                    if data:
                        records.append(self._normalize_udyam(data))
                    time.sleep(0.1)
                for pan in self.pan_list[: self.max_records]:
                    results = self._fetch_by_pan_sandbox(pan)
                    for r in results:
                        records.append(self._normalize_udyam(r))
                    time.sleep(0.1)

            df = pd.DataFrame(records) if records else pd.DataFrame()
            if self.category != "all" and not df.empty and "category" in df.columns:
                df = df[df["category"].str.lower() == self.category]
            if self.state_code and not df.empty and "state" in df.columns:
                df = df[df["state"].str.upper() == self.state_code]
            self.log_extraction(len(df), time.perf_counter() - start, 0)
            return df
        except Exception as exc:
            self.log_extraction(0, time.perf_counter() - start, 1)
            raise ExtractionError(self.source_id, f"MSME extraction failed: {exc}") from exc

    def extract_incremental(self, config: IncrementalConfig) -> pd.DataFrame:
        return self.extract_full(config)

    def get_record_count(self) -> int:
        return len(self.udyam_numbers) + len(self.pan_list)
