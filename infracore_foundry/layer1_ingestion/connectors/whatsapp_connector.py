"""
WhatsApp Business Cloud API connector (Meta Graph API v18+).

Two ingestion modes:
  1. webhook  — real-time: registers a webhook endpoint; messages arrive
                via POST to Layer 1's /webhooks endpoint and are queued.
  2. pull     — polling: reads sent/received message logs from the
                Business Management API (limited history; mainly for audit).

Indian SME context: WhatsApp is widely used to share daily reports, vendor
confirmations, GST invoices, and operational summaries between teams.
This connector extracts message text + media attachments for enrichment.

Auth: Permanent access token (recommended for server-to-server) or
      OAuth2 system user token from Meta Business Manager.

config keys:
  access_token          : str   Meta permanent access token
  phone_number_id       : str   WhatsApp Business phone number ID
  business_account_id   : str   WhatsApp Business Account (WABA) ID
  verify_token          : str   webhook verification token
  mode                  : "webhook" | "pull"  (default: webhook)
  download_media        : bool  download media files (images, docs) — default False
  max_messages          : int   default 200
"""

import logging
import time
from datetime import datetime, timezone
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

_GRAPH_BASE = "https://graph.facebook.com/v18.0"


class WhatsAppConnector(BaseConnector):
    """WhatsApp Business Cloud API connector via Meta Graph API."""

    REQUIRED_CONFIG_FIELDS = ["access_token", "phone_number_id"]

    def __init__(self, source_id: str, config: dict) -> None:
        super().__init__(source_id, config)
        self.access_token: str = config.get("access_token", "")
        self.phone_number_id: str = config.get("phone_number_id", "")
        self.business_account_id: str = config.get("business_account_id", "")
        self.verify_token: str = config.get("verify_token", "")
        self.mode: str = config.get("mode", "webhook")
        self.download_media: bool = bool(config.get("download_media", False))
        self.max_messages: int = int(config.get("max_messages", 200))

    @property
    def _auth_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
        }

    def _api_get(self, path: str, params: Optional[dict] = None) -> dict:
        url = f"{_GRAPH_BASE}/{path}"
        resp = httpx.get(url, headers=self._auth_headers, params=params or {}, timeout=30)
        if resp.status_code == 401:
            raise AuthenticationError(
                self.source_id, "Invalid or expired Meta access token"
            )
        resp.raise_for_status()
        return resp.json()

    def _get_media_url(self, media_id: str) -> Optional[str]:
        """Resolve media ID to a temporary download URL."""
        try:
            data = self._api_get(media_id)
            return data.get("url")
        except Exception:
            return None

    def test_connection(self) -> ConnectionTestResult:
        start = time.perf_counter()
        try:
            data = self._api_get(f"{self.phone_number_id}", params={"fields": "display_phone_number,verified_name"})
            elapsed = (time.perf_counter() - start) * 1000
            phone = data.get("display_phone_number", "unknown")
            name = data.get("verified_name", "unknown")
            return ConnectionTestResult(
                success=True,
                message=f"WhatsApp Business: {name} ({phone})",
                response_time_ms=elapsed,
            )
        except AuthenticationError:
            raise
        except Exception as exc:
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=False,
                message=str(exc),
                response_time_ms=elapsed,
                error=type(exc).__name__,
            )

    def extract_schema(self) -> SchemaDetectionResult:
        with self._timed_operation("whatsapp_schema_detection"):
            columns = [
                {"name": "message_id", "type": "string", "nullable": False, "sample_values": []},
                {"name": "from_number", "type": "string", "nullable": False, "sample_values": []},
                {"name": "to_number", "type": "string", "nullable": True, "sample_values": []},
                {"name": "timestamp", "type": "datetime64[ns]", "nullable": False, "sample_values": []},
                {"name": "message_type", "type": "string", "nullable": False, "sample_values": ["text", "document", "image"]},
                {"name": "text_body", "type": "string", "nullable": True, "sample_values": []},
                {"name": "media_id", "type": "string", "nullable": True, "sample_values": []},
                {"name": "media_mime_type", "type": "string", "nullable": True, "sample_values": []},
                {"name": "media_filename", "type": "string", "nullable": True, "sample_values": []},
                {"name": "status", "type": "string", "nullable": True, "sample_values": ["sent", "delivered", "read"]},
                {"name": "direction", "type": "string", "nullable": False, "sample_values": ["inbound", "outbound"]},
            ]
            return SchemaDetectionResult(
                columns=columns,
                total_columns=len(columns),
                detected_primary_key="message_id",
                timestamp_columns=["timestamp"],
            )

    def extract_full(self, config: ExtractionConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            records = self._fetch_conversation_logs()
            df = pd.DataFrame(records) if records else pd.DataFrame()
            self.log_extraction(len(df), time.perf_counter() - start, 0)
            return df
        except Exception as exc:
            self.log_extraction(0, time.perf_counter() - start, 1)
            raise ExtractionError(self.source_id, f"WhatsApp extraction failed: {exc}") from exc

    def extract_incremental(self, config: IncrementalConfig) -> pd.DataFrame:
        """WhatsApp API does not support server-side date filtering for message logs;
        fetch all and filter client-side by timestamp watermark."""
        df = self.extract_full(config)
        if df.empty or "timestamp" not in df.columns:
            return df
        if config.last_extracted_at:
            cutoff = pd.Timestamp(config.last_extracted_at, tz="UTC")
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
            df = df[df["timestamp"] > cutoff]
        return df

    def _fetch_conversation_logs(self) -> list[dict]:
        """
        Fetch message objects from the WhatsApp Business Account messages endpoint.
        The Conversations API provides access to outbound messages sent from the
        phone number; inbound messages arrive via webhook and are stored in the
        event queue (see webhook_connector.py for real-time flow).
        """
        if not self.business_account_id:
            self.logger.warning(
                "business_account_id not set; cannot pull message history. "
                "Use webhook mode for real-time ingestion."
            )
            return []

        records: list[dict] = []
        params: dict = {
            "fields": "id,from,to,timestamp,type,text,document,image,status",
            "limit": min(self.max_messages, 50),
        }
        path = f"{self.phone_number_id}/messages"
        page_count = 0
        while path and len(records) < self.max_messages and page_count < 20:
            try:
                data = self._api_get(path, params=params)
            except Exception as exc:
                self.logger.warning("WhatsApp message fetch failed: %s", exc)
                break

            for msg in data.get("data", []):
                records.append(self._normalize_message(msg))

            paging = data.get("paging", {})
            next_url = paging.get("next")
            path = next_url.replace(_GRAPH_BASE + "/", "") if next_url else ""
            params = {}
            page_count += 1

        return records

    def _normalize_message(self, msg: dict) -> dict:
        msg_type = msg.get("type", "text")
        text_body = ""
        media_id = ""
        media_mime = ""
        media_filename = ""

        if msg_type == "text":
            text_body = msg.get("text", {}).get("body", "")
        elif msg_type == "document":
            doc = msg.get("document", {})
            media_id = doc.get("id", "")
            media_mime = doc.get("mime_type", "")
            media_filename = doc.get("filename", "")
        elif msg_type == "image":
            img = msg.get("image", {})
            media_id = img.get("id", "")
            media_mime = img.get("mime_type", "image/jpeg")
            text_body = img.get("caption", "")

        # Determine direction: if `to` matches our phone_number_id it's inbound
        direction = "inbound" if msg.get("to") == self.phone_number_id else "outbound"

        ts_unix = msg.get("timestamp", 0)
        try:
            ts = datetime.fromtimestamp(int(ts_unix), tz=timezone.utc).isoformat()
        except (ValueError, TypeError, OSError):
            ts = str(ts_unix)

        return {
            "message_id": msg.get("id", ""),
            "from_number": msg.get("from", ""),
            "to_number": msg.get("to", ""),
            "timestamp": ts,
            "message_type": msg_type,
            "text_body": text_body,
            "media_id": media_id,
            "media_mime_type": media_mime,
            "media_filename": media_filename,
            "status": msg.get("status", ""),
            "direction": direction,
        }

    def get_record_count(self) -> int:
        # WhatsApp API doesn't expose a count endpoint; return 0 as safe default
        return 0
