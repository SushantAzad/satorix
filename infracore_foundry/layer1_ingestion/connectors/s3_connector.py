"""
S3-compatible object storage connector using boto3.
Works with AWS S3, MinIO, and other S3-compatible services.
"""

import io
import logging
import os
import time
from typing import Optional

import boto3
import pandas as pd
import pyarrow.parquet as pq

from layer1_ingestion.connectors.base_connector import (
    BaseConnector, ConnectionTestResult, SchemaDetectionResult,
    ExtractionConfig, IncrementalConfig, ExtractionError,
)

logger = logging.getLogger(__name__)


class S3Connector(BaseConnector):
    """S3-compatible object storage connector."""

    REQUIRED_CONFIG_FIELDS = ["bucket_name"]

    def __init__(self, source_id: str, config: dict) -> None:
        super().__init__(source_id, config)
        self.bucket_name: str = config.get("bucket_name", "")
        self.prefix: str = config.get("prefix", "")
        self.file_pattern: str = config.get("file_pattern", "*.csv")
        self.endpoint_url: Optional[str] = config.get("endpoint_url")
        self.access_key: str = config.get("access_key", "")
        self.secret_key: str = config.get("secret_key", "")
        self.region: str = config.get("region", "us-east-1")

    def _get_client(self):
        kwargs = {
            "aws_access_key_id": self.access_key,
            "aws_secret_access_key": self.secret_key,
            "region_name": self.region,
        }
        if self.endpoint_url:
            kwargs["endpoint_url"] = self.endpoint_url
        return boto3.client("s3", **kwargs)

    def test_connection(self) -> ConnectionTestResult:
        start = time.perf_counter()
        try:
            client = self._get_client()
            client.head_bucket(Bucket=self.bucket_name)
            resp = client.list_objects_v2(Bucket=self.bucket_name, Prefix=self.prefix, MaxKeys=1)
            count = resp.get("KeyCount", 0)
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=True,
                message=f"Bucket '{self.bucket_name}' accessible, prefix has objects" if count else f"Bucket '{self.bucket_name}' accessible (empty prefix)",
                response_time_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(success=False, message=str(e), response_time_ms=elapsed, error=type(e).__name__)

    def extract_schema(self) -> SchemaDetectionResult:
        with self._timed_operation("schema_detection"):
            client = self._get_client()
            keys = self._list_matching_keys(client)
            if not keys:
                return SchemaDetectionResult(columns=[], total_columns=0)
            obj = client.get_object(Bucket=self.bucket_name, Key=keys[0])
            data = obj["Body"].read()
            ext = os.path.splitext(keys[0])[1].lower()
            if ext == ".parquet":
                df = pq.read_table(io.BytesIO(data)).to_pandas().head(100)
            elif ext in (".csv", ".tsv"):
                df = pd.read_csv(io.BytesIO(data), nrows=100)
            else:
                df = pd.read_csv(io.BytesIO(data), nrows=100)
            columns = [
                {"name": str(c), "type": str(df[c].dtype), "nullable": bool(df[c].isnull().any()), "sample_values": df[c].dropna().head(5).tolist()}
                for c in df.columns
            ]
            return SchemaDetectionResult(columns=columns, total_columns=len(columns))

    def extract_full(self, config: ExtractionConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            client = self._get_client()
            keys = self._list_matching_keys(client)
            all_dfs = []
            for key in keys:
                obj = client.get_object(Bucket=self.bucket_name, Key=key)
                data = obj["Body"].read()
                ext = os.path.splitext(key)[1].lower()
                if ext == ".parquet":
                    df = pq.read_table(io.BytesIO(data)).to_pandas()
                elif ext in (".csv", ".tsv"):
                    df = pd.read_csv(io.BytesIO(data))
                elif ext in (".xlsx", ".xls"):
                    df = pd.read_excel(io.BytesIO(data))
                else:
                    df = pd.read_csv(io.BytesIO(data))
                df["_source_key"] = key
                all_dfs.append(df)
            combined = pd.concat(all_dfs, ignore_index=True) if all_dfs else pd.DataFrame()
            duration = time.perf_counter() - start
            self.log_extraction(len(combined), duration, 0)
            return combined
        except Exception as e:
            duration = time.perf_counter() - start
            self.log_extraction(0, duration, 1)
            raise ExtractionError(self.source_id, f"S3 extraction failed: {str(e)}") from e

    def extract_incremental(self, config: IncrementalConfig) -> pd.DataFrame:
        """Filter by LastModified date for incremental sync."""
        client = self._get_client()
        keys = self._list_matching_keys(client, after=config.last_extracted_at)
        if not keys:
            return pd.DataFrame()
        return self.extract_full(config)

    def get_record_count(self) -> int:
        client = self._get_client()
        return len(self._list_matching_keys(client))

    def _list_matching_keys(self, client, after=None) -> list[str]:
        import fnmatch
        paginator = client.get_paginator("list_objects_v2")
        keys = []
        for page in paginator.paginate(Bucket=self.bucket_name, Prefix=self.prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if fnmatch.fnmatch(os.path.basename(key), self.file_pattern):
                    if after and obj.get("LastModified"):
                        if obj["LastModified"].replace(tzinfo=None) <= after.replace(tzinfo=None):
                            continue
                    keys.append(key)
        return sorted(keys)
