"""
Zoho connector — Books, CRM, Inventory, and Payroll via Zoho REST API v3.

Zoho has the largest penetration in Indian mid-market (5M+ businesses).
This connector extracts financial records, customer/vendor data, and
HR data for corporate intelligence enrichment.

Modules supported:
  - zoho_books    : Invoices, bills, contacts, accounts, chart of accounts
  - zoho_crm      : Contacts, Accounts, Deals, Leads, Activities
  - zoho_inventory: Items, purchase orders, vendors
  - zoho_payroll  : Employees (count, designation, department)

Auth: OAuth2 with refresh token (Zoho Self Client or Server-based app).
Zoho tokens expire in 1 hour; refresh_token is long-lived.

config keys:
  module            : "zoho_books" | "zoho_crm" | "zoho_inventory" | "zoho_payroll"
  client_id         : str   Zoho app client ID
  client_secret     : str   Zoho app client secret
  refresh_token     : str   long-lived refresh token
  organization_id   : str   Zoho Books/Inventory organization ID
  region            : str   "in" (India) | "com" | "eu" | "au" — default "in"
  resource          : str   specific resource e.g. "invoices", "contacts", "deals"
  filter_date_field : str   date field for incremental (Books: "last_modified_time")
  page_size         : int   default 200 (Zoho max per page)
"""

import logging
import time
from datetime import datetime
from typing import Optional

import httpx
import pandas as pd

from layer1_ingestion.connectors.base_connector import (
    AuthenticationError,
    BaseConnector,
    ConnectionTestResult,
    ExtractionConfig,
    ExtractionError,
    IncrementalConfig,
    SchemaDetectionResult,
)

logger = logging.getLogger(__name__)

_ZOHO_ACCOUNTS = {
    "in": "https://accounts.zoho.in",
    "com": "https://accounts.zoho.com",
    "eu": "https://accounts.zoho.eu",
    "au": "https://accounts.zoho.com.au",
}
_ZOHO_BOOKS_BASE = {
    "in": "https://www.zohoapis.in/books/v3",
    "com": "https://www.zohoapis.com/books/v3",
    "eu": "https://www.zohoapis.eu/books/v3",
    "au": "https://www.zohoapis.com.au/books/v3",
}
_ZOHO_CRM_BASE = {
    "in": "https://www.zohoapis.in/crm/v3",
    "com": "https://www.zohoapis.com/crm/v3",
    "eu": "https://www.zohoapis.eu/crm/v3",
    "au": "https://www.zohoapis.com.au/crm/v3",
}

# Maps module → (base_url_dict, resource_key, id_field)
_MODULE_MAP = {
    "zoho_books":     (_ZOHO_BOOKS_BASE, "invoices",  "invoice_id"),
    "zoho_crm":       (_ZOHO_CRM_BASE,   "Contacts",  "id"),
    "zoho_inventory": (_ZOHO_BOOKS_BASE, "items",     "item_id"),
    "zoho_payroll":   (_ZOHO_BOOKS_BASE, "employees", "employee_id"),
}


class ZohoConnector(BaseConnector):
    """Zoho Books / CRM / Inventory connector with OAuth2 refresh."""

    REQUIRED_CONFIG_FIELDS = ["client_id", "client_secret", "refresh_token", "module"]

    def __init__(self, source_id: str, config: dict) -> None:
        super().__init__(source_id, config)
        self.module: str = config.get("module", "zoho_books")
        self.client_id_z: str = config.get("client_id", "")
        self.client_secret: str = config.get("client_secret", "")
        self.refresh_token: str = config.get("refresh_token", "")
        self.organization_id: str = config.get("organization_id", "")
        self.region: str = config.get("region", "in")
        self.resource: str = config.get("resource", "")
        self.filter_date_field: str = config.get("filter_date_field", "last_modified_time")
        self.page_size: int = int(config.get("page_size", 200))
        self._access_token: Optional[str] = None
        self._token_expires: float = 0.0

    def _refresh_access_token(self) -> str:
        url = f"{_ZOHO_ACCOUNTS.get(self.region, _ZOHO_ACCOUNTS['in'])}/oauth/v2/token"
        resp = httpx.post(
            url,
            params={
                "refresh_token": self.refresh_token,
                "client_id": self.client_id_z,
                "client_secret": self.client_secret,
                "grant_type": "refresh_token",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise AuthenticationError(
                self.source_id, f"Zoho token refresh failed: {data['error']}"
            )
        self._access_token = data["access_token"]
        self._token_expires = time.time() + data.get("expires_in", 3600)
        return self._access_token

    def _get_token(self) -> str:
        if self._access_token and time.time() < self._token_expires - 60:
            return self._access_token
        return self._refresh_access_token()

    @property
    def _headers(self) -> dict:
        return {"Authorization": f"Zoho-oauthtoken {self._get_token()}", "Accept": "application/json"}

    def _base_url(self) -> str:
        base_map, _, _ = _MODULE_MAP.get(self.module, (_ZOHO_BOOKS_BASE, "", ""))
        return base_map.get(self.region, list(base_map.values())[0])

    def _default_resource(self) -> str:
        _, resource, _ = _MODULE_MAP.get(self.module, (_ZOHO_BOOKS_BASE, "invoices", "id"))
        return self.resource or resource

    def _default_id_field(self) -> str:
        _, _, id_field = _MODULE_MAP.get(self.module, (_ZOHO_BOOKS_BASE, "", "id"))
        return id_field

    def _paginate(self, resource: str, extra_params: Optional[dict] = None) -> list[dict]:
        base = self._base_url()
        records: list[dict] = []
        page = 1
        while True:
            params: dict = {"page": page, "per_page": self.page_size}
            if self.organization_id and self.module != "zoho_crm":
                params["organization_id"] = self.organization_id
            if extra_params:
                params.update(extra_params)
            url = f"{base}/{resource}"
            resp = httpx.get(url, headers=self._headers, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            # Zoho wraps response in a key matching the resource name
            resource_key = resource.lower()
            items = data.get(resource_key, data.get("data", []))
            if not items:
                break
            records.extend(items if isinstance(items, list) else [items])
            page_ctx = data.get("page_context", {})
            if not page_ctx.get("has_more_page", False):
                break
            page += 1
        return records

    def test_connection(self) -> ConnectionTestResult:
        start = time.perf_counter()
        try:
            token = self._get_token()
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=bool(token),
                message=f"Zoho {self.module} token acquired (region: {self.region})",
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
        with self._timed_operation("zoho_schema_detection"):
            resource = self._default_resource()
            records = self._paginate(resource)
            if not records:
                return SchemaDetectionResult(columns=[], total_columns=0)
            sample = records[0]
            columns = [
                {"name": k, "type": type(v).__name__, "nullable": True, "sample_values": [v]}
                for k, v in sample.items()
            ]
            return SchemaDetectionResult(
                columns=columns,
                total_columns=len(columns),
                detected_primary_key=self._default_id_field(),
                timestamp_columns=[k for k in sample if "date" in k.lower() or "time" in k.lower()],
            )

    def extract_full(self, config: ExtractionConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            resource = self._default_resource()
            records = self._paginate(resource)
            df = pd.DataFrame(records) if records else pd.DataFrame()
            self.log_extraction(len(df), time.perf_counter() - start, 0)
            return df
        except Exception as exc:
            self.log_extraction(0, time.perf_counter() - start, 1)
            raise ExtractionError(
                self.source_id, f"Zoho extraction failed: {exc}"
            ) from exc

    def extract_incremental(self, config: IncrementalConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            resource = self._default_resource()
            extra: dict = {}
            if config.last_extracted_at:
                date_str = config.last_extracted_at.strftime("%Y-%m-%d")
                extra[self.filter_date_field] = date_str
            records = self._paginate(resource, extra_params=extra)
            df = pd.DataFrame(records) if records else pd.DataFrame()
            self.log_extraction(len(df), time.perf_counter() - start, 0)
            return df
        except Exception as exc:
            self.log_extraction(0, time.perf_counter() - start, 1)
            raise ExtractionError(
                self.source_id, f"Zoho incremental failed: {exc}"
            ) from exc

    def get_record_count(self) -> int:
        try:
            resource = self._default_resource()
            base = self._base_url()
            params: dict = {"page": 1, "per_page": 1}
            if self.organization_id and self.module != "zoho_crm":
                params["organization_id"] = self.organization_id
            resp = httpx.get(
                f"{base}/{resource}", headers=self._headers, params=params, timeout=30
            )
            resp.raise_for_status()
            data = resp.json()
            page_ctx = data.get("page_context", {})
            return page_ctx.get("total", 0)
        except Exception:
            return 0
