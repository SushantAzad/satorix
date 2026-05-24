"""
Slack connector via Slack Web API.

Extracts channel messages, user profiles, and file shares from Slack workspaces.
Used by startups and tech-forward enterprises to capture operational data
shared informally over Slack — vendor updates, risk flags, compliance discussions.

Auth: Bot token (xoxb-...) with channels:history, users:read, files:read scopes.

config keys:
  bot_token         : str   Slack bot OAuth token (xoxb-...)
  channel_ids       : list  specific channel IDs to extract (default: all public)
  include_threads   : bool  include thread replies — default False
  include_files     : bool  download shared file metadata — default True
  oldest            : str   Unix timestamp or ISO date for incremental
  message_limit     : int   max messages per channel — default 1000
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

_SLACK_API = "https://slack.com/api"


class SlackConnector(BaseConnector):
    """Slack Web API connector for channel message extraction."""

    REQUIRED_CONFIG_FIELDS = ["bot_token"]

    def __init__(self, source_id: str, config: dict) -> None:
        super().__init__(source_id, config)
        self.bot_token: str = config.get("bot_token", "")
        self.channel_ids: list = config.get("channel_ids", [])
        self.include_threads: bool = bool(config.get("include_threads", False))
        self.include_files: bool = bool(config.get("include_files", True))
        self.message_limit: int = int(config.get("message_limit", 1000))

    @property
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.bot_token}", "Accept": "application/json"}

    def _api(self, method: str, params: Optional[dict] = None) -> dict:
        resp = httpx.get(f"{_SLACK_API}/{method}", headers=self._headers, params=params or {}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            err = data.get("error", "unknown")
            if err in ("invalid_auth", "not_authed", "account_inactive"):
                raise AuthenticationError(self.source_id, f"Slack auth error: {err}")
            raise RuntimeError(f"Slack API error: {err}")
        return data

    def _get_channels(self) -> list[dict]:
        if self.channel_ids:
            channels = []
            for cid in self.channel_ids:
                try:
                    info = self._api("conversations.info", {"channel": cid})
                    channels.append(info.get("channel", {"id": cid, "name": cid}))
                except Exception:
                    channels.append({"id": cid, "name": cid})
            return channels
        # List all public channels the bot has access to
        channels: list[dict] = []
        cursor: Optional[str] = None
        while True:
            params: dict = {"limit": 200, "exclude_archived": True, "types": "public_channel"}
            if cursor:
                params["cursor"] = cursor
            data = self._api("conversations.list", params)
            channels.extend(data.get("channels", []))
            cursor = data.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
        return channels

    def _get_messages(self, channel_id: str, oldest_ts: Optional[str] = None) -> list[dict]:
        messages: list[dict] = []
        cursor: Optional[str] = None
        while len(messages) < self.message_limit:
            params: dict = {"channel": channel_id, "limit": 200}
            if oldest_ts:
                params["oldest"] = oldest_ts
            if cursor:
                params["cursor"] = cursor
            try:
                data = self._api("conversations.history", params)
            except RuntimeError as exc:
                # Channel might not be accessible
                logger.warning("Cannot read channel %s: %s", channel_id, exc)
                break
            for msg in data.get("messages", []):
                if msg.get("subtype") in ("channel_join", "channel_leave"):
                    continue
                messages.append(self._normalize_message(msg, channel_id))
            cursor = data.get("response_metadata", {}).get("next_cursor")
            if not cursor or not data.get("has_more"):
                break
        return messages

    def _normalize_message(self, msg: dict, channel_id: str) -> dict:
        ts_unix = float(msg.get("ts", 0))
        try:
            ts_iso = datetime.fromtimestamp(ts_unix, tz=timezone.utc).isoformat()
        except (ValueError, OSError):
            ts_iso = str(ts_unix)
        files = msg.get("files", [])
        return {
            "message_ts": msg.get("ts", ""),
            "channel_id": channel_id,
            "user_id": msg.get("user", ""),
            "text": msg.get("text", ""),
            "timestamp": ts_iso,
            "thread_ts": msg.get("thread_ts", ""),
            "reply_count": msg.get("reply_count", 0),
            "reactions": len(msg.get("reactions", [])),
            "file_count": len(files),
            "file_names": ",".join(f.get("name", "") for f in files),
            "message_type": msg.get("type", "message"),
        }

    def test_connection(self) -> ConnectionTestResult:
        start = time.perf_counter()
        try:
            data = self._api("auth.test")
            elapsed = (time.perf_counter() - start) * 1000
            return ConnectionTestResult(
                success=True,
                message=f"Slack: {data.get('team')} / {data.get('user')}",
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
        with self._timed_operation("slack_schema_detection"):
            columns = [
                {"name": "message_ts", "type": "string", "nullable": False, "sample_values": []},
                {"name": "channel_id", "type": "string", "nullable": False, "sample_values": []},
                {"name": "user_id", "type": "string", "nullable": True, "sample_values": []},
                {"name": "text", "type": "string", "nullable": True, "sample_values": []},
                {"name": "timestamp", "type": "datetime64[ns]", "nullable": False, "sample_values": []},
                {"name": "thread_ts", "type": "string", "nullable": True, "sample_values": []},
                {"name": "reply_count", "type": "int64", "nullable": False, "sample_values": [0]},
                {"name": "reactions", "type": "int64", "nullable": False, "sample_values": [0]},
                {"name": "file_count", "type": "int64", "nullable": False, "sample_values": [0]},
                {"name": "file_names", "type": "string", "nullable": True, "sample_values": []},
                {"name": "message_type", "type": "string", "nullable": True, "sample_values": ["message"]},
            ]
            return SchemaDetectionResult(
                columns=columns,
                total_columns=len(columns),
                detected_primary_key="message_ts",
                timestamp_columns=["timestamp"],
            )

    def extract_full(self, config: ExtractionConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            channels = self._get_channels()
            all_messages: list[dict] = []
            for ch in channels:
                msgs = self._get_messages(ch["id"])
                all_messages.extend(msgs)
            df = pd.DataFrame(all_messages) if all_messages else pd.DataFrame()
            self.log_extraction(len(df), time.perf_counter() - start, 0)
            return df
        except Exception as exc:
            self.log_extraction(0, time.perf_counter() - start, 1)
            raise ExtractionError(self.source_id, f"Slack extraction failed: {exc}") from exc

    def extract_incremental(self, config: IncrementalConfig) -> pd.DataFrame:
        start = time.perf_counter()
        try:
            oldest_ts: Optional[str] = None
            if config.last_extracted_at:
                oldest_ts = str(config.last_extracted_at.timestamp())
            channels = self._get_channels()
            all_messages: list[dict] = []
            for ch in channels:
                msgs = self._get_messages(ch["id"], oldest_ts=oldest_ts)
                all_messages.extend(msgs)
            df = pd.DataFrame(all_messages) if all_messages else pd.DataFrame()
            self.log_extraction(len(df), time.perf_counter() - start, 0)
            return df
        except Exception as exc:
            self.log_extraction(0, time.perf_counter() - start, 1)
            raise ExtractionError(self.source_id, f"Slack incremental failed: {exc}") from exc

    def get_record_count(self) -> int:
        return 0  # Slack doesn't expose a total message count
