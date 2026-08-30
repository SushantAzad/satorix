"""
Search Aggregator — queries Layer 3 and transforms results into grouped SearchResult objects.
"""
import logging
from typing import Dict, List, Optional

from core.layer_clients import LayerClients

logger = logging.getLogger(__name__)

_RISK_BAND_MAP = {range(0, 40): "LOW", range(40, 70): "MEDIUM", range(70, 101): "HIGH"}


def _risk_band(score: int) -> str:
    if score >= 70:
        return "HIGH"
    if score >= 40:
        return "MEDIUM"
    return "LOW"


def _extract_identifier(entity_type: str, props: Dict) -> Optional[str]:
    """Extract CIN/DIN/RERA number depending on entity type."""
    if entity_type == "company":
        return props.get("cin") or props.get("CIN")
    if entity_type == "director":
        return props.get("din") or props.get("DIN")
    if entity_type == "project":
        return props.get("rera_id") or props.get("project_id")
    return None


def _build_search_result(raw: Dict) -> Dict:
    """
    Convert a raw L3 search result into a normalised SearchResult dict.

    Handles two formats:
      - Elasticsearch format: { id, index, score, source, highlights }
      - Palantir-style:       { entityId, entityType, properties }
    """
    # ── Entity type ─────────────────────────────────────────────────────────
    entity_type: str = (
        raw.get("entityType")
        or raw.get("entity_type")
        or raw.get("type")
        or ""
    ).lower()

    if not entity_type and "index" in raw:
        # Elasticsearch index name format: "ontology_company" → "company"
        entity_type = str(raw["index"]).replace("ontology_", "").lower()

    entity_type = entity_type or "unknown"

    # ── Entity ID ────────────────────────────────────────────────────────────
    entity_id: str = (
        raw.get("entityId")
        or raw.get("entity_id")
        or raw.get("id")
        or ""
    )

    # ── Properties ──────────────────────────────────────────────────────────
    # ES format stores the document body in "source"; Palantir uses "properties"
    props: Dict = (
        raw.get("source")       # Elasticsearch format
        or raw.get("properties")
        or raw.get("data")
        or raw
    )
    if not isinstance(props, dict):
        props = raw

    # ── Name ────────────────────────────────────────────────────────────────
    name: str = (
        props.get("name")
        or props.get("company_name")
        or props.get("director_name")
        or props.get("project_name")
        or raw.get("name")
        or entity_id
    )

    # ── Risk ─────────────────────────────────────────────────────────────────
    risk_score: int = int(
        props.get("riskScore", props.get("risk_score",
        raw.get("riskScore", raw.get("risk_score", 0)))) or 0
    )
    risk_flags: List[str] = props.get("riskFlags", props.get("risk_flags",
        raw.get("riskFlags", raw.get("risk_flags", []))))
    if not isinstance(risk_flags, list):
        risk_flags = []

    match_score: float = float(raw.get("score", raw.get("matchScore", raw.get("match_score", 0.0))) or 0.0)

    description: str = (
        props.get("description")
        or props.get("industry")
        or props.get("companyType")
        or props.get("company_type")
        or raw.get("description")
        or ""
    )

    identifier = _extract_identifier(entity_type, props)

    return {
        "entityId": entity_id,
        "entityType": entity_type,
        "name": name,
        "riskScore": risk_score,
        "riskBand": "NONE" if props.get("riskScore", props.get("risk_score")) is None else _risk_band(risk_score),
        "riskFlags": risk_flags,
        "description": description,
        "identifier": identifier,
        "matchScore": match_score,
    }


async def search(
    clients: LayerClients,
    query: str,
    limit: int = 20,
    client_id: str = "PLATFORM_GLOBAL",
) -> Dict:
    """
    Search Layer 3, transform results, sort by risk score descending,
    and return grouped by entity type.
    """
    raw_results = await clients.search_entities(query, limit=limit, client_id=client_id)

    results = [_build_search_result(r) for r in raw_results]

    # Sort: highest risk first (riskiest entities surface to the top)
    results.sort(key=lambda r: (-r["riskScore"], -r["matchScore"]))

    # Cap at *limit*
    results = results[:limit]

    # Group by entity type for display
    grouped: Dict[str, List[Dict]] = {}
    for r in results:
        et = r["entityType"]
        grouped.setdefault(et, []).append(r)

    return {
        "query": query,
        "results": results,
        "grouped": grouped,
        "total": len(results),
    }
