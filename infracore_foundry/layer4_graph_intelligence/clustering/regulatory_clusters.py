"""
RegulatoryClusterDetector — groups entities by shared regulatory exposure.
Companies sharing the same SEBI/RBI/Tribunal action form a regulatory cluster.
"""
import logging
from collections import defaultdict
from datetime import datetime, timezone

from core.neo4j_client import get_session
from core.database import get_pool

logger = logging.getLogger(__name__)


class RegulatoryClusterDetector:
    CLUSTER_TYPE = "regulatory"

    async def run_and_persist(self, batch_run_id: str) -> dict:
        logger.info("Running regulatory cluster detection")
        action_entities = await self._load_regulatory_links()

        clusters: dict[str, list[str]] = defaultdict(list)
        for action_id, entity_ids in action_entities.items():
            if len(entity_ids) > 1:
                for eid in entity_ids:
                    clusters[action_id].append(eid)

        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM l4_cluster_memberships WHERE cluster_type = $1",
                self.CLUSTER_TYPE,
            )
            await conn.executemany(
                """
                INSERT INTO l4_cluster_memberships
                    (entity_id, entity_type, cluster_id, cluster_type, membership_score, computed_at, batch_run_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (entity_id, entity_type, cluster_type) DO UPDATE SET
                    cluster_id = EXCLUDED.cluster_id, computed_at = EXCLUDED.computed_at
                """,
                [
                    (eid, "Company", f"reg-{action_id[:20]}", self.CLUSTER_TYPE,
                     1.0, datetime.now(timezone.utc), batch_run_id)
                    for action_id, entities in clusters.items()
                    for eid in entities
                ],
            )

        logger.info("Regulatory clusters: %d clusters", len(clusters))
        return {"cluster_type": self.CLUSTER_TYPE, "clusters_found": len(clusters)}

    async def _load_regulatory_links(self) -> dict[str, list[str]]:
        async with get_session() as s:
            result = await s.run(
                """
                MATCH (c:Company)-[:HAS_REGULATORY_ACTION]->(ra:RegulatoryAction)
                RETURN ra.id AS actionId, collect(c.id) AS companies
                """
            )
            return {
                r["actionId"]: r["companies"]
                for r in await result.fetch(10_000)
                if r["actionId"]
            }
