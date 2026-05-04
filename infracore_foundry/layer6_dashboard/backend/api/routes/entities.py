"""
Entity routes — search, profile, and recent-views.
"""
import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text

from aggregators.entity_profile import build_entity_profile
from aggregators.search import search as aggregate_search
from core.auth import get_current_user
from core.database import get_db, upsert_recent_view
from core.layer_clients import layer_clients
from core.redis_client import cache_response, get_cached

logger = logging.getLogger(__name__)

router = APIRouter()

_VALID_ENTITY_TYPES = {
    "company",
    "director",
    "project",
    "regulatory_action",
    "address",
    "legal_case",
}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/search")
async def search_entities(
    q: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(10, ge=1, le=20),
    current_user: Dict = Depends(get_current_user),
) -> Dict:
    """
    Search for entities across all types.  Results are sorted by risk score descending.
    """
    cache_key = f"search:{q.lower()}:{limit}"
    cached = await get_cached(cache_key)
    if cached:
        return cached

    result = await aggregate_search(layer_clients, q, limit=limit)
    await cache_response(cache_key, result, ttl=60)
    return result


@router.get("/recent")
async def get_recent_views(
    current_user: Dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[Dict]:
    """Return the last 20 entities viewed by the current user."""
    result = await db.execute(
        text(
            """
            SELECT entity_type, entity_id, entity_name, risk_score, viewed_at
            FROM l6_recent_views
            WHERE user_id = :user_id
            ORDER BY viewed_at DESC
            LIMIT 20
            """
        ),
        {"user_id": current_user["sub"]},
    )
    rows = result.fetchall()
    return [
        {
            "entityType": r.entity_type,
            "entityId": r.entity_id,
            "name": r.entity_name,
            "riskScore": r.risk_score,
            "viewedAt": r.viewed_at.isoformat() if r.viewed_at else None,
        }
        for r in rows
    ]


@router.get("/{entity_type}/{entity_id}")
async def get_entity_profile(
    entity_type: str,
    entity_id: str,
    current_user: Dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict:
    """
    Return the full EntityProfileResponse for a given entity.
    Records the view in l6_recent_views.
    """
    if entity_type not in _VALID_ENTITY_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"entity_type must be one of: {sorted(_VALID_ENTITY_TYPES)}",
        )

    cache_key = f"entity_profile:{entity_type}:{entity_id}"
    cached = await get_cached(cache_key)
    if cached:
        # Still record the view even on cache hit
        await upsert_recent_view(
            db,
            current_user["sub"],
            entity_type,
            entity_id,
            cached.get("name", entity_id),
            cached.get("riskScore", 0),
        )
        return cached

    profile = await build_entity_profile(layer_clients, entity_type, entity_id)

    # Cache for 5 minutes
    await cache_response(cache_key, profile, ttl=300)

    # Record recent view
    await upsert_recent_view(
        db,
        current_user["sub"],
        entity_type,
        entity_id,
        profile.get("name", entity_id),
        profile.get("riskScore", 0),
    )

    return profile
