"""
Google Drive connector via Google Drive API v3.

Extracts file metadata and optionally downloads file content from a
specified Drive folder (My Drive or Shared Drive).

Commonly used by startups, PE funds, and compliance teams that store
reports and financial data in Google Drive.

Auth: Service Account (recommended for server-to-server) or OAuth2.

config keys:
  service_account_json : str   JSON string of service account credentials
  delegated_email      : str   user email to impersonate (domain-wide delegation)
  folder_id            : str   Google Drive folder ID (from URL)
  shared_drive_id      : str   Shared Drive ID (optional)
  file_extensions      : list  default ["csv","xlsx","xls","pdf","txt","docx","json"]
  include_subfolders   : bool  recursively list subfolders — default False
  download_content     : bool  download and embed file bytes as base64 — default True
  max_files            : int   default 500
"""

import base64
import json
import logging
import time
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

_DRIVE_API = "https://www.googleapis.com/drive/v3"
_EXPORT_MIME = {
    "application/vnd.google-apps.spreadsheet": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.google-apps.document": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.google-apps.presentation": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


class GoogleDriveConnector(BaseConnector):
    """Google Drive connector using service account credentials."""

    REQUIRED_CONFIG_FIELDS = ["service_account_json"]

    def __init__(self, source_id: str, config: dict) -> None:
        super().__init__(source_id, config)
        self.service_account_json: str = config.get("service_account_json", "")
        self.delegated_email: str = config.get("delegated_email", "")
        self.folder_id: str = config.get("folder_id", "root")
        self.shared_drive_id: str = config.get("shared_drive_id", "")
        self.file_extensions: list = config.get("file_extensions", ["csv", "xlsx", "xls", "pdf", "txt", "docx", "json"])
        self.include_subfolders: bool = bool(config.get("include_subfolders", False))
        self.download_content: bool = bool(config.get("download_content", True))
        self.max_files: int = int(config.get("max_files", 500))
        self._token: Optional[str] = None
        self._token_expires: float = 0.0

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expires - 60:
            return self._token
        try:
            from google.oauth2 import service_account
            from google.auth.transport.requests import Request
        except ImportError as exc:
            raise ImportError(
                "google-auth not installed. Run: pip install google-auth google-auth-httplib2"
            ) from exc

        sa_info = json.loads(self.service_account_json)
        scopes = ["https://www.googleapis.com/auth/drive.readonly"]
        credentials = service_account.Credentials.from_service_account_info(sa_info, scopes=scopes)
        if self.delegated_email:
            credentials = credentials.with_subject(self.delegated_email)
        credentials.refresh(Request())
        self._token = credentials.token
        self._token_expires = credentials.expiry.timestamp() if credentials.expiry else time.time() + 3600
        return self._token

    @property
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._get_token()}"}

    def _list_folder(self, folder_id: str) -> list[dict]:
        files: list[dict] = []
        page_token: Optional[str] = None
        q_parts = [f"'{folder_id}' in parents", "trashed = false"]
        ext_mimes = [
            "application/vnd.google-apps.spreadsheet",
            "application/vnd.google-apps.document",
        ]
        q = " and ".join(q_parts)

        while len(files) < self.max_files:
            params: dict = {
                "q": q,
                "fields": "nextPageToken,files(id,name,mimeType,size,modifiedTime,parents)",
                "pageSize": 100,
            }
            if self.shared_drive_id:
                params["driveId"] = self.shared_drive_id
                params["includeItemsFromAllDrives"] = True
                params["supportsAllDrives"] = True
                params["corpora"] = "drive"
            if page_token:
                params["pageToken"] = page_token

            resp = httpx.get(f"{_DRIVE_API}/files", headers=self._headers, params=params, timeout=30)
            if resp.status_code == 401:
                raise AuthenticationError(self.source_id, "Google Drive auth failed")
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("files", []):
                mime = item.get("mimeType", "")
                name = item.get("name", "")

                if mime == "application/vnd.google-apps.folder":
                    if self.include_subfolders:
                        files.extend(self._list_folder(item["id"]))
                    continue

                # Extension check
                ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
                is_google_workspace = mime in _EXPORT_MIME
                if not is_google_workspace and ext not in self.file_extensions:
                    continue

                record: dict = {
                    "file_id": item["id"],
                    "filename": name,
                    "mime_type": mime,
                    "size_bytes": int(item.get("size", 0)),
                    "modified_time": item.get("modifiedTime", ""),
                    "extension": ext,
                    "content_b64": "",
                }

                if self.download_content:
                    try:
                        record["content_b64"] = self._download_file(item["id"], mime)
                    except Exception as exc:
                        logger.debug("Download failed for %s: %s", name, exc)

                files.append(record)

            page_token = data.get("nextPageToken")
            if not page_token:
                break

        return files

    def _download_file(self, file_id: str, mime_type: str) -> str:
        if mime_type in _EXPORT_MIME:
            export_mime = _EXPORT_MIME[mime_type]
            resp = httpx.get(
                f"{_DRIVE_API}/files/{file_id}/export",
                headers=self._headers,
                params={"mimeType": export_mime},
                timeout=60,
            )
        else:
            resp = httpx.get(
                f"{_DRIVE_API}/files/{file_id}",
                headers=self._headers,
                params={"alt": "media"},
                timeout=60,
            )
        resp.raise_for_status()
        return base64.b64encode(resp.content).decode()

    def test_connection(self) -> ConnectionTestResult:
        start = time.perf_counter()
        try:
            token = self._get_token()
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=bool(token),
                message=f"Google Drive authenticated (folder_id={self.folder_id})",
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
        with self._timed_operation("gdrive_schema_detection"):
            columns = [
                {"name": "file_id", "type": "string", "nullable": False, "sample_values": []},
                {"name": "filename", "type": "string", "nullable": False, "sample_values": []},
                {"name": "mime_type", "type": "string", "nullable": True, "sample_values": []},
                {"name": "size_bytes", "type": "int64", "nullable": True, "sample_values": [0]},
                {"name": "modified_time", "type": "string", "nullable": True, "sample_values": []},
                {"name": "extension", "type": "string", "nullable": True, "sample_values": self.file_extensions[:3]},
                {"name": "content_b64", "type": "string", "nullable": True, "sample_values": []},
            ]
            return SchemaDetectionResult(
                columns=columns,
                total_columns=len(columns),
                detected_primary_key="file_id",
                timestamp_columns=["modified_time"],
            )

    def extract_full(self, config: ExtractionConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            files = self._list_folder(self.folder_id)
            df = pd.DataFrame(files) if files else pd.DataFrame()
            self.log_extraction(len(df), time.perf_counter() - start, 0)
            return df
        except Exception as exc:
            self.log_extraction(0, time.perf_counter() - start, 1)
            raise ExtractionError(
                self.source_id, f"Google Drive extraction failed: {exc}"
            ) from exc

    def extract_incremental(self, config: IncrementalConfig) -> pd.DataFrame:
        df = self.extract_full(config)
        if df.empty or "modified_time" not in df.columns or not config.last_extracted_at:
            return df
        cutoff = pd.Timestamp(config.last_extracted_at, tz="UTC")
        df["modified_time"] = pd.to_datetime(df["modified_time"], utc=True, errors="coerce")
        return df[df["modified_time"] > cutoff]

    def get_record_count(self) -> int:
        try:
            return len(self._list_folder(self.folder_id))
        except Exception:
            return 0
