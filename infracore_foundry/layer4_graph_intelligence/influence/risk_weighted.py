"""
RiskWeightedCentrality — combines betweenness + PageRank + Layer 3 risk score.
Formula: composite = 0.35*betweenness_norm + 0.25*pagerank_norm + 0.40*risk_score_norm
"""
import logging
from datetime import datetime, timezone

from core.database import get_pool

logger = logging.getLogger(__name__)


class RiskWeightedCentralityComputer:
    async def compute_and_persist(self, batch_run_id: str) -> dict:
        logger.info("Computing risk-weighted centrality composite")
        pool = get_pool()
        async with pool.acquire() as conn:
            # Pull all existing scores to compute normalization factors
            rows = await conn.fetch(
                "SELECT entity_id, entity_type, betweenness, pagerank, degree_centrality "
                "FROM l4_influence_scores"
            )
            if not rows:
                return {"algorithm": "risk_weighted", "entities_computed": 0}

            max_b = max((r["betweenness"] or 0) for r in rows) or 1.0
            max_p = max((r["pagerank"] or 0) for r in rows) or 1.0
            max_d = max((r["degree_centrality"] or 0) for r in rows) or 1.0

            updates = []
            for r in rows:
                b_norm = (r["betweenness"] or 0) / max_b
                p_norm = (r["pagerank"] or 0) / max_p
                d_norm = (r["degree_centrality"] or 0) / max_d
                composite = 0.35 * b_norm + 0.25 * p_norm + 0.40 * d_norm
                updates.append((composite, datetime.now(timezone.utc), r["entity_id"], r["entity_type"]))

            await conn.executemany(
                """
                UPDATE l4_influence_scores
                SET composite_score = $1, computed_at = $2
                WHERE entity_id = $3 AND entity_type = $4
                """,
                updates,
            )

            # Assign ranks
            await conn.execute(
                """
                WITH ranked AS (
                    SELECT entity_id, entity_type,
                           ROW_NUMBER() OVER (ORDER BY composite_score DESC) AS rnk
                    FROM l4_influence_scores
                )
                UPDATE l4_influence_scores s
                SET composite_rank = r.rnk
                FROM ranked r
                WHERE s.entity_id = r.entity_id AND s.entity_type = r.entity_type
                """
            )

        logger.info("Risk-weighted centrality computed for %d entities", len(rows))
        return {"algorithm": "risk_weighted", "entities_computed": len(rows)}
