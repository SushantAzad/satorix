"""
RotationTracker — identifies directors that cycle through companies rapidly.
Pattern: director A → company 1 (resign) → company 2 (join) within 30 days.
This pattern is common in MCA21 data for structured SPV operations.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from core.neo4j_client import get_session

logger = logging.getLogger(__name__)

ROTATION_WINDOW_DAYS = 30
MIN_ROTATION_COUNT = 2


class RotationTracker:
    async def find_rotating_directors(self, limit: int = 100) -> list[dict[str, Any]]:
        """Directors who resigned from one company and joined another within 30 days."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=365)
        async with get_session() as s:
            result = await s.run(
                """
                MATCH (d:Director)-[r1:DIRECTED]->(c1:Company)
                WHERE r1.cessationDate IS NOT NULL AND r1.cessationDate >= $cutoff
                MATCH (d)-[r2:DIRECTED]->(c2:Company)
                WHERE c1 <> c2 AND r2.appointedDate IS NOT NULL
                  AND abs(duration.inDays(date(r1.cessationDate), date(r2.appointedDate)).days) <= $window
                WITH d, count(DISTINCT c2) AS rotationCount, collect(DISTINCT c2.id) AS rotatedTo
                WHERE rotationCount >= $minCount
                RETURN d.id AS directorId, d.name AS name,
                       rotationCount, rotatedTo
                ORDER BY rotationCount DESC
                LIMIT $limit
                """,
                cutoff=cutoff.date().isoformat(),
                window=ROTATION_WINDOW_DAYS,
                minCount=MIN_ROTATION_COUNT,
                limit=limit,
            )
            return [dict(r) for r in await result.fetch(limit)]

    async def get_director_timeline(self, director_id: str) -> list[dict[str, Any]]:
        """Full chronological appointment history for a director."""
        async with get_session() as s:
            result = await s.run(
                """
                MATCH (d:Director {id: $id})-[r:DIRECTED]->(c:Company)
                RETURN c.id AS companyId, c.name AS companyName,
                       c.cin AS cin,
                       r.appointedDate AS appointedDate,
                       r.cessationDate AS cessationDate,
                       r.isCurrent AS isCurrent
                ORDER BY r.appointedDate
                """,
                id=director_id,
            )
            return [dict(r) for r in await result.fetch(200)]
