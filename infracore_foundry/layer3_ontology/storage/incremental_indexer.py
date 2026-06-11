import hashlib
import json
from typing import Any
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = logging.getLogger(__name__)


class IncrementalIndexer:
    """Detect changed objects using SHA-256 hashing, update only those."""

    def compute_hash(self, data: dict[str, Any]) -> str:
        serialized = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode()).hexdigest()

    async def get_stored_hash(
        self,
        db: AsyncSession,
        object_type: str,
        primary_key: str,
    ) -> str | None:
        result = await db.execute(
            text("""
                SELECT data_hash FROM ontology_objects
                WHERE object_type = :ot AND primary_key = :pk AND is_deleted = FALSE
            """),
            {"ot": object_type, "pk": primary_key},
        )
        row = result.first()
        return row[0] if row else None

    def has_changed(self, new_hash: str, stored_hash: str | None) -> bool:
        return stored_hash is None or stored_hash != new_hash

    async def filter_changed(
        self,
        db: AsyncSession,
        object_type: str,
        records: list[dict[str, Any]],
        primary_key_field: str,
    ) -> tuple[list[dict], dict]:
        """Return only changed records and stats."""
        changed = []
        stats = {"processed": len(records), "changed": 0, "unchanged": 0}

        for record in records:
            pk = str(record.get(primary_key_field, ""))
            new_hash = self.compute_hash(record)
            stored_hash = await self.get_stored_hash(db, object_type, pk)
            if self.has_changed(new_hash, stored_hash):
                changed.append(record)
                stats["changed"] += 1
            else:
                stats["unchanged"] += 1

        return changed, stats


incremental_indexer = IncrementalIndexer()
