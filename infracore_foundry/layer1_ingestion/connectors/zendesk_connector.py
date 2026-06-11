"""
Zendesk connector via Zendesk REST API v2.

Extracts tickets, users, organizations, and satisfaction ratings from
Zendesk Support. Useful for customer intelligence, complaint tracking,
and service-level analysis.

config keys:
  subdomain         : str   Zendesk subdomain e.g. "company" for company.zendesk.com
  email             : str   Agent email
  api_token         : str   Zendesk API token
  resource_types    : list  e.g. ["tickets","users","organizations"]  default ["tickets"]
  ticket_status     : list  filter e.g. ["open","pending","solved"]  default all
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


class ZendeskConnector(BaseConnector):
    """Zendesk Support connector."""

    REQUIRED_CONFIG_FIELDS: list[str] = ["subdomain", "email", "api_token"]

    def __init__(self, source_id: str, config: dict) -> None:
        super().__init__(source_id, config)
        self.subdomain: str = config.get("subdomain", "")
        self.email: str = config.get("email", "")
        self.api_token: str = config.get("api_token", "")
        self.resource_types: list = config.get("resource_types", ["tickets"])
        self.ticket_status: list = config.get("ticket_status", [])
        self.max_records: int = int(config.get("max_records", 10000))

    @property
    def _base_url(self) -> str:
        return f"https://{self.subdomain}.zendesk.com/api/v2"

    def _auth(self) -> tuple:
        return (f"{self.email}/token", self.api_token)

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        resp = httpx.get(
            f"{self._base_url}/{path}",
            auth=self._auth(),
            params=params or {},
            headers={"Accept": "application/json"},
            timeout=30,
        )
        if resp.status_code == 401:
            raise AuthenticationError(self.source_id, "Invalid Zendesk credentials")
        resp.raise_for_status()
        return resp.json()

    def _paginate(self, resource: str, key: str, params: Optional[dict] = None) -> list[dict]:
        records: list[dict] = []
        url = f"{resource}.json"
        page_params = {"per_page": 100, **(params or {})}
        while url and len(records) < self.max_records:
            data = self._get(url, page_params)
            records.extend(data.get(key, []))
            next_page = data.get("next_page")
            if next_page:
                # Extract path from full URL
                url = next_page.split(".zendesk.com/api/v2/")[-1]
                page_params = {}  # next_page URL contains all params
            else:
                break
        return records[: self.max_records]

    def _normalize_ticket(self, t: dict) -> dict:
        tags = t.get("tags", [])
        return {
            "ticket_id": t.get("id", ""),
            "subject": (t.get("subject") or "")[:500],
            "description": (t.get("description") or "")[:2000],
            "status": t.get("status", ""),
            "priority": t.get("priority", ""),
            "ticket_type": t.get("type", ""),
            "requester_id": t.get("requester_id", ""),
            "assignee_id": t.get("assignee_id", ""),
            "organization_id": t.get("organization_id", ""),
            "group_id": t.get("group_id", ""),
            "created_at": t.get("created_at", ""),
            "updated_at": t.get("updated_at", ""),
            "solved_at": t.get("solved_at", ""),
            "due_at": t.get("due_at", ""),
            "satisfaction_rating": str(t.get("satisfaction_rating") or ""),
            "tags": ",".join(tags) if tags else "",
            "channel": t.get("via", {}).get("channel", ""),
            "is_public": t.get("is_public", True),
        }

    def _normalize_user(self, u: dict) -> dict:
        return {
            "user_id": u.get("id", ""),
            "name": u.get("name", ""),
            "email": u.get("email", ""),
            "role": u.get("role", ""),
            "organization_id": u.get("organization_id", ""),
            "created_at": u.get("created_at", ""),
            "last_login_at": u.get("last_login_at", ""),
            "active": u.get("active", True),
            "verified": u.get("verified", False),
            "phone": u.get("phone", ""),
            "tags": ",".join(u.get("tags", [])),
        }

    def _normalize_org(self, o: dict) -> dict:
        return {
            "org_id": o.get("id", ""),
            "name": o.get("name", ""),
            "domain_names": ",".join(o.get("domain_names", [])),
            "created_at": o.get("created_at", ""),
            "notes": (o.get("notes") or "")[:500],
            "tags": ",".join(o.get("tags", [])),
        }

    def test_connection(self) -> ConnectionTestResult:
        start = time.perf_counter()
        try:
            data = self._get("users/me.json")
            user = data.get("user", {})
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=True,
                message=f"Zendesk: {user.get('name', '?')} @ {self.subdomain}.zendesk.com",
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
        with self._timed_operation("zendesk_schema_detection"):
            columns = [
                {"name": "ticket_id", "type": "int64", "nullable": False, "sample_values": []},
                {"name": "subject", "type": "string", "nullable": True, "sample_values": []},
                {"name": "status", "type": "string", "nullable": True, "sample_values": ["open","pending","solved","closed"]},
                {"name": "priority", "type": "string", "nullable": True, "sample_values": ["low","normal","high","urgent"]},
                {"name": "ticket_type", "type": "string", "nullable": True, "sample_values": ["incident","question","task"]},
                {"name": "created_at", "type": "string", "nullable": True, "sample_values": []},
                {"name": "updated_at", "type": "string", "nullable": True, "sample_values": []},
                {"name": "channel", "type": "string", "nullable": True, "sample_values": ["web","email","api"]},
                {"name": "tags", "type": "string", "nullable": True, "sample_values": []},
            ]
            return SchemaDetectionResult(
                columns=columns,
                total_columns=len(columns),
                detected_primary_key="ticket_id",
                timestamp_columns=["created_at", "updated_at", "solved_at"],
            )

    def extract_full(self, config: ExtractionConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            all_dfs: list[pd.DataFrame] = []
            for rtype in self.resource_types:
                if rtype == "tickets":
                    params = {}
                    if self.ticket_status:
                        params["status"] = ",".join(self.ticket_status)
                    records = self._paginate("tickets", "tickets", params)
                    df = pd.DataFrame([self._normalize_ticket(t) for t in records])
                elif rtype == "users":
                    records = self._paginate("users", "users", {"role": "end-user"})
                    df = pd.DataFrame([self._normalize_user(u) for u in records])
                elif rtype == "organizations":
                    records = self._paginate("organizations", "organizations")
                    df = pd.DataFrame([self._normalize_org(o) for o in records])
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
            raise ExtractionError(self.source_id, f"Zendesk extraction failed: {exc}") from exc

    def extract_incremental(self, config: IncrementalConfig) -> pd.DataFrame:
        if config.last_extracted_at:
            # Zendesk incremental export uses Unix timestamps
            unix_ts = int(config.last_extracted_at.timestamp())
            records: list[dict] = []
            try:
                data = self._get("incremental/tickets/cursor.json", {"start_time": unix_ts})
                for t in data.get("tickets", []):
                    records.append(self._normalize_ticket(t))
            except Exception as exc:
                logger.warning("Zendesk incremental export failed: %s", exc)
            return pd.DataFrame(records) if records else pd.DataFrame()
        return self.extract_full(config)

    def get_record_count(self) -> int:
        try:
            data = self._get("tickets/count.json")
            return data.get("count", {}).get("value", 0)
        except Exception:
            return 0
