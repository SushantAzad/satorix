"""
BetweennessCentrality — computes betweenness via GDS.
Runs on the Director↔Company bipartite subgraph for memory efficiency.
Falls back to sampled betweenness when node count > threshold.
"""
import logging
from datetime import datetime, timezone

from core.neo4j_client import get_session
from core.database import get_pool
from core.config import settings

logger = logging.getLogger(__name__)


class BetweennessCentralityComputer:
    async def run_and_persist(self, batch_run_id: str) -> dict:
        logger.info("Computing betweenness centrality")
        node_count = await self._get_node_count()
        sampled = node_count > settings.gds_betweenness_sample_threshold
        if sampled:
            logger.warning("Graph has %d nodes — using sampled betweenness (threshold=%d)",
                           node_count, settings.gds_betweenness_sample_threshold)

        rows = await self._run_gds_betweenness(sampled)
        if not rows:
            return {"algorithm": "betweenness", "entities_computed": 0}

        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO l4_influence_scores (entity_id, entity_type, betweenness, computed_at, batch_run_id)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (entity_id, entity_type) DO UPDATE SET
                    betweenness = EXCLUDED.betweenness,
                    computed_at = EXCLUDED.computed_at,
                    batch_run_id = EXCLUDED.batch_run_id
                """,
                [
                    (r["entityId"], r["entityType"], float(r["score"]),
                     datetime.now(timezone.utc), batch_run_id)
                    for r in rows
                    if r["entityId"]
                ],
            )

        logger.info("Betweenness: %d entities, sampled=%s", len(rows), sampled)
        return {"algorithm": "betweenness", "entities_computed": len(rows), "sampled": sampled}

    async def _get_node_count(self) -> int:
        async with get_session() as s:
            result = await s.run("MATCH (n) RETURN count(n) AS cnt")
            rec = await result.single()
            return int(rec["cnt"]) if rec else 0

    async def _run_gds_betweenness(self, sampled: bool) -> list[dict]:
        config_str = "{samplingSize: 100, samplingSeed: 42}" if sampled else "{}"
        async with get_session() as s:
            result = await s.run(
                f"""
                CALL gds.betweenness.stream('{settings.gds_projection_name}', {config_str})
                YIELD nodeId, score
                RETURN gds.util.asNode(nodeId).id AS entityId,
                       labels(gds.util.asNode(nodeId))[0] AS entityType,
                       score
                ORDER BY score DESC
                LIMIT 1000
                """
            )
            return [dict(r) for r in await result.fetch(1000)]
