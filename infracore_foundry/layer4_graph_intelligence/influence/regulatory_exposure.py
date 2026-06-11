"""
RegulatoryExposureComputer — scores each entity by regulatory action neighborhood.
Considers direct actions + first-order neighbor actions.
"""
import logging
from datetime import datetime, timezone

from core.neo4j_client import get_session
from core.database import get_pool

logger = logging.getLogger(__name__)


class RegulatoryExposureComputer:
    DIRECT_ACTION_WEIGHT = 20.0
    NEIGHBOR_ACTION_WEIGHT = 5.0
    MAX_SCORE = 100.0

    async def compute_and_persist(self, batch_run_id: str) -> dict:
        logger.info("Computing regulatory exposure scores")
        async with get_session() as s:
            result = await s.run(
                """
                MATCH (c:Company)
                OPTIONAL MATCH (c)-[:HAS_REGULATORY_ACTION]->(ra:RegulatoryAction)
                OPTIONAL MATCH (c)-[:DIRECTED|SHARES_ADDRESS_WITH|SHARES_DIRECTOR_WITH]-(neighbor)-[:HAS_REGULATORY_ACTION]->(nra:RegulatoryAction)
                RETURN c.id AS entityId,
                       count(DISTINCT ra) AS directActions,
                       count(DISTINCT nra) AS neighborActions
                """
            )
            rows = [dict(r) for r in await result.fetch(100_000)]

        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO l4_influence_scores (entity_id, entity_type, regulatory_exposure, computed_at, batch_run_id)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (entity_id, entity_type) DO UPDATE SET
                    regulatory_exposure = EXCLUDED.regulatory_exposure,
                    computed_at = EXCLUDED.computed_at
                """,
                [
                    (
                        r["entityId"],
                        "Company",
                        min(
                            r["directActions"] * self.DIRECT_ACTION_WEIGHT
                            + r["neighborActions"] * self.NEIGHBOR_ACTION_WEIGHT,
                            self.MAX_SCORE,
                        ),
                        datetime.now(timezone.utc),
                        batch_run_id,
                    )
                    for r in rows
                    if r["entityId"]
                ],
            )

        return {"algorithm": "regulatory_exposure", "entities_computed": len(rows)}
