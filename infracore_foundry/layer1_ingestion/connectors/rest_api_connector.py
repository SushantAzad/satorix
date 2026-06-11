"""
Generic REST API connector with 5 auth methods, 5 pagination strategies,
rate limiting, and exponential backoff.
"""

import base64
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
import pandas as pd

from layer1_ingestion.connectors.base_connector import (
    BaseConnector, ConnectionTestResult, SchemaDetectionResult,
    ExtractionConfig, IncrementalConfig,
    ConnectionError, AuthenticationError, ExtractionError, RateLimitError,
)

logger = logging.getLogger(__name__)

MAX_BACKOFF_SECONDS = 60
INITIAL_BACKOFF_SECONDS = 1


def _extract_json_path(data: Any, path: str) -> Any:
    """Extract nested data from JSON using dot-notation path (e.g., 'data.items')."""
    if not path:
        return data
    parts = path.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            current = current[int(part)]
        else:
            return None
        if current is None:
            return None
    return current


class RestAPIConnector(BaseConnector):
    """Generic REST API connector with configurable auth and pagination."""

    REQUIRED_CONFIG_FIELDS = ["base_url", "endpoint"]

    def __init__(self, source_id: str, config: dict) -> None:
        super().__init__(source_id, config)
        self.base_url: str = config.get("base_url", "").rstrip("/")
        self.endpoint: str = config.get("endpoint", "")
        self.method: str = config.get("method", "GET").upper()
        self.auth_method: str = config.get("auth_method", "no_auth")
        self.auth_config: dict = config.get("auth_config", {})
        self.pagination_strategy: str = config.get("pagination_strategy", "no_pagination")
        self.page_size: int = config.get("page_size", 100)
        self.response_data_path: str = config.get("response_data_path", "")
        self.headers: dict = config.get("headers", {})
        self.query_params: dict = config.get("query_params", {})
        self._oauth_token: Optional[str] = None
        self._oauth_expires_at: Optional[float] = None

    def _build_auth_headers(self) -> dict:
        """Build authentication headers based on configured method."""
        if self.auth_method == "api_key_header":
            header_name = self.auth_config.get("header_name", "X-API-Key")
            api_key = self.auth_config.get("api_key", "")
            return {header_name: api_key}
        elif self.auth_method == "bearer_token":
            token = self.auth_config.get("token", "")
            return {"Authorization": f"Bearer {token}"}
        elif self.auth_method == "basic_auth":
            username = self.auth_config.get("username", "")
            password = self.auth_config.get("password", "")
            encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
            return {"Authorization": f"Basic {encoded}"}
        elif self.auth_method == "oauth2_client_credentials":
            token = self._get_oauth_token()
            return {"Authorization": f"Bearer {token}"}
        return {}

    def _get_oauth_token(self) -> str:
        """Get OAuth2 token, refreshing if expired."""
        now = time.time()
        if self._oauth_token and self._oauth_expires_at and now < self._oauth_expires_at - 60:
            return self._oauth_token
        token_url = self.auth_config.get("token_url", "")
        client_id = self.auth_config.get("client_id", "")
        client_secret = self.auth_config.get("client_secret", "")
        scope = self.auth_config.get("scope", "")
        data = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }
        if scope:
            data["scope"] = scope
        with httpx.Client(timeout=30) as client:
            resp = client.post(token_url, data=data)
            resp.raise_for_status()
            token_data = resp.json()
        self._oauth_token = token_data["access_token"]
        expires_in = token_data.get("expires_in", 3600)
        self._oauth_expires_at = now + expires_in
        return self._oauth_token

    def _make_request(self, url: str, params: Optional[dict] = None, body: Optional[dict] = None) -> httpx.Response:
        """Make an HTTP request with retry logic and rate limit handling."""
        auth_headers = self._build_auth_headers()
        all_headers = {**self.headers, **auth_headers}
        backoff = INITIAL_BACKOFF_SECONDS
        for attempt in range(5):
            try:
                with httpx.Client(timeout=60) as client:
                    if self.method == "GET":
                        resp = client.get(url, headers=all_headers, params=params)
                    else:
                        resp = client.post(url, headers=all_headers, params=params, json=body)
                if resp.status_code == 429:
                    retry_after = float(resp.headers.get("Retry-After", backoff))
                    self.logger.warning(
                        "Rate limited, retrying after %.1fs", retry_after,
                        extra={"source_id": self.source_id, "attempt": attempt},
                    )
                    time.sleep(min(retry_after, MAX_BACKOFF_SECONDS))
                    backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
                    continue
                resp.raise_for_status()
                return resp
            except httpx.HTTPStatusError:
                raise
            except Exception as e:
                if attempt < 4:
                    time.sleep(backoff)
                    backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
                else:
                    raise
        raise RateLimitError(self.source_id, "Max retries exceeded for rate limiting")

    def test_connection(self) -> ConnectionTestResult:
        start = time.perf_counter()
        try:
            url = f"{self.base_url}{self.endpoint}"
            params = {**self.query_params}
            if self.pagination_strategy == "page_number":
                params["page"] = 1
                params["per_page"] = 1
            elif self.pagination_strategy == "offset_limit":
                params["offset"] = 0
                params["limit"] = 1
            resp = self._make_request(url, params=params)
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=True,
                message=f"API responded with status {resp.status_code}",
                response_time_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=False, message=str(e),
                response_time_ms=elapsed, error=type(e).__name__,
            )

    def extract_schema(self) -> SchemaDetectionResult:
        with self._timed_operation("schema_detection"):
            url = f"{self.base_url}{self.endpoint}"
            params = {**self.query_params}
            params["per_page"] = 10
            params["limit"] = 10
            resp = self._make_request(url, params=params)
            data = resp.json()
            items = _extract_json_path(data, self.response_data_path)
            if isinstance(items, list) and items:
                df = pd.json_normalize(items[:10])
                columns = [
                    {"name": str(c), "type": str(df[c].dtype), "nullable": bool(df[c].isnull().any()), "sample_values": df[c].dropna().head(3).tolist()}
                    for c in df.columns
                ]
                return SchemaDetectionResult(columns=columns, total_columns=len(columns))
            return SchemaDetectionResult(columns=[], total_columns=0)

    def extract_full(self, config: ExtractionConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            all_items = self._paginated_extract()
            if not all_items:
                df = pd.DataFrame()
            else:
                df = pd.json_normalize(all_items)
            duration = time.perf_counter() - start
            self.log_extraction(len(df), duration, 0)
            return df
        except Exception as e:
            duration = time.perf_counter() - start
            self.log_extraction(0, duration, 1)
            raise ExtractionError(self.source_id, f"API extraction failed: {str(e)}") from e

    def extract_incremental(self, config: IncrementalConfig) -> pd.DataFrame:
        """Pass last_sync timestamp as query param if configured."""
        if config.last_extracted_at:
            param_name = self.config.get("incremental_param", "updated_since")
            self.query_params[param_name] = config.last_extracted_at.isoformat()
        return self.extract_full(config)

    def get_record_count(self) -> int:
        url = f"{self.base_url}{self.endpoint}"
        resp = self._make_request(url, params={**self.query_params, "per_page": 1, "limit": 1})
        data = resp.json()
        for key in ("total", "total_count", "count", "total_results"):
            if key in data:
                return int(data[key])
        items = _extract_json_path(data, self.response_data_path)
        return len(items) if isinstance(items, list) else 0

    def _paginated_extract(self) -> list[dict]:
        """Extract all pages of data using the configured pagination strategy."""
        url = f"{self.base_url}{self.endpoint}"
        all_items: list[dict] = []

        if self.pagination_strategy == "no_pagination":
            resp = self._make_request(url, params=self.query_params)
            data = resp.json()
            items = _extract_json_path(data, self.response_data_path)
            return items if isinstance(items, list) else [data]

        elif self.pagination_strategy == "page_number":
            page = 1
            while True:
                params = {**self.query_params, "page": page, "per_page": self.page_size}
                resp = self._make_request(url, params=params)
                data = resp.json()
                items = _extract_json_path(data, self.response_data_path)
                if not items or not isinstance(items, list) or len(items) == 0:
                    break
                all_items.extend(items)
                if len(items) < self.page_size:
                    break
                page += 1

        elif self.pagination_strategy == "cursor":
            cursor = None
            while True:
                params = {**self.query_params, "per_page": self.page_size}
                if cursor:
                    params["cursor"] = cursor
                resp = self._make_request(url, params=params)
                data = resp.json()
                items = _extract_json_path(data, self.response_data_path)
                if not items or not isinstance(items, list):
                    break
                all_items.extend(items)
                cursor = data.get("next_cursor") or data.get("cursor")
                if not cursor:
                    break

        elif self.pagination_strategy == "offset_limit":
            offset = 0
            while True:
                params = {**self.query_params, "offset": offset, "limit": self.page_size}
                resp = self._make_request(url, params=params)
                data = resp.json()
                items = _extract_json_path(data, self.response_data_path)
                if not items or not isinstance(items, list) or len(items) == 0:
                    break
                all_items.extend(items)
                if len(items) < self.page_size:
                    break
                offset += self.page_size

        elif self.pagination_strategy == "link_header":
            next_url: Optional[str] = url
            while next_url:
                resp = self._make_request(next_url, params=self.query_params if next_url == url else None)
                data = resp.json()
                items = _extract_json_path(data, self.response_data_path)
                if items and isinstance(items, list):
                    all_items.extend(items)
                link = resp.headers.get("Link", "")
                next_url = None
                for part in link.split(","):
                    if 'rel="next"' in part:
                        next_url = part.split(";")[0].strip().strip("<>")
                        break

        return all_items
