"""
SharedDirectorDetector — identifies companies sharing one or more current directors.
"""
import logging
from typing import Any

from core.neo4j_client import get_session

logger = logging.getLogger(__name__)


class SharedDirectorDetector:
    async def detect(self, entity_id: str) -> list[dict[str, Any]]:
        """Companies sharing a director with entity_id."""
        async with get_session() as s:
            result = await s.run(
                """
                MATCH (c {id: $id})<-[:DIRECTED]-(d:Director)-[:DIRECTED]->(other)
                WHERE other.id <> $id AND other:Company
                RETURN other.id AS entityId, other.name AS entityName,
                       collect(d.id) AS sharedDirectors,
                       count(d) AS sharedCount
                ORDER BY sharedCount DESC
                LIMIT 50
                """,
                id=entity_id,
            )
            return [dict(r) for r in await result.fetch(50)]

    async def detect_bulk(self, min_shared: int = 2, limit: int = 10000) -> list[dict[str, Any]]:
        """All company pairs sharing ≥ min_shared directors."""
        async with get_session() as s:
            result = await s.run(
                """
                MATCH (c1:Company)<-[:DIRECTED]-(d:Director)-[:DIRECTED]->(c2:Company)
                WHERE id(c1) < id(c2)
                WITH c1, c2, collect(d.id) AS directors, count(d) AS cnt
                WHERE cnt >= $minShared
                RETURN c1.id AS entity1, c2.id AS entity2,
                       directors AS sharedDirectors, cnt AS sharedCount
                ORDER BY cnt DESC
                LIMIT $limit
                """,
                minShared=min_shared,
                limit=limit,
            )
            return [dict(r) for r in await result.fetch(limit)]
