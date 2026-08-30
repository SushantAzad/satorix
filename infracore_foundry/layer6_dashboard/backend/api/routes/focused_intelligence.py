"""Explainable investigation signals; not an ML prediction or legal finding."""
from fastapi import APIRouter, Depends, HTTPException
from core.auth import get_current_user
from core.layer_clients import layer_clients
from shared.relationship_exposure import relationship_exposure
from typing import Literal

router = APIRouter()


@router.get("/exposure/{entity_type}/{entity_id}")
async def exposure(entity_type: Literal["company", "director", "project", "address", "regulatory_action", "legal_case"],
                   entity_id: str, user=Depends(get_current_user)):
    tenant = user.get("client_id", "PLATFORM_GLOBAL")
    entity = await layer_clients.get_entity(entity_type, entity_id, client_id=tenant)
    if not entity:
        raise HTTPException(404, "Entity unavailable")
    graph = await layer_clients.get_network(entity_type, entity_id, depth=1, client_id=tenant)
    return relationship_exposure(entity_type, entity_id, graph)


@router.get("/{entity_id}")
async def inspect(entity_id: str, user=Depends(get_current_user)):
    tenant = user.get("client_id", "PLATFORM_GLOBAL")
    entity = await layer_clients.get_entity("company", entity_id, client_id=tenant)
    if not entity:
        raise HTTPException(404, "Company unavailable")
    graph = await layer_clients.get_network("company", entity_id, depth=2, client_id=tenant)
    risk = await layer_clients.get_risk_score("company", entity_id, client_id=tenant)
    if graph is None:
        raise HTTPException(503, "Relationship analysis unavailable")
    edges = graph.get("edges", [])
    directors = {e["sourcePK"] for e in edges if e["type"] == "DIRECTED" and e["targetPK"] == entity_id}
    shared = sorted({e["targetPK"] for e in edges if e["type"] == "DIRECTED"
                     and e["sourcePK"] in directors and e["targetPK"] != entity_id})
    return {
        "entity_id": entity_id, "name": entity.get("name", entity_id),
        "synthetic": bool(entity.get("synthetic")),
        "risk_score": risk.get("risk_score") if risk else None,
        "risk_band": risk.get("risk_band", "NONE") if risk else "NONE",
        "directors": sorted(directors), "companies_sharing_directors": shared,
        "relationship_count": len(edges),
        "review_signals": [
            *([f"{len(shared)} other loaded companies share a director. Review the connections."] if shared else []),
            *(["No risk assessment recorded. This does not mean low risk."] if not risk or risk.get("risk_score") is None else []),
            *(["No CSV source label on this entity. Inspect relationship evidence and source records for provenance."] if not entity.get("importSource") else []),
        ],
        "limitations": "Rule-based review of loaded records within depth 2. Relationships are not evidence of wrongdoing. No ML/LLM prediction or external verification performed.",
    }
