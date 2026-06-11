"""
MySQL connector using PyMySQL with chunked SELECT for large tables.
Key differences from PostgreSQL: LIMIT/OFFSET, utf8mb4, no RETURNING, no server-side cursors.
"""

import logging
import time
from typing import Optional

import pandas as pd
from sqlalchemy import create_engine, inspect, text

from layer1_ingestion.connectors.base_connector import (
    BaseConnector, ConnectionTestResult, SchemaDetectionResult,
    ExtractionConfig, IncrementalConfig, ExtractionError,
)

logger = logging.getLogger(__name__)


class MySQLConnector(BaseConnector):
    """Full MySQL integration using PyMySQL driver with chunked extraction."""

    REQUIRED_CONFIG_FIELDS = ["host", "database"]

    def __init__(self, source_id: str, config: dict) -> None:
        super().__init__(source_id, config)
        self.host: str = config.get("host", "localhost")
        self.port: int = config.get("port", 3306)
        self.database: str = config.get("database", "")
        self.username: str = config.get("username", "")
        self.password: str = config.get("password", "")
        self.table_name: Optional[str] = config.get("table_name")
        self.query: Optional[str] = config.get("query")
        self.ssl_ca: Optional[str] = config.get("ssl_ca")
        self.ssl_cert: Optional[str] = config.get("ssl_cert")
        self.ssl_key: Optional[str] = config.get("ssl_key")
        self.charset: str = config.get("charset", "utf8mb4")

    def _get_connection_url(self) -> str:
        url = (
            f"mysql+pymysql://{self.username}:{self.password}"
            f"@{self.host}:{self.port}/{self.database}"
            f"?charset={self.charset}"
        )
        return url

    def _get_engine(self):
        connect_args = {}
        if self.ssl_ca:
            ssl_config = {"ca": self.ssl_ca}
            if self.ssl_cert:
                ssl_config["cert"] = self.ssl_cert
            if self.ssl_key:
                ssl_config["key"] = self.ssl_key
            connect_args["ssl"] = ssl_config

        return create_engine(
            self._get_connection_url(),
            pool_pre_ping=True,
            pool_size=2,
            max_overflow=3,
            connect_args=connect_args,
        )

    def test_connection(self) -> ConnectionTestResult:
        start = time.perf_counter()
        try:
            engine = self._get_engine()
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            elapsed = (time.perf_counter() - start) * 1000
            engine.dispose()
            return ConnectionTestResult(
                success=True,
                message=f"Connected to MySQL {self.host}:{self.port}/{self.database}",
                response_time_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=False, message=str(e),
                response_time_ms=elapsed, error=type(e).__name__,
            )

    def extract_schema(self) -> SchemaDetectionResult:
        with self._timed_operation("schema_detection"):
            engine = self._get_engine()
            try:
                inspector = inspect(engine)
                if self.table_name:
                    cols = inspector.get_columns(self.table_name)
                    pk = inspector.get_pk_constraint(self.table_name)
                    columns = [
                        {
                            "name": c["name"], "type": str(c["type"]),
                            "nullable": c.get("nullable", True), "sample_values": [],
                        }
                        for c in cols
                    ]
                    with engine.connect() as conn:
                        result = conn.execute(
                            text(f"SELECT * FROM `{self.table_name}` LIMIT 5")
                        )
                        rows = result.fetchall()
                        keys = list(result.keys())
                        for i, ci in enumerate(columns):
                            if i < len(keys):
                                ci["sample_values"] = [
                                    r[i] for r in rows if r[i] is not None
                                ][:5]
                    pk_col = pk["constrained_columns"][0] if pk.get("constrained_columns") else None
                    ts_cols = [
                        c["name"] for c in cols
                        if "datetime" in str(c["type"]).lower()
                        or "timestamp" in str(c["type"]).lower()
                        or "date" in str(c["type"]).lower()
                    ]
                    with engine.connect() as conn:
                        count = conn.execute(
                            text(f"SELECT COUNT(*) FROM `{self.table_name}`")
                        ).scalar()
                    return SchemaDetectionResult(
                        columns=columns, total_columns=len(columns),
                        detected_primary_key=pk_col,
                        timestamp_columns=ts_cols, record_count_estimate=count,
                    )
                else:
                    with engine.connect() as conn:
                        result = conn.execute(text(f"SELECT * FROM ({self.query}) sq LIMIT 0"))
                        col_names = list(result.keys())
                    columns = [
                        {"name": n, "type": "unknown", "nullable": True, "sample_values": []}
                        for n in col_names
                    ]
                    return SchemaDetectionResult(columns=columns, total_columns=len(columns))
            finally:
                engine.dispose()

    def extract_full(self, config: ExtractionConfig) -> pd.DataFrame:
        """Chunked SELECT with LIMIT/OFFSET since MySQL lacks server-side cursors."""
        start = time.perf_counter()
        try:
            self.logger.info(
                "extraction_start",
                extra={"source_id": self.source_id, "table": self.table_name},
            )
            engine = self._get_engine()
            base_sql = (
                f"SELECT * FROM `{self.table_name}`"
                if self.table_name
                else f"SELECT * FROM ({self.query}) sq"
            )
            chunks = []
            offset = 0
            with engine.connect() as conn:
                while True:
                    sql = text(f"{base_sql} LIMIT :limit OFFSET :offset")
                    result = conn.execute(sql, {"limit": config.batch_size, "offset": offset})
                    col_names = list(result.keys())
                    rows = result.fetchall()
                    if not rows:
                        break
                    chunk_df = pd.DataFrame(rows, columns=col_names)
                    chunks.append(chunk_df)
                    if len(rows) < config.batch_size:
                        break
                    offset += config.batch_size
            engine.dispose()
            df = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()
            duration = time.perf_counter() - start
            self.log_extraction(len(df), duration, 0)
            return df
        except Exception as e:
            duration = time.perf_counter() - start
            self.log_extraction(0, duration, 1)
            raise ExtractionError(
                self.source_id, f"MySQL extraction failed: {str(e)}",
                context={"host": self.host, "database": self.database},
            ) from e

    def extract_incremental(self, config: IncrementalConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            engine = self._get_engine()
            if config.strategy == "timestamp":
                if not config.last_extracted_at:
                    return self.extract_full(config)
                ts_col = self.config.get("timestamp_column", "updated_at")
                base = f"SELECT * FROM `{self.table_name}`" if self.table_name else f"SELECT * FROM ({self.query}) sq"
                sql = text(f"{base} WHERE `{ts_col}` > :last_sync ORDER BY `{ts_col}` ASC")
                params = {"last_sync": config.last_extracted_at}
            elif config.strategy == "sequence":
                if not config.last_extracted_id:
                    return self.extract_full(config)
                id_col = self.config.get("id_column", "id")
                base = f"SELECT * FROM `{self.table_name}`" if self.table_name else f"SELECT * FROM ({self.query}) sq"
                sql = text(f"{base} WHERE `{id_col}` > :last_id ORDER BY `{id_col}` ASC")
                params = {"last_id": config.last_extracted_id}
            else:
                return self.extract_full(config)

            with engine.connect() as conn:
                result = conn.execute(sql, params)
                col_names = list(result.keys())
                rows = result.fetchall()
            engine.dispose()
            df = pd.DataFrame(rows, columns=col_names) if rows else pd.DataFrame()
            duration = time.perf_counter() - start
            self.log_extraction(len(df), duration, 0)
            return df
        except Exception as e:
            duration = time.perf_counter() - start
            self.log_extraction(0, duration, 1)
            raise ExtractionError(
                self.source_id, f"MySQL incremental failed: {str(e)}",
            ) from e

    def get_record_count(self) -> int:
        engine = self._get_engine()
        try:
            with engine.connect() as conn:
                if self.table_name:
                    result = conn.execute(text(f"SELECT COUNT(*) FROM `{self.table_name}`"))
                elif self.query:
                    result = conn.execute(text(f"SELECT COUNT(*) FROM ({self.query}) sq"))
                else:
                    return 0
                return result.scalar() or 0
        finally:
            engine.dispose()
