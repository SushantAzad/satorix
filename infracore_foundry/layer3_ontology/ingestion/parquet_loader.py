from datetime import datetime, timezone
from typing import Iterator
import pandas as pd
import pyarrow as pa
import logging
from core.minio_client import minio_client
from core.config import settings

logger = logging.getLogger(__name__)


class ParquetLoader:
    def list_source_files(self, client_id: str, source_id: str | None = None) -> list[str]:
        prefix = client_id
        if source_id:
            prefix = f"{client_id}/{source_id}"
        return minio_client.list_parquet_files(settings.minio_raw_bucket, prefix)

    def load_dataframe(
        self, bucket: str, object_name: str
    ) -> tuple[pd.DataFrame, dict]:
        table = minio_client.read_parquet(bucket, object_name)
        df = table.to_pandas()
        provenance = {
            "source_file": f"{bucket}/{object_name}",
            "loaded_at": datetime.now(timezone.utc).isoformat(),
            "row_count": len(df),
            "columns": list(df.columns),
        }
        return df, provenance

    def iter_sources(
        self,
        client_id: str,
        source_ids: list[str] | None = None,
    ) -> Iterator[tuple[str, pd.DataFrame, dict]]:
        files = self.list_source_files(client_id)
        for file_path in files:
            # Filter by source_ids if provided
            if source_ids:
                matched = any(sid in file_path for sid in source_ids)
                if not matched:
                    continue
            try:
                df, provenance = self.load_dataframe(settings.minio_raw_bucket, file_path)
                source_name = file_path.split("/")[-1].replace(".parquet", "")
                yield source_name, df, provenance
            except Exception as e:
                logger.error("Failed to load %s: %s", file_path, e)


parquet_loader = ParquetLoader()
