"""
Abstract base class for all data source connectors.
Defines the interface every connector must implement and provides
common utility methods for logging, validation, and Parquet output.
"""

import builtins
import hashlib
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd

from layer1_ingestion.core.storage import upload_parquet, generate_object_path

logger = logging.getLogger(__name__)


class ConnectionError(builtins.ConnectionError):
    """Cannot reach the data source. Extends builtins.ConnectionError so network errors
    raised by third-party libraries (httpx, psycopg2, paramiko) can also be caught here."""
    def __init__(self, source_id: str, message: str, context: Optional[dict] = None):
        self.source_id = source_id
        self.context = context or {}
        super().__init__(f"[{source_id}] Connection failed: {message}")


class AuthenticationError(Exception):
    """Credentials rejected by the data source."""
    def __init__(self, source_id: str, message: str, context: Optional[dict] = None):
        self.source_id = source_id
        self.context = context or {}
        super().__init__(f"[{source_id}] Authentication failed: {message}")


class SchemaError(Exception):
    """Unexpected data structure from the source."""
    def __init__(self, source_id: str, message: str, context: Optional[dict] = None):
        self.source_id = source_id
        self.context = context or {}
        super().__init__(f"[{source_id}] Schema error: {message}")


class ExtractionError(Exception):
    """Error during data extraction."""
    def __init__(self, source_id: str, message: str, context: Optional[dict] = None):
        self.source_id = source_id
        self.context = context or {}
        super().__init__(f"[{source_id}] Extraction error: {message}")


class RateLimitError(Exception):
    """API rate limit exceeded."""
    def __init__(self, source_id: str, message: str, retry_after: Optional[float] = None, context: Optional[dict] = None):
        self.source_id = source_id
        self.retry_after = retry_after
        self.context = context or {}
        super().__init__(f"[{source_id}] Rate limit exceeded: {message}")


@dataclass
class ConnectionTestResult:
    """Result of testing connectivity to a data source."""
    success: bool
    message: str
    response_time_ms: float
    schema_detected: Optional[dict] = None
    error: Optional[str] = None


@dataclass
class SchemaDetectionResult:
    """Result of schema detection on a data source."""
    columns: list[dict]  # [{name, type, nullable, sample_values}]
    total_columns: int
    detected_primary_key: Optional[str] = None
    indian_identifiers: dict = field(default_factory=dict)  # {col_name: identifier_type}
    timestamp_columns: list[str] = field(default_factory=list)
    record_count_estimate: Optional[int] = None


@dataclass
class ExtractionConfig:
    """Configuration for a full extraction run."""
    source_id: str
    client_id: str
    batch_size: int = 10000
    output_bucket: str = "raw-data"


@dataclass
class IncrementalConfig(ExtractionConfig):
    """Configuration for an incremental extraction run."""
    strategy: str = "timestamp"  # timestamp, sequence, cdc, full_refresh
    last_extracted_at: Optional[datetime] = None
    last_extracted_id: Optional[str] = None


class BaseConnector(ABC):
    """
    Abstract base class for all data source connectors.

    Every connector must implement:
    - test_connection()
    - extract_schema()
    - extract_full()
    - extract_incremental()
    - get_record_count()

    Connectors get these concrete methods for free:
    - validate_config()
    - log_extraction()
    - to_parquet()
    - compute_checksum()
    """

    def __init__(self, source_id: str, config: dict) -> None:
        self.source_id = source_id
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @abstractmethod
    def test_connection(self) -> ConnectionTestResult:
        """Test connectivity to the data source."""
        ...

    @abstractmethod
    def extract_schema(self) -> SchemaDetectionResult:
        """Detect and return the schema of the data source."""
        ...

    @abstractmethod
    def extract_full(self, config: ExtractionConfig) -> pd.DataFrame:
        """Extract all data from the source."""
        ...

    @abstractmethod
    def extract_incremental(self, config: IncrementalConfig) -> pd.DataFrame:
        """Extract only new/changed data since the last sync."""
        ...

    @abstractmethod
    def get_record_count(self) -> int:
        """Get the total number of records in the data source."""
        ...

    def validate_config(self) -> list[str]:
        """
        Validate the connector configuration.
        Returns a list of validation error messages (empty if valid).
        """
        errors: list[str] = []
        required_fields = getattr(self, "REQUIRED_CONFIG_FIELDS", [])
        for field_name in required_fields:
            if field_name not in self.config or not self.config[field_name]:
                errors.append(f"Missing required config field: {field_name}")
        return errors

    def log_extraction(self, records: int, duration: float, errors: int) -> None:
        """Log extraction statistics in structured format."""
        self.logger.info(
            "Extraction complete",
            extra={
                "source_id": self.source_id,
                "records_extracted": records,
                "records_failed": errors,
                "duration_seconds": round(duration, 2),
                "connector_type": self.__class__.__name__,
            },
        )

    def to_parquet(
        self,
        df: pd.DataFrame,
        client_id: str,
        batch_id: Optional[str] = None,
        bucket: str = "raw-data",
    ) -> str:
        """
        Upload a DataFrame to MinIO as a Parquet file.
        Returns the full object path.
        """
        object_path = generate_object_path(client_id, self.source_id, batch_id)
        result_path = upload_parquet(df, bucket, object_path)
        self.logger.info(
            "Data written to Parquet",
            extra={
                "source_id": self.source_id,
                "object_path": result_path,
                "records": len(df),
            },
        )
        return result_path

    @staticmethod
    def compute_checksum(df: pd.DataFrame) -> str:
        """Compute SHA-256 checksum of a DataFrame for change detection."""
        content = pd.util.hash_pandas_object(df, index=False).values.tobytes()
        return hashlib.sha256(content).hexdigest()

    def _timed_operation(self, operation_name: str):
        """Context manager for timing operations."""
        return _TimedOperation(self.logger, self.source_id, operation_name)


class _TimedOperation:
    """Helper context manager for timing connector operations."""

    def __init__(self, log: logging.Logger, source_id: str, operation: str) -> None:
        self.logger = log
        self.source_id = source_id
        self.operation = operation
        self.start_time: float = 0

    def __enter__(self) -> "_TimedOperation":
        self.start_time = time.perf_counter()
        self.logger.info(
            "%s started", self.operation,
            extra={"source_id": self.source_id},
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        elapsed = (time.perf_counter() - self.start_time) * 1000
        if exc_type is not None:
            self.logger.error(
                "%s failed after %.1fms: %s",
                self.operation, elapsed, str(exc_val),
                extra={"source_id": self.source_id, "elapsed_ms": elapsed},
            )
        else:
            self.logger.info(
                "%s completed in %.1fms",
                self.operation, elapsed,
                extra={"source_id": self.source_id, "elapsed_ms": elapsed},
            )
        return False

    @property
    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self.start_time) * 1000
