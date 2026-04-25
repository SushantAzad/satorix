import uuid
from datetime import datetime, timezone
from typing import Any, Optional
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = logging.getLogger(__name__)

EVENT_TYPES = {
    "OBJECT_CREATED",
    "PROPERTY_CHANGED",
    "LINK_CREATED",
    "LINK_DELETED",
    "STATUS_CHANGED",
    "OBJECT_DELETED",
    "RISK_SCORE_UPDATED",
}


class OntologyEvent:
    def __init__(
        self,
        object_type: str,
        object_id: str,
        event_type: str,
        actor_id: str,
        source: str,
        property_name: Optional[str] = None,
        old_value: Any = None,
        new_value: Any = None,
        metadata: Optional[dict] = None,
    ) -> None:
        self.id = str(uuid.uuid4())
        self.occurred_at = datetime.now(timezone.utc)
        self.object_type = object_type
        self.object_id = object_id
        self.event_type = event_type
        self.property_name = property_name
        self.old_value = old_value
        self.new_value = new_value
        self.actor_id = actor_id
        self.source = source
        self.metadata = metadata or {}


class EventStore:
    async def emit(self, db: AsyncSession, event: OntologyEvent) -> None:
        """Append-only write. Never fails silently."""
        try:
            await db.execute(
                text("""
                    INSERT INTO ontology_events
                        (id, occurred_at, object_type, object_id, event_type,
                         property_name, old_value, new_value, actor_id, source, metadata)
                    VALUES
                        (:id, :occurred_at, :object_type, :object_id, :event_type,
                         :property_name, :old_value::jsonb, :new_value::jsonb,
                         :actor_id, :source, :metadata::jsonb)
                """),
                {
                    "id": event.id,
                    "occurred_at": event.occurred_at,
                    "object_type": event.object_type,
                    "object_id": event.object_id,
                    "event_type": event.event_type,
                    "property_name": event.property_name,
                    "old_value": _json_safe(event.old_value),
                    "new_value": _json_safe(event.new_value),
                    "actor_id": event.actor_id,
                    "source": event.source,
                    "metadata": _json_safe(event.metadata),
                },
            )
            logger.debug("Event emitted: %s %s/%s", event.event_type, event.object_type, event.object_id)
        except Exception as e:
            logger.error("CRITICAL: Event store write failed for %s/%s: %s", event.object_type, event.object_id, e)
            raise

    async def get_events(
        self,
        db: AsyncSession,
        object_type: str,
        object_id: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        event_type: Optional[str] = None,
    ) -> list[dict]:
        conditions = ["object_type = :object_type", "object_id = :object_id"]
        params: dict[str, Any] = {"object_type": object_type, "object_id": object_id}

        if start:
            conditions.append("occurred_at >= :start")
            params["start"] = start
        if end:
            conditions.append("occurred_at <= :end")
            params["end"] = end
        if event_type:
            conditions.append("event_type = :event_type")
            params["event_type"] = event_type

        where_clause = " AND ".join(conditions)
        result = await db.execute(
            text(f"""
                SELECT id, occurred_at, object_type, object_id, event_type,
                       property_name, old_value, new_value, actor_id, source, metadata
                FROM ontology_events
                WHERE {where_clause}
                ORDER BY occurred_at ASC
            """),
            params,
        )
        rows = result.mappings().all()
        return [dict(row) for row in rows]

    async def get_property_history(
        self,
        db: AsyncSession,
        object_type: str,
        object_id: str,
        property_name: str,
    ) -> list[dict]:
        result = await db.execute(
            text("""
                SELECT occurred_at, old_value, new_value, actor_id, source
                FROM ontology_events
                WHERE object_type = :object_type
                  AND object_id = :object_id
                  AND property_name = :property_name
                  AND event_type = 'PROPERTY_CHANGED'
                ORDER BY occurred_at ASC
            """),
            {"object_type": object_type, "object_id": object_id, "property_name": property_name},
        )
        return [dict(row) for row in result.mappings().all()]


def _json_safe(value: Any) -> Optional[str]:
    if value is None:
        return None
    import json
    return json.dumps(value, default=str)


event_store = EventStore()
