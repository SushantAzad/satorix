"""
InfluenceAggregator — fast read path for the API.
Reads pre-computed l4_influence_scores and returns top-K entities.
"""
import logging
from typing import Any, Optional

from core.database import get_pool
from core.redis_client import cache_key, cache_get, cache_set
from core.config import settings

logger = logging.getLogger(__name__)


class InfluenceAggregator:
    async def top_k(
        self,
        entity_type: Optional[str] = None,
        metric: str = "composite_score",
        k: int = 50,
    ) -> list[dict[str, Any]]:
        allowed_metrics = {
            "composite_score", "betweenness", "pagerank",
            "degree_centrality", "risk_weighted_score", "regulatory_exposure",
        }
        if metric not in allowed_metrics:
            metric = "composite_score"

        ck = cache_key("influence_topk", et=entity_type or "all", metric=metric, k=k)
        cached = await cache_get(ck)
        if cached:
            return cached

        pool = get_pool()
        async with pool.acquire() as conn:
            if entity_type:
                rows = await conn.fetch(
                    f"SELECT entity_id, entity_type, {metric}, composite_rank "
                    f"FROM l4_influence_scores "
                    f"WHERE entity_type = $1 ORDER BY {metric} DESC NULLS LAST LIMIT $2",
                    entity_type, k,
                )
            else:
                rows = await conn.fetch(
                    f"SELECT entity_id, entity_type, {metric}, composite_rank "
                    f"FROM l4_influence_scores "
                    f"ORDER BY {metric} DESC NULLS LAST LIMIT $1",
                    k,
                )

        result = [dict(r) for r in rows]
        await cache_set(ck, result, settings.redis_ttl_medium)
        return result

    async def get_score(self, entity_id: str, entity_type: str) -> Optional[dict[str, Any]]:
        ck = cache_key("influence_score", eid=entity_id, et=entity_type)
        cached = await cache_get(ck)
        if cached:
            return cached

        pool = get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM l4_influence_scores WHERE entity_id=$1 AND entity_type=$2",
                entity_id, entity_type,
            )
        if not row:
            return None
        result = dict(row)
        await cache_set(ck, result, settings.redis_ttl_medium)
        return result
