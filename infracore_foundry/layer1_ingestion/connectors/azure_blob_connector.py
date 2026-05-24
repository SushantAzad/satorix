"""
Azure Blob Storage connector.

Large Indian enterprises using Microsoft Azure store reports, exports, and
compliance data in Blob Storage. This connector lists and downloads blobs
from a specified container, parsing CSV/Excel/JSON/Parquet content.

Auth: Connection string, Account Key, or SAS token.

config keys:
  connection_string : str   Azure Storage connection string (preferred)
  account_name      : str   Storage account name (alternative to connection_string)
  account_key       : str   Storage account key
  sas_token         : str   SAS token (alternative to account key)
  container_name    : str   Blob container name
  prefix            : str   Blob name prefix filter (virtual folder path)
  file_extensions   : list  default ["csv","xlsx","parquet","json","txt"]
  download_content  : bool  download blobs — default True
  max_blobs         : int   default 500
"""

import base64
import logging
import time
from datetime import datetime
from typing import Optional

import pandas as pd

from layer1_ingestion.connectors.base_connector import (
    BaseConnector,
    ConnectionTestResult,
    ExtractionConfig,
    ExtractionError,
    IncrementalConfig,
    SchemaDetectionResult,
)

logger = logging.getLogger(__name__)


class AzureBlobConnector(BaseConnector):
    """Azure Blob Storage connector using azure-storage-blob SDK."""

    REQUIRED_CONFIG_FIELDS = ["container_name"]

    def __init__(self, source_id: str, config: dict) -> None:
        super().__init__(source_id, config)
        self.connection_string: str = config.get("connection_string", "")
        self.account_name: str = config.get("account_name", "")
        self.account_key: str = config.get("account_key", "")
        self.sas_token: str = config.get("sas_token", "")
        self.container_name: str = config.get("container_name", "")
        self.prefix: str = config.get("prefix", "")
        self.file_extensions: list = config.get("file_extensions", ["csv", "xlsx", "parquet", "json", "txt"])
        self.download_content: bool = bool(config.get("download_content", True))
        self.max_blobs: int = int(config.get("max_blobs", 500))

    def _get_client(self):
        try:
            from azure.storage.blob import BlobServiceClient
        except ImportError as exc:
            raise ImportError(
                "azure-storage-blob not installed. Run: pip install azure-storage-blob"
            ) from exc

        if self.connection_string:
            return BlobServiceClient.from_connection_string(self.connection_string)
        elif self.account_name and self.account_key:
            return BlobServiceClient(
                account_url=f"https://{self.account_name}.blob.core.windows.net",
                credential=self.account_key,
            )
        elif self.account_name and self.sas_token:
            return BlobServiceClient(
                account_url=f"https://{self.account_name}.blob.core.windows.net",
                credential=self.sas_token,
            )
        raise ValueError("Azure Blob: provide connection_string or account_name+key/sas_token")

    def _list_blobs(self, since: Optional[datetime] = None) -> list[dict]:
        client = self._get_client()
        container = client.get_container_client(self.container_name)
        blobs: list[dict] = []
        for blob in container.list_blobs(name_starts_with=self.prefix or None):
            if len(blobs) >= self.max_blobs:
                break
            name = blob.name
            ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
            if ext not in self.file_extensions:
                continue
            last_mod = blob.last_modified
            if since and last_mod and last_mod.replace(tzinfo=None) <= since.replace(tzinfo=None):
                continue
            record: dict = {
                "blob_name": name,
                "size_bytes": blob.size or 0,
                "last_modified": last_mod.isoformat() if last_mod else "",
                "content_type": blob.content_settings.content_type if blob.content_settings else "",
                "extension": ext,
                "content_b64": "",
            }
            if self.download_content:
                try:
                    blob_client = container.get_blob_client(name)
                    data = blob_client.download_blob().readall()
                    record["content_b64"] = base64.b64encode(data).decode()
                except Exception as exc:
                    logger.debug("Blob download failed for %s: %s", name, exc)
            blobs.append(record)
        return blobs

    def test_connection(self) -> ConnectionTestResult:
        start = time.perf_counter()
        try:
            client = self._get_client()
            props = client.get_service_properties()
            container = client.get_container_client(self.container_name)
            container.get_container_properties()
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=True,
                message=f"Azure Blob connected — container: {self.container_name}",
                response_time_ms=elapsed,
            )
        except Exception as exc:
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=False, message=str(exc),
                response_time_ms=elapsed, error=type(exc).__name__,
            )

    def extract_schema(self) -> SchemaDetectionResult:
        with self._timed_operation("azure_blob_schema_detection"):
            columns = [
                {"name": "blob_name", "type": "string", "nullable": False, "sample_values": []},
                {"name": "size_bytes", "type": "int64", "nullable": False, "sample_values": [0]},
                {"name": "last_modified", "type": "string", "nullable": True, "sample_values": []},
                {"name": "content_type", "type": "string", "nullable": True, "sample_values": []},
                {"name": "extension", "type": "string", "nullable": True, "sample_values": self.file_extensions[:3]},
                {"name": "content_b64", "type": "string", "nullable": True, "sample_values": []},
            ]
            return SchemaDetectionResult(
                columns=columns,
                total_columns=len(columns),
                detected_primary_key="blob_name",
                timestamp_columns=["last_modified"],
            )

    def extract_full(self, config: ExtractionConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            blobs = self._list_blobs()
            df = pd.DataFrame(blobs) if blobs else pd.DataFrame()
            self.log_extraction(len(df), time.perf_counter() - start, 0)
            return df
        except Exception as exc:
            self.log_extraction(0, time.perf_counter() - start, 1)
            raise ExtractionError(
                self.source_id, f"Azure Blob extraction failed: {exc}"
            ) from exc

    def extract_incremental(self, config: IncrementalConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            blobs = self._list_blobs(since=config.last_extracted_at)
            df = pd.DataFrame(blobs) if blobs else pd.DataFrame()
            self.log_extraction(len(df), time.perf_counter() - start, 0)
            return df
        except Exception as exc:
            self.log_extraction(0, time.perf_counter() - start, 1)
            raise ExtractionError(
                self.source_id, f"Azure Blob incremental failed: {exc}"
            ) from exc

    def get_record_count(self) -> int:
        try:
            client = self._get_client()
            container = client.get_container_client(self.container_name)
            return sum(
                1 for b in container.list_blobs(name_starts_with=self.prefix or None)
                if (b.name.rsplit(".", 1)[-1].lower() if "." in b.name else "") in self.file_extensions
            )
        except Exception:
            return 0
