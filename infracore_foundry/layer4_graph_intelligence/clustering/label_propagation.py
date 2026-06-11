"""
LabelPropagation — alternative community detection for dense regulatory networks.
"""
import logging
from datetime import datetime, timezone

from core.gds_client import run_label_propagation
from core.database import get_pool

logger = logging.getLogger(__name__)


class LabelPropagationDetector:
    CLUSTER_TYPE = "label_propagation"

    async def run_and_persist(self, batch_run_id: str) -> dict:
        logger.info("Running Label Propagation community detection")
        rows = await run_label_propagation()
        if not rows:
            return {"cluster_type": self.CLUSTER_TYPE, "members_written": 0, "clusters_found": 0}

        community_ids = set(r["communityId"] for r in rows)
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
                DO UPDATE SET cluster_id = EXCLUDED.cluster_id, computed_at = EXCLUDED.computed_at
                """,
                [
                    (
                        r["entityId"],
                        r["entityType"],
                        f"lp-{r['communityId']}",
                        self.CLUSTER_TYPE,
                        1.0,
                        datetime.now(timezone.utc),
                        batch_run_id,
                    )
                    for r in rows
                    if r["entityId"]
                ],
            )
        return {
            "cluster_type": self.CLUSTER_TYPE,
            "members_written": len(rows),
            "clusters_found": len(community_ids),
        }
