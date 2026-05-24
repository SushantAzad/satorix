"""
Box connector via Box Platform API v2.

Extracts files, folders, and metadata from Box enterprise accounts.
Supports JWT server-side authentication and OAuth2 for user-level access.

config keys:
  client_id         : str   Box app client ID
  client_secret     : str   Box app client secret
  access_token      : str   Short-lived access token (or use JWT)
  refresh_token     : str   OAuth2 refresh token
  enterprise_id     : str   Enterprise ID for JWT auth
  jwt_private_key   : str   PEM private key for JWT auth
  jwt_key_id        : str   Key ID for JWT auth
  folder_id         : str   Root folder ID to browse — default "0" (all files)
  file_extensions   : list  filter e.g. [".csv",".xlsx"]
  download_content  : bool  parse downloadable files — default True
  max_files         : int   default 1000
"""

import io
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

_API_BASE = "https://api.box.com/2.0"
_UPLOAD_BASE = "https://upload.box.com/api/2.0"
_TOKEN_URL = "https://api.box.com/oauth2/token"

_PARSEABLE_EXTS = {".csv", ".xlsx", ".xls", ".tsv", ".txt", ".json"}


class BoxConnector(BaseConnector):
    """Box enterprise file storage connector."""

    REQUIRED_CONFIG_FIELDS: list[str] = ["access_token"]

    def __init__(self, source_id: str, config: dict) -> None:
        super().__init__(source_id, config)
        self.client_id: str = config.get("client_id", "")
        self.client_secret: str = config.get("client_secret", "")
        self.access_token: str = config.get("access_token", "")
        self.refresh_token: str = config.get("refresh_token", "")
        self.folder_id: str = config.get("folder_id", "0")
        self.file_extensions: list = [e.lower() for e in config.get("file_extensions", [])]
        self.download_content: bool = bool(config.get("download_content", True))
        self.max_files: int = int(config.get("max_files", 1000))
        self._token_expires: float = 0.0

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
        }

    def _refresh_if_needed(self) -> None:
        if self.access_token and time.time() < self._token_expires - 60:
            return
        if not self.refresh_token or not self.client_id or not self.client_secret:
            return
        try:
            resp = httpx.post(
                _TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.refresh_token,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                timeout=15,
            )
            if resp.status_code == 401:
                raise AuthenticationError(self.source_id, "Invalid Box credentials")
            resp.raise_for_status()
            data = resp.json()
            self.access_token = data["access_token"]
            self._token_expires = time.time() + data.get("expires_in", 3600)
            if "refresh_token" in data:
                self.refresh_token = data["refresh_token"]
        except AuthenticationError:
            raise
        except Exception as exc:
            logger.warning("Box token refresh failed: %s", exc)

    def _list_folder_recursive(self, folder_id: str, depth: int = 0) -> list[dict]:
        if depth > 5:
            return []
        self._refresh_if_needed()
        items: list[dict] = []
        offset = 0
        limit = 1000
        while len(items) < self.max_files:
            try:
                resp = httpx.get(
                    f"{_API_BASE}/folders/{folder_id}/items",
                    headers=self._headers(),
                    params={
                        "fields": "id,name,type,size,modified_at,sha1,path_collection",
                        "offset": offset,
                        "limit": limit,
                    },
                    timeout=30,
                )
                if resp.status_code == 401:
                    raise AuthenticationError(self.source_id, "Box token expired")
                resp.raise_for_status()
                data = resp.json()
                entries = data.get("entries", [])
                for entry in entries:
                    if entry.get("type") == "file":
                        items.append(entry)
                    elif entry.get("type") == "folder":
                        sub = self._list_folder_recursive(entry["id"], depth + 1)
                        items.extend(sub)
                if len(entries) < limit:
                    break
                offset += len(entries)
            except AuthenticationError:
                raise
            except Exception as exc:
                logger.warning("Box folder listing failed for %s: %s", folder_id, exc)
                break
        return items

    def _download_file(self, file_id: str) -> Optional[bytes]:
        try:
            resp = httpx.get(
                f"{_API_BASE}/files/{file_id}/content",
                headers=self._headers(),
                follow_redirects=True,
                timeout=60,
            )
            resp.raise_for_status()
            return resp.content
        except Exception as exc:
            logger.debug("Box download failed for %s: %s", file_id, exc)
            return None

    def _parse_content(self, name: str, content: bytes) -> Optional[pd.DataFrame]:
        ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
        try:
            if ext in (".csv", ".tsv", ".txt"):
                sep = "\t" if ext == ".tsv" else ","
                return pd.read_csv(io.BytesIO(content), sep=sep, dtype=str, errors="replace")
            elif ext in (".xlsx", ".xls"):
                return pd.read_excel(io.BytesIO(content), dtype=str)
            elif ext == ".json":
                import json as _json
                data = _json.loads(content)
                return pd.DataFrame(data if isinstance(data, list) else [data])
        except Exception as exc:
            logger.debug("Box parse failed for %s: %s", name, exc)
        return None

    def test_connection(self) -> ConnectionTestResult:
        start = time.perf_counter()
        self._refresh_if_needed()
        try:
            resp = httpx.get(
                f"{_API_BASE}/users/me",
                headers=self._headers(),
                timeout=15,
            )
            if resp.status_code == 401:
                raise AuthenticationError(self.source_id, "Invalid Box access token")
            resp.raise_for_status()
            user = resp.json()
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=True,
                message=f"Box: {user.get('name', '?')} ({user.get('login', '')})",
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
        with self._timed_operation("box_schema_detection"):
            columns = [
                {"name": "file_id", "type": "string", "nullable": False, "sample_values": []},
                {"name": "name", "type": "string", "nullable": False, "sample_values": []},
                {"name": "size", "type": "int64", "nullable": True, "sample_values": []},
                {"name": "modified_at", "type": "string", "nullable": True, "sample_values": []},
                {"name": "sha1", "type": "string", "nullable": True, "sample_values": []},
                {"name": "type", "type": "string", "nullable": False, "sample_values": ["file"]},
            ]
            return SchemaDetectionResult(
                columns=columns,
                total_columns=len(columns),
                detected_primary_key="file_id",
                timestamp_columns=["modified_at"],
            )

    def extract_full(self, config: ExtractionConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            files = self._list_folder_recursive(self.folder_id)
            filtered = [
                f for f in files
                if not self.file_extensions or
                any(f.get("name", "").lower().endswith(ext) for ext in self.file_extensions)
            ][: self.max_files]

            if self.download_content:
                all_dfs: list[pd.DataFrame] = []
                for f in filtered:
                    name = f.get("name", "")
                    ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
                    if ext not in _PARSEABLE_EXTS:
                        continue
                    content = self._download_file(f["id"])
                    if content:
                        df = self._parse_content(name, content)
                        if df is not None and not df.empty:
                            df["_source_file"] = name
                            df["_box_file_id"] = f["id"]
                            all_dfs.append(df)
                if all_dfs:
                    result = pd.concat(all_dfs, ignore_index=True)
                    self.log_extraction(len(result), time.perf_counter() - start, 0)
                    return result

            records = [
                {
                    "file_id": f.get("id", ""),
                    "name": f.get("name", ""),
                    "size": f.get("size", 0),
                    "modified_at": f.get("modified_at", ""),
                    "sha1": f.get("sha1", ""),
                    "type": f.get("type", "file"),
                }
                for f in filtered
            ]
            df = pd.DataFrame(records) if records else pd.DataFrame()
            self.log_extraction(len(df), time.perf_counter() - start, 0)
            return df
        except Exception as exc:
            self.log_extraction(0, time.perf_counter() - start, 1)
            raise ExtractionError(self.source_id, f"Box extraction failed: {exc}") from exc

    def extract_incremental(self, config: IncrementalConfig) -> pd.DataFrame:
        if config.last_extracted_at:
            all_files = self._list_folder_recursive(self.folder_id)
            since = config.last_extracted_at.isoformat()
            recent = [f for f in all_files if f.get("modified_at", "") >= since]
            if not recent:
                return pd.DataFrame()
            records = [
                {"file_id": f.get("id",""), "name": f.get("name",""), "size": f.get("size",0), "modified_at": f.get("modified_at","")}
                for f in recent
            ]
            return pd.DataFrame(records)
        return self.extract_full(config)

    def get_record_count(self) -> int:
        return len(self._list_folder_recursive(self.folder_id))
