"""Custom Airflow hooks for Layer 1 services."""

from airflow.hooks.base import BaseHook


class InfracoreMinIOHook(BaseHook):
    """Airflow hook for MinIO/S3 operations."""

    conn_name_attr = "minio_conn_id"
    default_conn_name = "minio_default"
    conn_type = "s3"
    hook_name = "Infracore MinIO"

    def __init__(self, minio_conn_id: str = "minio_default") -> None:
        super().__init__()
        self.minio_conn_id = minio_conn_id

    def get_client(self):
        from layer1_ingestion.core.storage import get_minio_client
        return get_minio_client()


class InfracoreDBHook(BaseHook):
    """Airflow hook for Layer 1 database."""

    conn_name_attr = "infracore_db_conn_id"
    default_conn_name = "infracore_db"
    conn_type = "postgres"
    hook_name = "Infracore Database"

    def __init__(self, db_conn_id: str = "infracore_db") -> None:
        super().__init__()
        self.db_conn_id = db_conn_id

    def get_session(self):
        from layer1_ingestion.core.database import get_db_context
        return get_db_context()
