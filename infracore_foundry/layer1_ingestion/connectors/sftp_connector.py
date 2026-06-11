"""
SFTP connector for retrieving files from remote servers via paramiko.
"""

import io
import logging
import os
import stat
import time
from typing import Optional

import pandas as pd
import paramiko

from layer1_ingestion.connectors.base_connector import (
    BaseConnector, ConnectionTestResult, SchemaDetectionResult,
    ExtractionConfig, IncrementalConfig,
    ConnectionError, AuthenticationError, ExtractionError,
)

logger = logging.getLogger(__name__)


class SFTPConnector(BaseConnector):
    """SFTP/SCP connector for retrieving remote files."""

    REQUIRED_CONFIG_FIELDS = ["host", "remote_path"]

    def __init__(self, source_id: str, config: dict) -> None:
        super().__init__(source_id, config)
        self.host: str = config.get("host", "")
        self.port: int = config.get("port", 22)
        self.username: str = config.get("username", "")
        self.password: Optional[str] = config.get("password")
        self.private_key_path: Optional[str] = config.get("private_key_path")
        self.remote_path: str = config.get("remote_path", "")
        self.file_pattern: str = config.get("file_pattern", "*.csv")

    def _get_transport(self) -> paramiko.Transport:
        transport = paramiko.Transport((self.host, self.port))
        if self.private_key_path:
            pkey = paramiko.RSAKey.from_private_key_file(self.private_key_path)
            transport.connect(username=self.username, pkey=pkey)
        elif self.password:
            transport.connect(username=self.username, password=self.password)
        else:
            raise AuthenticationError(self.source_id, "No password or private key provided")
        return transport

    def _get_sftp(self) -> tuple[paramiko.SFTPClient, paramiko.Transport]:
        transport = self._get_transport()
        sftp = paramiko.SFTPClient.from_transport(transport)
        return sftp, transport

    def test_connection(self) -> ConnectionTestResult:
        start = time.perf_counter()
        try:
            sftp, transport = self._get_sftp()
            file_list = sftp.listdir(self.remote_path)
            sftp.close()
            transport.close()
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=True,
                message=f"Connected. {len(file_list)} items in remote directory",
                response_time_ms=elapsed,
            )
        except paramiko.AuthenticationException as e:
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=False, message=f"Authentication failed: {e}",
                response_time_ms=elapsed, error="AuthenticationError",
            )
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=False, message=str(e),
                response_time_ms=elapsed, error=type(e).__name__,
            )

    def extract_schema(self) -> SchemaDetectionResult:
        with self._timed_operation("schema_detection"):
            sftp, transport = self._get_sftp()
            files = self._list_matching_files(sftp)
            if not files:
                sftp.close(); transport.close()
                return SchemaDetectionResult(columns=[], total_columns=0)
            buffer = io.BytesIO()
            sftp.getfo(files[0], buffer)
            buffer.seek(0)
            sftp.close(); transport.close()
            df = pd.read_csv(buffer, nrows=100)
            columns = [
                {"name": str(c), "type": str(df[c].dtype), "nullable": bool(df[c].isnull().any()), "sample_values": df[c].dropna().head(5).tolist()}
                for c in df.columns
            ]
            return SchemaDetectionResult(columns=columns, total_columns=len(columns))

    def extract_full(self, config: ExtractionConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            sftp, transport = self._get_sftp()
            files = self._list_matching_files(sftp)
            all_dfs = []
            for fp in files:
                buffer = io.BytesIO()
                sftp.getfo(fp, buffer)
                buffer.seek(0)
                ext = os.path.splitext(fp)[1].lower()
                if ext in (".csv", ".tsv"):
                    df = pd.read_csv(buffer, sep="\t" if ext == ".tsv" else ",")
                elif ext in (".xlsx", ".xls"):
                    df = pd.read_excel(buffer)
                elif ext == ".parquet":
                    import pyarrow.parquet as pq
                    df = pq.read_table(buffer).to_pandas()
                else:
                    df = pd.read_csv(buffer)
                df["_source_file"] = os.path.basename(fp)
                all_dfs.append(df)
            sftp.close(); transport.close()
            combined = pd.concat(all_dfs, ignore_index=True) if all_dfs else pd.DataFrame()
            duration = time.perf_counter() - start
            self.log_extraction(len(combined), duration, 0)
            return combined
        except Exception as e:
            duration = time.perf_counter() - start
            self.log_extraction(0, duration, 1)
            raise ExtractionError(self.source_id, f"SFTP extraction failed: {str(e)}") from e

    def extract_incremental(self, config: IncrementalConfig) -> pd.DataFrame:
        """Check file modification times for incremental sync."""
        sftp, transport = self._get_sftp()
        files = self._list_matching_files(sftp)
        new_files = []
        for fp in files:
            st = sftp.stat(fp)
            mtime = st.st_mtime or 0
            if config.last_extracted_at and mtime <= config.last_extracted_at.timestamp():
                continue
            new_files.append(fp)
        sftp.close(); transport.close()
        if not new_files:
            return pd.DataFrame()
        self.config["_incremental_files"] = new_files
        return self.extract_full(config)

    def get_record_count(self) -> int:
        sftp, transport = self._get_sftp()
        files = self._list_matching_files(sftp)
        sftp.close(); transport.close()
        return len(files)

    def _list_matching_files(self, sftp: paramiko.SFTPClient) -> list[str]:
        """List remote files matching the configured pattern."""
        import fnmatch
        try:
            entries = sftp.listdir_attr(self.remote_path)
        except FileNotFoundError:
            return []
        result = []
        for entry in entries:
            if stat.S_ISREG(entry.st_mode or 0):
                if fnmatch.fnmatch(entry.filename, self.file_pattern):
                    result.append(os.path.join(self.remote_path, entry.filename).replace("\\", "/"))
        return sorted(result)
