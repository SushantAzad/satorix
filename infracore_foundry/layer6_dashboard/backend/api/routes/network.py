"""
Network routes — Cytoscape.js graph data for the relationship explorer.
"""
import logging
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, Query, status

from aggregators.network import build_network
from core.auth import get_current_user
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


@router.get("/{entity_type}/{entity_id}")
async def get_network(
    entity_type: str,
    entity_id: str,
    depth: int = Query(2, ge=1, le=4, description="Graph traversal depth"),
    current_user: Dict = Depends(get_current_user),
) -> Dict:
    """
    Return a Cytoscape.js-compatible network graph for the given entity.
    Prefers Layer 4 pre-computed network; falls back to Layer 3.
    """
    if entity_type not in _VALID_ENTITY_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"entity_type must be one of: {sorted(_VALID_ENTITY_TYPES)}",
        )

    cache_key = f"network:{entity_type}:{entity_id}:depth{depth}"
    cached = await get_cached(cache_key)
    if cached:
        return cached

    network = await build_network(layer_clients, entity_type, entity_id, depth=depth)

    # Cache for 10 minutes — network graphs are expensive to compute
    await cache_response(cache_key, network, ttl=600)

    return network
