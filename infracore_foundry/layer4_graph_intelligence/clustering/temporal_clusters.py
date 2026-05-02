"""
TemporalClusterDetector — groups entities with synchronized temporal patterns.
E.g., companies that were all incorporated within the same 30-day window
and share a director → probable SPV farm.
"""
import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any

from core.neo4j_client import get_session
from core.database import get_pool

logger = logging.getLogger(__name__)


class TemporalClusterDetector:
    CLUSTER_TYPE = "temporal"
    WINDOW_DAYS = 30
    MIN_CLUSTER_SIZE = 3

    async def run_and_persist(self, batch_run_id: str) -> dict:
        logger.info("Running temporal cluster detection (window=%d days)", self.WINDOW_DAYS)
        companies = await self._load_incorporation_dates()

        # Sort by incorporation date
        dated = [(cid, dt) for cid, dt in companies.items() if dt]
        dated.sort(key=lambda x: x[1])

        # Sliding window
        clusters: list[list[str]] = []
        i = 0
        while i < len(dated):
            window_start = dated[i][1]
            window_end = window_start + timedelta(days=self.WINDOW_DAYS)
            window = [cid for cid, dt in dated[i:] if dt <= window_end]
            if len(window) >= self.MIN_CLUSTER_SIZE:
                clusters.append(window)
                i += len(window)
            else:
                i += 1

        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM l4_cluster_memberships WHERE cluster_type = $1",
                self.CLUSTER_TYPE,
            )
            for idx, members in enumerate(clusters):
                cluster_id = f"temp-{idx}"
                await conn.executemany(
                    """
                    INSERT INTO l4_cluster_memberships
                        (entity_id, entity_type, cluster_id, cluster_type, membership_score, computed_at, batch_run_id)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (entity_id, entity_type, cluster_type) DO UPDATE SET
                        cluster_id = EXCLUDED.cluster_id, computed_at = EXCLUDED.computed_at
                    """,
                    [
                        (m, "Company", cluster_id, self.CLUSTER_TYPE,
                         1.0, datetime.now(timezone.utc), batch_run_id)
                        for m in members
                    ],
                )

        return {"cluster_type": self.CLUSTER_TYPE, "clusters_found": len(clusters)}

    async def _load_incorporation_dates(self) -> dict[str, datetime]:
        async with get_session() as s:
            result = await s.run(
                """
                MATCH (c:Company)
                WHERE c.incorporationDate IS NOT NULL
                RETURN c.id AS cid, c.incorporationDate AS incDate
                """
            )
            out: dict[str, datetime] = {}
            for r in await result.fetch(100_000):
                try:
                    out[r["cid"]] = datetime.fromisoformat(str(r["incDate"]))
                except (ValueError, TypeError):
                    pass
            return out
