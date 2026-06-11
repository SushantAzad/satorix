"""
QuickBooks Online connector via Intuit OAuth2 API.

Extracts financial data from QuickBooks Online: customers, vendors,
invoices, bills, chart of accounts, profit & loss reports, and transactions.

config keys:
  client_id         : str   QuickBooks OAuth2 client ID
  client_secret     : str   QuickBooks OAuth2 client secret
  refresh_token     : str   OAuth2 refresh token (long-lived)
  realm_id          : str   QuickBooks company/realm ID
  environment       : "production" | "sandbox"  default "production"
  entity_types      : list  e.g. ["Customer","Invoice","Bill"]  default all
  max_records       : int   default 5000
"""

import logging
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

logger = logging.getLogger(__name__)

_PROD_BASE = "https://quickbooks.api.intuit.com/v3/company"
_SANDBOX_BASE = "https://sandbox-quickbooks.api.intuit.com/v3/company"
_TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"

_DEFAULT_ENTITIES = [
    "Customer", "Vendor", "Invoice", "Bill", "Payment",
    "Account", "Item", "Employee", "JournalEntry",
]


class QuickBooksConnector(BaseConnector):
    """QuickBooks Online financial data connector."""

    REQUIRED_CONFIG_FIELDS: list[str] = ["client_id", "client_secret", "refresh_token", "realm_id"]

    def __init__(self, source_id: str, config: dict) -> None:
        super().__init__(source_id, config)
        self.client_id: str = config.get("client_id", "")
        self.client_secret: str = config.get("client_secret", "")
        self.refresh_token: str = config.get("refresh_token", "")
        self.realm_id: str = config.get("realm_id", "")
        self.environment: str = config.get("environment", "production")
        self.entity_types: list = config.get("entity_types", _DEFAULT_ENTITIES)
        self.max_records: int = int(config.get("max_records", 5000))
        self._access_token: str = ""
        self._token_expires: float = 0.0

    @property
    def _base_url(self) -> str:
        base = _SANDBOX_BASE if self.environment == "sandbox" else _PROD_BASE
        return f"{base}/{self.realm_id}"

    def _ensure_token(self) -> None:
        if self._access_token and time.time() < self._token_expires - 60:
            return
        try:
            resp = httpx.post(
                _TOKEN_URL,
                data={"grant_type": "refresh_token", "refresh_token": self.refresh_token},
                auth=(self.client_id, self.client_secret),
                headers={"Accept": "application/json"},
                timeout=15,
            )
            if resp.status_code == 401:
                raise AuthenticationError(self.source_id, "Invalid QuickBooks credentials")
            resp.raise_for_status()
            data = resp.json()
            self._access_token = data["access_token"]
            self._token_expires = time.time() + data.get("expires_in", 3600)
            # Refresh token may rotate
            if "refresh_token" in data:
                self.refresh_token = data["refresh_token"]
        except AuthenticationError:
            raise
        except Exception as exc:
            raise AuthenticationError(self.source_id, f"Token refresh failed: {exc}") from exc

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json",
        }

    def _query(self, entity: str, where_clause: str = "", start: int = 1, max_results: int = 1000) -> list[dict]:
        self._ensure_token()
        query = f"SELECT * FROM {entity}"
        if where_clause:
            query += f" WHERE {where_clause}"
        query += f" STARTPOSITION {start} MAXRESULTS {max_results}"
        try:
            resp = httpx.get(
                f"{self._base_url}/query",
                headers=self._headers(),
                params={"query": query, "minorversion": "65"},
                timeout=30,
            )
            if resp.status_code == 401:
                raise AuthenticationError(self.source_id, "QuickBooks token expired")
            resp.raise_for_status()
            data = resp.json()
            query_response = data.get("QueryResponse", {})
            results = query_response.get(entity, [])
            return results if isinstance(results, list) else []
        except AuthenticationError:
            raise
        except Exception as exc:
            logger.warning("QuickBooks query for %s failed: %s", entity, exc)
            return []

    def _flatten_entity(self, entity: str, record: dict) -> dict:
        flat: dict = {"entity_type": entity}
        for k, v in record.items():
            if isinstance(v, dict):
                if "value" in v and len(v) <= 3:
                    flat[k] = v.get("value", "")
                    if "name" in v:
                        flat[f"{k}_name"] = v.get("name", "")
                else:
                    for sk, sv in v.items():
                        if not isinstance(sv, (dict, list)):
                            flat[f"{k}_{sk}"] = sv
            elif isinstance(v, list):
                flat[k] = str(v)
            else:
                flat[k] = v
        return flat

    def test_connection(self) -> ConnectionTestResult:
        start = time.perf_counter()
        try:
            self._ensure_token()
            resp = httpx.get(
                f"{self._base_url}/companyinfo/{self.realm_id}",
                headers=self._headers(),
                params={"minorversion": "65"},
                timeout=15,
            )
            resp.raise_for_status()
            info = resp.json().get("CompanyInfo", {})
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=True,
                message=f"QuickBooks: {info.get('CompanyName', self.realm_id)}",
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
        with self._timed_operation("quickbooks_schema_detection"):
            columns = [
                {"name": "entity_type", "type": "string", "nullable": False, "sample_values": _DEFAULT_ENTITIES},
                {"name": "Id", "type": "string", "nullable": False, "sample_values": []},
                {"name": "SyncToken", "type": "string", "nullable": True, "sample_values": []},
                {"name": "MetaData_CreateTime", "type": "string", "nullable": True, "sample_values": []},
                {"name": "MetaData_LastUpdatedTime", "type": "string", "nullable": True, "sample_values": []},
                {"name": "DisplayName", "type": "string", "nullable": True, "sample_values": []},
                {"name": "Active", "type": "bool", "nullable": True, "sample_values": []},
                {"name": "Balance", "type": "float64", "nullable": True, "sample_values": []},
                {"name": "TxnDate", "type": "string", "nullable": True, "sample_values": []},
                {"name": "TotalAmt", "type": "float64", "nullable": True, "sample_values": []},
            ]
            return SchemaDetectionResult(
                columns=columns,
                total_columns=len(columns),
                detected_primary_key="Id",
                timestamp_columns=["MetaData_CreateTime", "MetaData_LastUpdatedTime", "TxnDate"],
            )

    def extract_full(self, config: ExtractionConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            all_records: list[dict] = []
            for entity in self.entity_types:
                page_start = 1
                while len(all_records) < self.max_records:
                    batch = self._query(entity, start=page_start, max_results=min(1000, self.max_records - len(all_records)))
                    if not batch:
                        break
                    for rec in batch:
                        all_records.append(self._flatten_entity(entity, rec))
                    if len(batch) < 1000:
                        break
                    page_start += len(batch)
            df = pd.DataFrame(all_records) if all_records else pd.DataFrame()
            self.log_extraction(len(df), time.perf_counter() - start, 0)
            return df
        except Exception as exc:
            self.log_extraction(0, time.perf_counter() - start, 1)
            raise ExtractionError(self.source_id, f"QuickBooks extraction failed: {exc}") from exc

    def extract_incremental(self, config: IncrementalConfig) -> pd.DataFrame:
        if config.last_extracted_at:
            ts = config.last_extracted_at.strftime("%Y-%m-%dT%H:%M:%S")
            all_records: list[dict] = []
            for entity in self.entity_types:
                batch = self._query(entity, where_clause=f"MetaData.LastUpdatedTime >= '{ts}'")
                for rec in batch:
                    all_records.append(self._flatten_entity(entity, rec))
            return pd.DataFrame(all_records) if all_records else pd.DataFrame()
        return self.extract_full(config)

    def get_record_count(self) -> int:
        try:
            self._ensure_token()
            total = 0
            for entity in self.entity_types:
                result = self._query(f"SELECT COUNT(*) FROM {entity}".split()[-1], max_results=1)
                total += len(result)
            return total
        except Exception:
            return 0
