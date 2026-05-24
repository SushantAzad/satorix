from fastapi import APIRouter, Depends, Query, HTTPException
from typing import Any, Optional
from core.client_context import get_client_id
from storage.neo4j_store import Neo4jStore
from intelligence.graph_intelligence.shared_attribute import shared_attribute_analyzer

router = APIRouter(prefix="/graph", tags=["graph"])
_neo4j = Neo4jStore()


@router.get("/network/{object_type}/{primary_key}")
async def get_network(
    object_type: str,
    primary_key: str,
    depth: int = Query(default=2, ge=1, le=3),
    client_id: str = Depends(get_client_id),
) -> dict[str, Any]:
    network = await _neo4j.get_network(object_type, primary_key, depth, client_id=client_id)
    return {
        "object_type": object_type,
        "primary_key": primary_key,
        "depth": depth,
        **network,
    }


@router.get("/path/{source_type}/{source_id}/{target_type}/{target_id}")
async def find_path(
    source_type: str,
    source_id: str,
    target_type: str,
    target_id: str,
    max_depth: int = Query(default=5, ge=1, le=10),
    client_id: str = Depends(get_client_id),
) -> dict[str, Any]:
    path = await _neo4j.find_shortest_path(
        source_type, source_id, target_type, target_id, max_depth, client_id=client_id
    )
    if path is None:
        return {"path_found": False, "path": None, "hops": 0}
    return {"path_found": True, "path": path, "hops": len(path) - 1}


@router.get("/shared-attributes")
async def find_shared_attributes(
    attribute: str = Query(..., description="'address' or 'director'"),
    value: str = Query(..., description="The attribute value to look up"),
    client_id: str = Depends(get_client_id),
) -> dict[str, Any]:
    if attribute == "director":
        results = await shared_attribute_analyzer.find_shared_director(value, client_id=client_id)
    elif attribute == "address":
        results = await shared_attribute_analyzer.find_shared_address(value, client_id=client_id)
    else:
        raise HTTPException(status_code=400, detail="attribute must be 'address' or 'director'")
    return {"attribute": attribute, "value": value, "matches": results, "count": len(results)}


@router.get("/beneficial-ownership/{company_cin}")
async def get_beneficial_ownership(
    company_cin: str,
    client_id: str = Depends(get_client_id),
) -> dict[str, Any]:
    chain = await _neo4j.get_beneficial_ownership_chain(company_cin, client_id=client_id)
    has_gap = any(item.get("isOffshore") and not item.get("entity_name") for item in chain)
    return {
        "company_cin": company_cin,
        "ownership_chain": chain,
        "chain_depth": len(chain),
        "has_offshore_entity": any(item.get("isOffshore") for item in chain),
        "has_ownership_gap": has_gap,
    }
