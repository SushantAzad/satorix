"""
SEBI connector: scrapes enforcement orders, penalties, settlements,
and debarment notices from SEBI's website.
"""

import logging
import os
import re
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

SEBI_BASE_URL = "https://www.sebi.gov.in"
SEBI_ORDERS_URL = f"{SEBI_BASE_URL}/sebiweb/home/HomeAction.do?doListing=yes&sid=1&ssid=0&smession=No"
REQUEST_DELAY_SECONDS = 2


class SEBIConnector(BaseConnector):
    """Connector for scraping SEBI enforcement data."""

    REQUIRED_CONFIG_FIELDS = []

    def __init__(self, source_id: str, config: dict) -> None:
        super().__init__(source_id, config)
        self.order_types: list[str] = config.get("order_types", ["enforcement", "penalty", "settlement", "debarment"])
        self.max_pages: int = config.get("max_pages", 50)

    def test_connection(self) -> ConnectionTestResult:
        start = time.perf_counter()
        try:
            with httpx.Client(timeout=15, follow_redirects=True) as client:
                resp = client.get(SEBI_BASE_URL)
                resp.raise_for_status()
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=True, message=f"SEBI website reachable (status={resp.status_code})",
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
            {"name": "order_id", "type": "string", "nullable": True, "sample_values": []},
            {"name": "entity_name", "type": "string", "nullable": False, "sample_values": ["ABC Securities Ltd"]},
            {"name": "entity_type", "type": "string", "nullable": True, "sample_values": ["company", "individual"]},
            {"name": "order_date", "type": "datetime64", "nullable": True, "sample_values": ["2024-01-15"]},
            {"name": "order_type", "type": "string", "nullable": False, "sample_values": ["enforcement", "penalty"]},
            {"name": "penalty_amount", "type": "float64", "nullable": True, "sample_values": [500000.0]},
            {"name": "violation_description", "type": "string", "nullable": True, "sample_values": []},
            {"name": "pdf_url", "type": "string", "nullable": True, "sample_values": []},
            {"name": "extracted_at", "type": "datetime64", "nullable": False, "sample_values": []},
        ]
        return SchemaDetectionResult(columns=columns, total_columns=len(columns))

    def extract_full(self, config: ExtractionConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            self.logger.info("extraction_start", extra={"source_id": self.source_id, "types": self.order_types})
            all_records = []

            for order_type in self.order_types:
                records = self._scrape_order_type(order_type)
                all_records.extend(records)

            df = pd.DataFrame(all_records) if all_records else pd.DataFrame()
            if not df.empty:
                df["extracted_at"] = datetime.now(timezone.utc).isoformat()

            duration = time.perf_counter() - start
            self.log_extraction(len(df), duration, 0)
            return df
        except Exception as e:
            duration = time.perf_counter() - start
            self.log_extraction(0, duration, 1)
            raise ExtractionError(self.source_id, f"SEBI extraction failed: {str(e)}") from e

    def _scrape_order_type(self, order_type: str) -> list[dict]:
        """Scrape paginated orders of a specific type."""
        records = []
        url_map = {
            "enforcement": f"{SEBI_BASE_URL}/enforcement/orders/",
            "penalty": f"{SEBI_BASE_URL}/enforcement/orders/",
            "settlement": f"{SEBI_BASE_URL}/enforcement/settlement-orders/",
            "debarment": f"{SEBI_BASE_URL}/enforcement/debarment-orders/",
        }
        base_url = url_map.get(order_type, f"{SEBI_BASE_URL}/enforcement/orders/")

        for page in range(1, self.max_pages + 1):
            try:
                params = {"page": page}
                with httpx.Client(timeout=30, follow_redirects=True) as client:
                    resp = client.get(base_url, params=params)

                if resp.status_code != 200:
                    break

                soup = BeautifulSoup(resp.text, "html.parser")
                rows = soup.select("table tr, .list-items li, .order-item")

                if not rows:
                    break

                page_records = self._parse_order_page(soup, order_type)
                if not page_records:
                    break

                records.extend(page_records)
                time.sleep(REQUEST_DELAY_SECONDS)

            except Exception as e:
                logger.warning("Failed to scrape page %d of %s: %s", page, order_type, str(e))
                break

        return records

    def _parse_order_page(self, soup: BeautifulSoup, order_type: str) -> list[dict]:
        """Parse a single page of SEBI orders."""
        records = []

        # Try table format
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            for row in rows[1:]:  # Skip header
                cells = row.find_all(["td", "th"])
                if len(cells) < 3:
                    continue

                record = self._parse_table_row(cells, order_type)
                if record:
                    records.append(record)

        # Try list format
        if not records:
            items = soup.select(".list-items a, .content-area a")
            for item in items:
                href = item.get("href", "")
                text = item.get_text(strip=True)
                if text and (href.endswith(".pdf") or "/orders/" in href):
                    record = {
                        "order_id": href.split("/")[-1].replace(".pdf", ""),
                        "entity_name": self._extract_entity_name(text),
                        "entity_type": self._detect_entity_type(text),
                        "order_date": self._extract_date(text),
                        "order_type": order_type,
                        "penalty_amount": self._extract_penalty(text),
                        "violation_description": text,
                        "pdf_url": href if href.startswith("http") else f"{SEBI_BASE_URL}{href}",
                    }
                    records.append(record)
        return records

    def _parse_table_row(self, cells: list, order_type: str) -> Optional[dict]:
        """Parse a single table row into an order record."""
        texts = [c.get_text(strip=True) for c in cells]
        links = [a.get("href", "") for c in cells for a in c.find_all("a", href=True)]
        pdf_url = next((l for l in links if l.endswith(".pdf")), "")
        if pdf_url and not pdf_url.startswith("http"):
            pdf_url = f"{SEBI_BASE_URL}{pdf_url}"

        entity_name = texts[0] if texts else ""
        order_date = self._extract_date(" ".join(texts))
        penalty = self._extract_penalty(" ".join(texts))

        if not entity_name:
            return None

        return {
            "order_id": pdf_url.split("/")[-1].replace(".pdf", "") if pdf_url else "",
            "entity_name": entity_name,
            "entity_type": self._detect_entity_type(entity_name),
            "order_date": order_date,
            "order_type": order_type,
            "penalty_amount": penalty,
            "violation_description": " | ".join(texts[1:]) if len(texts) > 1 else "",
            "pdf_url": pdf_url,
        }

    @staticmethod
    def _extract_entity_name(text: str) -> str:
        parts = re.split(r"\s*[-–|]\s*", text)
        return parts[0].strip()[:200] if parts else text[:200]

    @staticmethod
    def _detect_entity_type(name: str) -> str:
        lower = name.lower()
        if any(w in lower for w in ["ltd", "limited", "pvt", "llp", "inc", "corp"]):
            return "company"
        return "individual"

    @staticmethod
    def _extract_date(text: str) -> Optional[str]:
        patterns = [
            r"(\d{2}[/.]\d{2}[/.]\d{4})",
            r"(\d{4}-\d{2}-\d{2})",
            r"(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                date_str = match.group(1)
                for fmt in ("%d/%m/%Y", "%d.%m.%Y", "%Y-%m-%d", "%d %B %Y"):
                    try:
                        return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
                    except ValueError:
                        continue
        return None

    @staticmethod
    def _extract_penalty(text: str) -> Optional[float]:
        match = re.search(r"(?:Rs\.?|₹|INR)\s*([\d,]+(?:\.\d+)?)", text)
        if match:
            amount_str = match.group(1).replace(",", "")
            try:
                return float(amount_str)
            except ValueError:
                pass
        return None

    def extract_incremental(self, config: IncrementalConfig) -> pd.DataFrame:
        """Track last scraped order date for incremental sync."""
        df = self.extract_full(config)
        if df.empty or not config.last_extracted_at:
            return df
        if "order_date" in df.columns:
            df["order_date_parsed"] = pd.to_datetime(df["order_date"], errors="coerce")
            df = df[df["order_date_parsed"] > config.last_extracted_at].drop(columns=["order_date_parsed"])
        return df.reset_index(drop=True)

    def get_record_count(self) -> int:
        return 0  # Unknown until extraction
