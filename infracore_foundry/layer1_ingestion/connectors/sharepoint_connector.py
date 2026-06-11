"""
SharePoint / OneDrive connector via Microsoft Graph API.

Microsoft 365 is the dominant productivity suite in Indian enterprises.
Companies store compliance documents, financial reports, board presentations,
and regulatory filings in SharePoint document libraries.

This connector:
  - Lists files in a SharePoint site/drive/folder
  - Downloads CSV, Excel, PDF, and text files for ingestion
  - Supports OneDrive for Business (user drives) and SharePoint (site drives)
  - Incremental: by lastModifiedDateTime

Auth: OAuth2 client credentials (app-only, M365 admin grants consent)

config keys:
  tenant_id         : str   Azure AD tenant ID
  client_id         : str   Azure app registration client ID
  client_secret     : str   Azure app registration secret
  mode              : "sharepoint" | "onedrive"  default: "sharepoint"
  site_id           : str   SharePoint site ID (for sharepoint mode)
  drive_id          : str   Drive ID (optional — uses default site drive if blank)
  user_id           : str   User ID or UPN (for onedrive mode)
  folder_path       : str   relative path within drive e.g. "/Compliance/Reports"
  file_extensions   : list  default ["csv","xlsx","xls","pdf","txt","docx"]
  max_files         : int   default 500
  download_content  : bool  download and embed file bytes — default True
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

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class SharePointConnector(BaseConnector):
    """SharePoint/OneDrive connector via Microsoft Graph API."""

    REQUIRED_CONFIG_FIELDS = ["tenant_id", "client_id", "client_secret"]

    def __init__(self, source_id: str, config: dict) -> None:
        super().__init__(source_id, config)
        self.tenant_id: str = config.get("tenant_id", "")
        self.client_id_sp: str = config.get("client_id", "")
        self.client_secret: str = config.get("client_secret", "")
        self.mode: str = config.get("mode", "sharepoint")
        self.site_id: str = config.get("site_id", "")
        self.drive_id: str = config.get("drive_id", "")
        self.user_id: str = config.get("user_id", "")
        self.folder_path: str = config.get("folder_path", "")
        self.file_extensions: list = config.get("file_extensions", ["csv", "xlsx", "xls", "pdf", "txt", "docx"])
        self.max_files: int = int(config.get("max_files", 500))
        self.download_content: bool = bool(config.get("download_content", True))
        self._token: Optional[str] = None
        self._token_expires: float = 0.0

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expires - 60:
            return self._token
        url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        resp = httpx.post(
            url,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id_sp,
                "client_secret": self.client_secret,
                "scope": "https://graph.microsoft.com/.default",
            },
            timeout=30,
        )
        if resp.status_code == 401:
            raise AuthenticationError(self.source_id, "Microsoft Graph auth failed")
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._token_expires = time.time() + data.get("expires_in", 3600)
        return self._token

    @property
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._get_token()}", "Accept": "application/json"}

    def _drive_base_url(self) -> str:
        if self.mode == "onedrive" and self.user_id:
            return f"{_GRAPH_BASE}/users/{self.user_id}/drive"
        if self.drive_id:
            return f"{_GRAPH_BASE}/drives/{self.drive_id}"
        if self.site_id:
            return f"{_GRAPH_BASE}/sites/{self.site_id}/drive"
        return f"{_GRAPH_BASE}/me/drive"

    def _list_files(self, since: Optional[datetime] = None) -> list[dict]:
        base = self._drive_base_url()
        if self.folder_path:
            path_enc = self.folder_path.lstrip("/")
            url = f"{base}/root:/{path_enc}:/children"
        else:
            url = f"{base}/root/children"

        files: list[dict] = []
        params: dict = {
            "$select": "id,name,size,lastModifiedDateTime,@microsoft.graph.downloadUrl,file",
            "$top": 100,
        }
        if since:
            params["$filter"] = (
                f"lastModifiedDateTime ge {since.strftime('%Y-%m-%dT%H:%M:%SZ')}"
            )

        while url and len(files) < self.max_files:
            resp = httpx.get(url, headers=self._headers, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            for item in data.get("value", []):
                if "file" not in item:
                    continue  # skip folders
                name = item.get("name", "")
                ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
                if ext not in self.file_extensions:
                    continue
                record: dict = {
                    "file_id": item.get("id", ""),
                    "filename": name,
                    "size_bytes": item.get("size", 0),
                    "last_modified": item.get("lastModifiedDateTime", ""),
                    "extension": ext,
                    "download_url": item.get("@microsoft.graph.downloadUrl", ""),
                    "content_b64": "",
                }
                if self.download_content and record["download_url"]:
                    try:
                        dl = httpx.get(record["download_url"], timeout=60, follow_redirects=True)
                        record["content_b64"] = base64.b64encode(dl.content).decode()
                    except Exception as exc:
                        logger.debug("Failed to download %s: %s", name, exc)
                files.append(record)
            url = data.get("@odata.nextLink")
            params = {}

        return files

    def test_connection(self) -> ConnectionTestResult:
        start = time.perf_counter()
        try:
            token = self._get_token()
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=bool(token),
                message="Microsoft Graph token acquired for SharePoint/OneDrive",
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
        with self._timed_operation("sharepoint_schema_detection"):
            columns = [
                {"name": "file_id", "type": "string", "nullable": False, "sample_values": []},
                {"name": "filename", "type": "string", "nullable": False, "sample_values": []},
                {"name": "size_bytes", "type": "int64", "nullable": False, "sample_values": [0]},
                {"name": "last_modified", "type": "string", "nullable": True, "sample_values": []},
                {"name": "extension", "type": "string", "nullable": True, "sample_values": self.file_extensions[:3]},
                {"name": "download_url", "type": "string", "nullable": True, "sample_values": []},
                {"name": "content_b64", "type": "string", "nullable": True, "sample_values": []},
            ]
            return SchemaDetectionResult(
                columns=columns,
                total_columns=len(columns),
                detected_primary_key="file_id",
                timestamp_columns=["last_modified"],
            )

    def extract_full(self, config: ExtractionConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            files = self._list_files()
            df = pd.DataFrame(files) if files else pd.DataFrame()
            self.log_extraction(len(df), time.perf_counter() - start, 0)
            return df
        except Exception as exc:
            self.log_extraction(0, time.perf_counter() - start, 1)
            raise ExtractionError(
                self.source_id, f"SharePoint extraction failed: {exc}"
            ) from exc

    def extract_incremental(self, config: IncrementalConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            files = self._list_files(since=config.last_extracted_at)
            df = pd.DataFrame(files) if files else pd.DataFrame()
            self.log_extraction(len(df), time.perf_counter() - start, 0)
            return df
        except Exception as exc:
            self.log_extraction(0, time.perf_counter() - start, 1)
            raise ExtractionError(
                self.source_id, f"SharePoint incremental failed: {exc}"
            ) from exc

    def get_record_count(self) -> int:
        try:
            return len(self._list_files())
        except Exception:
            return 0
