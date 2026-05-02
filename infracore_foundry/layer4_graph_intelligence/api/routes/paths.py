from fastapi import APIRouter, Depends, Query
from typing import Optional

from api.middleware.auth import verify_api_key
from pathfinding.shortest_path import ShortestPathFinder
from pathfinding.all_paths import AllPathsFinder
from pathfinding.path_scorer import PathScorer
from pathfinding.narrative_generator import NarrativeGenerator
from pathfinding.negative_space import NegativeSpaceAnalyzer

router = APIRouter(prefix="/paths", tags=["paths"])
_shortest = ShortestPathFinder()
_all_paths = AllPathsFinder()
_scorer = PathScorer()
_narrator = NarrativeGenerator()
_neg_space = NegativeSpaceAnalyzer()


@router.get("/shortest")
async def shortest_path(
    source: str = Query(...),
    target: str = Query(...),
    max_hops: int = Query(6, ge=1, le=8),
    narrative: bool = Query(False, description="Generate LLM narrative"),
    _key: str = Depends(verify_api_key),
):
    """Find shortest path between two entities."""
    result = await _shortest.find(source_id=source, target_id=target, max_hops=max_hops)
    response = result.to_dict()
    if narrative and result.found:
        scored = _scorer.score(
            node_path=result.node_path,
            node_types=result.node_types,
            hop_details=result.hop_details,
            node_properties={},
        )
        text = await _narrator.generate(
            source_id=source, target_id=target,
            node_path=result.node_path, node_types=result.node_types,
            hop_details=result.hop_details, signals=scored.signals,
            node_properties={},
        )
        response["narrative"] = text
        response["risk_signals"] = scored.signals
        response["path_risk"] = scored.path_risk
    return response


@router.get("/all")
async def all_paths(
    source: str = Query(...),
    target: str = Query(...),
    max_hops: int = Query(4, ge=1, le=5),
    max_paths: int = Query(5, ge=1, le=10),
    _key: str = Depends(verify_api_key),
):
    """Find up to K paths between two entities, ranked by risk."""
    result = await _all_paths.find_all(source_id=source, target_id=target,
                                        max_hops=max_hops, max_paths=max_paths)
    return result.to_dict()


@router.get("/negative-space/{entity_id}")
async def negative_space(
    entity_id: str,
    entity_type: str = Query("Company"),
    _key: str = Depends(verify_api_key),
):
    """Detect expected-but-absent relationships."""
    signals = await _neg_space.analyze(entity_id=entity_id, entity_type=entity_type)
    return {"entity_id": entity_id, "absence_signals": [
        {"expected_rel": s.expected_relationship, "reason": s.reason, "severity": s.severity}
        for s in signals
    ]}
