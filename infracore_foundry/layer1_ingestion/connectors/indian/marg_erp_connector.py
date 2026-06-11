"""
Marg ERP connector.

Marg ERP is one of India's most widely used ERP/accounting systems,
particularly in pharma distribution, retail, and manufacturing SMEs.
It exports data in CSV and XML formats via its export utility.

Marg exports commonly available:
  - Sales register (party-wise, item-wise)
  - Purchase register
  - Stock ledger (item movement)
  - Party ledger (outstanding/balance)
  - GST reports (GSTR-1, GSTR-2, GSTR-3B summaries)
  - Challan / invoice data

Marg-specific data patterns:
  - Batch numbers for pharma inventory
  - Expiry dates on stock items
  - MRP vs. selling price
  - Distributor margin tracking

config keys:
  data_dir          : str   path to Marg export files
  company_name      : str   Marg company name (for tagging)
  export_types      : list  e.g. ["sales","purchase","stock","gst"]  default all
  include_gst_data  : bool  extract GST-related columns — default True
  financial_year    : str   e.g. "2024-25"
  encoding          : str   default "utf-8" (Marg can use windows-1252)
  max_records       : int   default 100000
"""

import logging
import os
import time
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

_EXPORT_TYPES = ["sales", "purchase", "stock", "party", "gst", "challan"]


class MargERPConnector(BaseConnector):
    """Marg ERP export file connector for pharma/retail/distribution data."""

    REQUIRED_CONFIG_FIELDS: list[str] = ["data_dir"]

    def __init__(self, source_id: str, config: dict) -> None:
        super().__init__(source_id, config)
        self.data_dir: str = config.get("data_dir", "")
        self.company_name: str = config.get("company_name", "")
        self.export_types: list = config.get("export_types", _EXPORT_TYPES)
        self.include_gst_data: bool = bool(config.get("include_gst_data", True))
        self.financial_year: str = config.get("financial_year", "")
        self.encoding: str = config.get("encoding", "utf-8")
        self.max_records: int = int(config.get("max_records", 100000))

    def _detect_export_type(self, fname: str) -> str:
        fname_lower = fname.lower()
        if any(kw in fname_lower for kw in ["sale", "sreg", "sales_reg"]):
            return "sales"
        if any(kw in fname_lower for kw in ["purch", "preg", "purchase"]):
            return "purchase"
        if any(kw in fname_lower for kw in ["stock", "item", "inventory"]):
            return "stock"
        if any(kw in fname_lower for kw in ["party", "ledger", "customer", "supplier"]):
            return "party"
        if any(kw in fname_lower for kw in ["gst", "gstr", "tax"]):
            return "gst"
        if any(kw in fname_lower for kw in ["challan", "invoice"]):
            return "challan"
        return "unknown"

    def _read_file(self, fpath: str) -> Optional[pd.DataFrame]:
        ext = fpath.rsplit(".", 1)[-1].lower() if "." in fpath else ""
        encodings = [self.encoding, "utf-8", "windows-1252", "latin-1"]
        try:
            if ext in ("xlsx", "xls"):
                df = pd.read_excel(fpath, dtype=str)
                return df.dropna(how="all")
            elif ext == "csv":
                for enc in encodings:
                    try:
                        df = pd.read_csv(fpath, dtype=str, encoding=enc, errors="replace", skip_blank_lines=True)
                        return df.dropna(how="all")
                    except Exception:
                        continue
            elif ext == "txt":
                # Marg sometimes exports tab-delimited or fixed-width
                for sep in ("\t", "|", ","):
                    for enc in encodings:
                        try:
                            df = pd.read_csv(fpath, sep=sep, dtype=str, encoding=enc, errors="replace")
                            if len(df.columns) > 2:
                                return df.dropna(how="all")
                        except Exception:
                            continue
        except Exception as exc:
            logger.warning("Marg file read failed for %s: %s", fpath, exc)
        return None

    def _normalize_sales_row(self, row: dict) -> dict:
        def pick(keys: list[str]) -> str:
            for k in keys:
                for col, val in row.items():
                    if k.lower() in str(col).lower() and val and str(val) not in ("nan", ""):
                        return str(val).strip()
            return ""

        return {
            "invoice_no": pick(["invoice", "bill no", "voucher no", "challan no"]),
            "invoice_date": pick(["date", "invoice date", "bill date"]),
            "party_name": pick(["party name", "customer", "buyer"]),
            "party_gstin": pick(["gstin", "party gstin", "customer gstin"]),
            "item_name": pick(["item", "product", "material name"]),
            "batch_no": pick(["batch", "batch no", "lot no"]),
            "expiry_date": pick(["expiry", "exp date", "expiry date"]),
            "quantity": pick(["qty", "quantity", "units"]),
            "unit": pick(["unit", "uom"]),
            "mrp": pick(["mrp", "max retail price"]),
            "rate": pick(["rate", "selling price", "unit price"]),
            "gross_amount": pick(["gross", "gross amount", "amount before tax"]),
            "discount": pick(["discount", "disc"]),
            "taxable_amount": pick(["taxable", "net amount", "taxable amount"]),
            "sgst": pick(["sgst"]),
            "cgst": pick(["cgst"]),
            "igst": pick(["igst"]),
            "total_tax": pick(["total tax", "tax amount", "gst amount"]),
            "net_amount": pick(["net", "net total", "total amount", "invoice amount"]),
            "hsn_code": pick(["hsn", "hsn code", "sac"]),
            "company": self.company_name,
            "financial_year": self.financial_year,
        }

    def _normalize_stock_row(self, row: dict) -> dict:
        def pick(keys: list[str]) -> str:
            for k in keys:
                for col, val in row.items():
                    if k.lower() in str(col).lower() and val and str(val) not in ("nan", ""):
                        return str(val).strip()
            return ""

        return {
            "item_name": pick(["item", "product", "material"]),
            "item_code": pick(["code", "item code", "product code"]),
            "category": pick(["category", "group", "sub group"]),
            "hsn_code": pick(["hsn"]),
            "batch_no": pick(["batch"]),
            "expiry_date": pick(["expiry"]),
            "opening_qty": pick(["opening qty", "opening stock", "opening"]),
            "inward_qty": pick(["inward", "purchase qty", "received"]),
            "outward_qty": pick(["outward", "sales qty", "issued"]),
            "closing_qty": pick(["closing qty", "closing stock", "closing"]),
            "unit": pick(["unit", "uom"]),
            "purchase_rate": pick(["purchase rate", "cost price", "purchase price"]),
            "sale_rate": pick(["sale rate", "selling price"]),
            "mrp": pick(["mrp"]),
            "stock_value": pick(["value", "stock value", "amount"]),
            "company": self.company_name,
        }

    def _normalize_party_row(self, row: dict) -> dict:
        def pick(keys: list[str]) -> str:
            for k in keys:
                for col, val in row.items():
                    if k.lower() in str(col).lower() and val and str(val) not in ("nan", ""):
                        return str(val).strip()
            return ""

        return {
            "party_name": pick(["party name", "name", "customer name"]),
            "party_code": pick(["code", "party code"]),
            "gstin": pick(["gstin", "gst no"]),
            "pan": pick(["pan"]),
            "state": pick(["state"]),
            "city": pick(["city"]),
            "pincode": pick(["pin", "pincode"]),
            "mobile": pick(["mobile", "phone"]),
            "email": pick(["email"]),
            "credit_limit": pick(["credit limit", "limit"]),
            "outstanding": pick(["outstanding", "balance", "due amount"]),
            "last_transaction": pick(["last transaction", "last date"]),
            "party_type": pick(["type", "party type"]),
            "drug_license": pick(["drug license", "dl no", "license"]),
            "company": self.company_name,
        }

    def test_connection(self) -> ConnectionTestResult:
        start = time.perf_counter()
        if not os.path.isdir(self.data_dir):
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=False,
                message=f"Marg data_dir not found: {self.data_dir}",
                response_time_ms=elapsed,
            )
        supported_exts = (".csv", ".xlsx", ".xls", ".txt")
        files = [f for f in os.listdir(self.data_dir) if f.lower().endswith(supported_exts)]
        elapsed = (time.perf_counter() - start) * 1000
        return ConnectionTestResult(
            success=bool(files),
            message=f"Marg ERP connector: {len(files)} export file(s) found in {self.data_dir}",
            response_time_ms=elapsed,
        )

    def extract_schema(self) -> SchemaDetectionResult:
        with self._timed_operation("marg_schema_detection"):
            columns = [
                {"name": "invoice_no", "type": "string", "nullable": True, "sample_values": []},
                {"name": "invoice_date", "type": "string", "nullable": True, "sample_values": []},
                {"name": "party_name", "type": "string", "nullable": True, "sample_values": []},
                {"name": "party_gstin", "type": "string", "nullable": True, "sample_values": []},
                {"name": "item_name", "type": "string", "nullable": True, "sample_values": []},
                {"name": "batch_no", "type": "string", "nullable": True, "sample_values": []},
                {"name": "expiry_date", "type": "string", "nullable": True, "sample_values": []},
                {"name": "quantity", "type": "string", "nullable": True, "sample_values": []},
                {"name": "mrp", "type": "string", "nullable": True, "sample_values": []},
                {"name": "net_amount", "type": "string", "nullable": True, "sample_values": []},
                {"name": "hsn_code", "type": "string", "nullable": True, "sample_values": []},
                {"name": "sgst", "type": "string", "nullable": True, "sample_values": []},
                {"name": "cgst", "type": "string", "nullable": True, "sample_values": []},
                {"name": "igst", "type": "string", "nullable": True, "sample_values": []},
            ]
            return SchemaDetectionResult(
                columns=columns,
                total_columns=len(columns),
                detected_primary_key="invoice_no",
                timestamp_columns=["invoice_date", "expiry_date"],
                indian_identifiers={"party_gstin": "GSTIN", "pan": "PAN"},
            )

    def extract_full(self, config: ExtractionConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            all_records: list[dict] = []
            if not os.path.isdir(self.data_dir):
                self.log_extraction(0, time.perf_counter() - start, 0)
                return pd.DataFrame()

            for fname in sorted(os.listdir(self.data_dir)):
                fpath = os.path.join(self.data_dir, fname)
                if not os.path.isfile(fpath):
                    continue
                export_type = self._detect_export_type(fname)
                if export_type not in self.export_types and "unknown" not in self.export_types:
                    continue

                df = self._read_file(fpath)
                if df is None or df.empty:
                    continue

                normalizer = {
                    "sales": self._normalize_sales_row,
                    "purchase": self._normalize_sales_row,
                    "gst": self._normalize_sales_row,
                    "challan": self._normalize_sales_row,
                    "stock": self._normalize_stock_row,
                    "party": self._normalize_party_row,
                }.get(export_type, self._normalize_sales_row)

                for _, row in df.iterrows():
                    rec = normalizer(row.to_dict())
                    rec["_export_type"] = export_type
                    rec["_source_file"] = fname
                    all_records.append(rec)
                    if len(all_records) >= self.max_records:
                        break

                if len(all_records) >= self.max_records:
                    break

            result = pd.DataFrame(all_records) if all_records else pd.DataFrame()
            if not self.include_gst_data and not result.empty:
                gst_cols = [c for c in result.columns if any(g in c.lower() for g in ["gst", "sgst", "cgst", "igst", "hsn"])]
                result = result.drop(columns=gst_cols, errors="ignore")

            self.log_extraction(len(result), time.perf_counter() - start, 0)
            return result
        except Exception as exc:
            self.log_extraction(0, time.perf_counter() - start, 1)
            raise ExtractionError(self.source_id, f"Marg ERP extraction failed: {exc}") from exc

    def extract_incremental(self, config: IncrementalConfig) -> pd.DataFrame:
        if config.last_extracted_at:
            since_ts = config.last_extracted_at.timestamp()
            all_records: list[dict] = []
            if not os.path.isdir(self.data_dir):
                return pd.DataFrame()
            for fname in os.listdir(self.data_dir):
                fpath = os.path.join(self.data_dir, fname)
                if not os.path.isfile(fpath) or os.path.getmtime(fpath) < since_ts:
                    continue
                export_type = self._detect_export_type(fname)
                df = self._read_file(fpath)
                if df is None or df.empty:
                    continue
                normalizer = {
                    "sales": self._normalize_sales_row,
                    "purchase": self._normalize_sales_row,
                    "stock": self._normalize_stock_row,
                    "party": self._normalize_party_row,
                }.get(export_type, self._normalize_sales_row)
                for _, row in df.iterrows():
                    rec = normalizer(row.to_dict())
                    rec["_export_type"] = export_type
                    all_records.append(rec)
            return pd.DataFrame(all_records) if all_records else pd.DataFrame()
        return self.extract_full(config)

    def get_record_count(self) -> int:
        if not os.path.isdir(self.data_dir):
            return 0
        return sum(
            1 for f in os.listdir(self.data_dir)
            if f.lower().endswith((".csv", ".xlsx", ".xls", ".txt"))
        )
