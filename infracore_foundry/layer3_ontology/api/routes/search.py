from fastapi import APIRouter, Query
from typing import Any, Optional
from storage.elasticsearch_store import ElasticsearchStore

router = APIRouter(prefix="/search", tags=["search"])
_es_store = ElasticsearchStore()


@router.get("")
async def universal_search(
    q: str = Query(..., description="Search text"),
    object_types: Optional[str] = Query(default=None, description="Comma-separated object types"),
    riskScore_min: Optional[int] = None,
    state: Optional[str] = None,
    status: Optional[str] = None,
    size: int = Query(default=50, le=200),
) -> dict[str, Any]:
    ot_list = [ot.strip() for ot in object_types.split(",")] if object_types else None
    filters: dict[str, Any] = {}
    if state:
        filters["registeredState"] = state
    if status:
        filters["status"] = status
    if riskScore_min is not None:
        filters["riskScore_min"] = riskScore_min

    try:
        results = await _es_store.search_objects(q, ot_list, filters, size)
    except Exception as e:
        return {"query": q, "results": [], "error": str(e), "total": 0}

    return {
        "query": q,
        "total": len(results),
        "results": results,
    }


@router.get("/semantic")
async def semantic_search(
    natural_language_query: str = Query(...),
    size: int = Query(default=20, le=100),
) -> dict[str, Any]:
    # Parse natural language intent into structured search
    query_lower = natural_language_query.lower()

    # Extract hints from natural language
    object_types = None
    if "compan" in query_lower:
        object_types = ["company"]
    elif "director" in query_lower:
        object_types = ["director"]
    elif "project" in query_lower:
        object_types = ["project"]

    filters: dict[str, Any] = {}
    if "cirp" in query_lower or "insolvency" in query_lower:
        filters["status"] = "UnderCIRP"
    if "gujarat" in query_lower:
        filters["registeredState"] = "Gujarat"
    if "maharashtra" in query_lower:
        filters["registeredState"] = "Maharashtra"
    if "high risk" in query_lower or "risk" in query_lower:
        filters["riskScore_min"] = 70

    try:
        results = await _es_store.search_objects(natural_language_query, object_types, filters, size)
    except Exception as e:
        return {"query": natural_language_query, "results": [], "error": str(e)}

    return {
        "natural_language_query": natural_language_query,
        "interpreted_filters": filters,
        "total": len(results),
        "results": results,
    }
