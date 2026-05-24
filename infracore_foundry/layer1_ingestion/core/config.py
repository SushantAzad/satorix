"""
Application configuration using pydantic-settings.
Loads all environment variables from .env file.
"""

import logging
from functools import lru_cache
from typing import Any, Optional

from pydantic import Field
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # PostgreSQL
    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_db: str = Field(default="infracore", alias="POSTGRES_DB")
    postgres_user: str = Field(default="infracore", alias="POSTGRES_USER")
    postgres_password: str = Field(default="infracore_dev_password", alias="POSTGRES_PASSWORD")

    # MinIO
    minio_endpoint: str = Field(default="localhost:9000", alias="MINIO_ENDPOINT")
    minio_access_key: str = Field(default="infracore_minio", alias="MINIO_ACCESS_KEY")
    minio_secret_key: str = Field(default="infracore_minio_secret", alias="MINIO_SECRET_KEY")
    minio_raw_bucket: str = Field(default="raw-data", alias="MINIO_RAW_BUCKET")
    minio_secure: bool = Field(default=False, alias="MINIO_SECURE")

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    # Encryption
    encryption_key: str = Field(default="", alias="ENCRYPTION_KEY")

    # External APIs
    sandbox_api_key: str = Field(default="", alias="SANDBOX_API_KEY")
    google_credentials_path: str = Field(
        default="./credentials/google_service_account.json",
        alias="GOOGLE_CREDENTIALS_PATH",
    )

    # API Server
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8001, alias="API_PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    # API authentication — set a strong random value in .env for production.
    # Generate with: python -c "import secrets; print(secrets.token_hex(32))"
    api_key: str = Field(default="", alias="API_KEY")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "populate_by_name": True,
        "extra": "ignore",
    }

    @property
    def database_url(self) -> str:
        """Construct SQLAlchemy database URL."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def async_database_url(self) -> str:
        """Construct async SQLAlchemy database URL."""
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached application settings.
    Uses lru_cache so settings are only loaded once from env.
    """
    settings = Settings()
    logger.info(
        "Settings loaded",
        extra={
            "postgres_host": settings.postgres_host,
            "minio_endpoint": settings.minio_endpoint,
            "log_level": settings.log_level,
        },
    )
    return settings


CONNECTOR_TYPES: dict[str, Any] = {}


def register_connector(name: str, connector_class: Any) -> None:
    """Register a connector class by name for dynamic lookup."""
    CONNECTOR_TYPES[name] = connector_class
    logger.debug("Registered connector type: %s -> %s", name, connector_class.__name__)


def get_connector_class(name: str) -> Optional[Any]:
    """
    Look up a connector class by its registered name.
    Returns None (not raises) when the type is unknown so callers can
    handle the missing-connector case gracefully.
    """
    cls = CONNECTOR_TYPES.get(name)
    if cls is None:
        available = ", ".join(CONNECTOR_TYPES.keys()) or "(none registered)"
        logger.warning(
            "Unknown connector type %r — available: %s", name, available
        )
    return cls


def _auto_register_connectors() -> None:
    """
    Import all known connector modules so they self-register.
    Called once at app startup and at the top of each Airflow task.
    """
    try:
        from layer1_ingestion.connectors.csv_connector import CSVConnector
        register_connector("csv", CSVConnector)
    except ImportError:
        pass
    try:
        from layer1_ingestion.connectors.excel_connector import ExcelConnector
        register_connector("excel", ExcelConnector)
    except ImportError:
        pass
    try:
        from layer1_ingestion.connectors.postgresql_connector import PostgreSQLConnector
        register_connector("postgresql", PostgreSQLConnector)
    except ImportError:
        pass
    try:
        from layer1_ingestion.connectors.mysql_connector import MySQLConnector
        register_connector("mysql", MySQLConnector)
    except ImportError:
        pass
    try:
        from layer1_ingestion.connectors.rest_api_connector import RESTAPIConnector
        register_connector("rest_api", RESTAPIConnector)
    except ImportError:
        pass
    try:
        from layer1_ingestion.connectors.pdf_connector import PDFConnector
        register_connector("pdf", PDFConnector)
    except ImportError:
        pass
    try:
        from layer1_ingestion.connectors.s3_connector import S3Connector
        register_connector("s3", S3Connector)
    except ImportError:
        pass
    try:
        from layer1_ingestion.connectors.sftp_connector import SFTPConnector
        register_connector("sftp", SFTPConnector)
    except ImportError:
        pass
    try:
        from layer1_ingestion.connectors.google_sheets_connector import GoogleSheetsConnector
        register_connector("google_sheets", GoogleSheetsConnector)
    except ImportError:
        pass
    try:
        from layer1_ingestion.connectors.indian.mca21_connector import MCA21Connector
        register_connector("mca21", MCA21Connector)
    except ImportError:
        pass
    try:
        from layer1_ingestion.connectors.indian.sebi_connector import SEBIConnector
        register_connector("sebi", SEBIConnector)
    except ImportError:
        pass
    try:
        from layer1_ingestion.connectors.indian.rbi_connector import RBIConnector
        register_connector("rbi", RBIConnector)
    except ImportError:
        pass
    try:
        from layer1_ingestion.connectors.indian.tally_connector import TallyConnector
        register_connector("tally", TallyConnector)
    except ImportError:
        pass

    # ── New generic connectors ──────────────────────────────────────────────
    try:
        from layer1_ingestion.connectors.email_connector import EmailConnector
        register_connector("email", EmailConnector)
    except ImportError:
        pass
    try:
        from layer1_ingestion.connectors.whatsapp_connector import WhatsAppConnector
        register_connector("whatsapp", WhatsAppConnector)
    except ImportError:
        pass
    try:
        from layer1_ingestion.connectors.mssql_connector import MSSQLConnector
        register_connector("mssql", MSSQLConnector)
    except ImportError:
        pass
    try:
        from layer1_ingestion.connectors.oracle_connector import OracleConnector
        register_connector("oracle", OracleConnector)
    except ImportError:
        pass
    try:
        from layer1_ingestion.connectors.mongodb_connector import MongoDBConnector
        register_connector("mongodb", MongoDBConnector)
    except ImportError:
        pass
    try:
        from layer1_ingestion.connectors.salesforce_connector import SalesforceConnector
        register_connector("salesforce", SalesforceConnector)
    except ImportError:
        pass
    try:
        from layer1_ingestion.connectors.sharepoint_connector import SharePointConnector
        register_connector("sharepoint", SharePointConnector)
    except ImportError:
        pass
    try:
        from layer1_ingestion.connectors.zoho_connector import ZohoConnector
        register_connector("zoho", ZohoConnector)
    except ImportError:
        pass
    try:
        from layer1_ingestion.connectors.sap_connector import SAPConnector
        register_connector("sap", SAPConnector)
    except ImportError:
        pass
    try:
        from layer1_ingestion.connectors.hubspot_connector import HubSpotConnector
        register_connector("hubspot", HubSpotConnector)
    except ImportError:
        pass
    try:
        from layer1_ingestion.connectors.freshdesk_connector import FreshdeskConnector
        register_connector("freshdesk", FreshdeskConnector)
    except ImportError:
        pass
    try:
        from layer1_ingestion.connectors.google_drive_connector import GoogleDriveConnector
        register_connector("google_drive", GoogleDriveConnector)
    except ImportError:
        pass
    try:
        from layer1_ingestion.connectors.azure_blob_connector import AzureBlobConnector
        register_connector("azure_blob", AzureBlobConnector)
    except ImportError:
        pass
    try:
        from layer1_ingestion.connectors.slack_connector import SlackConnector
        register_connector("slack", SlackConnector)
    except ImportError:
        pass
    try:
        from layer1_ingestion.connectors.notion_connector import NotionConnector
        register_connector("notion", NotionConnector)
    except ImportError:
        pass
    try:
        from layer1_ingestion.connectors.telegram_connector import TelegramConnector
        register_connector("telegram", TelegramConnector)
    except ImportError:
        pass
    try:
        from layer1_ingestion.connectors.dropbox_connector import DropboxConnector
        register_connector("dropbox", DropboxConnector)
    except ImportError:
        pass
    try:
        from layer1_ingestion.connectors.box_connector import BoxConnector
        register_connector("box", BoxConnector)
    except ImportError:
        pass
    try:
        from layer1_ingestion.connectors.quickbooks_connector import QuickBooksConnector
        register_connector("quickbooks", QuickBooksConnector)
    except ImportError:
        pass
    try:
        from layer1_ingestion.connectors.jira_connector import JiraConnector
        register_connector("jira", JiraConnector)
    except ImportError:
        pass
    try:
        from layer1_ingestion.connectors.zendesk_connector import ZendeskConnector
        register_connector("zendesk", ZendeskConnector)
    except ImportError:
        pass
    try:
        from layer1_ingestion.connectors.pipedrive_connector import PipedriveConnector
        register_connector("pipedrive", PipedriveConnector)
    except ImportError:
        pass
    try:
        from layer1_ingestion.connectors.ftp_connector import FTPConnector
        register_connector("ftp", FTPConnector)
    except ImportError:
        pass

    # ── New Indian-specific connectors ─────────────────────────────────────
    try:
        from layer1_ingestion.connectors.indian.gstn_connector import GSTNConnector
        register_connector("gstn", GSTNConnector)
    except ImportError:
        pass
    try:
        from layer1_ingestion.connectors.indian.ibbi_connector import IBBIConnector
        register_connector("ibbi", IBBIConnector)
    except ImportError:
        pass
    try:
        from layer1_ingestion.connectors.indian.bse_nse_connector import BSENSEConnector
        register_connector("bse_nse", BSENSEConnector)
    except ImportError:
        pass
    try:
        from layer1_ingestion.connectors.indian.rera_connector import RERAConnector
        register_connector("rera", RERAConnector)
    except ImportError:
        pass
    try:
        from layer1_ingestion.connectors.indian.epfo_connector import EPFOConnector
        register_connector("epfo", EPFOConnector)
    except ImportError:
        pass
    try:
        from layer1_ingestion.connectors.indian.msme_connector import MSMEConnector
        register_connector("msme", MSMEConnector)
    except ImportError:
        pass
    try:
        from layer1_ingestion.connectors.indian.busy_accounting_connector import BUSYAccountingConnector
        register_connector("busy", BUSYAccountingConnector)
    except ImportError:
        pass
    try:
        from layer1_ingestion.connectors.indian.traces_connector import TRACESConnector
        register_connector("traces", TRACESConnector)
    except ImportError:
        pass
    try:
        from layer1_ingestion.connectors.indian.marg_erp_connector import MargERPConnector
        register_connector("marg_erp", MargERPConnector)
    except ImportError:
        pass


# Run auto-registration on module import.
_auto_register_connectors()
