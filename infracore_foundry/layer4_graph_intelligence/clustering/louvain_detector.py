"""
LouvainDetector — wraps GDS Louvain community detection and persists results
to l4_cluster_memberships + l4_cluster_memberships.
"""
import logging
import uuid
from datetime import datetime, timezone

from core.gds_client import run_louvain
from core.database import get_pool

logger = logging.getLogger(__name__)


class LouvainDetector:
    CLUSTER_TYPE = "louvain"

    async def run_and_persist(self, batch_run_id: str) -> dict:
        logger.info("Running Louvain community detection")
        rows = await run_louvain()
        if not rows:
            logger.warning("Louvain returned no results")
            return {"cluster_type": self.CLUSTER_TYPE, "members_written": 0, "clusters_found": 0}

        community_ids = set(r["communityId"] for r in rows)
        cluster_id_map: dict[int, str] = {
            cid: f"louvain-{cid}" for cid in community_ids
        }

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
                ON CONFLICT (entity_id, entity_type, cluster_type)
                DO UPDATE SET cluster_id = EXCLUDED.cluster_id,
                              computed_at = EXCLUDED.computed_at,
                              batch_run_id = EXCLUDED.batch_run_id
                """,
                [
                    (
                        r["entityId"],
                        r["entityType"],
                        cluster_id_map[r["communityId"]],
                        self.CLUSTER_TYPE,
                        1.0,
                        datetime.now(timezone.utc),
                        batch_run_id,
                    )
                    for r in rows
                    if r["entityId"]
                ],
            )

        logger.info("Louvain: %d members in %d clusters", len(rows), len(community_ids))
        return {
            "cluster_type": self.CLUSTER_TYPE,
            "members_written": len(rows),
            "clusters_found": len(community_ids),
        }
