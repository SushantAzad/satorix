from fastapi import APIRouter, Query, HTTPException
from typing import Any, Optional
from storage.neo4j_store import Neo4jStore
from intelligence.graph_intelligence.shared_attribute import shared_attribute_analyzer

router = APIRouter(prefix="/graph", tags=["graph"])
_neo4j = Neo4jStore()


@router.get("/network/{object_type}/{primary_key}")
async def get_network(
    object_type: str,
    primary_key: str,
    depth: int = Query(default=2, ge=1, le=3),
) -> dict[str, Any]:
    network = await _neo4j.get_network(object_type, primary_key, depth)
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
) -> dict[str, Any]:
    path = await _neo4j.find_shortest_path(source_type, source_id, target_type, target_id, max_depth)
    if path is None:
        return {"path_found": False, "path": None, "hops": 0}
    return {"path_found": True, "path": path, "hops": len(path) - 1}


@router.get("/shared-attributes")
async def find_shared_attributes(
    attribute: str = Query(..., description="'address' or 'director'"),
    value: str = Query(..., description="The attribute value to look up"),
) -> dict[str, Any]:
    if attribute == "director":
        results = await shared_attribute_analyzer.find_shared_director(value)
    elif attribute == "address":
        results = await shared_attribute_analyzer.find_shared_address(value)
    else:
        raise HTTPException(status_code=400, detail="attribute must be 'address' or 'director'")
    return {"attribute": attribute, "value": value, "matches": results, "count": len(results)}


@router.get("/beneficial-ownership/{company_cin}")
async def get_beneficial_ownership(company_cin: str) -> dict[str, Any]:
    chain = await _neo4j.get_beneficial_ownership_chain(company_cin)
    has_gap = any(item.get("isOffshore") and not item.get("entity_name") for item in chain)
    return {
        "company_cin": company_cin,
        "ownership_chain": chain,
        "chain_depth": len(chain),
        "has_offshore_entity": any(item.get("isOffshore") for item in chain),
        "has_ownership_gap": has_gap,
    }
