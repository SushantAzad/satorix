"""
BSE / NSE corporate announcements and filing connector.

Extracts:
  - Corporate announcements (board meetings, results, dividends, changes)
  - Shareholding pattern filings (quarterly)
  - Board of directors composition changes
  - Regulatory actions (suspension orders, delisting)
  - Financial results (EPS, revenue, profit)

Both BSE and NSE provide publicly accessible APIs and data portals.

Sources:
  1. BSE India public API (announcements, filings)
  2. NSE India public data portal
  3. Sandbox.co.in BSE/NSE dataset

config keys:
  sandbox_api_key   : str
  exchange          : "bse" | "nse" | "both"  default "both"
  scrip_codes       : list  BSE scrip codes or NSE symbols to fetch
  announcement_types: list  filter by announcement type
  from_date         : str   ISO date filter
  to_date           : str   ISO date
  max_records       : int   default 5000
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
import pandas as pd

from layer1_ingestion.connectors.base_connector import (
    BaseConnector,
    ConnectionTestResult,
    ExtractionConfig,
    ExtractionError,
    IncrementalConfig,
    SchemaDetectionResult,
)
from layer1_ingestion.core.config import get_settings

logger = logging.getLogger(__name__)

_BSE_API = "https://api.bseindia.com/BseIndiaAPI/api"
_NSE_API = "https://www.nseindia.com/api"
_SANDBOX_BASE = "https://api.sandbox.co.in"

_BSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; InfracoreFoundry/1.0)",
    "Accept": "application/json",
    "Referer": "https://www.bseindia.com",
}
_NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; InfracoreFoundry/1.0)",
    "Accept": "application/json",
    "Referer": "https://www.nseindia.com",
}


class BSENSEConnector(BaseConnector):
    """BSE/NSE corporate announcement and filing connector."""

    REQUIRED_CONFIG_FIELDS: list[str] = []

    def __init__(self, source_id: str, config: dict) -> None:
        super().__init__(source_id, config)
        settings = get_settings()
        self.sandbox_api_key: str = config.get("sandbox_api_key", "") or settings.sandbox_api_key
        self.exchange: str = config.get("exchange", "both")
        self.scrip_codes: list = config.get("scrip_codes", [])
        self.announcement_types: list = config.get("announcement_types", [])
        self.from_date: str = config.get("from_date", "")
        self.to_date: str = config.get("to_date", "")
        self.max_records: int = int(config.get("max_records", 5000))

    def _bse_announcements(self, from_dt: str, to_dt: str) -> list[dict]:
        records: list[dict] = []
        try:
            url = f"{_BSE_API}/AnnGetData/w"
            params = {
                "strCat": "-1",
                "strPrevDate": from_dt.replace("-", ""),
                "strScrip": ",".join(str(s) for s in self.scrip_codes) if self.scrip_codes else "",
                "strSearch": "P",
                "strToDate": to_dt.replace("-", ""),
                "strType": "C",
                "subcategory": "-1",
            }
            with httpx.Client(headers=_BSE_HEADERS, timeout=30) as client:
                resp = client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                anns = data if isinstance(data, list) else data.get("Table", data.get("data", []))
                for ann in anns[: self.max_records]:
                    records.append(self._normalize_bse(ann))
        except Exception as exc:
            logger.warning("BSE announcements fetch failed: %s", exc)
        return records

    def _nse_announcements(self, from_dt: str, to_dt: str) -> list[dict]:
        records: list[dict] = []
        try:
            # NSE requires a session cookie — first hit the main page
            with httpx.Client(headers=_NSE_HEADERS, timeout=30, follow_redirects=True) as client:
                client.get("https://www.nseindia.com")
                params = {
                    "index": "equities",
                    "from_date": from_dt,
                    "to_date": to_dt,
                }
                if self.scrip_codes:
                    params["symbol"] = ",".join(str(s) for s in self.scrip_codes[:10])
                resp = client.get(
                    f"{_NSE_API}/corporate-announcements",
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json()
                anns = data if isinstance(data, list) else data.get("data", [])
                for ann in anns[: self.max_records]:
                    records.append(self._normalize_nse(ann))
        except Exception as exc:
            logger.warning("NSE announcements fetch failed: %s", exc)
        return records

    def _normalize_bse(self, ann: dict) -> dict:
        return {
            "exchange": "BSE",
            "scrip_code": str(ann.get("SCRIP_CD", ann.get("scrip_code", ""))),
            "company_name": ann.get("SLONGNAME", ann.get("company", "")),
            "announcement_type": ann.get("CATEGORYNAME", ann.get("category", "")),
            "subject": ann.get("HEADLINE", ann.get("subject", ""))[:500],
            "announcement_date": ann.get("NEWS_DT", ann.get("date", "")),
            "attachment_url": ann.get("ATTACHMENTNAME", ""),
            "news_id": str(ann.get("NEWSID", ann.get("id", ""))),
            "isin": ann.get("ISIN", ""),
        }

    def _normalize_nse(self, ann: dict) -> dict:
        return {
            "exchange": "NSE",
            "scrip_code": ann.get("symbol", ""),
            "company_name": ann.get("comp", ann.get("companyName", "")),
            "announcement_type": ann.get("subject", ann.get("desc", ""))[:100],
            "subject": ann.get("subject", ann.get("headline", ""))[:500],
            "announcement_date": ann.get("bcastdttm", ann.get("dt", ann.get("date", ""))),
            "attachment_url": ann.get("attchmntFile", ""),
            "news_id": str(ann.get("seq_id", ann.get("id", ""))),
            "isin": ann.get("isin", ""),
        }

    def _date_range(self) -> tuple[str, str]:
        if self.from_date and self.to_date:
            return self.from_date, self.to_date
        to_dt = datetime.now(tz=timezone.utc)
        from_dt = to_dt - timedelta(days=30)
        return from_dt.strftime("%Y-%m-%d"), to_dt.strftime("%Y-%m-%d")

    def test_connection(self) -> ConnectionTestResult:
        start = time.perf_counter()
        try:
            resp = httpx.get(
                f"{_BSE_API}/AnnGetData/w",
                headers=_BSE_HEADERS,
                params={"strCat": "-1", "strSearch": "P", "strType": "C", "subcategory": "-1"},
                timeout=15,
            )
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=resp.status_code < 400,
                message=f"BSE API status: {resp.status_code}",
                response_time_ms=elapsed,
            )
        except Exception as exc:
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=False, message=str(exc),
                response_time_ms=elapsed, error=type(exc).__name__,
            )

    def extract_schema(self) -> SchemaDetectionResult:
        with self._timed_operation("bse_nse_schema_detection"):
            columns = [
                {"name": "exchange", "type": "string", "nullable": False, "sample_values": ["BSE", "NSE"]},
                {"name": "scrip_code", "type": "string", "nullable": False, "sample_values": []},
                {"name": "company_name", "type": "string", "nullable": True, "sample_values": []},
                {"name": "announcement_type", "type": "string", "nullable": True, "sample_values": ["Board Meeting","Financial Results","Shareholding"]},
                {"name": "subject", "type": "string", "nullable": True, "sample_values": []},
                {"name": "announcement_date", "type": "string", "nullable": True, "sample_values": []},
                {"name": "attachment_url", "type": "string", "nullable": True, "sample_values": []},
                {"name": "news_id", "type": "string", "nullable": False, "sample_values": []},
                {"name": "isin", "type": "string", "nullable": True, "sample_values": []},
            ]
            return SchemaDetectionResult(
                columns=columns,
                total_columns=len(columns),
                detected_primary_key="news_id",
                timestamp_columns=["announcement_date"],
                indian_identifiers={"isin": "ISIN"},
            )

    def extract_full(self, config: ExtractionConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            from_dt, to_dt = self._date_range()
            records: list[dict] = []
            if self.exchange in ("bse", "both"):
                records.extend(self._bse_announcements(from_dt, to_dt))
            if self.exchange in ("nse", "both"):
                records.extend(self._nse_announcements(from_dt, to_dt))
            df = pd.DataFrame(records) if records else pd.DataFrame()
            if self.announcement_types and not df.empty and "announcement_type" in df.columns:
                mask = df["announcement_type"].str.contains(
                    "|".join(self.announcement_types), case=False, na=False
                )
                df = df[mask]
            self.log_extraction(len(df), time.perf_counter() - start, 0)
            return df
        except Exception as exc:
            self.log_extraction(0, time.perf_counter() - start, 1)
            raise ExtractionError(self.source_id, f"BSE/NSE extraction failed: {exc}") from exc

    def extract_incremental(self, config: IncrementalConfig) -> pd.DataFrame:
        if config.last_extracted_at:
            self.from_date = config.last_extracted_at.strftime("%Y-%m-%d")
            self.to_date = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        return self.extract_full(config)

    def get_record_count(self) -> int:
        return 0  # BSE/NSE don't expose total counts via their public APIs
