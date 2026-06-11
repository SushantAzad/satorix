"""
EPFO (Employees' Provident Fund Organisation) connector.

Extracts employee provident fund data: establishment registration,
compliance status, ECR (Electronic Challan-cum-Return) filing status,
and employee count data.

This data is extremely valuable for:
  - Verifying headcount claims by companies
  - Checking ESI/EPF compliance (non-compliance = financial risk indicator)
  - Linking employees to establishments via UAN numbers

Data sources:
  1. Sandbox.co.in EPFO API (recommended — handles complexity)
  2. EPFO public data portal (https://epfindia.gov.in)
  3. Bulk CSV files from EPFO public dataset

config keys:
  sandbox_api_key   : str   Sandbox.co.in API key
  mode              : "sandbox" | "bulk" | "api"  default "sandbox"
  data_dir          : str   path to downloaded EPFO files
  establishment_ids : list  EPFO establishment IDs to look up
  pan_list          : list  PANs of companies to check EPFO status
  state_code        : str   filter by state (2-letter code)
  compliance_only   : bool  return only non-compliant establishments
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
_EPFO_PUBLIC = "https://unifiedportal-mem.epfindia.gov.in/publicPortal/api"


class EPFOConnector(BaseConnector):
    """EPFO employee provident fund and compliance connector."""

    REQUIRED_CONFIG_FIELDS: list[str] = []

    def __init__(self, source_id: str, config: dict) -> None:
        super().__init__(source_id, config)
        settings = get_settings()
        self.sandbox_api_key: str = config.get("sandbox_api_key", "") or settings.sandbox_api_key
        self.mode: str = config.get("mode", "sandbox")
        self.data_dir: str = config.get("data_dir", "/tmp/epfo_data")
        self.establishment_ids: list = config.get("establishment_ids", [])
        self.pan_list: list = config.get("pan_list", [])
        self.state_code: str = config.get("state_code", "").upper()
        self.compliance_only: bool = bool(config.get("compliance_only", False))
        self.max_records: int = int(config.get("max_records", 5000))

    def _sandbox_headers(self) -> dict:
        return {
            "x-api-key": self.sandbox_api_key,
            "Content-Type": "application/json",
        }

    def _fetch_establishment_sandbox(self, establishment_id: str) -> Optional[dict]:
        try:
            resp = httpx.get(
                f"{_SANDBOX_BASE}/epfo/establishments/{establishment_id}",
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
            logger.debug("EPFO establishment fetch failed for %s: %s", establishment_id, exc)
            return None

    def _fetch_by_pan_sandbox(self, pan: str) -> list[dict]:
        try:
            resp = httpx.get(
                f"{_SANDBOX_BASE}/epfo/establishments/search",
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
            logger.debug("EPFO PAN search failed for %s: %s", pan, exc)
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
                logger.warning("Failed to parse EPFO file %s: %s", fname, exc)
        return records

    def _normalize_establishment(self, data: dict) -> dict:
        return {
            "establishment_id": data.get("establishment_id") or data.get("est_id", ""),
            "establishment_name": data.get("establishment_name") or data.get("name", ""),
            "pan": data.get("pan", ""),
            "address": data.get("address", ""),
            "state": data.get("state", self.state_code),
            "district": data.get("district", ""),
            "pincode": data.get("pincode") or data.get("pin_code", ""),
            "industry_type": data.get("industry_type") or data.get("industry", ""),
            "employee_count": data.get("employee_count") or data.get("headcount", ""),
            "registration_date": data.get("registration_date") or data.get("reg_date", ""),
            "compliance_status": data.get("compliance_status") or data.get("status", ""),
            "ecr_filed_months": data.get("ecr_filed_months") or data.get("filing_months", ""),
            "last_ecr_date": data.get("last_ecr_date") or data.get("last_filing", ""),
            "pf_contribution": data.get("pf_contribution") or data.get("contribution_amount", ""),
            "exemption_type": data.get("exemption_type", ""),
            "is_compliant": str(data.get("is_compliant", "")),
        }

    def _normalize_row(self, row: dict) -> dict:
        def pick(keys: list[str]) -> str:
            for k in keys:
                for col, val in row.items():
                    if k.lower() in str(col).lower() and val and str(val) not in ("nan", ""):
                        return str(val).strip()
            return ""

        return {
            "establishment_id": pick(["establishment id", "est id", "epfo id"]),
            "establishment_name": pick(["establishment name", "name", "company"]),
            "pan": pick(["pan"]),
            "address": pick(["address"]),
            "state": pick(["state"]) or self.state_code,
            "district": pick(["district"]),
            "pincode": pick(["pin", "pincode"]),
            "industry_type": pick(["industry", "type", "sector"]),
            "employee_count": pick(["employee count", "headcount", "employees", "members"]),
            "registration_date": pick(["registration date", "reg date"]),
            "compliance_status": pick(["compliance", "status"]),
            "ecr_filed_months": pick(["ecr filed", "filed months", "ecr"]),
            "last_ecr_date": pick(["last ecr", "last filing"]),
            "pf_contribution": pick(["pf contribution", "contribution amount"]),
            "exemption_type": pick(["exemption"]),
            "is_compliant": pick(["compliant", "compliance flag"]),
        }

    def test_connection(self) -> ConnectionTestResult:
        start = time.perf_counter()
        if self.mode == "bulk":
            files = [f for f in os.listdir(self.data_dir) if f.endswith((".xlsx", ".csv"))] if os.path.isdir(self.data_dir) else []
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=bool(files),
                message=f"EPFO bulk mode: {len(files)} file(s) in {self.data_dir}",
                response_time_ms=elapsed,
            )
        try:
            resp = httpx.get(
                f"{_SANDBOX_BASE}/epfo/establishments/search",
                headers=self._sandbox_headers(),
                params={"pan": "AAACN5014H"},
                timeout=15,
            )
            if resp.status_code == 401:
                raise AuthenticationError(self.source_id, "Invalid Sandbox.co.in API key")
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=resp.status_code < 400,
                message=f"EPFO Sandbox API status: {resp.status_code}",
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
        with self._timed_operation("epfo_schema_detection"):
            columns = [
                {"name": "establishment_id", "type": "string", "nullable": False, "sample_values": []},
                {"name": "establishment_name", "type": "string", "nullable": False, "sample_values": []},
                {"name": "pan", "type": "string", "nullable": True, "sample_values": []},
                {"name": "state", "type": "string", "nullable": True, "sample_values": []},
                {"name": "district", "type": "string", "nullable": True, "sample_values": []},
                {"name": "industry_type", "type": "string", "nullable": True, "sample_values": []},
                {"name": "employee_count", "type": "string", "nullable": True, "sample_values": []},
                {"name": "registration_date", "type": "string", "nullable": True, "sample_values": []},
                {"name": "compliance_status", "type": "string", "nullable": True, "sample_values": ["Compliant","Defaulter","Exempted"]},
                {"name": "ecr_filed_months", "type": "string", "nullable": True, "sample_values": []},
                {"name": "last_ecr_date", "type": "string", "nullable": True, "sample_values": []},
                {"name": "pf_contribution", "type": "string", "nullable": True, "sample_values": []},
                {"name": "is_compliant", "type": "string", "nullable": True, "sample_values": []},
            ]
            return SchemaDetectionResult(
                columns=columns,
                total_columns=len(columns),
                detected_primary_key="establishment_id",
                timestamp_columns=["registration_date", "last_ecr_date"],
                indian_identifiers={"pan": "PAN"},
            )

    def extract_full(self, config: ExtractionConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            if self.mode == "bulk":
                records = self._load_from_files()
            elif self.mode == "sandbox":
                records = []
                for est_id in self.establishment_ids[: self.max_records]:
                    data = self._fetch_establishment_sandbox(est_id)
                    if data:
                        records.append(self._normalize_establishment(data))
                    time.sleep(0.1)
                for pan in self.pan_list[: self.max_records]:
                    results = self._fetch_by_pan_sandbox(pan)
                    for r in results:
                        records.append(self._normalize_establishment(r))
                    time.sleep(0.1)
            else:
                records = []

            df = pd.DataFrame(records) if records else pd.DataFrame()
            if self.compliance_only and not df.empty and "is_compliant" in df.columns:
                df = df[df["is_compliant"].str.lower().isin(["false", "0", "no", "defaulter"])]
            if self.state_code and not df.empty and "state" in df.columns:
                df = df[df["state"].str.upper() == self.state_code]
            self.log_extraction(len(df), time.perf_counter() - start, 0)
            return df
        except Exception as exc:
            self.log_extraction(0, time.perf_counter() - start, 1)
            raise ExtractionError(self.source_id, f"EPFO extraction failed: {exc}") from exc

    def extract_incremental(self, config: IncrementalConfig) -> pd.DataFrame:
        return self.extract_full(config)

    def get_record_count(self) -> int:
        return len(self.establishment_ids) + len(self.pan_list)
