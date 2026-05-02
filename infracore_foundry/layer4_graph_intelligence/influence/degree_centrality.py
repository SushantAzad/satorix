"""Degree centrality — simple connection count normalized by graph size."""
import logging
from datetime import datetime, timezone

from core.neo4j_client import get_session
from core.database import get_pool

logger = logging.getLogger(__name__)


class DegreeCentralityComputer:
    async def run_and_persist(self, batch_run_id: str) -> dict:
        logger.info("Computing degree centrality")
        async with get_session() as s:
            result = await s.run(
                """
                MATCH (n)
                RETURN n.id AS entityId, labels(n)[0] AS entityType, count{(n)-[]-()} AS degree
                ORDER BY degree DESC
                LIMIT 10000
                """
            )
            rows = [dict(r) for r in await result.fetch(10000)]

        if not rows:
            return {"algorithm": "degree", "entities_computed": 0}

        max_degree = max(r["degree"] for r in rows) or 1
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO l4_influence_scores (entity_id, entity_type, degree_centrality, computed_at, batch_run_id)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (entity_id, entity_type) DO UPDATE SET
                    degree_centrality = EXCLUDED.degree_centrality,
                    computed_at = EXCLUDED.computed_at
                """,
                [
                    (r["entityId"], r["entityType"], r["degree"] / max_degree,
                     datetime.now(timezone.utc), batch_run_id)
                    for r in rows
                    if r["entityId"]
                ],
            )
        return {"algorithm": "degree", "entities_computed": len(rows)}
