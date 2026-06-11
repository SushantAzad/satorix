"""
FTP/FTPS connector for file retrieval and content parsing.

Complements the existing SFTP connector. Many legacy enterprise systems
still push data via plain FTP or FTPS. This connector handles both.

config keys:
  host              : str   FTP server hostname or IP
  port              : int   default 21 (FTP), 990 (FTPS implicit)
  username          : str
  password          : str
  use_tls           : bool  use FTPS — default False
  implicit_tls      : bool  implicit TLS mode (port 990) — default False
  remote_dir        : str   remote directory to list/download — default "/"
  file_patterns     : list  filename patterns e.g. ["*.csv", "report_*.xlsx"]
  download_content  : bool  parse file contents — default True
  encoding          : str   text file encoding — default "utf-8"
  max_files         : int   default 500
"""

import fnmatch
import io
import logging
import time
from datetime import datetime, timezone
from ftplib import FTP, FTP_TLS
from typing import Optional

import pandas as pd

from layer1_ingestion.connectors.base_connector import (
    AuthenticationError,
    BaseConnector,
    ConnectionTestResult,
    ExtractionConfig,
    ExtractionError,
    IncrementalConfig,
    SchemaDetectionResult,
)

logger = logging.getLogger(__name__)

_PARSEABLE_EXTS = {".csv", ".tsv", ".txt", ".xlsx", ".xls", ".json"}


class FTPConnector(BaseConnector):
    """FTP/FTPS file retrieval and parsing connector."""

    REQUIRED_CONFIG_FIELDS: list[str] = ["host", "username", "password"]

    def __init__(self, source_id: str, config: dict) -> None:
        super().__init__(source_id, config)
        self.host: str = config.get("host", "")
        self.port: int = int(config.get("port", 21))
        self.username: str = config.get("username", "")
        self.password: str = config.get("password", "")
        self.use_tls: bool = bool(config.get("use_tls", False))
        self.implicit_tls: bool = bool(config.get("implicit_tls", False))
        self.remote_dir: str = config.get("remote_dir", "/")
        self.file_patterns: list = config.get("file_patterns", [])
        self.download_content: bool = bool(config.get("download_content", True))
        self.encoding: str = config.get("encoding", "utf-8")
        self.max_files: int = int(config.get("max_files", 500))

    def _connect(self) -> FTP:
        try:
            if self.use_tls or self.implicit_tls:
                ftp: FTP = FTP_TLS()
            else:
                ftp = FTP()
            ftp.connect(self.host, self.port, timeout=30)
            try:
                ftp.login(self.username, self.password)
            except Exception as exc:
                raise AuthenticationError(self.source_id, f"FTP login failed: {exc}") from exc
            if isinstance(ftp, FTP_TLS):
                ftp.prot_p()  # Upgrade data connection to TLS
            return ftp
        except AuthenticationError:
            raise
        except Exception as exc:
            raise ConnectionError(f"FTP connection failed: {exc}") from exc

    def _list_files(self, ftp: FTP, directory: str) -> list[dict]:
        entries: list[dict] = []
        try:
            ftp.cwd(directory)
            lines: list[str] = []
            ftp.retrlines("LIST", lines.append)
            for line in lines:
                parts = line.split()
                if len(parts) < 9:
                    continue
                perms = parts[0]
                size = int(parts[4]) if parts[4].isdigit() else 0
                name = " ".join(parts[8:])
                is_dir = perms.startswith("d")
                entries.append({
                    "name": name,
                    "path": f"{directory.rstrip('/')}/{name}",
                    "is_dir": is_dir,
                    "size": size,
                    "raw_date": " ".join(parts[5:8]),
                })
        except Exception as exc:
            logger.warning("FTP LIST failed for %s: %s", directory, exc)
        return entries

    def _matches_patterns(self, name: str) -> bool:
        if not self.file_patterns:
            return True
        return any(fnmatch.fnmatch(name.lower(), pat.lower()) for pat in self.file_patterns)

    def _download_file(self, ftp: FTP, path: str) -> Optional[bytes]:
        buf = io.BytesIO()
        try:
            ftp.retrbinary(f"RETR {path}", buf.write)
            return buf.getvalue()
        except Exception as exc:
            logger.debug("FTP RETR failed for %s: %s", path, exc)
            return None

    def _parse_content(self, name: str, content: bytes) -> Optional[pd.DataFrame]:
        ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
        try:
            if ext in (".csv", ".txt"):
                return pd.read_csv(io.BytesIO(content), dtype=str, encoding=self.encoding, errors="replace")
            elif ext == ".tsv":
                return pd.read_csv(io.BytesIO(content), sep="\t", dtype=str, encoding=self.encoding, errors="replace")
            elif ext in (".xlsx", ".xls"):
                return pd.read_excel(io.BytesIO(content), dtype=str)
            elif ext == ".json":
                import json as _json
                data = _json.loads(content)
                return pd.DataFrame(data if isinstance(data, list) else [data])
        except Exception as exc:
            logger.debug("FTP parse failed for %s: %s", name, exc)
        return None

    def test_connection(self) -> ConnectionTestResult:
        start = time.perf_counter()
        try:
            ftp = self._connect()
            welcome = ftp.getwelcome()
            ftp.quit()
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=True,
                message=f"FTP connected to {self.host}: {welcome[:100]}",
                response_time_ms=elapsed,
            )
        except AuthenticationError:
            raise
        except Exception as exc:
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=False, message=str(exc),
                response_time_ms=elapsed, error=type(exc).__name__,
            )

    def extract_schema(self) -> SchemaDetectionResult:
        with self._timed_operation("ftp_schema_detection"):
            columns = [
                {"name": "path", "type": "string", "nullable": False, "sample_values": []},
                {"name": "name", "type": "string", "nullable": False, "sample_values": []},
                {"name": "size", "type": "int64", "nullable": True, "sample_values": []},
                {"name": "is_dir", "type": "bool", "nullable": False, "sample_values": [False]},
                {"name": "raw_date", "type": "string", "nullable": True, "sample_values": []},
            ]
            return SchemaDetectionResult(
                columns=columns,
                total_columns=len(columns),
                detected_primary_key="path",
                timestamp_columns=["raw_date"],
            )

    def extract_full(self, config: ExtractionConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            ftp = self._connect()
            entries = self._list_files(ftp, self.remote_dir)
            file_entries = [
                e for e in entries
                if not e["is_dir"] and self._matches_patterns(e["name"])
            ][: self.max_files]

            if self.download_content:
                all_dfs: list[pd.DataFrame] = []
                for entry in file_entries:
                    ext = "." + entry["name"].rsplit(".", 1)[-1].lower() if "." in entry["name"] else ""
                    if ext not in _PARSEABLE_EXTS:
                        continue
                    content = self._download_file(ftp, entry["path"])
                    if content:
                        df = self._parse_content(entry["name"], content)
                        if df is not None and not df.empty:
                            df["_source_path"] = entry["path"]
                            all_dfs.append(df)
                ftp.quit()
                if all_dfs:
                    result = pd.concat(all_dfs, ignore_index=True)
                    self.log_extraction(len(result), time.perf_counter() - start, 0)
                    return result

            ftp.quit()
            df = pd.DataFrame([
                {"path": e["path"], "name": e["name"], "size": e["size"],
                 "is_dir": e["is_dir"], "raw_date": e["raw_date"]}
                for e in entries[: self.max_files]
            ]) if entries else pd.DataFrame()
            self.log_extraction(len(df), time.perf_counter() - start, 0)
            return df
        except Exception as exc:
            self.log_extraction(0, time.perf_counter() - start, 1)
            raise ExtractionError(self.source_id, f"FTP extraction failed: {exc}") from exc

    def extract_incremental(self, config: IncrementalConfig) -> pd.DataFrame:
        return self.extract_full(config)

    def get_record_count(self) -> int:
        try:
            ftp = self._connect()
            entries = self._list_files(ftp, self.remote_dir)
            ftp.quit()
            return sum(1 for e in entries if not e["is_dir"])
        except Exception:
            return 0
