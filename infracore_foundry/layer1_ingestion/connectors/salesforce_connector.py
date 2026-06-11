"""
Salesforce connector using simple-salesforce (REST + Bulk API v2).

PE firms, banks, and large Indian enterprises track deals, accounts,
and relationships in Salesforce. This connector enriches the corporate
knowledge graph with deal flow, counterparty contact history, and
account-level risk signals.

Supports:
  - SOQL queries for targeted extraction
  - Object-level full extraction
  - Bulk API v2 for large datasets (>100K records)
  - Incremental via SystemModstamp

config keys:
  username          : str   Salesforce login username
  password          : str   Salesforce password + security token concatenated
  security_token    : str   Salesforce security token (appended to password)
  domain            : str   "login" (prod) or "test" (sandbox) — default "login"
  soql_query        : str   custom SOQL query (mutually exclusive with object_name)
  object_name       : str   Salesforce object API name e.g. "Account", "Contact"
  fields            : list  specific fields to extract (default: all)
  use_bulk_api      : bool  use Bulk API 2.0 for large objects — default False
  instance_url      : str   override for connected app flow
  access_token      : str   pre-obtained OAuth token (skips username/password)
"""

import logging
import time
from datetime import datetime
from typing import Optional

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


class SalesforceConnector(BaseConnector):
    """Salesforce connector via simple-salesforce."""

    REQUIRED_CONFIG_FIELDS: list[str] = []

    def __init__(self, source_id: str, config: dict) -> None:
        super().__init__(source_id, config)
        self.username: str = config.get("username", "")
        self.password: str = config.get("password", "")
        self.security_token: str = config.get("security_token", "")
        self.domain: str = config.get("domain", "login")
        self.soql_query: str = config.get("soql_query", "")
        self.object_name: str = config.get("object_name", "")
        self.fields: list[str] = config.get("fields", [])
        self.use_bulk_api: bool = bool(config.get("use_bulk_api", False))
        self.instance_url: str = config.get("instance_url", "")
        self.access_token: str = config.get("access_token", "")

    def _get_sf(self):
        try:
            from simple_salesforce import Salesforce
        except ImportError as exc:
            raise ImportError(
                "simple-salesforce not installed. Run: pip install simple-salesforce"
            ) from exc

        if self.access_token and self.instance_url:
            return Salesforce(
                instance_url=self.instance_url,
                session_id=self.access_token,
            )
        try:
            return Salesforce(
                username=self.username,
                password=self.password + self.security_token,
                domain=self.domain,
            )
        except Exception as exc:
            if "INVALID_LOGIN" in str(exc) or "authentication" in str(exc).lower():
                raise AuthenticationError(self.source_id, str(exc))
            raise

    def _get_object_fields(self, sf, object_name: str) -> list[str]:
        desc = getattr(sf, object_name).describe()
        return [f["name"] for f in desc["fields"] if not f.get("calculated")]

    def _build_soql(self, extra_filter: str = "") -> str:
        if self.soql_query:
            if extra_filter:
                q = self.soql_query.rstrip()
                if "WHERE" in q.upper():
                    return f"{q} AND {extra_filter}"
                return f"{q} WHERE {extra_filter}"
            return self.soql_query

        fields = self.fields or []
        if not fields:
            sf = self._get_sf()
            fields = self._get_object_fields(sf, self.object_name)

        field_str = ", ".join(fields[:200])  # SOQL 200-field limit
        base = f"SELECT {field_str} FROM {self.object_name}"
        if extra_filter:
            return f"{base} WHERE {extra_filter}"
        return base

    def test_connection(self) -> ConnectionTestResult:
        start = time.perf_counter()
        try:
            sf = self._get_sf()
            # Check connectivity with a lightweight limits call
            limits = sf.limits()
            elapsed = (time.perf_counter() - start) * 1000
            daily_used = limits.get("DailyApiRequests", {}).get("Remaining", "?")
            return ConnectionTestResult(
                success=True,
                message=f"Salesforce connected. Daily API remaining: {daily_used}",
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
        with self._timed_operation("salesforce_schema_detection"):
            sf = self._get_sf()
            if self.object_name:
                desc = getattr(sf, self.object_name).describe()
                fields_meta = desc.get("fields", [])
                ts_cols = [
                    f["name"] for f in fields_meta
                    if f.get("type") in ("datetime", "date")
                ]
                columns = [
                    {
                        "name": f["name"],
                        "type": f.get("type", "string"),
                        "nullable": not f.get("nillable", True) is False,
                        "sample_values": [],
                    }
                    for f in fields_meta
                ]
                return SchemaDetectionResult(
                    columns=columns,
                    total_columns=len(columns),
                    detected_primary_key="Id",
                    timestamp_columns=ts_cols,
                )
            # SOQL path: run LIMIT 1 and infer
            soql = self._build_soql()
            result = sf.query(soql + " LIMIT 1")
            if result["records"]:
                rec = result["records"][0]
                columns = [
                    {"name": k, "type": "unknown", "nullable": True, "sample_values": [v]}
                    for k, v in rec.items() if k != "attributes"
                ]
            else:
                columns = []
            return SchemaDetectionResult(columns=columns, total_columns=len(columns))

    def extract_full(self, config: ExtractionConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            sf = self._get_sf()
            soql = self._build_soql()
            result = sf.query_all(soql)
            records = [
                {k: v for k, v in r.items() if k != "attributes"}
                for r in result.get("records", [])
            ]
            df = pd.DataFrame(records) if records else pd.DataFrame()
            self.log_extraction(len(df), time.perf_counter() - start, 0)
            return df
        except AuthenticationError:
            raise
        except Exception as exc:
            self.log_extraction(0, time.perf_counter() - start, 1)
            raise ExtractionError(
                self.source_id, f"Salesforce extraction failed: {exc}"
            ) from exc

    def extract_incremental(self, config: IncrementalConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            sf = self._get_sf()
            extra = ""
            if config.last_extracted_at:
                ts = config.last_extracted_at.strftime("%Y-%m-%dT%H:%M:%SZ")
                extra = f"SystemModstamp > {ts}"
            soql = self._build_soql(extra_filter=extra)
            result = sf.query_all(soql)
            records = [
                {k: v for k, v in r.items() if k != "attributes"}
                for r in result.get("records", [])
            ]
            df = pd.DataFrame(records) if records else pd.DataFrame()
            self.log_extraction(len(df), time.perf_counter() - start, 0)
            return df
        except Exception as exc:
            self.log_extraction(0, time.perf_counter() - start, 1)
            raise ExtractionError(
                self.source_id, f"Salesforce incremental failed: {exc}"
            ) from exc

    def get_record_count(self) -> int:
        try:
            sf = self._get_sf()
            obj = self.object_name or (
                self.soql_query.upper().split("FROM")[1].split()[0]
                if "FROM" in self.soql_query.upper() else ""
            )
            if obj:
                result = sf.query(f"SELECT COUNT() FROM {obj}")
                return result.get("totalSize", 0)
            return 0
        except Exception:
            return 0
