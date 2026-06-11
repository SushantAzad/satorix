"""
Oracle Database connector using python-oracledb (thin mode — no Oracle Client required).

PSUs and large private-sector enterprises in India (banks, oil & gas, telecom)
run Oracle as their primary RDBMS. python-oracledb thin mode works without
installing Oracle Instant Client, which is critical for containerised deployments.

config keys:
  host            : str   Oracle host
  port            : int   default 1521
  service_name    : str   Oracle service name (preferred over SID)
  sid             : str   Oracle SID (legacy; use service_name when possible)
  username        : str
  password        : str
  table_name      : str   (mutually exclusive with query)
  query           : str
  schema          : str   Oracle schema/owner — defaults to username
  fetch_size      : int   arraysize for cursor — default 1000
  timestamp_column : str
  id_column        : str
"""

import logging
import time
from typing import Optional

import pandas as pd

from layer1_ingestion.connectors.base_connector import (
    BaseConnector,
    ConnectionTestResult,
    ExtractionConfig,
    ExtractionError,
    IncrementalConfig,
    SchemaDetectionResult,
)

logger = logging.getLogger(__name__)


class OracleConnector(BaseConnector):
    """Oracle Database connector using python-oracledb thin mode."""

    REQUIRED_CONFIG_FIELDS = ["host", "username", "password"]

    def __init__(self, source_id: str, config: dict) -> None:
        super().__init__(source_id, config)
        self.host: str = config.get("host", "")
        self.port: int = int(config.get("port", 1521))
        self.service_name: str = config.get("service_name", "")
        self.sid: str = config.get("sid", "")
        self.username: str = config.get("username", "")
        self.password: str = config.get("password", "")
        self.table_name: Optional[str] = config.get("table_name")
        self.schema: str = config.get("schema", self.username).upper()
        self.query: Optional[str] = config.get("query")
        self.fetch_size: int = int(config.get("fetch_size", 1000))

    def _get_connection(self):
        try:
            import oracledb
        except ImportError as exc:
            raise ImportError(
                "python-oracledb not installed. Run: pip install oracledb"
            ) from exc

        if self.service_name:
            dsn = oracledb.makedsn(self.host, self.port, service_name=self.service_name)
        elif self.sid:
            dsn = oracledb.makedsn(self.host, self.port, sid=self.sid)
        else:
            dsn = f"{self.host}:{self.port}"

        return oracledb.connect(user=self.username, password=self.password, dsn=dsn)

    def _qualified_table(self) -> str:
        return f'"{self.schema}"."{self.table_name}"'

    def test_connection(self) -> ConnectionTestResult:
        start = time.perf_counter()
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute("SELECT banner FROM v$version WHERE ROWNUM = 1")
            version = cur.fetchone()
            cur.close()
            conn.close()
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=True,
                message=f"Connected: {str(version[0])[:80] if version else 'Oracle'}",
                response_time_ms=elapsed,
            )
        except Exception as exc:
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=False, message=str(exc),
                response_time_ms=elapsed, error=type(exc).__name__,
            )

    def extract_schema(self) -> SchemaDetectionResult:
        with self._timed_operation("oracle_schema_detection"):
            conn = self._get_connection()
            try:
                cur = conn.cursor()
                if self.table_name:
                    cur.execute(
                        """
                        SELECT column_name, data_type, nullable
                        FROM all_tab_columns
                        WHERE owner = :owner AND table_name = :table
                        ORDER BY column_id
                        """,
                        owner=self.schema, table=self.table_name.upper(),
                    )
                    col_rows = cur.fetchall()
                    columns = [
                        {
                            "name": r[0],
                            "type": r[1],
                            "nullable": r[2] == "Y",
                            "sample_values": [],
                        }
                        for r in col_rows
                    ]
                    # Primary key
                    cur.execute(
                        """
                        SELECT cc.column_name
                        FROM all_constraints c
                        JOIN all_cons_columns cc
                          ON c.constraint_name = cc.constraint_name AND c.owner = cc.owner
                        WHERE c.constraint_type = 'P'
                          AND c.owner = :owner AND c.table_name = :table
                        ORDER BY cc.position
                        """,
                        owner=self.schema, table=self.table_name.upper(),
                    )
                    pk_row = cur.fetchone()
                    pk_col = pk_row[0] if pk_row else None
                    # Timestamps
                    ts_cols = [
                        c["name"] for c in columns
                        if any(t in c["type"].upper() for t in ("DATE", "TIMESTAMP"))
                    ]
                    # Sample rows
                    cur.execute(f"SELECT * FROM {self._qualified_table()} WHERE ROWNUM <= 5")
                    sample_rows = cur.fetchall()
                    for i, col in enumerate(columns):
                        col["sample_values"] = [
                            r[i] for r in sample_rows if r[i] is not None
                        ][:3]
                    # Count
                    cur.execute(f"SELECT COUNT(*) FROM {self._qualified_table()}")
                    count = cur.fetchone()[0]
                    cur.close()
                    return SchemaDetectionResult(
                        columns=columns,
                        total_columns=len(columns),
                        detected_primary_key=pk_col,
                        timestamp_columns=ts_cols,
                        record_count_estimate=count,
                    )
                else:
                    cur.execute(f"SELECT * FROM ({self.query}) WHERE ROWNUM = 0")
                    col_names = [desc[0] for desc in cur.description]
                    cur.close()
                    columns = [
                        {"name": n, "type": "unknown", "nullable": True, "sample_values": []}
                        for n in col_names
                    ]
                    return SchemaDetectionResult(columns=columns, total_columns=len(columns))
            finally:
                conn.close()

    def extract_full(self, config: ExtractionConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.arraysize = self.fetch_size

            base_sql = (
                f"SELECT * FROM {self._qualified_table()}"
                if self.table_name
                else f"SELECT * FROM ({self.query})"
            )
            cur.execute(base_sql)
            col_names = [desc[0] for desc in cur.description]
            chunks: list[pd.DataFrame] = []
            while True:
                rows = cur.fetchmany(config.batch_size)
                if not rows:
                    break
                chunks.append(pd.DataFrame(rows, columns=col_names))
            cur.close()
            conn.close()
            df = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()
            self.log_extraction(len(df), time.perf_counter() - start, 0)
            return df
        except Exception as exc:
            self.log_extraction(0, time.perf_counter() - start, 1)
            raise ExtractionError(
                self.source_id, f"Oracle extraction failed: {exc}"
            ) from exc

    def extract_incremental(self, config: IncrementalConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.arraysize = self.fetch_size

            if config.strategy == "timestamp" and config.last_extracted_at:
                ts_col = self.config.get("timestamp_column", "UPDATED_AT")
                base = (
                    f"SELECT * FROM {self._qualified_table()}"
                    if self.table_name
                    else f"SELECT * FROM ({self.query})"
                )
                sql = f"{base} WHERE \"{ts_col}\" > :last_sync ORDER BY \"{ts_col}\" ASC"
                cur.execute(sql, last_sync=config.last_extracted_at)
            elif config.strategy == "sequence" and config.last_extracted_id:
                id_col = self.config.get("id_column", "ID")
                base = (
                    f"SELECT * FROM {self._qualified_table()}"
                    if self.table_name
                    else f"SELECT * FROM ({self.query})"
                )
                sql = f"{base} WHERE \"{id_col}\" > :last_id ORDER BY \"{id_col}\" ASC"
                cur.execute(sql, last_id=config.last_extracted_id)
            else:
                cur.close()
                conn.close()
                return self.extract_full(config)

            col_names = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
            cur.close()
            conn.close()
            df = pd.DataFrame(rows, columns=col_names) if rows else pd.DataFrame()
            self.log_extraction(len(df), time.perf_counter() - start, 0)
            return df
        except Exception as exc:
            self.log_extraction(0, time.perf_counter() - start, 1)
            raise ExtractionError(
                self.source_id, f"Oracle incremental failed: {exc}"
            ) from exc

    def get_record_count(self) -> int:
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            if self.table_name:
                cur.execute(f"SELECT COUNT(*) FROM {self._qualified_table()}")
            elif self.query:
                cur.execute(f"SELECT COUNT(*) FROM ({self.query})")
            else:
                return 0
            result = cur.fetchone()
            cur.close()
            return result[0] if result else 0
        finally:
            conn.close()
