"""
PDF connector with two extraction modes: digital (pdfplumber) and scanned (OCR).
Auto-detects which mode to use based on text content availability.
"""

import io
import logging
import os
import re
import time
from typing import Optional

import pandas as pd

from layer1_ingestion.connectors.base_connector import (
    BaseConnector, ConnectionTestResult, SchemaDetectionResult,
    ExtractionConfig, IncrementalConfig,
    ConnectionError, ExtractionError,
)

logger = logging.getLogger(__name__)

# Common OCR errors in Indian business documents
OCR_CORRECTIONS = {
    "0": {"O": 0.3},  # In numeric contexts, O -> 0
    "1": {"I": 0.3, "l": 0.3},  # In numeric contexts
    "₹": {"Rs": 0.5, "Rs.": 0.5, "INR": 0.5},
}


def _has_selectable_text(file_path: str) -> bool:
    """Check if a PDF has selectable text (digital) or is scanned."""
    try:
        import pdfplumber
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages[:3]:  # Check first 3 pages
                text = page.extract_text()
                if text and len(text.strip()) > 50:
                    return True
        return False
    except Exception:
        return False


def _clean_table_cell(value: Optional[str]) -> Optional[str]:
    """Clean OCR artifacts from table cell values."""
    if value is None:
        return None
    # Remove spurious line breaks within cells
    cleaned = re.sub(r"\n+", " ", str(value)).strip()
    # Fix common OCR number errors in numeric-looking values
    if re.match(r"^[\d,.\s₹RsINR-]+$", cleaned, re.IGNORECASE):
        cleaned = cleaned.replace("O", "0").replace("l", "1").replace("I", "1")
    return cleaned if cleaned else None


def _extract_tables_digital(file_path: str, pages: Optional[list[int]] = None) -> list[dict]:
    """
    Extract tables from a digital PDF using pdfplumber.
    Returns a list of dicts with 'dataframe' and 'metadata'.
    """
    import pdfplumber

    results = []
    with pdfplumber.open(file_path) as pdf:
        target_pages = pages if pages else range(len(pdf.pages))
        for page_idx in target_pages:
            if page_idx >= len(pdf.pages):
                continue
            page = pdf.pages[page_idx]
            tables = page.extract_tables()

            for table_idx, table in enumerate(tables):
                if not table or len(table) < 2:
                    continue

                # Detect if first row is a header
                first_row = table[0]
                has_header = all(
                    isinstance(cell, str) and not cell.replace(".", "").replace(",", "").isdigit()
                    for cell in first_row if cell
                )

                if has_header:
                    headers = [_clean_table_cell(h) or f"Column_{i}" for i, h in enumerate(first_row)]
                    data_rows = table[1:]
                else:
                    headers = [f"Column_{i}" for i in range(len(first_row))]
                    data_rows = table

                cleaned_rows = []
                for row in data_rows:
                    cleaned = [_clean_table_cell(cell) for cell in row]
                    # Pad to header length
                    while len(cleaned) < len(headers):
                        cleaned.append(None)
                    cleaned = cleaned[:len(headers)]
                    cleaned_rows.append(cleaned)

                df = pd.DataFrame(cleaned_rows, columns=headers)
                df = df.dropna(how="all").reset_index(drop=True)

                if not df.empty:
                    results.append({
                        "dataframe": df,
                        "metadata": {
                            "page_number": page_idx + 1,
                            "table_index": table_idx,
                            "extraction_mode": "digital",
                            "rows": len(df),
                        },
                    })
    return results


def _extract_tables_ocr(
    file_path: str,
    pages: Optional[list[int]] = None,
    language: str = "eng",
) -> list[dict]:
    """
    Extract tables from scanned PDF using OCR (Tesseract + PyMuPDF).
    """
    import fitz  # PyMuPDF
    from PIL import Image
    import pytesseract

    results = []
    doc = fitz.open(file_path)

    target_pages = pages if pages else range(len(doc))
    lang_str = f"{language}+hin" if language == "eng" else language

    for page_idx in target_pages:
        if page_idx >= len(doc):
            continue
        page = doc[page_idx]
        # Render page as high-resolution image
        mat = fitz.Matrix(3.0, 3.0)  # 3x zoom for better OCR
        pix = page.get_pixmap(matrix=mat)
        img_data = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_data))

        # Run OCR
        try:
            ocr_text = pytesseract.image_to_string(img, lang=lang_str)
        except Exception as e:
            logger.warning(
                "OCR failed for page %d: %s", page_idx + 1, str(e),
                extra={"source_id": "pdf_connector"},
            )
            continue

        # Attempt table reconstruction from whitespace analysis
        lines = ocr_text.strip().split("\n")
        if len(lines) < 2:
            continue

        # Detect columns using whitespace patterns
        table_data = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Split by 2+ spaces (likely column separator in OCR output)
            cells = re.split(r"\s{2,}", line)
            cells = [_clean_table_cell(c) for c in cells]
            table_data.append(cells)

        if len(table_data) < 2:
            continue

        # Normalize column count
        max_cols = max(len(row) for row in table_data)
        for row in table_data:
            while len(row) < max_cols:
                row.append(None)

        # First row as header
        headers = [h or f"Column_{i}" for i, h in enumerate(table_data[0])]
        data_rows = table_data[1:]

        df = pd.DataFrame(data_rows, columns=headers[:max_cols])
        df = df.dropna(how="all").reset_index(drop=True)

        if not df.empty:
            results.append({
                "dataframe": df,
                "metadata": {
                    "page_number": page_idx + 1,
                    "table_index": 0,
                    "extraction_mode": "ocr",
                    "rows": len(df),
                },
            })

    doc.close()
    return results


class PDFConnector(BaseConnector):
    """Connector for PDF file extraction with digital and OCR modes."""

    REQUIRED_CONFIG_FIELDS = ["file_path"]

    def __init__(self, source_id: str, config: dict) -> None:
        super().__init__(source_id, config)
        self.file_path: str = config.get("file_path", "")
        self.pages: Optional[list[int]] = config.get("pages")
        self.extract_mode: str = config.get("extract_mode", "auto")  # auto, digital, scanned
        self.language: str = config.get("language", "eng")

    def test_connection(self) -> ConnectionTestResult:
        """Check if the PDF file exists and is valid."""
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

            import fitz
            doc = fitz.open(self.file_path)
            page_count = len(doc)
            has_text = _has_selectable_text(self.file_path)
            doc.close()

            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=True,
                message=f"Valid PDF: {page_count} pages, {'digital' if has_text else 'scanned'}",
                response_time_ms=elapsed,
                schema_detected={
                    "pages": page_count,
                    "type": "digital" if has_text else "scanned",
                },
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
        """Detect schema from the first table found in the PDF."""
        with self._timed_operation("schema_detection"):
            mode = self._resolve_mode()
            if mode == "digital":
                tables = _extract_tables_digital(self.file_path, [0])
            else:
                tables = _extract_tables_ocr(self.file_path, [0], self.language)

            if not tables:
                return SchemaDetectionResult(columns=[], total_columns=0)

            df = tables[0]["dataframe"]
            columns = [
                {
                    "name": str(col),
                    "type": str(df[col].dtype),
                    "nullable": bool(df[col].isnull().any()),
                    "sample_values": df[col].dropna().head(5).tolist(),
                }
                for col in df.columns
            ]
            return SchemaDetectionResult(
                columns=columns,
                total_columns=len(df.columns),
            )

    def extract_full(self, config: ExtractionConfig) -> pd.DataFrame:
        """Extract all tables from the PDF and combine into single DataFrame."""
        start = time.perf_counter()
        try:
            self.logger.info(
                "extraction_start",
                extra={"source_id": self.source_id, "file": self.file_path},
            )

            mode = self._resolve_mode()
            if mode == "digital":
                tables = _extract_tables_digital(self.file_path, self.pages)
            else:
                tables = _extract_tables_ocr(self.file_path, self.pages, self.language)

            if not tables:
                duration = time.perf_counter() - start
                self.log_extraction(0, duration, 0)
                return pd.DataFrame()

            # Add metadata and combine
            all_dfs = []
            for t in tables:
                df = t["dataframe"].copy()
                df["_page_number"] = t["metadata"]["page_number"]
                df["_table_index"] = t["metadata"]["table_index"]
                df["_extraction_mode"] = t["metadata"]["extraction_mode"]
                all_dfs.append(df)

            combined = pd.concat(all_dfs, ignore_index=True)
            duration = time.perf_counter() - start
            self.log_extraction(len(combined), duration, 0)
            return combined

        except Exception as e:
            duration = time.perf_counter() - start
            self.log_extraction(0, duration, 1)
            raise ExtractionError(
                self.source_id,
                f"PDF extraction failed: {str(e)}",
                context={"file_path": self.file_path, "mode": self.extract_mode},
            ) from e

    def extract_incremental(self, config: IncrementalConfig) -> pd.DataFrame:
        """For PDF files, always do full extraction (no incremental for PDFs)."""
        return self.extract_full(config)

    def get_record_count(self) -> int:
        """Estimate record count by extracting all tables."""
        mode = self._resolve_mode()
        if mode == "digital":
            tables = _extract_tables_digital(self.file_path, self.pages)
        else:
            tables = _extract_tables_ocr(self.file_path, self.pages, self.language)
        return sum(t["metadata"]["rows"] for t in tables)

    def _resolve_mode(self) -> str:
        """Determine extraction mode: digital or scanned."""
        if self.extract_mode == "auto":
            return "digital" if _has_selectable_text(self.file_path) else "scanned"
        return self.extract_mode
