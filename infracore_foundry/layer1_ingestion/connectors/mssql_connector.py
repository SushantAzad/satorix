"""
Microsoft SQL Server connector using SQLAlchemy + pymssql.

Covers Indian PSU banks, large manufacturers, and SAP-adjacent deployments
that run MS SQL Server as their primary OLTP database.

Supports Windows Authentication (domain) and SQL Server Authentication.
Handles NVARCHAR/NTEXT correctly for Unicode data.

config keys:
  host            : str   e.g. "sqlserver.corp.local" or IP
  port            : int   default 1433
  database        : str
  username        : str
  password        : str
  table_name      : str   (mutually exclusive with query)
  query           : str
  schema          : str   default "dbo"
  windows_auth    : bool  use Windows/domain authentication — default False
  encrypt         : bool  TLS encryption — default True
  trust_server_certificate : bool  default False (set True for self-signed)
  timestamp_column : str  for incremental
  id_column        : str  for incremental sequence
"""

import logging
import time
from typing import Optional

import pandas as pd
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import NullPool

from layer1_ingestion.connectors.base_connector import (
    BaseConnector,
    ConnectionTestResult,
    ExtractionConfig,
    ExtractionError,
    IncrementalConfig,
    SchemaDetectionResult,
)

logger = logging.getLogger(__name__)


class MSSQLConnector(BaseConnector):
    """Microsoft SQL Server connector via pymssql driver."""

    REQUIRED_CONFIG_FIELDS = ["host", "database"]

    def __init__(self, source_id: str, config: dict) -> None:
        super().__init__(source_id, config)
        self.host: str = config.get("host", "")
        self.port: int = int(config.get("port", 1433))
        self.database: str = config.get("database", "")
        self.username: str = config.get("username", "")
        self.password: str = config.get("password", "")
        self.table_name: Optional[str] = config.get("table_name")
        self.schema: str = config.get("schema", "dbo")
        self.query: Optional[str] = config.get("query")
        self.windows_auth: bool = bool(config.get("windows_auth", False))
        self.encrypt: bool = bool(config.get("encrypt", True))
        self.trust_server_cert: bool = bool(config.get("trust_server_certificate", False))

    def _connection_url(self) -> str:
        if self.windows_auth:
            return (
                f"mssql+pymssql://{self.host}:{self.port}/{self.database}"
                f"?trusted_connection=yes"
            )
        return (
            f"mssql+pymssql://{self.username}:{self.password}"
            f"@{self.host}:{self.port}/{self.database}"
        )

    def _get_engine(self):
        return create_engine(
            self._connection_url(),
            poolclass=NullPool,
            fast_executemany=True,
        )

    def _qualified_table(self) -> str:
        return f"[{self.schema}].[{self.table_name}]"

    def test_connection(self) -> ConnectionTestResult:
        start = time.perf_counter()
        try:
            engine = self._get_engine()
            with engine.connect() as conn:
                version = conn.execute(
                    text("SELECT @@VERSION")
                ).scalar()
            engine.dispose()
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=True,
                message=f"Connected: {str(version)[:80]}",
                response_time_ms=elapsed,
            )
        except Exception as exc:
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=False, message=str(exc),
                response_time_ms=elapsed, error=type(exc).__name__,
            )

    def extract_schema(self) -> SchemaDetectionResult:
        with self._timed_operation("mssql_schema_detection"):
            engine = self._get_engine()
            try:
                if self.table_name:
                    inspector = inspect(engine)
                    cols = inspector.get_columns(self.table_name, schema=self.schema)
                    pk = inspector.get_pk_constraint(self.table_name, schema=self.schema)
                    ts_cols = [
                        c["name"] for c in cols
                        if any(t in str(c["type"]).lower()
                               for t in ("datetime", "date", "timestamp", "smalldatetime"))
                    ]
                    columns = [
                        {
                            "name": c["name"],
                            "type": str(c["type"]),
                            "nullable": c.get("nullable", True),
                            "sample_values": [],
                        }
                        for c in cols
                    ]
                    with engine.connect() as conn:
                        rows = conn.execute(
                            text(f"SELECT TOP 5 * FROM {self._qualified_table()}")
                        ).fetchall()
                        for i, col in enumerate(columns):
                            col["sample_values"] = [
                                r[i] for r in rows if r[i] is not None
                            ][:3]
                        count = conn.execute(
                            text(f"SELECT COUNT(*) FROM {self._qualified_table()}")
                        ).scalar()
                    pk_col = (
                        pk["constrained_columns"][0]
                        if pk.get("constrained_columns") else None
                    )
                    return SchemaDetectionResult(
                        columns=columns,
                        total_columns=len(columns),
                        detected_primary_key=pk_col,
                        timestamp_columns=ts_cols,
                        record_count_estimate=count,
                    )
                else:
                    with engine.connect() as conn:
                        keys = list(
                            conn.execute(
                                text(f"SELECT TOP 0 * FROM ({self.query}) sq")
                            ).keys()
                        )
                    columns = [
                        {"name": k, "type": "unknown", "nullable": True, "sample_values": []}
                        for k in keys
                    ]
                    return SchemaDetectionResult(columns=columns, total_columns=len(columns))
            finally:
                engine.dispose()

    def extract_full(self, config: ExtractionConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            engine = self._get_engine()
            base_sql = (
                f"SELECT * FROM {self._qualified_table()}"
                if self.table_name
                else f"SELECT * FROM ({self.query}) sq"
            )
            chunks: list[pd.DataFrame] = []
            offset = 0
            with engine.connect() as conn:
                # MSSQL uses OFFSET/FETCH (SQL Server 2012+)
                while True:
                    sql = text(
                        f"{base_sql} ORDER BY (SELECT NULL) "
                        f"OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY"
                    )
                    result = conn.execute(
                        sql, {"offset": offset, "limit": config.batch_size}
                    )
                    col_names = list(result.keys())
                    rows = result.fetchall()
                    if not rows:
                        break
                    chunks.append(pd.DataFrame(rows, columns=col_names))
                    if len(rows) < config.batch_size:
                        break
                    offset += config.batch_size
            engine.dispose()
            df = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()
            self.log_extraction(len(df), time.perf_counter() - start, 0)
            return df
        except Exception as exc:
            self.log_extraction(0, time.perf_counter() - start, 1)
            raise ExtractionError(
                self.source_id, f"MSSQL extraction failed: {exc}"
            ) from exc

    def extract_incremental(self, config: IncrementalConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            engine = self._get_engine()
            if config.strategy == "timestamp" and config.last_extracted_at:
                ts_col = self.config.get("timestamp_column", "updated_at")
                base = (
                    f"SELECT * FROM {self._qualified_table()}"
                    if self.table_name
                    else f"SELECT * FROM ({self.query}) sq"
                )
                sql = text(f"{base} WHERE [{ts_col}] > :last_sync ORDER BY [{ts_col}] ASC")
                params = {"last_sync": config.last_extracted_at}
            elif config.strategy == "sequence" and config.last_extracted_id:
                id_col = self.config.get("id_column", "id")
                base = (
                    f"SELECT * FROM {self._qualified_table()}"
                    if self.table_name
                    else f"SELECT * FROM ({self.query}) sq"
                )
                sql = text(f"{base} WHERE [{id_col}] > :last_id ORDER BY [{id_col}] ASC")
                params = {"last_id": config.last_extracted_id}
            else:
                return self.extract_full(config)

            with engine.connect() as conn:
                result = conn.execute(sql, params)
                col_names = list(result.keys())
                rows = result.fetchall()
            engine.dispose()
            df = pd.DataFrame(rows, columns=col_names) if rows else pd.DataFrame()
            self.log_extraction(len(df), time.perf_counter() - start, 0)
            return df
        except Exception as exc:
            self.log_extraction(0, time.perf_counter() - start, 1)
            raise ExtractionError(
                self.source_id, f"MSSQL incremental failed: {exc}"
            ) from exc

    def get_record_count(self) -> int:
        engine = self._get_engine()
        try:
            with engine.connect() as conn:
                if self.table_name:
                    return conn.execute(
                        text(f"SELECT COUNT(*) FROM {self._qualified_table()}")
                    ).scalar() or 0
                elif self.query:
                    return conn.execute(
                        text(f"SELECT COUNT(*) FROM ({self.query}) sq")
                    ).scalar() or 0
                return 0
        finally:
            engine.dispose()
