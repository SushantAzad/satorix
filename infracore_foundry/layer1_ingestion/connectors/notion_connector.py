"""
Notion connector via Notion API v1.

Startups and knowledge-heavy teams maintain company wikis, OKRs, and
due diligence notes in Notion. Extracting Notion database records provides
unstructured intelligence that complements structured graph data.

Supports:
  - Database query (tabular Notion databases → DataFrame)
  - Page content extraction (rich text → plain text)

Auth: Notion Internal Integration token.

config keys:
  token             : str   Notion integration secret token
  database_id       : str   Notion database ID (for database extraction)
  page_id           : str   Notion page ID (for page content extraction)
  mode              : "database" | "page"  default: "database"
  filter            : dict  Notion filter object (JSON)
  sorts             : list  Notion sort objects (JSON)
  extract_page_content : bool  also extract full page text — default False
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

_NOTION_BASE = "https://api.notion.com/v1"
_NOTION_VERSION = "2022-06-28"


def _extract_property_value(prop: dict) -> any:
    """Flatten a Notion property value to a scalar."""
    ptype = prop.get("type")
    val = prop.get(ptype)
    if val is None:
        return None
    if ptype == "title":
        return " ".join(t.get("plain_text", "") for t in (val or []))
    if ptype == "rich_text":
        return " ".join(t.get("plain_text", "") for t in (val or []))
    if ptype in ("number", "checkbox", "url", "email", "phone_number"):
        return val
    if ptype == "select":
        return val.get("name") if val else None
    if ptype == "multi_select":
        return ",".join(o.get("name", "") for o in (val or []))
    if ptype in ("date",):
        return val.get("start") if val else None
    if ptype == "relation":
        return ",".join(r.get("id", "") for r in (val or []))
    if ptype in ("created_time", "last_edited_time"):
        return val
    if ptype == "formula":
        formula_val = val or {}
        ftype = formula_val.get("type", "")
        return formula_val.get(ftype)
    if ptype == "rollup":
        rollup_val = val or {}
        rtype = rollup_val.get("type", "")
        return rollup_val.get(rtype)
    if ptype == "people":
        return ",".join(
            p.get("name", p.get("id", "")) for p in (val or [])
        )
    if ptype == "files":
        return ",".join(
            f.get("name", "") for f in (val or [])
        )
    if ptype == "status":
        return val.get("name") if val else None
    # Fallback: stringify
    return str(val)


class NotionConnector(BaseConnector):
    """Notion database and page connector."""

    REQUIRED_CONFIG_FIELDS = ["token"]

    def __init__(self, source_id: str, config: dict) -> None:
        super().__init__(source_id, config)
        self.token: str = config.get("token", "")
        self.database_id: str = config.get("database_id", "")
        self.page_id: str = config.get("page_id", "")
        self.mode: str = config.get("mode", "database")
        self.filter: Optional[dict] = config.get("filter")
        self.sorts: list = config.get("sorts", [])
        self.extract_page_content: bool = bool(config.get("extract_page_content", False))

    @property
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": _NOTION_VERSION,
            "Content-Type": "application/json",
        }

    def _post(self, path: str, body: Optional[dict] = None) -> dict:
        resp = httpx.post(
            f"{_NOTION_BASE}/{path}",
            headers=self._headers,
            json=body or {},
            timeout=30,
        )
        if resp.status_code == 401:
            raise AuthenticationError(self.source_id, "Invalid Notion integration token")
        resp.raise_for_status()
        return resp.json()

    def _get(self, path: str) -> dict:
        resp = httpx.get(
            f"{_NOTION_BASE}/{path}",
            headers=self._headers,
            timeout=30,
        )
        if resp.status_code == 401:
            raise AuthenticationError(self.source_id, "Invalid Notion integration token")
        resp.raise_for_status()
        return resp.json()

    def _query_database(self, extra_filter: Optional[dict] = None) -> list[dict]:
        records: list[dict] = []
        cursor: Optional[str] = None
        body: dict = {"page_size": 100}
        if self.sorts:
            body["sorts"] = self.sorts
        combined_filter = self.filter
        if extra_filter:
            if combined_filter:
                combined_filter = {"and": [combined_filter, extra_filter]}
            else:
                combined_filter = extra_filter
        if combined_filter:
            body["filter"] = combined_filter

        while True:
            if cursor:
                body["start_cursor"] = cursor
            data = self._post(f"databases/{self.database_id}/query", body)
            for page in data.get("results", []):
                record: dict = {"page_id": page.get("id", "")}
                record["created_time"] = page.get("created_time", "")
                record["last_edited_time"] = page.get("last_edited_time", "")
                props = page.get("properties", {})
                for prop_name, prop_val in props.items():
                    record[prop_name] = _extract_property_value(prop_val)
                if self.extract_page_content:
                    record["page_content"] = self._get_page_text(page["id"])
                records.append(record)
            cursor = data.get("next_cursor")
            if not data.get("has_more") or not cursor:
                break
        return records

    def _get_page_text(self, page_id: str) -> str:
        """Extract plain text content from all blocks of a page."""
        try:
            data = self._get(f"blocks/{page_id}/children")
            texts = []
            for block in data.get("results", []):
                btype = block.get("type", "")
                content = block.get(btype, {})
                rich = content.get("rich_text", [])
                if rich:
                    texts.append(" ".join(r.get("plain_text", "") for r in rich))
            return " ".join(texts)[:5000]
        except Exception:
            return ""

    def test_connection(self) -> ConnectionTestResult:
        start = time.perf_counter()
        try:
            data = self._get("users/me")
            elapsed = (time.perf_counter() - start) * 1000
            name = data.get("name", data.get("id", "unknown"))
            return ConnectionTestResult(
                success=True,
                message=f"Notion connected as: {name}",
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
        with self._timed_operation("notion_schema_detection"):
            if self.mode == "database":
                data = self._get(f"databases/{self.database_id}")
                props = data.get("properties", {})
                columns = [
                    {"name": name, "type": meta.get("type", "unknown"), "nullable": True, "sample_values": []}
                    for name, meta in props.items()
                ]
                columns = [{"name": "page_id", "type": "string", "nullable": False, "sample_values": []}] + columns
                return SchemaDetectionResult(
                    columns=columns,
                    total_columns=len(columns),
                    detected_primary_key="page_id",
                    timestamp_columns=["created_time", "last_edited_time"],
                )
            columns = [
                {"name": "page_id", "type": "string", "nullable": False, "sample_values": []},
                {"name": "page_content", "type": "string", "nullable": True, "sample_values": []},
            ]
            return SchemaDetectionResult(columns=columns, total_columns=2, detected_primary_key="page_id")

    def extract_full(self, config: ExtractionConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            if self.mode == "database":
                records = self._query_database()
            else:
                records = [{"page_id": self.page_id, "page_content": self._get_page_text(self.page_id)}]
            df = pd.DataFrame(records) if records else pd.DataFrame()
            self.log_extraction(len(df), time.perf_counter() - start, 0)
            return df
        except Exception as exc:
            self.log_extraction(0, time.perf_counter() - start, 1)
            raise ExtractionError(self.source_id, f"Notion extraction failed: {exc}") from exc

    def extract_incremental(self, config: IncrementalConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            extra_filter: Optional[dict] = None
            if config.last_extracted_at and self.mode == "database":
                ts = config.last_extracted_at.strftime("%Y-%m-%dT%H:%M:%S.000Z")
                extra_filter = {
                    "timestamp": "last_edited_time",
                    "last_edited_time": {"after": ts},
                }
            records = self._query_database(extra_filter=extra_filter) if self.mode == "database" else []
            df = pd.DataFrame(records) if records else pd.DataFrame()
            self.log_extraction(len(df), time.perf_counter() - start, 0)
            return df
        except Exception as exc:
            self.log_extraction(0, time.perf_counter() - start, 1)
            raise ExtractionError(self.source_id, f"Notion incremental failed: {exc}") from exc

    def get_record_count(self) -> int:
        try:
            records = self._query_database()
            return len(records)
        except Exception:
            return 0
