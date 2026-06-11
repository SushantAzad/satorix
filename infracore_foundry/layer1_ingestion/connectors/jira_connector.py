"""
Jira connector via Atlassian REST API v3.

Extracts issues, projects, sprints, epics, and user data from Jira Cloud
and Jira Server/Data Center. Useful for enterprise clients who track
compliance actions, legal cases, or regulatory tasks in Jira.

config keys:
  base_url          : str   Jira instance URL e.g. "https://company.atlassian.net"
  email             : str   User email (Cloud auth) or username (Server)
  api_token         : str   API token (Cloud) or password (Server)
  project_keys      : list  e.g. ["LEGAL", "COMPLIANCE"]  default all
  issue_types       : list  filter by issue type e.g. ["Story","Bug"]
  jql               : str   custom JQL query (overrides project_keys/issue_types)
  include_comments  : bool  fetch issue comments — default False
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


class JiraConnector(BaseConnector):
    """Jira issue tracking connector."""

    REQUIRED_CONFIG_FIELDS: list[str] = ["base_url", "email", "api_token"]

    def __init__(self, source_id: str, config: dict) -> None:
        super().__init__(source_id, config)
        self.base_url: str = config.get("base_url", "").rstrip("/")
        self.email: str = config.get("email", "")
        self.api_token: str = config.get("api_token", "")
        self.project_keys: list = config.get("project_keys", [])
        self.issue_types: list = config.get("issue_types", [])
        self.jql: str = config.get("jql", "")
        self.include_comments: bool = bool(config.get("include_comments", False))
        self.max_records: int = int(config.get("max_records", 10000))

    def _auth(self) -> tuple:
        return (self.email, self.api_token)

    def _api_get(self, path: str, params: Optional[dict] = None) -> dict:
        resp = httpx.get(
            f"{self.base_url}/rest/api/3/{path}",
            auth=self._auth(),
            params=params or {},
            headers={"Accept": "application/json"},
            timeout=30,
        )
        if resp.status_code == 401:
            raise AuthenticationError(self.source_id, "Invalid Jira credentials")
        resp.raise_for_status()
        return resp.json()

    def _build_jql(self, extra_clause: str = "") -> str:
        if self.jql:
            return self.jql + (f" AND {extra_clause}" if extra_clause else "")
        parts: list[str] = []
        if self.project_keys:
            keys = ", ".join(f'"{k}"' for k in self.project_keys)
            parts.append(f"project IN ({keys})")
        if self.issue_types:
            types = ", ".join(f'"{t}"' for t in self.issue_types)
            parts.append(f"issuetype IN ({types})")
        if extra_clause:
            parts.append(extra_clause)
        return " AND ".join(parts) if parts else "ORDER BY created DESC"

    def _normalize_issue(self, issue: dict) -> dict:
        fields = issue.get("fields", {})
        assignee = fields.get("assignee") or {}
        reporter = fields.get("reporter") or {}
        priority = fields.get("priority") or {}
        status = fields.get("status") or {}
        issue_type = fields.get("issuetype") or {}
        project = fields.get("project") or {}
        resolution = fields.get("resolution") or {}
        labels = fields.get("labels", [])
        return {
            "issue_key": issue.get("key", ""),
            "issue_id": issue.get("id", ""),
            "summary": (fields.get("summary") or "")[:500],
            "description": str(fields.get("description") or "")[:2000],
            "issue_type": issue_type.get("name", ""),
            "status": status.get("name", ""),
            "priority": priority.get("name", ""),
            "project_key": project.get("key", ""),
            "project_name": project.get("name", ""),
            "assignee": assignee.get("displayName", assignee.get("emailAddress", "")),
            "reporter": reporter.get("displayName", reporter.get("emailAddress", "")),
            "created": fields.get("created", ""),
            "updated": fields.get("updated", ""),
            "due_date": fields.get("duedate", ""),
            "resolved": fields.get("resolutiondate", ""),
            "resolution": resolution.get("name", ""),
            "labels": ",".join(labels) if labels else "",
            "story_points": fields.get("story_points", fields.get("customfield_10016", "")),
            "epic_link": fields.get("customfield_10014", ""),
            "sprint": str(fields.get("customfield_10020") or ""),
            "components": ",".join(
                c.get("name", "") for c in (fields.get("components") or [])
            ),
        }

    def test_connection(self) -> ConnectionTestResult:
        start = time.perf_counter()
        try:
            data = self._api_get("myself")
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=True,
                message=f"Jira: {data.get('displayName', data.get('emailAddress', '?'))} @ {self.base_url}",
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
        with self._timed_operation("jira_schema_detection"):
            columns = [
                {"name": "issue_key", "type": "string", "nullable": False, "sample_values": ["LEGAL-123"]},
                {"name": "issue_id", "type": "string", "nullable": False, "sample_values": []},
                {"name": "summary", "type": "string", "nullable": True, "sample_values": []},
                {"name": "issue_type", "type": "string", "nullable": True, "sample_values": ["Story","Bug","Task","Epic"]},
                {"name": "status", "type": "string", "nullable": True, "sample_values": ["Open","In Progress","Done"]},
                {"name": "priority", "type": "string", "nullable": True, "sample_values": ["High","Medium","Low"]},
                {"name": "project_key", "type": "string", "nullable": True, "sample_values": []},
                {"name": "project_name", "type": "string", "nullable": True, "sample_values": []},
                {"name": "assignee", "type": "string", "nullable": True, "sample_values": []},
                {"name": "reporter", "type": "string", "nullable": True, "sample_values": []},
                {"name": "created", "type": "string", "nullable": True, "sample_values": []},
                {"name": "updated", "type": "string", "nullable": True, "sample_values": []},
                {"name": "due_date", "type": "string", "nullable": True, "sample_values": []},
                {"name": "resolution", "type": "string", "nullable": True, "sample_values": []},
                {"name": "labels", "type": "string", "nullable": True, "sample_values": []},
            ]
            return SchemaDetectionResult(
                columns=columns,
                total_columns=len(columns),
                detected_primary_key="issue_key",
                timestamp_columns=["created", "updated", "due_date", "resolved"],
            )

    def extract_full(self, config: ExtractionConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            jql = self._build_jql()
            all_issues: list[dict] = []
            start_at = 0
            batch_size = 100
            while len(all_issues) < self.max_records:
                data = self._api_get(
                    "search",
                    {
                        "jql": jql,
                        "startAt": start_at,
                        "maxResults": min(batch_size, self.max_records - len(all_issues)),
                        "fields": "*all",
                    },
                )
                issues = data.get("issues", [])
                if not issues:
                    break
                for issue in issues:
                    all_issues.append(self._normalize_issue(issue))
                if len(issues) < batch_size:
                    break
                start_at += len(issues)

            df = pd.DataFrame(all_issues) if all_issues else pd.DataFrame()
            self.log_extraction(len(df), time.perf_counter() - start, 0)
            return df
        except Exception as exc:
            self.log_extraction(0, time.perf_counter() - start, 1)
            raise ExtractionError(self.source_id, f"Jira extraction failed: {exc}") from exc

    def extract_incremental(self, config: IncrementalConfig) -> pd.DataFrame:
        if config.last_extracted_at:
            ts = config.last_extracted_at.strftime("%Y-%m-%d %H:%M")
            extra = f'updated >= "{ts}"'
            old_jql = self.jql
            self.jql = self._build_jql(extra)
            try:
                return self.extract_full(config)
            finally:
                self.jql = old_jql
        return self.extract_full(config)

    def get_record_count(self) -> int:
        try:
            data = self._api_get("search", {"jql": self._build_jql(), "maxResults": 0})
            return data.get("total", 0)
        except Exception:
            return 0
