from fastapi import APIRouter, Depends, Query
from typing import Optional

from api.middleware.auth import verify_api_key
from core.database import get_pool
from core.redis_client import cache_key, cache_get, cache_set
from core.config import settings

router = APIRouter(prefix="/clusters", tags=["clusters"])


@router.get("/{entity_id}")
async def get_entity_clusters(
    entity_id: str,
    _key: str = Depends(verify_api_key),
):
    """All cluster memberships for a given entity."""
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT cluster_id, cluster_type, membership_score, computed_at "
            "FROM l4_cluster_memberships WHERE entity_id = $1",
            entity_id,
        )
    return {"entity_id": entity_id, "clusters": [dict(r) for r in rows]}


@router.get("/type/{cluster_type}/members")
async def get_cluster_members(
    cluster_type: str,
    cluster_id: str = Query(...),
    _key: str = Depends(verify_api_key),
):
    """All members of a specific cluster."""
    ck = cache_key("cluster_members", ct=cluster_type, cid=cluster_id)
    cached = await cache_get(ck)
    if cached:
        return cached

    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT entity_id, entity_type, membership_score "
            "FROM l4_cluster_memberships WHERE cluster_type=$1 AND cluster_id=$2",
            cluster_type, cluster_id,
        )
    result = {"cluster_id": cluster_id, "cluster_type": cluster_type,
              "members": [dict(r) for r in rows]}
    await cache_set(ck, result, settings.redis_ttl_medium)
    return result


@router.get("/address/top")
async def top_address_clusters(
    limit: int = Query(20, ge=1, le=100),
    min_members: int = Query(3, ge=2),
    _key: str = Depends(verify_api_key),
):
    """Top address clusters ranked by risk signal."""
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM l4_address_clusters WHERE member_count >= $1 "
            "ORDER BY risk_signal DESC LIMIT $2",
            min_members, limit,
        )
    return {"clusters": [dict(r) for r in rows]}
