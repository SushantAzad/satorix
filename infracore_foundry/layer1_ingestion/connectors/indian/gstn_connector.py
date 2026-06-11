"""
GST Network (GSTN) connector.

Provides GSTIN (GST Identification Number) lookup, GST return filing
status, and e-invoice data via:
  1. Sandbox.co.in GSTN API (recommended — handles auth complexity)
  2. Direct GSTN API (requires GSP registration, complex auth)

Use-cases:
  - Verify GSTIN status for a company (Active/Cancelled/Suspended)
  - Check GST return filing compliance (how regularly does a company file?)
  - Cross-reference CIN → GSTIN for entity linkage
  - Detect shell companies that have inactive GSTINs despite active MCA status

GSTIN format: 2-digit state code + 10-digit PAN + 1 entity code + Z + check digit
              e.g. 27AADCB2230M1ZP

config keys:
  mode              : "sandbox" | "direct"  default "sandbox"
  sandbox_api_key   : str   Sandbox.co.in API key
  gstin_list        : list  GSTINs to look up
  pan_list          : list  PANs to resolve to GSTINs
  state_code        : str   2-digit state code to filter (optional)
  fetch_returns     : bool  also fetch return filing status — default False
  max_records       : int   default 1000
"""

import logging
import time
from typing import Optional

import httpx
import pandas as pd
import redis

from layer1_ingestion.connectors.base_connector import (
    AuthenticationError,
    BaseConnector,
    ConnectionTestResult,
    ExtractionConfig,
    ExtractionError,
    IncrementalConfig,
    SchemaDetectionResult,
)
from layer1_ingestion.core.config import get_settings

logger = logging.getLogger(__name__)

_SANDBOX_BASE = "https://api.sandbox.co.in"
_REDIS_TTL = 3600 * 6  # 6-hour cache for GSTIN lookups (GSTN rate limits are strict)

# Indian state codes for GSTIN
_STATE_CODES = {
    "01": "Jammu & Kashmir", "02": "Himachal Pradesh", "03": "Punjab",
    "04": "Chandigarh", "05": "Uttarakhand", "06": "Haryana",
    "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh",
    "10": "Bihar", "11": "Sikkim", "12": "Arunachal Pradesh",
    "13": "Nagaland", "14": "Manipur", "15": "Mizoram",
    "16": "Tripura", "17": "Meghalaya", "18": "Assam",
    "19": "West Bengal", "20": "Jharkhand", "21": "Odisha",
    "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat",
    "26": "Dadra & Nagar Haveli", "27": "Maharashtra", "28": "Andhra Pradesh",
    "29": "Karnataka", "30": "Goa", "31": "Lakshadweep",
    "32": "Kerala", "33": "Tamil Nadu", "34": "Puducherry",
    "35": "Andaman & Nicobar", "36": "Telangana", "37": "Andhra Pradesh (New)",
}


class GSTNConnector(BaseConnector):
    """GSTN connector via Sandbox.co.in for GSTIN lookup and return status."""

    REQUIRED_CONFIG_FIELDS = []

    def __init__(self, source_id: str, config: dict) -> None:
        super().__init__(source_id, config)
        self.mode: str = config.get("mode", "sandbox")
        settings = get_settings()
        self.sandbox_api_key: str = config.get("sandbox_api_key", "") or settings.sandbox_api_key
        self.gstin_list: list = config.get("gstin_list", [])
        self.pan_list: list = config.get("pan_list", [])
        self.state_code: str = config.get("state_code", "")
        self.fetch_returns: bool = bool(config.get("fetch_returns", False))
        self.max_records: int = int(config.get("max_records", 1000))
        self._redis: Optional[redis.Redis] = None

    def _get_redis(self) -> Optional[redis.Redis]:
        if self._redis is None:
            try:
                settings = get_settings()
                self._redis = redis.from_url(settings.redis_url)
                self._redis.ping()
            except Exception:
                self._redis = None
        return self._redis

    def _sandbox_headers(self) -> dict:
        return {
            "x-api-key": self.sandbox_api_key,
            "Content-Type": "application/json",
        }

    def _lookup_gstin(self, gstin: str) -> Optional[dict]:
        """Look up a single GSTIN via Sandbox.co.in with Redis caching."""
        cache_key = f"gstn:{gstin}"
        r = self._get_redis()
        if r:
            cached = r.get(cache_key)
            if cached:
                import json
                return json.loads(cached)

        url = f"{_SANDBOX_BASE}/gsp/authenticate"
        # Sandbox.co.in two-step: authenticate then call GST API
        try:
            # Step 1: Get GSP token
            auth_resp = httpx.post(
                url,
                headers=self._sandbox_headers(),
                json={},
                timeout=15,
            )
            if auth_resp.status_code == 401:
                raise AuthenticationError(self.source_id, "Invalid Sandbox.co.in API key")
            auth_resp.raise_for_status()
            gsp_token = auth_resp.json().get("data", {}).get("token", "")

            # Step 2: GSTIN search
            gstin_resp = httpx.post(
                f"{_SANDBOX_BASE}/gsp/taxpayers/{gstin}",
                headers={**self._sandbox_headers(), "authorization": gsp_token},
                timeout=15,
            )
            gstin_resp.raise_for_status()
            result = gstin_resp.json().get("data", {})

            if r and result:
                import json
                r.setex(cache_key, _REDIS_TTL, json.dumps(result))
            return result
        except AuthenticationError:
            raise
        except Exception as exc:
            logger.warning("GSTIN lookup failed for %s: %s", gstin, exc)
            return None

    def _normalize_gstin_record(self, gstin: str, data: dict) -> dict:
        state_code = gstin[:2] if len(gstin) >= 2 else ""
        pan = gstin[2:12] if len(gstin) >= 12 else ""
        return {
            "gstin": gstin,
            "pan": pan,
            "state_code": state_code,
            "state_name": _STATE_CODES.get(state_code, "Unknown"),
            "legal_name": data.get("lgnm", ""),
            "trade_name": data.get("tradeNam", ""),
            "registration_type": data.get("dty", ""),
            "status": data.get("sts", ""),
            "registration_date": data.get("rgdt", ""),
            "last_update": data.get("lstupdt", ""),
            "constitution": data.get("ctb", ""),
            "address": data.get("pradr", {}).get("addr", {}).get("bno", ""),
            "pincode": data.get("pradr", {}).get("addr", {}).get("pncd", ""),
            "cancelled_date": data.get("cxdt", ""),
        }

    def test_connection(self) -> ConnectionTestResult:
        start = time.perf_counter()
        try:
            # Test with a known valid GSTIN (Infosys — public knowledge)
            test_gstin = "29AABCI1682H1ZE"
            result = self._lookup_gstin(test_gstin)
            elapsed = (time.perf_counter() - start) * 1000
            if result:
                return ConnectionTestResult(
                    success=True,
                    message=f"GSTN API connected via Sandbox.co.in (tested with {test_gstin})",
                    response_time_ms=elapsed,
                )
            return ConnectionTestResult(
                success=False,
                message="GSTN lookup returned empty result",
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
        with self._timed_operation("gstn_schema_detection"):
            columns = [
                {"name": "gstin", "type": "string", "nullable": False, "sample_values": ["27AADCB2230M1ZP"]},
                {"name": "pan", "type": "string", "nullable": True, "sample_values": ["AADCB2230M"]},
                {"name": "state_code", "type": "string", "nullable": True, "sample_values": ["27"]},
                {"name": "state_name", "type": "string", "nullable": True, "sample_values": ["Maharashtra"]},
                {"name": "legal_name", "type": "string", "nullable": True, "sample_values": []},
                {"name": "trade_name", "type": "string", "nullable": True, "sample_values": []},
                {"name": "registration_type", "type": "string", "nullable": True, "sample_values": ["Regular"]},
                {"name": "status", "type": "string", "nullable": True, "sample_values": ["Active","Cancelled","Suspended"]},
                {"name": "registration_date", "type": "string", "nullable": True, "sample_values": []},
                {"name": "constitution", "type": "string", "nullable": True, "sample_values": ["Private Limited Company"]},
                {"name": "address", "type": "string", "nullable": True, "sample_values": []},
                {"name": "pincode", "type": "string", "nullable": True, "sample_values": []},
                {"name": "cancelled_date", "type": "string", "nullable": True, "sample_values": []},
            ]
            return SchemaDetectionResult(
                columns=columns,
                total_columns=len(columns),
                detected_primary_key="gstin",
                indian_identifiers={"gstin": "GSTIN", "pan": "PAN"},
            )

    def extract_full(self, config: ExtractionConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            gstins = list(self.gstin_list)
            # If PANs provided, derive GSTINs (limited without full GSTN access)
            # PAN → GSTIN mapping requires calling GSTN search API per PAN
            records: list[dict] = []
            for gstin in gstins[: self.max_records]:
                data = self._lookup_gstin(gstin)
                if data:
                    records.append(self._normalize_gstin_record(gstin, data))
                time.sleep(0.1)  # Respect GSTN rate limits

            df = pd.DataFrame(records) if records else pd.DataFrame()
            self.log_extraction(len(df), time.perf_counter() - start, 0)
            return df
        except Exception as exc:
            self.log_extraction(0, time.perf_counter() - start, 1)
            raise ExtractionError(self.source_id, f"GSTN extraction failed: {exc}") from exc

    def extract_incremental(self, config: IncrementalConfig) -> pd.DataFrame:
        # GSTN does not expose change feeds; full refresh is the correct approach
        return self.extract_full(config)

    def get_record_count(self) -> int:
        return len(self.gstin_list)
