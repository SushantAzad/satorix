from fastapi import APIRouter, Depends, Query
from typing import Optional

from api.middleware.auth import verify_api_key
from network.network_mapper import NetworkMapper
from network.pruning_engine import PruningEngine

router = APIRouter(prefix="/network", tags=["network"])
_mapper = NetworkMapper()
_pruner = PruningEngine()


@router.get("/expand/{entity_id}")
async def expand_network(
    entity_id: str,
    hops: int = Query(2, ge=1, le=4),
    node_types: Optional[str] = Query(None, description="Comma-separated node types"),
    rel_types: Optional[str] = Query(None, description="Comma-separated relationship types"),
    min_risk_score: float = Query(0.0, ge=0.0, le=100.0),
    max_nodes: int = Query(200, ge=10, le=500),
    _key: str = Depends(verify_api_key),
):
    """Expand network around an entity up to N hops."""
    nt = [t.strip() for t in node_types.split(",")] if node_types else None
    rt = [t.strip() for t in rel_types.split(",")] if rel_types else None
    network = await _mapper.expand(
        seed_id=entity_id, hops=hops,
        node_types=nt, rel_types=rt,
        min_risk_score=min_risk_score,
    )
    pruned = _pruner.prune(network, max_nodes=max_nodes, min_risk_score=min_risk_score)
    return pruned.to_dict()


@router.get("/neighbors/{entity_id}")
async def get_neighbors(
    entity_id: str,
    _key: str = Depends(verify_api_key),
):
    """Direct neighbors (1 hop) of an entity."""
    network = await _mapper.expand(seed_id=entity_id, hops=1)
    return network.to_dict()
