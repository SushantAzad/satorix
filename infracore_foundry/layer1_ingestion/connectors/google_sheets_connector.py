"""
Google Sheets connector using gspread with service account authentication.
"""

import logging
import time
from typing import Optional

import pandas as pd

from layer1_ingestion.connectors.base_connector import (
    BaseConnector, ConnectionTestResult, SchemaDetectionResult,
    ExtractionConfig, IncrementalConfig,
    ConnectionError, AuthenticationError, ExtractionError,
)

logger = logging.getLogger(__name__)


class GoogleSheetsConnector(BaseConnector):
    """Connector for Google Sheets via gspread and service account auth."""

    REQUIRED_CONFIG_FIELDS = ["spreadsheet_id"]

    def __init__(self, source_id: str, config: dict) -> None:
        super().__init__(source_id, config)
        self.spreadsheet_id: str = config.get("spreadsheet_id", "")
        self.sheet_name: Optional[str] = config.get("sheet_name")
        self.credentials_path: str = config.get("credentials_path", "")
        self.header_row: int = config.get("header_row", 1)

    def _get_client(self):
        import gspread
        from google.oauth2.service_account import Credentials

        scopes = [
            "https://www.googleapis.com/auth/spreadsheets.readonly",
            "https://www.googleapis.com/auth/drive.readonly",
        ]
        creds = Credentials.from_service_account_file(self.credentials_path, scopes=scopes)
        return gspread.authorize(creds)

    def test_connection(self) -> ConnectionTestResult:
        start = time.perf_counter()
        try:
            gc = self._get_client()
            spreadsheet = gc.open_by_key(self.spreadsheet_id)
            sheets = [ws.title for ws in spreadsheet.worksheets()]
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=True,
                message=f"Connected: '{spreadsheet.title}' with {len(sheets)} sheet(s)",
                response_time_ms=elapsed,
                schema_detected={"sheets": sheets},
            )
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            error_str = str(e)
            if "403" in error_str or "permission" in error_str.lower():
                return ConnectionTestResult(
                    success=False, message="Permission denied",
                    response_time_ms=elapsed, error="AuthenticationError",
                )
            return ConnectionTestResult(
                success=False, message=error_str,
                response_time_ms=elapsed, error=type(e).__name__,
            )

    def extract_schema(self) -> SchemaDetectionResult:
        with self._timed_operation("schema_detection"):
            gc = self._get_client()
            spreadsheet = gc.open_by_key(self.spreadsheet_id)
            ws = spreadsheet.worksheet(self.sheet_name) if self.sheet_name else spreadsheet.sheet1
            rows = ws.get_all_values()
            if not rows or len(rows) < 2:
                return SchemaDetectionResult(columns=[], total_columns=0)
            headers = rows[self.header_row - 1]
            data_rows = rows[self.header_row: self.header_row + 100]
            df = pd.DataFrame(data_rows, columns=headers)
            columns = [
                {"name": str(c), "type": str(df[c].dtype), "nullable": bool(df[c].isin(["", None]).any()), "sample_values": df[c].head(5).tolist()}
                for c in df.columns
            ]
            return SchemaDetectionResult(columns=columns, total_columns=len(columns), record_count_estimate=len(rows) - self.header_row)

    def extract_full(self, config: ExtractionConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            gc = self._get_client()
            spreadsheet = gc.open_by_key(self.spreadsheet_id)
            ws = spreadsheet.worksheet(self.sheet_name) if self.sheet_name else spreadsheet.sheet1
            rows = ws.get_all_values()
            if not rows or len(rows) < 2:
                return pd.DataFrame()
            headers = rows[self.header_row - 1]
            data = rows[self.header_row:]
            df = pd.DataFrame(data, columns=headers)
            df = df.replace("", pd.NA)
            df = df.dropna(how="all").reset_index(drop=True)
            duration = time.perf_counter() - start
            self.log_extraction(len(df), duration, 0)
            return df
        except Exception as e:
            duration = time.perf_counter() - start
            self.log_extraction(0, duration, 1)
            raise ExtractionError(self.source_id, f"Google Sheets extraction failed: {str(e)}") from e

    def extract_incremental(self, config: IncrementalConfig) -> pd.DataFrame:
        return self.extract_full(config)

    def get_record_count(self) -> int:
        gc = self._get_client()
        spreadsheet = gc.open_by_key(self.spreadsheet_id)
        ws = spreadsheet.worksheet(self.sheet_name) if self.sheet_name else spreadsheet.sheet1
        return max(0, ws.row_count - self.header_row)
