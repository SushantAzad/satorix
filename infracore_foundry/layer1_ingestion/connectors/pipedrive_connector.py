"""
Pipedrive CRM connector via Pipedrive REST API v1.

Extracts deals, organizations, persons, activities, pipelines, and
notes from Pipedrive. Useful for sales intelligence and customer
relationship tracking.

config keys:
  api_token         : str   Pipedrive API token
  company_domain    : str   Pipedrive company domain (optional, for custom URL)
  resource_types    : list  e.g. ["deals","orgs","persons"]  default all
  pipeline_ids      : list  filter deals by pipeline ID
  stage_ids         : list  filter deals by stage ID
  max_records       : int   default 10000
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

_DEFAULT_RESOURCES = ["deals", "organizations", "persons", "activities", "pipelines"]


class PipedriveConnector(BaseConnector):
    """Pipedrive CRM connector."""

    REQUIRED_CONFIG_FIELDS: list[str] = ["api_token"]

    def __init__(self, source_id: str, config: dict) -> None:
        super().__init__(source_id, config)
        self.api_token: str = config.get("api_token", "")
        domain = config.get("company_domain", "api.pipedrive.com")
        self._base_url = f"https://{domain}/v1"
        self.resource_types: list = config.get("resource_types", _DEFAULT_RESOURCES)
        self.pipeline_ids: list = config.get("pipeline_ids", [])
        self.stage_ids: list = config.get("stage_ids", [])
        self.max_records: int = int(config.get("max_records", 10000))

    def _get(self, resource: str, params: Optional[dict] = None) -> dict:
        p = {"api_token": self.api_token, "limit": 500, **(params or {})}
        resp = httpx.get(f"{self._base_url}/{resource}", params=p, timeout=30)
        if resp.status_code == 401:
            raise AuthenticationError(self.source_id, "Invalid Pipedrive API token")
        resp.raise_for_status()
        return resp.json()

    def _paginate(self, resource: str, extra_params: Optional[dict] = None) -> list[dict]:
        records: list[dict] = []
        start = 0
        while len(records) < self.max_records:
            data = self._get(resource, {"start": start, **(extra_params or {})})
            if not data.get("success"):
                break
            items = data.get("data") or []
            if not items:
                break
            records.extend(items)
            pagination = data.get("additional_data", {}).get("pagination", {})
            if not pagination.get("more_items_in_collection"):
                break
            start += len(items)
        return records[: self.max_records]

    def _normalize_deal(self, d: dict) -> dict:
        org = d.get("org_id") or {}
        person = d.get("person_id") or {}
        owner = d.get("user_id") or {}
        return {
            "deal_id": d.get("id", ""),
            "title": d.get("title", ""),
            "value": d.get("value", ""),
            "currency": d.get("currency", ""),
            "status": d.get("status", ""),
            "stage": d.get("stage_id", ""),
            "pipeline_id": d.get("pipeline_id", ""),
            "org_name": org.get("name", "") if isinstance(org, dict) else "",
            "person_name": person.get("name", "") if isinstance(person, dict) else "",
            "owner_name": owner.get("name", "") if isinstance(owner, dict) else "",
            "expected_close_date": d.get("expected_close_date", ""),
            "close_time": d.get("close_time", ""),
            "add_time": d.get("add_time", ""),
            "update_time": d.get("update_time", ""),
            "won_time": d.get("won_time", ""),
            "lost_time": d.get("lost_time", ""),
            "probability": d.get("probability", ""),
            "activities_count": d.get("activities_count", 0),
            "emails_count": d.get("email_messages_count", 0),
        }

    def _normalize_org(self, o: dict) -> dict:
        return {
            "org_id": o.get("id", ""),
            "name": o.get("name", ""),
            "address": o.get("address", ""),
            "people_count": o.get("people_count", 0),
            "open_deals_count": o.get("open_deals_count", 0),
            "won_deals_count": o.get("won_deals_count", 0),
            "lost_deals_count": o.get("lost_deals_count", 0),
            "owner_name": (o.get("owner_id") or {}).get("name", "") if isinstance(o.get("owner_id"), dict) else "",
            "add_time": o.get("add_time", ""),
            "update_time": o.get("update_time", ""),
        }

    def _normalize_person(self, p: dict) -> dict:
        emails = [e.get("value", "") for e in (p.get("email") or [])]
        phones = [ph.get("value", "") for ph in (p.get("phone") or [])]
        org = p.get("org_id") or {}
        return {
            "person_id": p.get("id", ""),
            "name": p.get("name", ""),
            "email": emails[0] if emails else "",
            "phone": phones[0] if phones else "",
            "org_name": org.get("name", "") if isinstance(org, dict) else "",
            "open_deals_count": p.get("open_deals_count", 0),
            "add_time": p.get("add_time", ""),
            "update_time": p.get("update_time", ""),
        }

    def test_connection(self) -> ConnectionTestResult:
        start = time.perf_counter()
        try:
            data = self._get("users/me")
            user = (data.get("data") or {})
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=bool(data.get("success")),
                message=f"Pipedrive: {user.get('name', '?')} ({user.get('email', '')})",
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
        with self._timed_operation("pipedrive_schema_detection"):
            columns = [
                {"name": "deal_id", "type": "int64", "nullable": False, "sample_values": []},
                {"name": "title", "type": "string", "nullable": True, "sample_values": []},
                {"name": "value", "type": "float64", "nullable": True, "sample_values": []},
                {"name": "currency", "type": "string", "nullable": True, "sample_values": ["USD","EUR","INR"]},
                {"name": "status", "type": "string", "nullable": True, "sample_values": ["open","won","lost"]},
                {"name": "org_name", "type": "string", "nullable": True, "sample_values": []},
                {"name": "person_name", "type": "string", "nullable": True, "sample_values": []},
                {"name": "expected_close_date", "type": "string", "nullable": True, "sample_values": []},
                {"name": "add_time", "type": "string", "nullable": True, "sample_values": []},
                {"name": "update_time", "type": "string", "nullable": True, "sample_values": []},
            ]
            return SchemaDetectionResult(
                columns=columns,
                total_columns=len(columns),
                detected_primary_key="deal_id",
                timestamp_columns=["add_time", "update_time", "expected_close_date"],
            )

    def extract_full(self, config: ExtractionConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            all_dfs: list[pd.DataFrame] = []
            for rtype in self.resource_types:
                if rtype == "deals":
                    params = {}
                    if self.pipeline_ids:
                        params["filter_id"] = self.pipeline_ids[0]
                    records = self._paginate("deals", params)
                    df = pd.DataFrame([self._normalize_deal(d) for d in records])
                elif rtype in ("organizations", "orgs"):
                    records = self._paginate("organizations")
                    df = pd.DataFrame([self._normalize_org(o) for o in records])
                elif rtype == "persons":
                    records = self._paginate("persons")
                    df = pd.DataFrame([self._normalize_person(p) for p in records])
                elif rtype == "activities":
                    records = self._paginate("activities")
                    df = pd.DataFrame(records)
                elif rtype == "pipelines":
                    data = self._get("pipelines")
                    records = data.get("data") or []
                    df = pd.DataFrame(records)
                else:
                    continue
                if not df.empty:
                    df["_resource_type"] = rtype
                    all_dfs.append(df)

            result = pd.concat(all_dfs, ignore_index=True) if all_dfs else pd.DataFrame()
            self.log_extraction(len(result), time.perf_counter() - start, 0)
            return result
        except Exception as exc:
            self.log_extraction(0, time.perf_counter() - start, 1)
            raise ExtractionError(self.source_id, f"Pipedrive extraction failed: {exc}") from exc

    def extract_incremental(self, config: IncrementalConfig) -> pd.DataFrame:
        if config.last_extracted_at:
            ts = config.last_extracted_at.strftime("%Y-%m-%d %H:%M:%S")
            # Pipedrive supports since_timestamp for activities and some resources
            all_dfs: list[pd.DataFrame] = []
            for rtype in self.resource_types:
                if rtype in ("deals",):
                    records = self._paginate(rtype, {"since_timestamp": ts})
                    df = pd.DataFrame([self._normalize_deal(d) for d in records]) if records else pd.DataFrame()
                else:
                    continue
                if not df.empty:
                    all_dfs.append(df)
            return pd.concat(all_dfs, ignore_index=True) if all_dfs else pd.DataFrame()
        return self.extract_full(config)

    def get_record_count(self) -> int:
        try:
            data = self._get("deals", {"limit": 1})
            return data.get("additional_data", {}).get("pagination", {}).get("total_items", 0)
        except Exception:
            return 0
