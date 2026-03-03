"""
Incremental sync strategies: timestamp, sequence, full-refresh-with-dedup, and CDC.
"""

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Generator, Optional

import pandas as pd
from sqlalchemy import text

logger = logging.getLogger(__name__)


@dataclass
class ChangeEvent:
    operation: str  # INSERT, UPDATE, DELETE
    table: str
    before: Optional[dict]
    after: Optional[dict]
    lsn: Optional[str]
    timestamp: datetime


class TimestampIncremental:
    """Timestamp-based incremental extraction."""

    @staticmethod
    def get_query_filter(table: str, timestamp_col: str, last_sync_at: datetime) -> str:
        return f'SELECT * FROM "{table}" WHERE "{timestamp_col}" > :last_sync ORDER BY "{timestamp_col}" ASC'

    @staticmethod
    def get_params(last_sync_at: datetime) -> dict:
        return {"last_sync": last_sync_at}

    @staticmethod
    def extract_new_watermark(df: pd.DataFrame, timestamp_col: str) -> Optional[datetime]:
        if df.empty or timestamp_col not in df.columns:
            return None
        max_val = df[timestamp_col].max()
        if pd.isna(max_val):
            return None
        if isinstance(max_val, str):
            return datetime.fromisoformat(max_val)
        return max_val.to_pydatetime() if hasattr(max_val, "to_pydatetime") else max_val


class SequenceIncremental:
    """Sequence/ID-based incremental extraction."""

    @staticmethod
    def get_query_filter(table: str, id_col: str, last_id: str) -> str:
        return f'SELECT * FROM "{table}" WHERE "{id_col}" > :last_id ORDER BY "{id_col}" ASC'

    @staticmethod
    def get_params(last_id: str) -> dict:
        return {"last_id": last_id}

    @staticmethod
    def extract_new_watermark(df: pd.DataFrame, id_col: str) -> Optional[str]:
        if df.empty or id_col not in df.columns:
            return None
        return str(df[id_col].max())


class FullRefreshWithDedup:
    """Full table extract, then diff against previous to find changes."""

    @staticmethod
    def compute_row_hash(row: pd.Series) -> str:
        content = "|".join(str(v) for v in row.values)
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def extract_full_and_diff(
        new_df: pd.DataFrame,
        existing_df: pd.DataFrame,
        primary_key: str,
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        Compare new data against existing data.
        Returns: (new_rows, updated_rows, deleted_rows)
        """
        if existing_df.empty:
            return new_df, pd.DataFrame(), pd.DataFrame()
        if new_df.empty:
            return pd.DataFrame(), pd.DataFrame(), existing_df

        new_df = new_df.copy()
        existing_df = existing_df.copy()
        new_df["_row_hash"] = new_df.apply(FullRefreshWithDedup.compute_row_hash, axis=1)
        existing_df["_row_hash"] = existing_df.apply(FullRefreshWithDedup.compute_row_hash, axis=1)

        new_keys = set(new_df[primary_key].astype(str))
        existing_keys = set(existing_df[primary_key].astype(str))

        # New rows
        added_keys = new_keys - existing_keys
        new_rows = new_df[new_df[primary_key].astype(str).isin(added_keys)].drop(columns=["_row_hash"])

        # Deleted rows
        deleted_keys = existing_keys - new_keys
        deleted_rows = existing_df[existing_df[primary_key].astype(str).isin(deleted_keys)].drop(columns=["_row_hash"])

        # Updated rows
        common_keys = new_keys & existing_keys
        updated_rows_list = []
        for key in common_keys:
            new_hash = new_df.loc[new_df[primary_key].astype(str) == key, "_row_hash"].iloc[0]
            exist_hash = existing_df.loc[existing_df[primary_key].astype(str) == key, "_row_hash"].iloc[0]
            if new_hash != exist_hash:
                row = new_df[new_df[primary_key].astype(str) == key].drop(columns=["_row_hash"])
                updated_rows_list.append(row)

        updated_rows = pd.concat(updated_rows_list, ignore_index=True) if updated_rows_list else pd.DataFrame()

        logger.info(
            "Full refresh diff: %d new, %d updated, %d deleted",
            len(new_rows), len(updated_rows), len(deleted_rows),
        )
        return new_rows, updated_rows, deleted_rows


class CDCConnector:
    """Change Data Capture via PostgreSQL WAL replication slots."""

    def __init__(self, connection_string: str, slot_name: str = "infracore_cdc") -> None:
        self.connection_string = connection_string
        self.slot_name = slot_name
        self._connection = None

    def connect_to_wal(self) -> None:
        """Create a logical replication slot for CDC."""
        import psycopg2
        from psycopg2.extras import LogicalReplicationConnection

        self._connection = psycopg2.connect(
            self.connection_string,
            connection_factory=LogicalReplicationConnection,
        )
        cursor = self._connection.cursor()
        try:
            cursor.create_replication_slot(self.slot_name, output_plugin="wal2json")
            logger.info("Created replication slot: %s", self.slot_name)
        except psycopg2.errors.DuplicateObject:
            logger.info("Replication slot %s already exists", self.slot_name)

    def stream_changes(self) -> Generator[ChangeEvent, None, None]:
        """Stream change events from the WAL."""
        import psycopg2
        import json

        if not self._connection:
            self.connect_to_wal()

        cursor = self._connection.cursor()
        cursor.start_replication(slot_name=self.slot_name, decode=True)

        for msg in cursor:
            try:
                payload = json.loads(msg.payload)
                for change in payload.get("change", []):
                    yield ChangeEvent(
                        operation=change.get("kind", "").upper(),
                        table=change.get("table", ""),
                        before=dict(zip(change.get("columnnames", []), change.get("oldvalues", []))) if "oldvalues" in change else None,
                        after=dict(zip(change.get("columnnames", []), change.get("columnvalues", []))) if "columnvalues" in change else None,
                        lsn=str(msg.data_start),
                        timestamp=datetime.now(timezone.utc),
                    )
                cursor.send_feedback(flush_lsn=msg.data_start)
            except Exception as e:
                logger.error("Error processing CDC message: %s", str(e))

    def close(self) -> None:
        if self._connection:
            self._connection.close()
            self._connection = None
