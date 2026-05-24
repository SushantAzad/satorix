"""
BUSY Accounting Software connector.

BUSY is one of India's most widely used accounting software packages,
especially in the SME segment. It exports data in XML, CSV, and proprietary
formats. This connector handles BUSY's export file formats.

Export paths (from BUSY):
  - Reports > Export to XML/CSV/Excel
  - Company > Data Export
  - Vouchers can be exported per type (Sales, Purchase, Payments, Receipts)

Supported BUSY export types:
  - Sales register (invoice-level data with party, amount, tax breakdown)
  - Purchase register
  - Ledger master (chart of accounts with balances)
  - Party master (customers/vendors with contact details)
  - Stock summary (inventory data)
  - Day book (all transactions)
  - Trial balance / Balance Sheet

config keys:
  data_dir          : str   path to BUSY export files
  company_name      : str   BUSY company name (for validation/tagging)
  export_types      : list  e.g. ["sales","purchase","ledger","party","stock"]
                            default all
  financial_year    : str   e.g. "2024-25" (for tagging/filtering)
  xml_encoding      : str   default "utf-8" (BUSY sometimes uses windows-1252)
  max_records       : int   default 50000
"""

import logging
import os
import xml.etree.ElementTree as ET
from datetime import datetime
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

_EXPORT_TYPES = ["sales", "purchase", "ledger", "party", "stock", "daybook", "trial_balance"]

# BUSY XML namespace (varies by version)
_BUSY_NS = {"busy": "http://www.busywin.com/exports"}


class BUSYAccountingConnector(BaseConnector):
    """BUSY Accounting Software export file connector."""

    REQUIRED_CONFIG_FIELDS: list[str] = ["data_dir"]

    def __init__(self, source_id: str, config: dict) -> None:
        super().__init__(source_id, config)
        self.data_dir: str = config.get("data_dir", "")
        self.company_name: str = config.get("company_name", "")
        self.export_types: list = config.get("export_types", _EXPORT_TYPES)
        self.financial_year: str = config.get("financial_year", "")
        self.xml_encoding: str = config.get("xml_encoding", "utf-8")
        self.max_records: int = int(config.get("max_records", 50000))

    def _detect_export_type(self, fname: str, content_preview: str) -> str:
        fname_lower = fname.lower()
        if any(kw in fname_lower for kw in ["sale", "sales_reg", "sreg"]):
            return "sales"
        if any(kw in fname_lower for kw in ["purchase", "purch_reg", "preg"]):
            return "purchase"
        if any(kw in fname_lower for kw in ["ledger", "ledger_master", "ledger_bal"]):
            return "ledger"
        if any(kw in fname_lower for kw in ["party", "customer", "vendor", "supplier"]):
            return "party"
        if any(kw in fname_lower for kw in ["stock", "inventory", "item"]):
            return "stock"
        if any(kw in fname_lower for kw in ["daybook", "day_book", "journal"]):
            return "daybook"
        if any(kw in fname_lower for kw in ["trial", "balance", "tb"]):
            return "trial_balance"
        # Fall back to content analysis
        preview = content_preview.lower()
        if "sale" in preview or "invoice" in preview:
            return "sales"
        if "purchase" in preview or "bill" in preview:
            return "purchase"
        return "unknown"

    def _parse_xml_file(self, fpath: str, export_type: str) -> list[dict]:
        records: list[dict] = []
        try:
            tree = ET.parse(fpath)
            root = tree.getroot()

            # BUSY XML uses various root element names; find voucher/master rows
            row_tags = {"VOUCHER", "LEDGER", "PARTY", "ITEM", "STOCKITEM", "MASTER", "RECORD"}
            row_elements = []

            # Try namespace-aware lookup first
            for tag in row_tags:
                row_elements = root.findall(f".//{tag}") or root.findall(f".//{{*}}{tag}")
                if row_elements:
                    break

            # Generic: use most common child element
            if not row_elements:
                child_counts: dict = {}
                for child in root:
                    child_counts[child.tag] = child_counts.get(child.tag, 0) + 1
                if child_counts:
                    most_common = max(child_counts, key=lambda t: child_counts[t])
                    row_elements = root.findall(most_common)

            for elem in row_elements[: self.max_records]:
                record: dict = {"_export_type": export_type, "_company": self.company_name}
                for child in elem:
                    tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                    text = (child.text or "").strip()
                    # Flatten nested elements one level deep
                    if len(child) > 0:
                        for grandchild in child:
                            gtag = grandchild.tag.split("}")[-1] if "}" in grandchild.tag else grandchild.tag
                            record[f"{tag}_{gtag}"] = (grandchild.text or "").strip()
                    else:
                        record[tag] = text
                if record:
                    records.append(record)
        except ET.ParseError as exc:
            logger.warning("BUSY XML parse error in %s: %s", fpath, exc)
        except Exception as exc:
            logger.warning("BUSY XML processing failed for %s: %s", fpath, exc)
        return records

    def _parse_csv_file(self, fpath: str, export_type: str) -> list[dict]:
        records: list[dict] = []
        # BUSY CSVs sometimes have header rows with company info — skip them
        try:
            # Try to detect encoding
            encodings = [self.xml_encoding, "utf-8", "windows-1252", "latin-1"]
            df = None
            for enc in encodings:
                try:
                    df = pd.read_csv(fpath, dtype=str, encoding=enc, errors="replace", skip_blank_lines=True)
                    break
                except Exception:
                    continue
            if df is None or df.empty:
                return records

            # Drop rows where all values are NaN
            df = df.dropna(how="all")
            # Tag each record
            df["_export_type"] = export_type
            df["_company"] = self.company_name
            records = df.to_dict(orient="records")
        except Exception as exc:
            logger.warning("BUSY CSV parse failed for %s: %s", fpath, exc)
        return records

    def _parse_excel_file(self, fpath: str, export_type: str) -> list[dict]:
        records: list[dict] = []
        try:
            # BUSY Excel files may have merged header cells — use header=0 or skip rows
            df = pd.read_excel(fpath, dtype=str)
            # Drop rows where all non-NaN values are header-like
            df = df.dropna(how="all")
            df["_export_type"] = export_type
            df["_company"] = self.company_name
            records = df.to_dict(orient="records")
        except Exception as exc:
            logger.warning("BUSY Excel parse failed for %s: %s", fpath, exc)
        return records

    def _normalize_date(self, date_str: str) -> str:
        if not date_str:
            return ""
        # BUSY uses DD/MM/YYYY or DD-MM-YYYY
        for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y"):
            try:
                return datetime.strptime(date_str.strip(), fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return date_str

    def test_connection(self) -> ConnectionTestResult:
        import time
        start = time.perf_counter()
        if not os.path.isdir(self.data_dir):
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=False,
                message=f"BUSY data_dir not found: {self.data_dir}",
                response_time_ms=elapsed,
            )
        supported_exts = (".xml", ".csv", ".xlsx", ".xls")
        files = [f for f in os.listdir(self.data_dir) if f.lower().endswith(supported_exts)]
        elapsed = (time.perf_counter() - start) * 1000
        return ConnectionTestResult(
            success=bool(files),
            message=f"BUSY connector: {len(files)} export file(s) found in {self.data_dir}",
            response_time_ms=elapsed,
        )

    def extract_schema(self) -> SchemaDetectionResult:
        with self._timed_operation("busy_schema_detection"):
            columns = [
                {"name": "_export_type", "type": "string", "nullable": False, "sample_values": _EXPORT_TYPES},
                {"name": "_company", "type": "string", "nullable": True, "sample_values": []},
                {"name": "VoucherNo", "type": "string", "nullable": True, "sample_values": []},
                {"name": "Date", "type": "string", "nullable": True, "sample_values": []},
                {"name": "PartyName", "type": "string", "nullable": True, "sample_values": []},
                {"name": "Amount", "type": "string", "nullable": True, "sample_values": []},
                {"name": "TaxAmount", "type": "string", "nullable": True, "sample_values": []},
                {"name": "NetAmount", "type": "string", "nullable": True, "sample_values": []},
                {"name": "LedgerName", "type": "string", "nullable": True, "sample_values": []},
                {"name": "Narration", "type": "string", "nullable": True, "sample_values": []},
                {"name": "GSTIN", "type": "string", "nullable": True, "sample_values": []},
            ]
            return SchemaDetectionResult(
                columns=columns,
                total_columns=len(columns),
                detected_primary_key="VoucherNo",
                timestamp_columns=["Date"],
                indian_identifiers={"GSTIN": "GSTIN"},
            )

    def extract_full(self, config: ExtractionConfig) -> pd.DataFrame:
        import time
        start = time.perf_counter()
        try:
            all_records: list[dict] = []
            if not os.path.isdir(self.data_dir):
                self.log_extraction(0, time.perf_counter() - start, 0)
                return pd.DataFrame()

            for fname in sorted(os.listdir(self.data_dir)):
                fpath = os.path.join(self.data_dir, fname)
                ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""

                # Read a preview for type detection
                try:
                    with open(fpath, "r", encoding=self.xml_encoding, errors="replace") as fh:
                        preview = fh.read(500)
                except Exception:
                    preview = ""

                export_type = self._detect_export_type(fname, preview)
                if export_type not in self.export_types and "unknown" not in self.export_types:
                    continue

                if ext == "xml":
                    records = self._parse_xml_file(fpath, export_type)
                elif ext in ("xlsx", "xls"):
                    records = self._parse_excel_file(fpath, export_type)
                elif ext == "csv":
                    records = self._parse_csv_file(fpath, export_type)
                else:
                    continue

                all_records.extend(records)
                if len(all_records) >= self.max_records:
                    all_records = all_records[: self.max_records]
                    break

            df = pd.DataFrame(all_records) if all_records else pd.DataFrame()
            # Normalize date columns if present
            for col in df.columns:
                if "date" in col.lower() or col in ("Date", "VoucherDate"):
                    df[col] = df[col].apply(lambda x: self._normalize_date(str(x)) if pd.notna(x) else "")

            self.log_extraction(len(df), time.perf_counter() - start, 0)
            return df
        except Exception as exc:
            import time as _t
            self.log_extraction(0, _t.perf_counter() - start, 1)
            raise ExtractionError(self.source_id, f"BUSY extraction failed: {exc}") from exc

    def extract_incremental(self, config: IncrementalConfig) -> pd.DataFrame:
        if config.last_extracted_at:
            since_ts = config.last_extracted_at.timestamp()
            # Only process files modified since last extraction
            all_records: list[dict] = []
            if not os.path.isdir(self.data_dir):
                return pd.DataFrame()
            for fname in os.listdir(self.data_dir):
                fpath = os.path.join(self.data_dir, fname)
                if os.path.getmtime(fpath) < since_ts:
                    continue
                ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
                try:
                    with open(fpath, "r", encoding=self.xml_encoding, errors="replace") as fh:
                        preview = fh.read(500)
                except Exception:
                    preview = ""
                export_type = self._detect_export_type(fname, preview)
                if ext == "xml":
                    all_records.extend(self._parse_xml_file(fpath, export_type))
                elif ext in ("xlsx", "xls"):
                    all_records.extend(self._parse_excel_file(fpath, export_type))
                elif ext == "csv":
                    all_records.extend(self._parse_csv_file(fpath, export_type))
            return pd.DataFrame(all_records) if all_records else pd.DataFrame()
        return self.extract_full(config)

    def get_record_count(self) -> int:
        if not os.path.isdir(self.data_dir):
            return 0
        return sum(
            1 for f in os.listdir(self.data_dir)
            if f.lower().endswith((".xml", ".csv", ".xlsx", ".xls"))
        )
