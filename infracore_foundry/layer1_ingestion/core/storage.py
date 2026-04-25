"""
MinIO client wrapper for raw Parquet file storage.
All data is stored in S3-compatible MinIO object storage.
"""

import hashlib
import io
import logging
import threading
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from minio import Minio
from minio.error import S3Error

from layer1_ingestion.core.config import get_settings

logger = logging.getLogger(__name__)

# Module-level MinIO client — one instance, thread-safe.
_minio_client: Optional[Minio] = None
_minio_lock = threading.Lock()


def get_minio_client() -> Minio:
    """Return a singleton MinIO client. Thread-safe."""
    global _minio_client
    if _minio_client is None:
        with _minio_lock:
            if _minio_client is None:
                settings = get_settings()
                _minio_client = Minio(
                    endpoint=settings.minio_endpoint,
                    access_key=settings.minio_access_key,
                    secret_key=settings.minio_secret_key,
                    secure=settings.minio_secure,
                )
                logger.info("MinIO client created for endpoint=%s", settings.minio_endpoint)
    return _minio_client


def ensure_bucket_exists(bucket_name: str) -> None:
    client = get_minio_client()
    try:
        if not client.bucket_exists(bucket_name):
            client.make_bucket(bucket_name)
            logger.info("Created MinIO bucket: %s", bucket_name)
    except S3Error as exc:
        logger.error("Failed to ensure bucket %s exists: %s", bucket_name, str(exc))
        raise


def object_exists(bucket: str, object_path: str) -> bool:
    """Return True if the object already exists in MinIO."""
    client = get_minio_client()
    try:
        client.stat_object(bucket, object_path)
        return True
    except S3Error as exc:
        if exc.code == "NoSuchKey":
            return False
        raise


def upload_parquet(
    df: pd.DataFrame,
    bucket: str,
    object_path: str,
    extra_metadata: Optional[dict] = None,
) -> str:
    """
    Write a DataFrame to Parquet and upload to MinIO.
    Returns the full object path.
    Raises if the upload fails — does NOT swallow errors.
    """
    client = get_minio_client()
    ensure_bucket_exists(bucket)

    table = pa.Table.from_pandas(df, preserve_index=False)

    existing_meta = table.schema.metadata or {}
    base_meta: dict[bytes, bytes] = {
        b"infracore_uploaded_at": datetime.now(timezone.utc).isoformat().encode(),
        b"infracore_record_count": str(len(df)).encode(),
        b"infracore_columns": ",".join(str(c) for c in df.columns).encode(),
    }
    if extra_metadata:
        for k, v in extra_metadata.items():
            base_meta[k.encode() if isinstance(k, str) else k] = (
                v.encode() if isinstance(v, str) else str(v).encode()
            )
    table = table.replace_schema_metadata({**existing_meta, **base_meta})

    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="snappy")
    buffer.seek(0)
    file_size = buffer.getbuffer().nbytes

    client.put_object(
        bucket_name=bucket,
        object_name=object_path,
        data=buffer,
        length=file_size,
        content_type="application/octet-stream",
    )

    logger.info(
        "Uploaded Parquet to MinIO",
        extra={
            "bucket": bucket,
            "object_path": object_path,
            "records": len(df),
            "size_bytes": file_size,
        },
    )
    return object_path


def download_parquet(bucket: str, object_path: str) -> pd.DataFrame:
    client = get_minio_client()
    try:
        response = client.get_object(bucket, object_path)
        data = response.read()
        response.close()
        response.release_conn()
        table = pq.read_table(io.BytesIO(data))
        df = table.to_pandas()
        logger.info(
            "Downloaded Parquet from MinIO",
            extra={"bucket": bucket, "object_path": object_path, "records": len(df)},
        )
        return df
    except S3Error as exc:
        logger.error("Failed to download Parquet: %s/%s - %s", bucket, object_path, str(exc))
        raise


def list_parquet_files(bucket: str, prefix: str) -> list[str]:
    client = get_minio_client()
    try:
        objects = client.list_objects(bucket, prefix=prefix, recursive=True)
        return sorted(
            obj.object_name
            for obj in objects
            if obj.object_name.endswith(".parquet")
        )
    except S3Error as exc:
        logger.error("Failed to list objects in %s/%s: %s", bucket, prefix, str(exc))
        raise


def get_latest_parquet(bucket: str, source_prefix: str) -> Optional[pd.DataFrame]:
    files = list_parquet_files(bucket, source_prefix)
    if not files:
        return None
    return download_parquet(bucket, files[-1])


def generate_batch_id(source_id: str, sync_type: str, partition_key: str) -> str:
    """
    Deterministic batch_id — same inputs always produce the same ID.
    partition_key: 'YYYY-MM-DD' for daily, 'YYYY-MM-DDTHH' for hourly.

    Re-running a sync for the same source + type + partition returns the
    same batch_id, which lets SyncEngine detect and skip duplicate runs.
    """
    content = f"{source_id}:{sync_type}:{partition_key}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def generate_object_path(
    client_id: str,
    source_id: str,
    batch_id: Optional[str] = None,
) -> str:
    """
    Standardized object path: client_id/source_id/YYYY/MM/DD/batch_id.parquet
    If batch_id is not provided a random one is generated (for ad-hoc uploads).
    """
    now = datetime.now(timezone.utc)
    if batch_id is None:
        batch_id = uuid4().hex
    return f"{client_id}/{source_id}/{now.year}/{now.month:02d}/{now.day:02d}/{batch_id}.parquet"
