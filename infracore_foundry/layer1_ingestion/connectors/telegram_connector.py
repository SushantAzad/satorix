"""
Telegram connector via Telegram Bot API.

Telegram is heavily used by Indian business communities, stock market groups,
and compliance/legal networks for sharing intelligence, regulatory updates,
and market information. This connector extracts channel/group messages.

Modes:
  bot    — uses a Bot token to read messages from channels/groups where
           the bot is an admin (can read recent history via getUpdates or
           channels via getChatHistory equivalent via forwardFrom workaround)
  tdlib  — uses TDLib session for full history (requires phone auth, not server-suitable)

For production server use, "bot" mode is practical. A bot added to a channel
as admin can read all messages via updates or channel post notifications.

config keys:
  bot_token         : str   Telegram bot token from @BotFather
  chat_ids          : list  specific chat/channel IDs (e.g. ["@channelname", "-1001234"])
  offset            : int   update offset for incremental (persisted in sync state)
  max_updates       : int   default 100 per poll
  allowed_updates   : list  default ["channel_post","message"]
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


class TelegramConnector(BaseConnector):
    """Telegram Bot API connector for channel/group message extraction."""

    REQUIRED_CONFIG_FIELDS = ["bot_token"]

    def __init__(self, source_id: str, config: dict) -> None:
        super().__init__(source_id, config)
        self.bot_token: str = config.get("bot_token", "")
        self.chat_ids: list = config.get("chat_ids", [])
        self.offset: int = int(config.get("offset", 0))
        self.max_updates: int = int(config.get("max_updates", 100))
        self.allowed_updates: list = config.get("allowed_updates", ["channel_post", "message"])

    @property
    def _base(self) -> str:
        return f"https://api.telegram.org/bot{self.bot_token}"

    def _call(self, method: str, params: Optional[dict] = None) -> dict:
        resp = httpx.get(
            f"{self._base}/{method}",
            params=params or {},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            err = data.get("description", "unknown")
            if "unauthorized" in err.lower() or "bot token" in err.lower():
                raise AuthenticationError(self.source_id, f"Telegram auth error: {err}")
            raise RuntimeError(f"Telegram API error: {err}")
        return data

    def _normalize_message(self, msg: dict, update_type: str) -> dict:
        ts_unix = msg.get("date", 0)
        try:
            ts_iso = datetime.fromtimestamp(ts_unix, tz=timezone.utc).isoformat()
        except (ValueError, OSError):
            ts_iso = str(ts_unix)

        chat = msg.get("chat", {})
        sender = msg.get("from", {})
        text = msg.get("text", "") or msg.get("caption", "")
        doc = msg.get("document", {})
        photo = msg.get("photo", [])

        return {
            "message_id": msg.get("message_id", ""),
            "update_type": update_type,
            "chat_id": str(chat.get("id", "")),
            "chat_title": chat.get("title", chat.get("username", "")),
            "chat_type": chat.get("type", ""),
            "sender_id": str(sender.get("id", "")),
            "sender_username": sender.get("username", ""),
            "text": text,
            "timestamp": ts_iso,
            "has_document": bool(doc),
            "document_filename": doc.get("file_name", ""),
            "has_photo": bool(photo),
            "forward_from_chat": str(msg.get("forward_from_chat", {}).get("id", "")),
            "entities_count": len(msg.get("entities", [])),
        }

    def _get_updates(self, offset: int = 0) -> list[dict]:
        records: list[dict] = []
        params: dict = {
            "offset": offset,
            "limit": self.max_updates,
            "allowed_updates": self.allowed_updates,
            "timeout": 0,
        }
        data = self._call("getUpdates", params)
        for update in data.get("result", []):
            update_id = update.get("update_id", 0)
            for utype in self.allowed_updates:
                msg = update.get(utype)
                if msg:
                    # Filter by chat_ids if specified
                    chat_id = str(msg.get("chat", {}).get("id", ""))
                    if self.chat_ids and not any(
                        str(cid).lstrip("@") in chat_id or chat_id == str(cid)
                        for cid in self.chat_ids
                    ):
                        continue
                    record = self._normalize_message(msg, utype)
                    record["update_id"] = update_id
                    records.append(record)
        return records

    def test_connection(self) -> ConnectionTestResult:
        start = time.perf_counter()
        try:
            data = self._call("getMe")
            bot = data.get("result", {})
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=True,
                message=f"Telegram Bot: @{bot.get('username', '?')} ({bot.get('first_name', '')})",
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
        with self._timed_operation("telegram_schema_detection"):
            columns = [
                {"name": "update_id", "type": "int64", "nullable": False, "sample_values": []},
                {"name": "message_id", "type": "int64", "nullable": False, "sample_values": []},
                {"name": "update_type", "type": "string", "nullable": False, "sample_values": ["channel_post"]},
                {"name": "chat_id", "type": "string", "nullable": False, "sample_values": []},
                {"name": "chat_title", "type": "string", "nullable": True, "sample_values": []},
                {"name": "chat_type", "type": "string", "nullable": True, "sample_values": ["channel","group"]},
                {"name": "sender_id", "type": "string", "nullable": True, "sample_values": []},
                {"name": "sender_username", "type": "string", "nullable": True, "sample_values": []},
                {"name": "text", "type": "string", "nullable": True, "sample_values": []},
                {"name": "timestamp", "type": "datetime64[ns]", "nullable": False, "sample_values": []},
                {"name": "has_document", "type": "bool", "nullable": False, "sample_values": [False]},
                {"name": "document_filename", "type": "string", "nullable": True, "sample_values": []},
                {"name": "has_photo", "type": "bool", "nullable": False, "sample_values": [False]},
            ]
            return SchemaDetectionResult(
                columns=columns,
                total_columns=len(columns),
                detected_primary_key="update_id",
                timestamp_columns=["timestamp"],
            )

    def extract_full(self, config: ExtractionConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            records = self._get_updates(offset=self.offset)
            df = pd.DataFrame(records) if records else pd.DataFrame()
            self.log_extraction(len(df), time.perf_counter() - start, 0)
            return df
        except Exception as exc:
            self.log_extraction(0, time.perf_counter() - start, 1)
            raise ExtractionError(self.source_id, f"Telegram extraction failed: {exc}") from exc

    def extract_incremental(self, config: IncrementalConfig) -> pd.DataFrame:
        """Telegram uses update_id as watermark — pass last_extracted_id as offset."""
        offset = int(config.last_extracted_id) + 1 if config.last_extracted_id else self.offset
        start = time.perf_counter()
        try:
            records = self._get_updates(offset=offset)
            df = pd.DataFrame(records) if records else pd.DataFrame()
            self.log_extraction(len(df), time.perf_counter() - start, 0)
            return df
        except Exception as exc:
            self.log_extraction(0, time.perf_counter() - start, 1)
            raise ExtractionError(self.source_id, f"Telegram incremental failed: {exc}") from exc

    def get_record_count(self) -> int:
        return 0  # Telegram doesn't expose historical message counts via Bot API
