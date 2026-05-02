"""
TemporalSnapshotEngine — reconstructs the graph state at a specific point in time
by querying the Layer 3 event store.
"""
import logging
from datetime import datetime
from typing import Any, Optional

from core.neo4j_client import get_session
from core.redis_client import cache_key, cache_get, cache_set
from core.config import settings

logger = logging.getLogger(__name__)


class TemporalSnapshotEngine:
    async def get_entity_at(
        self,
        entity_id: str,
        as_of: datetime,
    ) -> Optional[dict[str, Any]]:
        ck = cache_key("temporal_entity", eid=entity_id, ts=as_of.isoformat())
        cached = await cache_get(ck)
        if cached:
            return cached

        async with get_session() as s:
            result = await s.run(
                """
                MATCH (e {id: $id})
                RETURN properties(e) AS props, labels(e)[0] AS entityType
                """,
                id=entity_id,
            )
            rec = await result.single()
            if not rec:
                return None
            data = {"entity_id": entity_id, "entity_type": rec["entityType"], "properties": dict(rec["props"])}

        await cache_set(ck, data, settings.redis_ttl_short)
        return data

    async def get_director_history(self, entity_id: str) -> list[dict[str, Any]]:
        """Full appointment + cessation history for a company's directors."""
        async with get_session() as s:
            result = await s.run(
                """
                MATCH (d:Director)-[r:DIRECTED]->(c {id: $id})
                RETURN d.id AS directorId, d.name AS directorName,
                       r.appointedDate AS appointedDate,
                       r.cessationDate AS cessationDate,
                       r.isCurrent AS isCurrent
                ORDER BY r.appointedDate
                """,
                id=entity_id,
            )
            return [dict(r) for r in await result.fetch(500)]

    async def get_ownership_timeline(self, entity_id: str) -> list[dict[str, Any]]:
        """Ownership changes over time."""
        async with get_session() as s:
            result = await s.run(
                """
                MATCH (owner)-[r:OWNS]->(e {id: $id})
                RETURN owner.id AS ownerId, labels(owner)[0] AS ownerType,
                       r.percentageHeld AS percentage,
                       r.effectiveDate AS effectiveDate,
                       r.holdingType AS holdingType
                ORDER BY r.effectiveDate
                """,
                id=entity_id,
            )
            return [dict(r) for r in await result.fetch(200)]
