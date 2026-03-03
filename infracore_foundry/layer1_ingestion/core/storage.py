"""
MinIO client wrapper for raw Parquet file storage.
All data is stored in S3-compatible MinIO object storage.
"""

import io
import logging
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


def get_minio_client() -> Minio:
    """Create and return a MinIO client instance."""
    settings = get_settings()
    client = Minio(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )
    logger.debug("MinIO client created for endpoint=%s", settings.minio_endpoint)
    return client


def ensure_bucket_exists(bucket_name: str) -> None:
    """Create the bucket if it does not already exist."""
    client = get_minio_client()
    try:
        if not client.bucket_exists(bucket_name):
            client.make_bucket(bucket_name)
            logger.info("Created MinIO bucket: %s", bucket_name)
        else:
            logger.debug("MinIO bucket already exists: %s", bucket_name)
    except S3Error as exc:
        logger.error("Failed to ensure bucket %s exists: %s", bucket_name, str(exc))
        raise


def upload_parquet(
    df: pd.DataFrame,
    bucket: str,
    object_path: str,
) -> str:
    """
    Write a DataFrame to Parquet format and upload to MinIO.

    Object path format: client_id/source_id/YYYY/MM/DD/batch_id.parquet

    Args:
        df: DataFrame to upload.
        bucket: Target bucket name.
        object_path: Full object path within the bucket.

    Returns:
        The full object path where the file was stored.
    """
    client = get_minio_client()
    ensure_bucket_exists(bucket)

    table = pa.Table.from_pandas(df, preserve_index=False)

    # Add metadata to the Parquet schema
    existing_meta = table.schema.metadata or {}
    custom_meta = {
        b"infracore_uploaded_at": datetime.now(timezone.utc).isoformat().encode(),
        b"infracore_record_count": str(len(df)).encode(),
        b"infracore_columns": ",".join(df.columns).encode(),
    }
    merged_meta = {**existing_meta, **custom_meta}
    table = table.replace_schema_metadata(merged_meta)

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
    """
    Download a Parquet file from MinIO and return as a DataFrame.

    Args:
        bucket: Source bucket name.
        object_path: Object path within the bucket.

    Returns:
        DataFrame loaded from the Parquet file.
    """
    client = get_minio_client()
    try:
        response = client.get_object(bucket, object_path)
        data = response.read()
        response.close()
        response.release_conn()

        buffer = io.BytesIO(data)
        table = pq.read_table(buffer)
        df = table.to_pandas()

        logger.info(
            "Downloaded Parquet from MinIO",
            extra={
                "bucket": bucket,
                "object_path": object_path,
                "records": len(df),
            },
        )
        return df
    except S3Error as exc:
        logger.error(
            "Failed to download Parquet: %s/%s - %s", bucket, object_path, str(exc)
        )
        raise


def list_parquet_files(bucket: str, prefix: str) -> list[str]:
    """
    List all Parquet files in a bucket matching the given prefix.

    Args:
        bucket: Bucket name.
        prefix: Object prefix to filter by.

    Returns:
        List of object paths matching the prefix that end in .parquet.
    """
    client = get_minio_client()
    try:
        objects = client.list_objects(bucket, prefix=prefix, recursive=True)
        parquet_files = [
            obj.object_name
            for obj in objects
            if obj.object_name.endswith(".parquet")
        ]
        logger.debug(
            "Listed %d Parquet files in %s/%s", len(parquet_files), bucket, prefix
        )
        return sorted(parquet_files)
    except S3Error as exc:
        logger.error("Failed to list objects in %s/%s: %s", bucket, prefix, str(exc))
        raise


def get_latest_parquet(bucket: str, source_prefix: str) -> Optional[pd.DataFrame]:
    """
    Get the most recently uploaded Parquet file for a given source.

    Args:
        bucket: Bucket name.
        source_prefix: Prefix path (e.g., client_id/source_id/).

    Returns:
        DataFrame from the latest Parquet file, or None if no files exist.
    """
    files = list_parquet_files(bucket, source_prefix)
    if not files:
        logger.info("No Parquet files found for prefix: %s", source_prefix)
        return None

    latest_path = files[-1]  # Sorted by path; date-partitioned paths sort chronologically
    logger.info("Loading latest Parquet file: %s", latest_path)
    return download_parquet(bucket, latest_path)


def generate_object_path(
    client_id: str,
    source_id: str,
    batch_id: Optional[str] = None,
) -> str:
    """
    Generate a standardized object path for storing Parquet files.

    Format: client_id/source_id/YYYY/MM/DD/batch_id.parquet

    Args:
        client_id: Client organization identifier.
        source_id: Data source identifier.
        batch_id: Optional batch identifier. Generated if not provided.

    Returns:
        Formatted object path string.
    """
    now = datetime.now(timezone.utc)
    if batch_id is None:
        batch_id = uuid4().hex[:12]
    path = f"{client_id}/{source_id}/{now.year}/{now.month:02d}/{now.day:02d}/{batch_id}.parquet"
    return path
