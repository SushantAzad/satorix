"""
Excel connector for .xlsx, .xls, .xlsm files.
Handles merged cells, multiple headers, hidden sheets, formula values,
mixed data types, Excel date integers, and multi-sheet extraction.
"""

import hashlib
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Optional, Union

import openpyxl
import pandas as pd

from layer1_ingestion.connectors.base_connector import (
    BaseConnector, ConnectionTestResult, SchemaDetectionResult,
    ExtractionConfig, IncrementalConfig,
    ConnectionError, ExtractionError, SchemaError,
)

logger = logging.getLogger(__name__)

# Excel epoch: dates stored as days since 1899-12-30 (Excel's quirky epoch)
EXCEL_EPOCH = datetime(1899, 12, 30)


def _is_excel_date_integer(series: pd.Series) -> bool:
    """Detect if a numeric column likely contains Excel date serial numbers."""
    numeric = pd.to_numeric(series.dropna(), errors="coerce").dropna()
    if len(numeric) < 5:
        return False
    # Excel dates are typically between 1 (1900-01-01) and 55000 (~2050)
    in_range = ((numeric >= 1) & (numeric <= 55000)).mean()
    return in_range > 0.8


def _excel_serial_to_date(serial: float) -> Optional[datetime]:
    """Convert Excel date serial number to Python datetime."""
    try:
        if serial < 1:
            return None
        # Excel erroneously considers 1900 a leap year — adjust for dates after Feb 28, 1900
        if serial > 59:
            serial -= 1
        return EXCEL_EPOCH + timedelta(days=serial)
    except (ValueError, OverflowError):
        return None


def _detect_merged_cells(ws) -> dict:
    """
    Detect merged cell ranges and build a mapping of cells to their merged values.
    Returns {(row, col): value} for all cells that are part of a merge.
    """
    merge_map = {}
    for merge_range in ws.merged_cells.ranges:
        min_row, min_col = merge_range.min_row, merge_range.min_col
        value = ws.cell(row=min_row, column=min_col).value
        for row in range(merge_range.min_row, merge_range.max_row + 1):
            for col in range(merge_range.min_col, merge_range.max_col + 1):
                merge_map[(row, col)] = value
    return merge_map


def _detect_multi_header(ws, max_check: int = 5) -> int:
    """
    Detect if the worksheet has multiple header rows.
    Returns the number of header rows (1 or 2).
    """
    if ws.max_row < 3:
        return 1

    row1_types = set()
    row2_types = set()
    for col_idx in range(1, min(ws.max_column + 1, 20)):
        v1 = ws.cell(row=1, column=col_idx).value
        v2 = ws.cell(row=2, column=col_idx).value
        v3 = ws.cell(row=3, column=col_idx).value
        if v1 is not None:
            row1_types.add(type(v1).__name__)
        if v2 is not None:
            row2_types.add(type(v2).__name__)

    # If both first two rows are primarily strings and row 3 has different types, it's multi-header
    row1_all_str = row1_types <= {"str", "NoneType"}
    row2_all_str = row2_types <= {"str", "NoneType"}

    if row1_all_str and row2_all_str:
        # Check if row 3 has numeric data
        row3_has_data = False
        for col_idx in range(1, min(ws.max_column + 1, 20)):
            v3 = ws.cell(row=3, column=col_idx).value
            if isinstance(v3, (int, float)):
                row3_has_data = True
                break
        if row3_has_data:
            return 2
    return 1


def _is_date_like_sheet_name(name: str) -> bool:
    """Check if a sheet name represents a date or quarter period."""
    date_patterns = [
        r"Q[1-4]\s*\d{4}", r"\d{4}\s*Q[1-4]",
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)",
        r"\d{4}-\d{2}", r"FY\s*\d{2,4}",
        r"\d{2}/\d{2}/\d{4}", r"\d{4}/\d{2}",
    ]
    import re
    return any(re.search(p, name, re.IGNORECASE) for p in date_patterns)


class ExcelConnector(BaseConnector):
    """Connector for Excel files (.xlsx, .xls, .xlsm)."""

    REQUIRED_CONFIG_FIELDS = ["file_path"]

    def __init__(self, source_id: str, config: dict) -> None:
        super().__init__(source_id, config)
        self.file_path: str = config.get("file_path", "")
        self.sheet_name: Optional[Union[str, int]] = config.get("sheet_name")
        self.header_row: int = config.get("header_row", 0)
        self.skip_footer_rows: int = config.get("skip_footer_rows", 0)
        self.named_range: Optional[str] = config.get("named_range")
        self.include_hidden: bool = config.get("include_hidden", False)

    def test_connection(self) -> ConnectionTestResult:
        """Check if the Excel file exists and is valid."""
        start = time.perf_counter()
        try:
            if not os.path.exists(self.file_path):
                elapsed = (time.perf_counter() - start) * 1000
                return ConnectionTestResult(
                    success=False,
                    message=f"File not found: {self.file_path}",
                    response_time_ms=elapsed,
                    error="FileNotFoundError",
                )

            wb = openpyxl.load_workbook(self.file_path, read_only=True, data_only=True)
            sheet_names = wb.sheetnames
            wb.close()

            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=True,
                message=f"Valid Excel file with {len(sheet_names)} sheet(s): {', '.join(sheet_names[:5])}",
                response_time_ms=elapsed,
                schema_detected={"sheets": sheet_names},
            )
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=False,
                message=str(e),
                response_time_ms=elapsed,
                error=type(e).__name__,
            )

    def extract_schema(self) -> SchemaDetectionResult:
        """Detect schema from the first sheet (or specified sheet)."""
        with self._timed_operation("schema_detection"):
            df = self._read_sheet(nrows=1000)
            if isinstance(df, dict):
                df = list(df.values())[0]

            columns = []
            for col in df.columns:
                col_info = {
                    "name": str(col),
                    "type": str(df[col].dtype),
                    "nullable": bool(df[col].isnull().any()),
                    "sample_values": df[col].dropna().head(5).tolist(),
                }
                columns.append(col_info)

            indian_ids: dict = {}
            try:
                from layer1_ingestion.schema.indian_identifiers import detect_identifier_columns
                indian_ids = detect_identifier_columns(df)
            except ImportError:
                pass

            return SchemaDetectionResult(
                columns=columns,
                total_columns=len(df.columns),
                indian_identifiers=indian_ids,
                timestamp_columns=[
                    str(c) for c in df.columns
                    if pd.api.types.is_datetime64_any_dtype(df[c])
                ],
            )

    def extract_full(self, config: ExtractionConfig) -> pd.DataFrame:
        """Extract all data from the Excel file."""
        start = time.perf_counter()
        try:
            self.logger.info(
                "extraction_start",
                extra={"source_id": self.source_id, "file": self.file_path},
            )

            result = self._read_sheet()

            if isinstance(result, dict):
                # Multiple sheets — check if schemas match for union
                dfs = list(result.values())
                schemas_match = all(
                    list(df.columns) == list(dfs[0].columns) for df in dfs[1:]
                )
                if schemas_match:
                    combined = pd.concat(dfs, ignore_index=True)
                    duration = time.perf_counter() - start
                    self.log_extraction(len(combined), duration, 0)
                    return combined
                else:
                    # Return first sheet if schemas don't match, with metadata
                    first_key = list(result.keys())[0]
                    df = result[first_key]
                    self.logger.warning(
                        "Multi-sheet file with mismatched schemas, returning first sheet",
                        extra={"source_id": self.source_id, "sheet": first_key},
                    )
                    duration = time.perf_counter() - start
                    self.log_extraction(len(df), duration, 0)
                    return df
            else:
                duration = time.perf_counter() - start
                self.log_extraction(len(result), duration, 0)
                return result

        except Exception as e:
            duration = time.perf_counter() - start
            self.log_extraction(0, duration, 1)
            raise ExtractionError(
                self.source_id,
                f"Excel extraction failed: {str(e)}",
                context={"file_path": self.file_path},
            ) from e

    def extract_incremental(self, config: IncrementalConfig) -> pd.DataFrame:
        """Compare file checksum for change detection."""
        current_checksum = self._compute_file_checksum()
        if config.last_extracted_id == current_checksum:
            self.logger.info(
                "File unchanged, skipping extraction",
                extra={"source_id": self.source_id},
            )
            return pd.DataFrame()
        return self.extract_full(config)

    def get_record_count(self) -> int:
        """Get approximate record count from the Excel file."""
        wb = openpyxl.load_workbook(self.file_path, read_only=True, data_only=True)
        try:
            if self.sheet_name and self.sheet_name != "all":
                ws = wb[self.sheet_name] if isinstance(self.sheet_name, str) else wb.worksheets[self.sheet_name]
                return max(0, ws.max_row - 1 - self.header_row)
            else:
                ws = wb.worksheets[0]
                return max(0, ws.max_row - 1 - self.header_row)
        finally:
            wb.close()

    def _read_sheet(
        self, nrows: Optional[int] = None,
    ) -> Union[pd.DataFrame, dict[str, pd.DataFrame]]:
        """
        Core sheet reading logic with merged cell handling.
        """
        wb = openpyxl.load_workbook(self.file_path, read_only=False, data_only=True)
        try:
            if self.sheet_name == "all":
                result = {}
                for name in wb.sheetnames:
                    ws = wb[name]
                    # Skip hidden sheets unless configured
                    if ws.sheet_state == "hidden" and not self.include_hidden:
                        continue
                    df = self._worksheet_to_dataframe(ws, nrows)
                    if not df.empty:
                        # Add period column if sheet names look like dates
                        if _is_date_like_sheet_name(name):
                            df["_period"] = name
                        df["_sheet_name"] = name
                        result[name] = df
                return result
            elif self.sheet_name is not None:
                if isinstance(self.sheet_name, str):
                    ws = wb[self.sheet_name]
                else:
                    ws = wb.worksheets[self.sheet_name]
                return self._worksheet_to_dataframe(ws, nrows)
            else:
                # Default: first visible sheet
                for ws in wb.worksheets:
                    if ws.sheet_state != "hidden" or self.include_hidden:
                        return self._worksheet_to_dataframe(ws, nrows)
                return pd.DataFrame()
        finally:
            wb.close()

    def _worksheet_to_dataframe(
        self, ws, nrows: Optional[int] = None,
    ) -> pd.DataFrame:
        """
        Convert an openpyxl worksheet to DataFrame with merged cell handling,
        multi-header detection, and Excel date conversion.
        """
        # Unmerge cells and fill values
        merge_map = _detect_merged_cells(ws)
        for cell_range in list(ws.merged_cells.ranges):
            ws.unmerge_cells(str(cell_range))

        # Detect multi-header
        num_header_rows = _detect_multi_header(ws)

        # Read all data
        data = []
        headers = []
        for row_idx, row in enumerate(ws.iter_rows(values_only=False), 1):
            row_values = []
            for cell in row:
                pos = (cell.row, cell.column)
                value = merge_map.get(pos, cell.value)
                row_values.append(value)

            if row_idx <= num_header_rows + self.header_row:
                if row_idx > self.header_row:
                    headers.append(row_values)
                continue

            if nrows is not None and len(data) >= nrows:
                break
            data.append(row_values)

        if not data:
            return pd.DataFrame()

        # Build column names
        if num_header_rows == 2 and len(headers) == 2:
            col_names = []
            for i in range(len(headers[0])):
                h1 = str(headers[0][i]) if headers[0][i] is not None else ""
                h2 = str(headers[1][i]) if i < len(headers[1]) and headers[1][i] is not None else ""
                name = f"{h1}_{h2}".strip("_") if h1 and h2 else (h1 or h2 or f"Column_{i}")
                col_names.append(name)
        elif headers:
            col_names = [
                str(h) if h is not None else f"Column_{i}"
                for i, h in enumerate(headers[0])
            ]
        else:
            max_cols = max(len(r) for r in data) if data else 0
            col_names = [f"Column_{i}" for i in range(max_cols)]

        # Skip footer rows
        if self.skip_footer_rows > 0:
            data = data[:-self.skip_footer_rows] if len(data) > self.skip_footer_rows else data

        # Ensure all rows have same number of columns
        max_cols = len(col_names)
        normalized_data = []
        for row in data:
            if len(row) < max_cols:
                row = list(row) + [None] * (max_cols - len(row))
            elif len(row) > max_cols:
                row = row[:max_cols]
            normalized_data.append(row)

        df = pd.DataFrame(normalized_data, columns=col_names)

        # Convert Excel date integers to proper dates
        for col in df.columns:
            if df[col].dtype in ("float64", "int64") and _is_excel_date_integer(df[col]):
                df[col] = df[col].apply(
                    lambda v: _excel_serial_to_date(v) if pd.notna(v) else None
                )

        # Drop completely empty rows
        df = df.dropna(how="all").reset_index(drop=True)

        return df

    def _compute_file_checksum(self) -> str:
        """Compute SHA-256 checksum of the Excel file."""
        sha256 = hashlib.sha256()
        with open(self.file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
