"""
DirectorClusterDetector — finds groups of companies sharing multiple directors.
High-overlap Jaccard similarity → potential related-party network.
"""
import logging
from collections import defaultdict
from datetime import datetime, timezone
from itertools import combinations

from core.neo4j_client import get_session
from core.database import get_pool

logger = logging.getLogger(__name__)


class DirectorClusterDetector:
    JACCARD_THRESHOLD = 0.3   # share ≥30% of directors
    CLUSTER_TYPE = "director"

    async def run_and_persist(self, batch_run_id: str) -> dict:
        logger.info("Running director cluster detection (Jaccard threshold=%.2f)", self.JACCARD_THRESHOLD)
        company_directors = await self._load_company_directors()

        pairs: list[tuple[str, str, float]] = []
        company_ids = list(company_directors.keys())
        for c1, c2 in combinations(company_ids, 2):
            s1 = company_directors[c1]
            s2 = company_directors[c2]
            if not s1 or not s2:
                continue
            intersection = len(s1 & s2)
            union = len(s1 | s2)
            jaccard = intersection / union if union else 0.0
            if jaccard >= self.JACCARD_THRESHOLD:
                pairs.append((c1, c2, jaccard))

        # Union-Find to build clusters from pairs
        parent: dict[str, str] = {c: c for c in company_ids}

        def find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x: str, y: str) -> None:
            parent[find(x)] = find(y)

        for c1, c2, _ in pairs:
            union(c1, c2)

        clusters: dict[str, list[str]] = defaultdict(list)
        for c in company_ids:
            clusters[find(c)].append(c)

        multi = {root: members for root, members in clusters.items() if len(members) > 1}

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
                    (c, "Company", f"dir-{root}", self.CLUSTER_TYPE,
                     1.0, datetime.now(timezone.utc), batch_run_id)
                    for root, members in multi.items()
                    for c in members
                ],
            )

        logger.info("Director clusters: %d clusters from %d companies", len(multi), len(company_ids))
        return {
            "cluster_type": self.CLUSTER_TYPE,
            "companies_processed": len(company_ids),
            "clusters_found": len(multi),
        }

    async def _load_company_directors(self) -> dict[str, set[str]]:
        async with get_session() as s:
            result = await s.run(
                """
                MATCH (d:Director)-[:DIRECTED]->(c:Company)
                RETURN c.id AS companyId, collect(d.id) AS directors
                """
            )
            return {
                r["companyId"]: set(r["directors"])
                for r in await result.fetch(100_000)
                if r["companyId"]
            }
