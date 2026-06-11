"""
HubSpot CRM connector via HubSpot REST API v3.

PE firms, investment banks, and large Indian enterprises use HubSpot to
manage deal pipelines, investor relations, and portfolio company contacts.

Supported objects: contacts, companies, deals, tickets, line_items, products.
Supports full extraction and incremental via lastmodifieddate.

Auth: Private App access token (recommended) or OAuth2.

config keys:
  access_token      : str   HubSpot Private App token (Bearer)
  object_type       : str   e.g. "contacts", "companies", "deals" — default "companies"
  properties        : list  specific properties to fetch (default: all)
  associations      : list  associated object types to fetch e.g. ["contacts","deals"]
  filter_groups     : list  HubSpot filter groups for server-side filtering (JSON)
  page_size         : int   default 100 (HubSpot max: 100)
"""

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

_HS_BASE = "https://api.hubapi.com"


class HubSpotConnector(BaseConnector):
    """HubSpot CRM connector using API v3."""

    REQUIRED_CONFIG_FIELDS = ["access_token"]

    def __init__(self, source_id: str, config: dict) -> None:
        super().__init__(source_id, config)
        self.access_token: str = config.get("access_token", "")
        self.object_type: str = config.get("object_type", "companies")
        self.properties: list = config.get("properties", [])
        self.associations: list = config.get("associations", [])
        self.filter_groups: list = config.get("filter_groups", [])
        self.page_size: int = min(int(config.get("page_size", 100)), 100)

    @property
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}

    def _get_properties(self) -> list[str]:
        if self.properties:
            return self.properties
        # Fetch all non-calculated property names for the object
        resp = httpx.get(
            f"{_HS_BASE}/crm/v3/properties/{self.object_type}",
            headers=self._headers, timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return [
            p["name"] for p in data.get("results", [])
            if not p.get("calculated") and not p.get("hubspotDefined")
        ] or ["name", "domain", "createdate", "lastmodifieddate"]

    def _search(self, extra_filters: Optional[list] = None, after: Optional[str] = None) -> dict:
        props = self._get_properties()
        body: dict = {
            "limit": self.page_size,
            "properties": props[:100],  # API limit
        }
        if self.associations:
            body["associations"] = self.associations
        filters = list(self.filter_groups)
        if extra_filters:
            filters.extend(extra_filters)
        if filters:
            body["filterGroups"] = [{"filters": filters}]
        if after:
            body["after"] = after

        resp = httpx.post(
            f"{_HS_BASE}/crm/v3/objects/{self.object_type}/search",
            headers=self._headers,
            json=body,
            timeout=30,
        )
        if resp.status_code == 401:
            raise AuthenticationError(self.source_id, "Invalid HubSpot access token")
        resp.raise_for_status()
        return resp.json()

    def _paginate_all(self, extra_filters: Optional[list] = None) -> list[dict]:
        records: list[dict] = []
        after: Optional[str] = None
        while True:
            data = self._search(extra_filters=extra_filters, after=after)
            for result in data.get("results", []):
                flat: dict = {"hs_object_id": result.get("id")}
                flat.update(result.get("properties", {}))
                if self.associations:
                    for assoc_type, assoc_data in result.get("associations", {}).items():
                        ids = [r["id"] for r in assoc_data.get("results", [])]
                        flat[f"_assoc_{assoc_type}"] = ",".join(ids)
                records.append(flat)
            paging = data.get("paging", {})
            after = paging.get("next", {}).get("after")
            if not after:
                break
        return records

    def test_connection(self) -> ConnectionTestResult:
        start = time.perf_counter()
        try:
            resp = httpx.get(
                f"{_HS_BASE}/crm/v3/objects/{self.object_type}",
                headers=self._headers,
                params={"limit": 1},
                timeout=15,
            )
            if resp.status_code == 401:
                raise AuthenticationError(self.source_id, "Invalid HubSpot token")
            resp.raise_for_status()
            elapsed = (time.perf_counter() - start) * 1000
            total = resp.json().get("total", "?")
            return ConnectionTestResult(
                success=True,
                message=f"HubSpot {self.object_type}: {total:,} records",
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
        with self._timed_operation("hubspot_schema_detection"):
            data = self._search()
            results = data.get("results", [])
            if not results:
                return SchemaDetectionResult(columns=[], total_columns=0)
            sample = results[0].get("properties", {})
            columns = [
                {"name": k, "type": "string", "nullable": True, "sample_values": [v] if v else []}
                for k, v in sample.items()
            ]
            return SchemaDetectionResult(
                columns=columns,
                total_columns=len(columns),
                detected_primary_key="hs_object_id",
                timestamp_columns=["createdate", "lastmodifieddate", "closedate"],
            )

    def extract_full(self, config: ExtractionConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            records = self._paginate_all()
            df = pd.DataFrame(records) if records else pd.DataFrame()
            self.log_extraction(len(df), time.perf_counter() - start, 0)
            return df
        except Exception as exc:
            self.log_extraction(0, time.perf_counter() - start, 1)
            raise ExtractionError(
                self.source_id, f"HubSpot extraction failed: {exc}"
            ) from exc

    def extract_incremental(self, config: IncrementalConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            extra_filters = []
            if config.last_extracted_at:
                ts_ms = str(int(config.last_extracted_at.timestamp() * 1000))
                extra_filters = [{"propertyName": "lastmodifieddate", "operator": "GT", "value": ts_ms}]
            records = self._paginate_all(extra_filters=extra_filters)
            df = pd.DataFrame(records) if records else pd.DataFrame()
            self.log_extraction(len(df), time.perf_counter() - start, 0)
            return df
        except Exception as exc:
            self.log_extraction(0, time.perf_counter() - start, 1)
            raise ExtractionError(
                self.source_id, f"HubSpot incremental failed: {exc}"
            ) from exc

    def get_record_count(self) -> int:
        try:
            data = self._search()
            return data.get("total", 0)
        except Exception:
            return 0
