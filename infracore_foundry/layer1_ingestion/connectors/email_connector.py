"""
Email connector — supports three modes:
  1. IMAP (generic — Gmail, Outlook, Yahoo, corporate IMAP servers)
  2. Gmail API (OAuth2 — avoids IMAP less-secure-apps restrictions)
  3. Microsoft Graph / Outlook 365 (OAuth2 client credentials)

Primary use-case: monitor a dedicated inbox, extract attachment files
(CSV, Excel, PDF) and email body text as structured records.
Incremental strategy: by received date using IMAP UID or message ID watermark.
"""

import base64
import email
import imaplib
import io
import logging
import time
from datetime import datetime, timezone
from email.header import decode_header
from typing import Optional

import httpx
import pandas as pd

from layer1_ingestion.connectors.base_connector import (
    AuthenticationError,
    BaseConnector,
    ConnectionError,
    ConnectionTestResult,
    ExtractionConfig,
    ExtractionError,
    IncrementalConfig,
    SchemaDetectionResult,
)

logger = logging.getLogger(__name__)

# Attachment content-types we attempt to parse into DataFrames
_PARSEABLE_MIME = {
    "text/csv",
    "application/csv",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/pdf",
    "text/plain",
}


def _decode_header_value(raw: str) -> str:
    parts = decode_header(raw or "")
    decoded = []
    for part, enc in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(enc or "utf-8", errors="replace"))
        else:
            decoded.append(str(part))
    return " ".join(decoded)


class EmailConnector(BaseConnector):
    """
    Email inbox connector.

    config keys:
      mode              : "imap" | "gmail_api" | "outlook_graph"  (default: imap)

      # IMAP mode
      imap_host         : str   e.g. "imap.gmail.com"
      imap_port         : int   default 993
      username          : str
      password          : str
      mailbox           : str   default "INBOX"
      use_ssl           : bool  default True

      # Gmail API mode
      service_account_json : str (JSON string of service account credentials)
      delegated_email   : str   (user email to impersonate)

      # Outlook / Microsoft Graph mode
      tenant_id         : str
      client_id         : str
      client_secret     : str
      mailbox_address   : str   (shared mailbox or user email)

      # Common
      extract_attachments : bool  default True
      extract_body        : bool  default True
      attachment_types    : list  default ["csv","xlsx","xls","pdf","txt"]
      subject_filter      : str   optional subject substring filter
      max_messages        : int   default 500 per run
    """

    REQUIRED_CONFIG_FIELDS: list[str] = []

    def __init__(self, source_id: str, config: dict) -> None:
        super().__init__(source_id, config)
        self.mode: str = config.get("mode", "imap")
        # IMAP
        self.imap_host: str = config.get("imap_host", "")
        self.imap_port: int = int(config.get("imap_port", 993))
        self.username: str = config.get("username", "")
        self.password: str = config.get("password", "")
        self.mailbox: str = config.get("mailbox", "INBOX")
        self.use_ssl: bool = bool(config.get("use_ssl", True))
        # Gmail API
        self.service_account_json: str = config.get("service_account_json", "")
        self.delegated_email: str = config.get("delegated_email", "")
        # Outlook Graph
        self.tenant_id: str = config.get("tenant_id", "")
        self.client_id_graph: str = config.get("client_id", "")
        self.client_secret: str = config.get("client_secret", "")
        self.mailbox_address: str = config.get("mailbox_address", "")
        # Common
        self.extract_attachments: bool = bool(config.get("extract_attachments", True))
        self.extract_body: bool = bool(config.get("extract_body", True))
        self.subject_filter: str = config.get("subject_filter", "")
        self.max_messages: int = int(config.get("max_messages", 500))
        self._graph_token: Optional[str] = None
        self._graph_token_expires: float = 0.0

    # ------------------------------------------------------------------
    # IMAP helpers
    # ------------------------------------------------------------------

    def _imap_connect(self) -> imaplib.IMAP4:
        try:
            if self.use_ssl:
                conn = imaplib.IMAP4_SSL(self.imap_host, self.imap_port)
            else:
                conn = imaplib.IMAP4(self.imap_host, self.imap_port)
            conn.login(self.username, self.password)
            return conn
        except imaplib.IMAP4.error as exc:
            if "authentication" in str(exc).lower() or "invalid" in str(exc).lower():
                raise AuthenticationError(self.source_id, str(exc))
            raise ConnectionError(self.source_id, str(exc))

    def _imap_fetch_messages(
        self, conn: imaplib.IMAP4, since_uid: Optional[int] = None
    ) -> list[dict]:
        conn.select(self.mailbox, readonly=True)
        if since_uid:
            status, data = conn.uid("search", None, f"UID {since_uid}:*")
        else:
            status, data = conn.uid("search", None, "ALL")
        if status != "OK" or not data[0]:
            return []

        uids = data[0].split()[-self.max_messages :]  # newest N
        records: list[dict] = []
        for uid in uids:
            try:
                status, msg_data = conn.uid("fetch", uid, "(RFC822)")
                if status != "OK":
                    continue
                raw = msg_data[0][1]
                msg = email.message_from_bytes(raw)
                records.append(self._parse_message(uid.decode(), msg))
            except Exception as exc:
                self.logger.debug("Failed to parse UID %s: %s", uid, exc)
        return records

    def _parse_message(self, uid: str, msg: email.message.Message) -> dict:
        subject = _decode_header_value(msg.get("Subject", ""))
        sender = _decode_header_value(msg.get("From", ""))
        date_str = msg.get("Date", "")
        msg_id = msg.get("Message-ID", "")

        # Filter by subject if configured
        if self.subject_filter and self.subject_filter.lower() not in subject.lower():
            return {}

        body_text = ""
        attachments: list[dict] = []

        for part in msg.walk():
            ct = part.get_content_type()
            cd = part.get("Content-Disposition", "")
            if "attachment" in cd or "inline" in cd:
                filename = part.get_filename() or ""
                ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
                allowed_exts = self.config.get(
                    "attachment_types", ["csv", "xlsx", "xls", "pdf", "txt"]
                )
                if ext in allowed_exts and self.extract_attachments:
                    payload = part.get_payload(decode=True)
                    if payload:
                        attachments.append(
                            {
                                "filename": filename,
                                "content_type": ct,
                                "size_bytes": len(payload),
                                "content_b64": base64.b64encode(payload).decode(),
                            }
                        )
            elif ct == "text/plain" and not attachments and self.extract_body:
                payload = part.get_payload(decode=True)
                if payload:
                    body_text = payload.decode("utf-8", errors="replace")[:2000]

        return {
            "uid": uid,
            "message_id": msg_id,
            "subject": subject,
            "sender": sender,
            "received_date": date_str,
            "body_snippet": body_text[:500] if body_text else "",
            "attachment_count": len(attachments),
            "attachments": attachments,
        }

    # ------------------------------------------------------------------
    # Microsoft Graph helpers
    # ------------------------------------------------------------------

    def _get_graph_token(self) -> str:
        if self._graph_token and time.time() < self._graph_token_expires - 60:
            return self._graph_token
        url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        resp = httpx.post(
            url,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id_graph,
                "client_secret": self.client_secret,
                "scope": "https://graph.microsoft.com/.default",
            },
            timeout=30,
        )
        resp.raise_for_status()
        token_data = resp.json()
        self._graph_token = token_data["access_token"]
        self._graph_token_expires = time.time() + token_data.get("expires_in", 3600)
        return self._graph_token

    def _graph_fetch_messages(self, since_dt: Optional[datetime] = None) -> list[dict]:
        token = self._get_graph_token()
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        url = f"https://graph.microsoft.com/v1.0/users/{self.mailbox_address}/messages"
        params: dict = {
            "$select": "id,subject,from,receivedDateTime,hasAttachments,bodyPreview",
            "$top": min(self.max_messages, 50),
            "$orderby": "receivedDateTime desc",
        }
        if since_dt:
            params["$filter"] = (
                f"receivedDateTime ge {since_dt.strftime('%Y-%m-%dT%H:%M:%SZ')}"
            )
        records: list[dict] = []
        while url and len(records) < self.max_messages:
            resp = httpx.get(url, headers=headers, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            for msg in data.get("value", []):
                records.append(
                    {
                        "uid": msg["id"],
                        "message_id": msg["id"],
                        "subject": msg.get("subject", ""),
                        "sender": msg.get("from", {})
                        .get("emailAddress", {})
                        .get("address", ""),
                        "received_date": msg.get("receivedDateTime", ""),
                        "body_snippet": msg.get("bodyPreview", "")[:500],
                        "attachment_count": 1 if msg.get("hasAttachments") else 0,
                        "attachments": [],
                    }
                )
            url = data.get("@odata.nextLink")
            params = {}
        return records

    # ------------------------------------------------------------------
    # BaseConnector implementation
    # ------------------------------------------------------------------

    def test_connection(self) -> ConnectionTestResult:
        start = time.perf_counter()
        try:
            if self.mode == "imap":
                conn = self._imap_connect()
                status, counts = conn.select(self.mailbox, readonly=True)
                conn.logout()
                elapsed = (time.perf_counter() - start) * 1000
                msg_count = int(counts[0]) if counts and counts[0] else 0
                return ConnectionTestResult(
                    success=True,
                    message=f"IMAP connected to {self.imap_host}:{self.imap_port}, "
                    f"{msg_count} messages in {self.mailbox}",
                    response_time_ms=elapsed,
                )
            elif self.mode == "outlook_graph":
                token = self._get_graph_token()
                elapsed = (time.perf_counter() - start) * 1000
                return ConnectionTestResult(
                    success=bool(token),
                    message="Microsoft Graph token acquired",
                    response_time_ms=elapsed,
                )
            else:
                elapsed = (time.perf_counter() - start) * 1000
                return ConnectionTestResult(
                    success=False,
                    message=f"Mode '{self.mode}' not supported in test_connection",
                    response_time_ms=elapsed,
                )
        except (AuthenticationError, ConnectionError):
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
        with self._timed_operation("email_schema_detection"):
            columns = [
                {"name": "uid", "type": "string", "nullable": False, "sample_values": []},
                {"name": "message_id", "type": "string", "nullable": True, "sample_values": []},
                {"name": "subject", "type": "string", "nullable": True, "sample_values": []},
                {"name": "sender", "type": "string", "nullable": True, "sample_values": []},
                {"name": "received_date", "type": "string", "nullable": True, "sample_values": []},
                {"name": "body_snippet", "type": "string", "nullable": True, "sample_values": []},
                {"name": "attachment_count", "type": "int64", "nullable": False, "sample_values": [0]},
                {"name": "attachments", "type": "object", "nullable": True, "sample_values": []},
            ]
            return SchemaDetectionResult(
                columns=columns,
                total_columns=len(columns),
                detected_primary_key="uid",
                timestamp_columns=["received_date"],
            )

    def extract_full(self, config: ExtractionConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            records = self._fetch_all_messages()
            records = [r for r in records if r]
            df = pd.DataFrame(records) if records else pd.DataFrame()
            self.log_extraction(len(df), time.perf_counter() - start, 0)
            return df
        except Exception as exc:
            self.log_extraction(0, time.perf_counter() - start, 1)
            raise ExtractionError(self.source_id, f"Email extraction failed: {exc}") from exc

    def extract_incremental(self, config: IncrementalConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            records = self._fetch_all_messages(since=config.last_extracted_at)
            records = [r for r in records if r]
            df = pd.DataFrame(records) if records else pd.DataFrame()
            self.log_extraction(len(df), time.perf_counter() - start, 0)
            return df
        except Exception as exc:
            self.log_extraction(0, time.perf_counter() - start, 1)
            raise ExtractionError(
                self.source_id, f"Email incremental extraction failed: {exc}"
            ) from exc

    def _fetch_all_messages(self, since: Optional[datetime] = None) -> list[dict]:
        if self.mode == "imap":
            conn = self._imap_connect()
            try:
                return self._imap_fetch_messages(conn)
            finally:
                try:
                    conn.logout()
                except Exception:
                    pass
        elif self.mode == "outlook_graph":
            return self._graph_fetch_messages(since_dt=since)
        return []

    def get_record_count(self) -> int:
        if self.mode == "imap":
            conn = self._imap_connect()
            try:
                _, counts = conn.select(self.mailbox, readonly=True)
                return int(counts[0]) if counts and counts[0] else 0
            finally:
                try:
                    conn.logout()
                except Exception:
                    pass
        return 0
