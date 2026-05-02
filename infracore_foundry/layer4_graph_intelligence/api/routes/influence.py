from fastapi import APIRouter, Depends, Query
from typing import Optional

from api.middleware.auth import verify_api_key
from influence.influence_aggregator import InfluenceAggregator

router = APIRouter(prefix="/influence", tags=["influence"])
_agg = InfluenceAggregator()


@router.get("/top")
async def top_influencers(
    entity_type: Optional[str] = Query(None),
    metric: str = Query("composite_score"),
    k: int = Query(50, ge=1, le=500),
    _key: str = Depends(verify_api_key),
):
    """Top-K entities by influence metric."""
    return {"top_k": await _agg.top_k(entity_type=entity_type, metric=metric, k=k)}


@router.get("/{entity_type}/{entity_id}")
async def entity_influence(
    entity_type: str,
    entity_id: str,
    _key: str = Depends(verify_api_key),
):
    """Full influence score breakdown for a specific entity."""
    score = await _agg.get_score(entity_id=entity_id, entity_type=entity_type)
    if not score:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"No influence scores for {entity_id}")
    return score
