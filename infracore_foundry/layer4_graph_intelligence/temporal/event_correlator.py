"""
EventCorrelator — correlates entity-level events with market/regulatory events.
Used to build the timeline view in the Intelligence Dashboard.
"""
import logging
from datetime import datetime
from typing import Any

from core.neo4j_client import get_session

logger = logging.getLogger(__name__)


class EventCorrelator:
    async def get_entity_timeline(
        self,
        entity_id: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []

        director_events = await self._director_events(entity_id, start, end)
        events.extend(director_events)

        ownership_events = await self._ownership_events(entity_id, start, end)
        events.extend(ownership_events)

        regulatory_events = await self._regulatory_events(entity_id, start, end)
        events.extend(regulatory_events)

        events.sort(key=lambda e: e.get("date") or "")
        return events

    async def _director_events(self, entity_id: str, start, end) -> list[dict]:
        async with get_session() as s:
            result = await s.run(
                """
                MATCH (d:Director)-[r:DIRECTED]->(c {id: $id})
                RETURN d.id AS relatedId, d.name AS name,
                       'DIRECTOR_APPOINTED' AS eventType, r.appointedDate AS date
                WHERE r.appointedDate IS NOT NULL
                UNION
                MATCH (d:Director)-[r:DIRECTED]->(c {id: $id})
                WHERE r.cessationDate IS NOT NULL
                RETURN d.id AS relatedId, d.name AS name,
                       'DIRECTOR_RESIGNED' AS eventType, r.cessationDate AS date
                """,
                id=entity_id,
            )
            events = [dict(r) for r in await result.fetch(500)]
        if start:
            events = [e for e in events if e.get("date") and e["date"] >= start.isoformat()]
        if end:
            events = [e for e in events if e.get("date") and e["date"] <= end.isoformat()]
        return events

    async def _ownership_events(self, entity_id: str, start, end) -> list[dict]:
        async with get_session() as s:
            result = await s.run(
                """
                MATCH (owner)-[r:OWNS]->(e {id: $id})
                WHERE r.effectiveDate IS NOT NULL
                RETURN owner.id AS relatedId, owner.name AS name,
                       'OWNERSHIP_CHANGE' AS eventType, r.effectiveDate AS date
                """,
                id=entity_id,
            )
            return [dict(r) for r in await result.fetch(200)]

    async def _regulatory_events(self, entity_id: str, start, end) -> list[dict]:
        async with get_session() as s:
            result = await s.run(
                """
                MATCH (c {id: $id})-[:HAS_REGULATORY_ACTION]->(ra:RegulatoryAction)
                RETURN ra.id AS relatedId, ra.description AS name,
                       'REGULATORY_ACTION' AS eventType, ra.actionDate AS date
                """,
                id=entity_id,
            )
            return [dict(r) for r in await result.fetch(200)]
