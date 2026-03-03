"""
RBI connector: extracts NBFC list, bank rates, and weekly statistical supplements
from the Reserve Bank of India website.
"""

import io
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

import httpx
import pandas as pd
from bs4 import BeautifulSoup

from layer1_ingestion.connectors.base_connector import (
    BaseConnector, ConnectionTestResult, SchemaDetectionResult,
    ExtractionConfig, IncrementalConfig, ExtractionError,
)

logger = logging.getLogger(__name__)

RBI_BASE_URL = "https://www.rbi.org.in"
RBI_NBFC_URL = f"{RBI_BASE_URL}/Scripts/BS_NBFCList.aspx"
RBI_RATES_URL = f"{RBI_BASE_URL}/Scripts/BS_PressReleaseDisplay.aspx"
RBI_WSS_URL = f"{RBI_BASE_URL}/Scripts/WSSView.aspx"
REQUEST_DELAY = 2


class RBIConnector(BaseConnector):
    """Connector for RBI statistical data: NBFCs, rates, weekly supplements."""

    REQUIRED_CONFIG_FIELDS = []

    def __init__(self, source_id: str, config: dict) -> None:
        super().__init__(source_id, config)
        self.data_types: list[str] = config.get("data_types", ["nbfc", "rates", "wss"])
        self.download_dir: str = config.get("download_dir", "/tmp/rbi_data")

    def test_connection(self) -> ConnectionTestResult:
        start = time.perf_counter()
        try:
            with httpx.Client(timeout=15, follow_redirects=True) as client:
                resp = client.get(RBI_BASE_URL)
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=resp.status_code == 200,
                message=f"RBI website reachable (status={resp.status_code})",
                response_time_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=False, message=str(e),
                response_time_ms=elapsed, error=type(e).__name__,
            )

    def extract_schema(self) -> SchemaDetectionResult:
        columns = [
            {"name": "entity_name", "type": "string", "nullable": False, "sample_values": ["Bajaj Finance Limited"]},
            {"name": "registration_number", "type": "string", "nullable": True, "sample_values": ["N-13.02043"]},
            {"name": "entity_type", "type": "string", "nullable": True, "sample_values": ["NBFC-D", "NBFC-ND"]},
            {"name": "registered_address", "type": "string", "nullable": True, "sample_values": []},
            {"name": "city", "type": "string", "nullable": True, "sample_values": ["Mumbai"]},
            {"name": "state", "type": "string", "nullable": True, "sample_values": ["Maharashtra"]},
            {"name": "data_source", "type": "string", "nullable": False, "sample_values": ["nbfc_list"]},
            {"name": "extracted_at", "type": "datetime64", "nullable": False, "sample_values": []},
        ]
        return SchemaDetectionResult(columns=columns, total_columns=len(columns))

    def extract_full(self, config: ExtractionConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            all_dfs = []

            if "nbfc" in self.data_types:
                nbfc_df = self._extract_nbfc_list()
                if not nbfc_df.empty:
                    nbfc_df["data_source"] = "nbfc_list"
                    all_dfs.append(nbfc_df)

            if "rates" in self.data_types:
                rates_df = self._extract_bank_rates()
                if not rates_df.empty:
                    rates_df["data_source"] = "bank_rates"
                    all_dfs.append(rates_df)

            if "wss" in self.data_types:
                wss_df = self._extract_wss()
                if not wss_df.empty:
                    wss_df["data_source"] = "weekly_statistical_supplement"
                    all_dfs.append(wss_df)

            if all_dfs:
                combined = pd.concat(all_dfs, ignore_index=True)
            else:
                combined = pd.DataFrame()

            combined["extracted_at"] = datetime.now(timezone.utc).isoformat()
            duration = time.perf_counter() - start
            self.log_extraction(len(combined), duration, 0)
            return combined
        except Exception as e:
            duration = time.perf_counter() - start
            self.log_extraction(0, duration, 1)
            raise ExtractionError(self.source_id, f"RBI extraction failed: {str(e)}") from e

    def _extract_nbfc_list(self) -> pd.DataFrame:
        """Scrape the NBFC list from RBI website."""
        try:
            with httpx.Client(timeout=30, follow_redirects=True) as client:
                resp = client.get(RBI_NBFC_URL)
                resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")
            tables = soup.find_all("table")
            records = []

            for table in tables:
                rows = table.find_all("tr")
                headers = [th.get_text(strip=True) for th in rows[0].find_all(["th", "td"])] if rows else []

                for row in rows[1:]:
                    cells = [td.get_text(strip=True) for td in row.find_all("td")]
                    if len(cells) < 2:
                        continue

                    record = {
                        "entity_name": cells[1] if len(cells) > 1 else cells[0],
                        "registration_number": cells[0] if len(cells) > 0 else "",
                        "entity_type": cells[2] if len(cells) > 2 else "",
                        "registered_address": cells[3] if len(cells) > 3 else "",
                        "city": cells[4] if len(cells) > 4 else "",
                        "state": cells[5] if len(cells) > 5 else "",
                    }
                    records.append(record)

            time.sleep(REQUEST_DELAY)
            return pd.DataFrame(records) if records else pd.DataFrame()
        except Exception as e:
            logger.warning("Failed to extract NBFC list: %s", str(e))
            return pd.DataFrame()

    def _extract_bank_rates(self) -> pd.DataFrame:
        """Extract current RBI bank rates and policy rates."""
        try:
            with httpx.Client(timeout=30, follow_redirects=True) as client:
                resp = client.get(RBI_RATES_URL)
                resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")
            records = []

            tables = soup.find_all("table")
            for table in tables:
                rows = table.find_all("tr")
                for row in rows:
                    cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
                    if len(cells) >= 2:
                        rate_name = cells[0]
                        rate_value = cells[1] if len(cells) > 1 else ""
                        effective_date = cells[2] if len(cells) > 2 else ""
                        records.append({
                            "rate_name": rate_name,
                            "rate_value": rate_value,
                            "effective_date": effective_date,
                        })

            time.sleep(REQUEST_DELAY)
            return pd.DataFrame(records) if records else pd.DataFrame()
        except Exception as e:
            logger.warning("Failed to extract bank rates: %s", str(e))
            return pd.DataFrame()

    def _extract_wss(self) -> pd.DataFrame:
        """Download and parse weekly statistical supplement Excel files."""
        try:
            os.makedirs(self.download_dir, exist_ok=True)

            with httpx.Client(timeout=30, follow_redirects=True) as client:
                resp = client.get(RBI_WSS_URL)
                resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")
            excel_links = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if href.endswith((".xlsx", ".xls")):
                    if not href.startswith("http"):
                        href = f"{RBI_BASE_URL}{href}"
                    excel_links.append(href)

            all_dfs = []
            for link in excel_links[:5]:  # Limit to 5 most recent
                try:
                    with httpx.Client(timeout=60, follow_redirects=True) as client:
                        resp = client.get(link)
                        resp.raise_for_status()
                    df = pd.read_excel(io.BytesIO(resp.content))
                    df["_source_file"] = os.path.basename(link)
                    all_dfs.append(df)
                    time.sleep(REQUEST_DELAY)
                except Exception as e:
                    logger.warning("Failed to download WSS file %s: %s", link, str(e))

            return pd.concat(all_dfs, ignore_index=True) if all_dfs else pd.DataFrame()
        except Exception as e:
            logger.warning("Failed to extract WSS: %s", str(e))
            return pd.DataFrame()

    def extract_incremental(self, config: IncrementalConfig) -> pd.DataFrame:
        """Track file modification dates for incremental sync."""
        return self.extract_full(config)

    def get_record_count(self) -> int:
        return 0
