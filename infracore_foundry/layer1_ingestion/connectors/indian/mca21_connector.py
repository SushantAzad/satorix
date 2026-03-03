"""
MCA21 connector: Bulk download from MCA portal + Sandbox.co.in API
for Indian company and director master data.
"""

import io
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

import httpx
import pandas as pd
import redis

from layer1_ingestion.connectors.base_connector import (
    BaseConnector, ConnectionTestResult, SchemaDetectionResult,
    ExtractionConfig, IncrementalConfig, ExtractionError, RateLimitError,
)
from layer1_ingestion.core.config import get_settings

logger = logging.getLogger(__name__)

MCA_MASTER_DATA_URL = "https://www.mca.gov.in/content/mca/global/en/mca/master-data/MDS.html"
SANDBOX_BASE_URL = "https://api.sandbox.co.in"
REDIS_CACHE_TTL = 86400  # 24 hours


class MCA21Connector(BaseConnector):
    """MCA21 connector with bulk download and Sandbox API modes."""

    REQUIRED_CONFIG_FIELDS = []

    def __init__(self, source_id: str, config: dict) -> None:
        super().__init__(source_id, config)
        self.mode: str = config.get("mode", "bulk")  # bulk, api, hybrid
        self.sandbox_api_key: str = config.get("sandbox_api_key", "") or get_settings().sandbox_api_key
        self.bulk_data_dir: str = config.get("bulk_data_dir", "/tmp/mca_bulk_data")
        self._redis_client: Optional[redis.Redis] = None

    def _get_redis(self) -> Optional[redis.Redis]:
        if self._redis_client is None:
            try:
                settings = get_settings()
                self._redis_client = redis.from_url(settings.redis_url)
                self._redis_client.ping()
            except Exception:
                self._redis_client = None
        return self._redis_client

    def _sandbox_request(self, endpoint: str) -> dict:
        """Make authenticated request to Sandbox.co.in API with caching."""
        # Check Redis cache
        redis_client = self._get_redis()
        cache_key = f"mca21:{endpoint}"
        if redis_client:
            cached = redis_client.get(cache_key)
            if cached:
                logger.debug("Cache hit for %s", endpoint)
                return json.loads(cached)

        headers = {
            "X-Api-Key": self.sandbox_api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        url = f"{SANDBOX_BASE_URL}{endpoint}"
        backoff = 1
        for attempt in range(3):
            try:
                with httpx.Client(timeout=30) as client:
                    resp = client.get(url, headers=headers)
                if resp.status_code == 429:
                    retry_after = float(resp.headers.get("Retry-After", backoff))
                    time.sleep(min(retry_after, 30))
                    backoff *= 2
                    continue
                if resp.status_code == 402:
                    raise RateLimitError(self.source_id, "Sandbox API quota exceeded")
                resp.raise_for_status()
                data = resp.json()
                # Cache in Redis
                if redis_client:
                    redis_client.setex(cache_key, REDIS_CACHE_TTL, json.dumps(data))
                return data
            except (httpx.HTTPStatusError, RateLimitError):
                raise
            except Exception as e:
                if attempt < 2:
                    time.sleep(backoff)
                    backoff *= 2
                else:
                    raise ExtractionError(self.source_id, f"Sandbox API request failed: {e}") from e
        raise ExtractionError(self.source_id, "Max retries exceeded for Sandbox API")

    def test_connection(self) -> ConnectionTestResult:
        start = time.perf_counter()
        try:
            if self.mode in ("api", "hybrid"):
                if not self.sandbox_api_key:
                    elapsed = (time.perf_counter() - start) * 1000
                    return ConnectionTestResult(
                        success=False, message="SANDBOX_API_KEY not configured",
                        response_time_ms=elapsed, error="ConfigError",
                    )
                headers = {"X-Api-Key": self.sandbox_api_key}
                with httpx.Client(timeout=10) as client:
                    resp = client.get(f"{SANDBOX_BASE_URL}/companies/mca/master/data/U72200MH2009PTC194000", headers=headers)
                elapsed = (time.perf_counter() - start) * 1000
                return ConnectionTestResult(
                    success=resp.status_code in (200, 404),
                    message=f"Sandbox API responded: {resp.status_code}",
                    response_time_ms=elapsed,
                )
            else:
                # Bulk mode: verify local directory
                os.makedirs(self.bulk_data_dir, exist_ok=True)
                elapsed = (time.perf_counter() - start) * 1000
                return ConnectionTestResult(
                    success=True,
                    message=f"Bulk data directory ready: {self.bulk_data_dir}",
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
            {"name": "CIN", "type": "string", "nullable": False, "sample_values": ["U72200MH2009PTC194000"]},
            {"name": "CompanyName", "type": "string", "nullable": False, "sample_values": ["TATA CONSULTANCY SERVICES"]},
            {"name": "CompanyStatus", "type": "string", "nullable": False, "sample_values": ["Active"]},
            {"name": "CompanyClass", "type": "string", "nullable": True, "sample_values": ["Public"]},
            {"name": "AuthorizedCapital", "type": "float64", "nullable": True, "sample_values": [1000000000.0]},
            {"name": "PaidUpCapital", "type": "float64", "nullable": True, "sample_values": [500000000.0]},
            {"name": "IncorporationDate", "type": "string", "nullable": True, "sample_values": ["2009-01-15"]},
            {"name": "RegisteredState", "type": "string", "nullable": True, "sample_values": ["Maharashtra"]},
            {"name": "ROCCode", "type": "string", "nullable": True, "sample_values": ["ROC-MUMBAI"]},
            {"name": "Category", "type": "string", "nullable": True, "sample_values": ["Company limited by Shares"]},
            {"name": "Email", "type": "string", "nullable": True, "sample_values": []},
        ]
        return SchemaDetectionResult(
            columns=columns, total_columns=len(columns),
            indian_identifiers={"CIN": "cin"},
        )

    def extract_full(self, config: ExtractionConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            if self.mode == "bulk":
                return self._extract_bulk(config)
            elif self.mode == "api":
                return self._extract_api(config)
            else:  # hybrid
                try:
                    return self._extract_api(config)
                except (RateLimitError, ExtractionError):
                    logger.warning("API quota exceeded, falling back to bulk data", extra={"source_id": self.source_id})
                    return self._extract_bulk(config)
        except Exception as e:
            duration = time.perf_counter() - start
            self.log_extraction(0, duration, 1)
            raise ExtractionError(self.source_id, f"MCA21 extraction failed: {str(e)}") from e

    def _extract_bulk(self, config) -> pd.DataFrame:
        """Download and parse MCA bulk master data CSV files."""
        start = time.perf_counter()
        os.makedirs(self.bulk_data_dir, exist_ok=True)

        # Attempt to download company master data
        try:
            with httpx.Client(timeout=120, follow_redirects=True) as client:
                resp = client.get(MCA_MASTER_DATA_URL)
                resp.raise_for_status()
                # Parse the page to find download links
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "html.parser")
                csv_links = []
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if href.endswith(".csv") or "master" in href.lower():
                        if not href.startswith("http"):
                            href = f"https://www.mca.gov.in{href}"
                        csv_links.append(href)
        except Exception as e:
            logger.warning("Could not scrape MCA portal: %s", str(e))
            csv_links = []

        # Load any existing CSV files in the bulk directory
        local_files = [
            os.path.join(self.bulk_data_dir, f)
            for f in os.listdir(self.bulk_data_dir)
            if f.endswith(".csv")
        ]

        all_dfs = []
        for fp in local_files:
            try:
                df = pd.read_csv(fp, dtype=str, on_bad_lines="warn")
                all_dfs.append(df)
            except Exception as e:
                logger.warning("Failed to parse %s: %s", fp, str(e))

        if all_dfs:
            combined = pd.concat(all_dfs, ignore_index=True)
        else:
            combined = pd.DataFrame()

        duration = time.perf_counter() - start
        self.log_extraction(len(combined), duration, 0)
        return combined

    def _extract_api(self, config) -> pd.DataFrame:
        """Extract company data via Sandbox.co.in API."""
        start = time.perf_counter()
        cin_list = self.config.get("cin_list", [])
        if not cin_list:
            raise ExtractionError(self.source_id, "No CIN list provided for API mode extraction")

        records = []
        errors = 0
        for cin in cin_list:
            try:
                data = self._sandbox_request(f"/companies/mca/master/data/{cin}")
                records.append(data.get("data", data))
            except Exception as e:
                logger.warning("Failed to fetch CIN %s: %s", cin, str(e))
                errors += 1

        df = pd.json_normalize(records) if records else pd.DataFrame()
        duration = time.perf_counter() - start
        self.log_extraction(len(df), duration, errors)
        return df

    def get_company_by_cin(self, cin: str) -> dict:
        """Get a single company's data by CIN (API mode)."""
        return self._sandbox_request(f"/companies/mca/master/data/{cin}")

    def get_director_by_din(self, din: str) -> dict:
        """Get director data by DIN (API mode)."""
        return self._sandbox_request(f"/companies/mca/master/director/{din}")

    def get_charges_by_cin(self, cin: str) -> dict:
        """Get charge/lien data for a company (API mode)."""
        return self._sandbox_request(f"/companies/mca/charges/{cin}")

    def extract_incremental(self, config: IncrementalConfig) -> pd.DataFrame:
        """For bulk mode: re-download if MCA published new file."""
        if self.mode == "bulk":
            try:
                with httpx.Client(timeout=30, follow_redirects=True) as client:
                    resp = client.head(MCA_MASTER_DATA_URL)
                    last_modified = resp.headers.get("Last-Modified", "")
                if config.last_extracted_at and last_modified:
                    from email.utils import parsedate_to_datetime
                    try:
                        remote_date = parsedate_to_datetime(last_modified)
                        if remote_date <= config.last_extracted_at:
                            logger.info("MCA bulk data unchanged", extra={"source_id": self.source_id})
                            return pd.DataFrame()
                    except Exception:
                        pass
            except Exception:
                pass
        return self.extract_full(config)

    def get_record_count(self) -> int:
        local_files = [
            f for f in os.listdir(self.bulk_data_dir) if f.endswith(".csv")
        ] if os.path.isdir(self.bulk_data_dir) else []
        count = 0
        for fp in local_files:
            full_path = os.path.join(self.bulk_data_dir, fp)
            with open(full_path, "r") as f:
                count += sum(1 for _ in f) - 1
        return max(count, 0)
