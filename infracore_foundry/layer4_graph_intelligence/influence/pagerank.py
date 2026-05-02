"""PageRank — computes authority score across the full entity graph."""
import logging
from datetime import datetime, timezone

from core.gds_client import run_pagerank
from core.database import get_pool

logger = logging.getLogger(__name__)


class PageRankComputer:
    async def run_and_persist(self, batch_run_id: str) -> dict:
        logger.info("Computing PageRank")
        rows = await run_pagerank()
        if not rows:
            return {"algorithm": "pagerank", "entities_computed": 0}

        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO l4_influence_scores (entity_id, entity_type, pagerank, computed_at, batch_run_id)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (entity_id, entity_type) DO UPDATE SET
                    pagerank = EXCLUDED.pagerank,
                    computed_at = EXCLUDED.computed_at
                """,
                [
                    (r["entityId"], r["entityType"], float(r["score"]),
                     datetime.now(timezone.utc), batch_run_id)
                    for r in rows
                    if r["entityId"]
                ],
            )

        logger.info("PageRank: %d entities", len(rows))
        return {"algorithm": "pagerank", "entities_computed": len(rows)}
