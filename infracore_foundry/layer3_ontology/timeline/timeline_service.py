from datetime import datetime
from typing import Any, Optional
import json
import logging
from core.database import AsyncSessionLocal
from storage.event_store import event_store
from sqlalchemy import text

logger = logging.getLogger(__name__)


class TimelineService:
    async def get_object_at_time(
        self,
        object_type: str,
        object_id: str,
        as_of: datetime,
    ) -> dict[str, Any]:
        """Reconstruct object state at a specific point in time."""
        async with AsyncSessionLocal() as db:
            # Get creation event (OBJECT_CREATED has new_value as full object)
            created_result = await db.execute(
                text("""
                    SELECT new_value FROM ontology_events
                    WHERE object_type = :ot AND object_id = :oid
                      AND event_type = 'OBJECT_CREATED'
                      AND occurred_at <= :as_of
                    ORDER BY occurred_at ASC LIMIT 1
                """),
                {"ot": object_type, "oid": object_id, "as_of": as_of},
            )
            created_row = created_result.first()
            if not created_row:
                return {}

            state = created_row[0] if isinstance(created_row[0], dict) else json.loads(created_row[0] or "{}")

            # Apply all PROPERTY_CHANGED events up to as_of
            changes_result = await db.execute(
                text("""
                    SELECT property_name, new_value FROM ontology_events
                    WHERE object_type = :ot AND object_id = :oid
                      AND event_type IN ('PROPERTY_CHANGED', 'STATUS_CHANGED')
                      AND occurred_at <= :as_of
                    ORDER BY occurred_at ASC
                """),
                {"ot": object_type, "oid": object_id, "as_of": as_of},
            )
            for change_row in changes_result.fetchall():
                prop = change_row[0]
                val = change_row[1] if isinstance(change_row[1], dict) else json.loads(change_row[1] or "null")
                if prop:
                    state[prop] = val

        return state

    async def get_property_history(
        self,
        object_type: str,
        object_id: str,
        property_name: str,
    ) -> list[dict[str, Any]]:
        async with AsyncSessionLocal() as db:
            return await event_store.get_property_history(db, object_type, object_id, property_name)

    async def get_object_timeline(
        self,
        object_type: str,
        object_id: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> list[dict[str, Any]]:
        async with AsyncSessionLocal() as db:
            return await event_store.get_events(db, object_type, object_id, start, end)


timeline_service = TimelineService()
