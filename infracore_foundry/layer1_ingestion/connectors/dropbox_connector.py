"""
Dropbox connector via Dropbox API v2.

Extracts files and folder listings from Dropbox Business and personal
accounts. Supports file download, metadata extraction, and content parsing
for CSV, Excel, PDF, and text files.

config keys:
  access_token      : str   OAuth2 access token (long-lived or refreshable)
  refresh_token     : str   OAuth2 refresh token for token renewal
  app_key           : str   Dropbox app key (for token refresh)
  app_secret        : str   Dropbox app secret (for token refresh)
  folder_path       : str   Dropbox folder path e.g. "/reports"  default "/"
  file_extensions   : list  filter by extension e.g. [".csv", ".xlsx"]
  include_deleted   : bool  include deleted files — default False
  download_content  : bool  download and parse file contents — default True
  max_files         : int   max files to process — default 1000
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

_API_BASE = "https://api.dropboxapi.com/2"
_CONTENT_BASE = "https://content.dropboxapi.com/2"
_AUTH_URL = "https://api.dropbox.com/oauth2/token"

_PARSEABLE_EXTS = {".csv", ".xlsx", ".xls", ".tsv", ".txt", ".json"}


class DropboxConnector(BaseConnector):
    """Dropbox file storage connector."""

    REQUIRED_CONFIG_FIELDS: list[str] = ["access_token"]

    def __init__(self, source_id: str, config: dict) -> None:
        super().__init__(source_id, config)
        self.access_token: str = config.get("access_token", "")
        self.refresh_token: str = config.get("refresh_token", "")
        self.app_key: str = config.get("app_key", "")
        self.app_secret: str = config.get("app_secret", "")
        self.folder_path: str = config.get("folder_path", "")  # "" = root
        self.file_extensions: list = [e.lower() for e in config.get("file_extensions", [])]
        self.include_deleted: bool = bool(config.get("include_deleted", False))
        self.download_content: bool = bool(config.get("download_content", True))
        self.max_files: int = int(config.get("max_files", 1000))
        self._token_expires: float = 0.0

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def _refresh_token_if_needed(self) -> None:
        if not self.refresh_token or not self.app_key or not self.app_secret:
            return
        if time.time() < self._token_expires - 60:
            return
        try:
            resp = httpx.post(
                _AUTH_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.refresh_token,
                },
                auth=(self.app_key, self.app_secret),
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            self.access_token = data["access_token"]
            self._token_expires = time.time() + data.get("expires_in", 14400)
        except Exception as exc:
            logger.warning("Dropbox token refresh failed: %s", exc)

    def _list_folder(self) -> list[dict]:
        self._refresh_token_if_needed()
        entries: list[dict] = []
        try:
            resp = httpx.post(
                f"{_API_BASE}/files/list_folder",
                headers=self._headers(),
                json={
                    "path": self.folder_path,
                    "recursive": True,
                    "include_deleted": self.include_deleted,
                    "include_media_info": False,
                    "limit": 2000,
                },
                timeout=30,
            )
            if resp.status_code == 401:
                raise AuthenticationError(self.source_id, "Invalid Dropbox access token")
            resp.raise_for_status()
            data = resp.json()
            entries.extend(data.get("entries", []))
            cursor = data.get("cursor")
            has_more = data.get("has_more", False)

            while has_more and len(entries) < self.max_files:
                cont = httpx.post(
                    f"{_API_BASE}/files/list_folder/continue",
                    headers=self._headers(),
                    json={"cursor": cursor},
                    timeout=30,
                )
                cont.raise_for_status()
                cont_data = cont.json()
                entries.extend(cont_data.get("entries", []))
                cursor = cont_data.get("cursor")
                has_more = cont_data.get("has_more", False)
        except AuthenticationError:
            raise
        except Exception as exc:
            logger.warning("Dropbox list_folder failed: %s", exc)
        return entries

    def _download_file(self, path: str) -> Optional[bytes]:
        try:
            import json as _json
            resp = httpx.post(
                f"{_CONTENT_BASE}/files/download",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Dropbox-API-Arg": _json.dumps({"path": path}),
                },
                timeout=60,
            )
            resp.raise_for_status()
            return resp.content
        except Exception as exc:
            logger.debug("Dropbox download failed for %s: %s", path, exc)
            return None

    def _parse_file_content(self, path: str, content: bytes) -> Optional[pd.DataFrame]:
        ext = "." + path.rsplit(".", 1)[-1].lower() if "." in path else ""
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
            logger.debug("Failed to parse %s: %s", path, exc)
        return None

    def _normalize_entry(self, entry: dict) -> dict:
        tag = entry.get(".tag", "")
        modified = entry.get("server_modified", entry.get("client_modified", ""))
        return {
            "path": entry.get("path_display", entry.get("path_lower", "")),
            "name": entry.get("name", ""),
            "type": tag,
            "size_bytes": entry.get("size", 0),
            "modified_at": modified,
            "content_hash": entry.get("content_hash", ""),
            "rev": entry.get("rev", ""),
            "is_downloadable": entry.get("is_downloadable", tag == "file"),
        }

    def test_connection(self) -> ConnectionTestResult:
        start = time.perf_counter()
        self._refresh_token_if_needed()
        try:
            resp = httpx.post(
                f"{_API_BASE}/users/get_current_account",
                headers=self._headers(),
                timeout=15,
            )
            if resp.status_code == 401:
                raise AuthenticationError(self.source_id, "Invalid Dropbox access token")
            resp.raise_for_status()
            account = resp.json()
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=True,
                message=f"Dropbox: {account.get('name', {}).get('display_name', '?')} ({account.get('email', '')})",
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
        with self._timed_operation("dropbox_schema_detection"):
            columns = [
                {"name": "path", "type": "string", "nullable": False, "sample_values": []},
                {"name": "name", "type": "string", "nullable": False, "sample_values": []},
                {"name": "type", "type": "string", "nullable": False, "sample_values": ["file", "folder"]},
                {"name": "size_bytes", "type": "int64", "nullable": True, "sample_values": []},
                {"name": "modified_at", "type": "string", "nullable": True, "sample_values": []},
                {"name": "content_hash", "type": "string", "nullable": True, "sample_values": []},
                {"name": "rev", "type": "string", "nullable": True, "sample_values": []},
                {"name": "is_downloadable", "type": "bool", "nullable": False, "sample_values": [True]},
            ]
            return SchemaDetectionResult(
                columns=columns,
                total_columns=len(columns),
                detected_primary_key="path",
                timestamp_columns=["modified_at"],
            )

    def extract_full(self, config: ExtractionConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            entries = self._list_folder()
            # Filter to files only and by extension
            file_entries = [
                e for e in entries
                if e.get(".tag") == "file" and (
                    not self.file_extensions or
                    any(e.get("name", "").lower().endswith(ext) for ext in self.file_extensions)
                )
            ][: self.max_files]

            if self.download_content:
                all_dfs: list[pd.DataFrame] = []
                for entry in file_entries:
                    path = entry.get("path_display", entry.get("path_lower", ""))
                    ext = "." + path.rsplit(".", 1)[-1].lower() if "." in path else ""
                    if ext not in _PARSEABLE_EXTS:
                        continue
                    content = self._download_file(path)
                    if content:
                        df = self._parse_file_content(path, content)
                        if df is not None and not df.empty:
                            df["_source_path"] = path
                            all_dfs.append(df)
                if all_dfs:
                    result_df = pd.concat(all_dfs, ignore_index=True)
                    self.log_extraction(len(result_df), time.perf_counter() - start, 0)
                    return result_df

            # Metadata-only mode
            records = [self._normalize_entry(e) for e in entries[: self.max_files]]
            df = pd.DataFrame(records) if records else pd.DataFrame()
            self.log_extraction(len(df), time.perf_counter() - start, 0)
            return df
        except Exception as exc:
            self.log_extraction(0, time.perf_counter() - start, 1)
            raise ExtractionError(self.source_id, f"Dropbox extraction failed: {exc}") from exc

    def extract_incremental(self, config: IncrementalConfig) -> pd.DataFrame:
        if config.last_extracted_at:
            since = config.last_extracted_at
            self.download_content = False  # metadata scan first
            entries = self._list_folder()
            recent = [
                e for e in entries
                if e.get(".tag") == "file" and
                e.get("server_modified", "") >= since.isoformat()
            ]
            if not recent:
                return pd.DataFrame()
            # Download only changed files
            self.download_content = True
            all_dfs: list[pd.DataFrame] = []
            for entry in recent[: self.max_files]:
                path = entry.get("path_display", "")
                ext = "." + path.rsplit(".", 1)[-1].lower() if "." in path else ""
                if ext not in _PARSEABLE_EXTS:
                    continue
                content = self._download_file(path)
                if content:
                    df = self._parse_file_content(path, content)
                    if df is not None and not df.empty:
                        df["_source_path"] = path
                        all_dfs.append(df)
            return pd.concat(all_dfs, ignore_index=True) if all_dfs else pd.DataFrame()
        return self.extract_full(config)

    def get_record_count(self) -> int:
        entries = self._list_folder()
        return sum(1 for e in entries if e.get(".tag") == "file")
