"""
Freshdesk (Freshworks) connector via Freshdesk REST API v2.

Freshworks is an Indian company with massive penetration in Indian SMEs and
mid-market — widely used for customer support, IT helpdesk, and vendor SLAs.
Extracting ticket data surfaces vendor performance, customer complaint patterns,
and operational risk signals.

Supported resources: tickets, contacts, companies, agents, groups.

Auth: API Key (base64 encoded, passed as Basic auth username with 'X' password).

config keys:
  domain            : str   Freshdesk subdomain e.g. "mycompany" → mycompany.freshdesk.com
  api_key           : str   Freshdesk API key
  resource          : str   "tickets"|"contacts"|"companies"|"agents" — default "tickets"
  include_stats     : bool  include ticket statistics — default False
  ticket_filter     : str   Freshdesk ticket filter name (predefined views)
  updated_since     : str   ISO date for filtering (tickets only)
  page_size         : int   default 100 (Freshdesk max: 100)
"""

import base64
import logging
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

logger = logging.getLogger(__name__)


class FreshdeskConnector(BaseConnector):
    """Freshdesk CRM/helpdesk connector via API v2."""

    REQUIRED_CONFIG_FIELDS = ["domain", "api_key"]

    def __init__(self, source_id: str, config: dict) -> None:
        super().__init__(source_id, config)
        self.domain: str = config.get("domain", "")
        self.api_key: str = config.get("api_key", "")
        self.resource: str = config.get("resource", "tickets")
        self.include_stats: bool = bool(config.get("include_stats", False))
        self.ticket_filter: str = config.get("ticket_filter", "")
        self.page_size: int = min(int(config.get("page_size", 100)), 100)

    @property
    def _base_url(self) -> str:
        return f"https://{self.domain}.freshdesk.com/api/v2"

    @property
    def _auth(self):
        # Freshdesk uses API key as username with 'X' as password
        return (self.api_key, "X")

    def _get(self, path: str, params: Optional[dict] = None) -> httpx.Response:
        resp = httpx.get(
            f"{self._base_url}/{path}",
            auth=self._auth,
            params=params or {},
            timeout=30,
        )
        if resp.status_code == 401:
            raise AuthenticationError(self.source_id, "Invalid Freshdesk API key")
        resp.raise_for_status()
        return resp

    def _paginate(self, resource: str, extra_params: Optional[dict] = None) -> list[dict]:
        records: list[dict] = []
        page = 1
        while True:
            params: dict = {"page": page, "per_page": self.page_size}
            if extra_params:
                params.update(extra_params)
            resp = self._get(resource, params=params)
            items = resp.json()
            if not isinstance(items, list) or not items:
                break
            records.extend(items)
            if len(items) < self.page_size:
                break
            page += 1
        return records

    def test_connection(self) -> ConnectionTestResult:
        start = time.perf_counter()
        try:
            resp = self._get(self.resource, params={"per_page": 1, "page": 1})
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=True,
                message=f"Freshdesk connected to {self.domain}.freshdesk.com — {self.resource}",
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
        with self._timed_operation("freshdesk_schema_detection"):
            items = self._paginate(self.resource, extra_params={"per_page": 5})
            if not items:
                return SchemaDetectionResult(columns=[], total_columns=0)
            sample = items[0]
            ts_keys = [k for k in sample if "date" in k.lower() or "_at" in k.lower()]
            columns = [
                {"name": k, "type": type(v).__name__, "nullable": True, "sample_values": [v] if v is not None else []}
                for k, v in sample.items()
            ]
            return SchemaDetectionResult(
                columns=columns,
                total_columns=len(columns),
                detected_primary_key="id",
                timestamp_columns=ts_keys,
            )

    def extract_full(self, config: ExtractionConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            extra: dict = {}
            if self.ticket_filter and self.resource == "tickets":
                extra["filter"] = self.ticket_filter
            records = self._paginate(self.resource, extra_params=extra)
            df = pd.DataFrame(records) if records else pd.DataFrame()
            self.log_extraction(len(df), time.perf_counter() - start, 0)
            return df
        except Exception as exc:
            self.log_extraction(0, time.perf_counter() - start, 1)
            raise ExtractionError(
                self.source_id, f"Freshdesk extraction failed: {exc}"
            ) from exc

    def extract_incremental(self, config: IncrementalConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            extra: dict = {}
            if config.last_extracted_at and self.resource == "tickets":
                extra["updated_since"] = config.last_extracted_at.strftime("%Y-%m-%dT%H:%M:%SZ")
            records = self._paginate(self.resource, extra_params=extra)
            df = pd.DataFrame(records) if records else pd.DataFrame()
            self.log_extraction(len(df), time.perf_counter() - start, 0)
            return df
        except Exception as exc:
            self.log_extraction(0, time.perf_counter() - start, 1)
            raise ExtractionError(
                self.source_id, f"Freshdesk incremental failed: {exc}"
            ) from exc

    def get_record_count(self) -> int:
        try:
            resp = self._get(self.resource, params={"per_page": 1, "page": 1})
            # Freshdesk returns X-Total-Count header for some resources
            total = resp.headers.get("X-Total-Count")
            if total:
                return int(total)
            return len(resp.json())
        except Exception:
            return 0
