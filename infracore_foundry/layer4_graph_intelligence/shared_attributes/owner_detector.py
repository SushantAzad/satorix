"""
SharedOwnerDetector — identifies entities sharing a common beneficial owner (UBO).
"""
import logging
from typing import Any

from core.neo4j_client import get_session

logger = logging.getLogger(__name__)


class SharedOwnerDetector:
    async def detect(self, entity_id: str) -> list[dict[str, Any]]:
        async with get_session() as s:
            result = await s.run(
                """
                MATCH (owner)-[:OWNS]->(c {id: $id})
                MATCH (owner)-[:OWNS]->(other)
                WHERE other.id <> $id
                RETURN other.id AS entityId, labels(other)[0] AS entityType,
                       other.name AS entityName,
                       owner.id AS ownerId, owner.name AS ownerName,
                       labels(owner)[0] AS ownerType
                LIMIT 50
                """,
                id=entity_id,
            )
            return [dict(r) for r in await result.fetch(50)]

    async def detect_circular_ownership(self, limit: int = 100) -> list[dict[str, Any]]:
        """Detect A owns B and B owns A (or longer cycles)."""
        async with get_session() as s:
            result = await s.run(
                """
                MATCH path = (a:Company)-[:OWNS*2..5]->(a)
                WITH path, [n IN nodes(path) | n.id] AS cycle
                RETURN cycle, length(path) AS cycleLength
                ORDER BY cycleLength ASC
                LIMIT $limit
                """,
                limit=limit,
            )
            return [dict(r) for r in await result.fetch(limit)]
