from minio import Minio
from minio.error import S3Error
import pyarrow.parquet as pq
import pyarrow as pa
import io
from typing import Iterator
import logging
from .config import settings

logger = logging.getLogger(__name__)


class MinioClient:
    def __init__(self) -> None:
        self._client: Minio | None = None

    def connect(self) -> None:
        self._client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        # Verify connectivity
        try:
            self._client.list_buckets()
            logger.info("MinIO connected at %s", settings.minio_endpoint)
        except Exception as e:
            logger.error("MinIO connection failed: %s", e)
            raise

    @property
    def client(self) -> Minio:
        if not self._client:
            raise RuntimeError("MinIO client not initialized")
        return self._client

    def list_parquet_files(self, bucket: str, prefix: str = "") -> list[str]:
        objects = self.client.list_objects(bucket, prefix=prefix, recursive=True)
        return [
            obj.object_name
            for obj in objects
            if obj.object_name and obj.object_name.endswith(".parquet")
        ]

    def read_parquet(self, bucket: str, object_name: str) -> pa.Table:
        response = self.client.get_object(bucket, object_name)
        try:
            data = response.read()
        finally:
            response.close()
            response.release_conn()
        buf = io.BytesIO(data)
        table = pq.read_table(buf)
        logger.info("Read Parquet: %s/%s (%d rows)", bucket, object_name, len(table))
        return table

    def upload_parquet(self, bucket: str, object_name: str, table: pa.Table) -> None:
        buf = io.BytesIO()
        pq.write_table(table, buf)
        buf.seek(0)
        size = buf.getbuffer().nbytes
        self.client.put_object(bucket, object_name, buf, size, content_type="application/octet-stream")
        logger.info("Uploaded Parquet: %s/%s (%d bytes)", bucket, object_name, size)

    def iter_parquet_files(self, bucket: str, prefix: str = "") -> Iterator[tuple[str, pa.Table]]:
        files = self.list_parquet_files(bucket, prefix)
        for file_path in files:
            try:
                table = self.read_parquet(bucket, file_path)
                yield file_path, table
            except Exception as e:
                logger.error("Failed to read %s: %s", file_path, e)


minio_client = MinioClient()
