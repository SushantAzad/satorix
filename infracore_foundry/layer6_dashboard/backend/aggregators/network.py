"""
Network Aggregator — converts Layer 3 / Layer 4 graph data into
Cytoscape.js-compatible format for the frontend relationship explorer.
"""
import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple  # noqa: F401

from core.layer_clients import LayerClients

logger = logging.getLogger(__name__)

# Map of raw link types to display names
_LINK_LABEL_MAP: Dict[str, str] = {
    "DIRECTED": "Director",
    "OWNS": "Owns",
    "SUBJECT_OF": "Subject of",
    "SHARES_DIRECTOR_WITH": "Shared Director",
    "REGULATED_BY": "Regulated by",
    "INVOLVED_IN": "Involved in",
    "LOCATED_AT": "Located at",
    "SUBSIDIARY_OF": "Subsidiary of",
    "PARTNER_OF": "Partner of",
    "AUDITED_BY": "Audited by",
    "LENDER_TO": "Lender to",
    "PLEDGED_TO": "Pledged to",
    "CHARGED_AGAINST": "Charged against",
    "GUARANTOR_FOR": "Guarantor for",
}

_RISK_BAND_MAP = {
    "HIGH": "HIGH",
    "MEDIUM": "MEDIUM",
    "LOW": "LOW",
}


# ---------------------------------------------------------------------------
# Node / edge builders
# ---------------------------------------------------------------------------

def _risk_band(score: int) -> str:
    if score >= 70:
        return "HIGH"
    if score >= 40:
        return "MEDIUM"
    return "LOW"


def _node_size(betweenness: float) -> float:
    raw = 20.0 + betweenness * 30.0
    return max(20.0, min(60.0, raw))


def _node_id(entity_type: str, entity_id: str) -> str:
    return f"{entity_type}:{entity_id}"


_PK_FIELDS = ("cin", "din", "projectId", "actionId", "caseId", "cirpId",
               "normalizedAddress", "bodyId", "entityId", "eventId", "alertId", "id")


def _build_node(
    raw_node: Dict,
    centrality_map: Optional[Dict[str, float]] = None,
) -> Dict:
    """Convert a raw L3/L4 node dict into a Cytoscape node element."""
    # Layer 3 Neo4j nodes store type in "object_type"; L4 uses "entityType"
    entity_type: str = (
        raw_node.get("entityType")
        or raw_node.get("entity_type")
        or raw_node.get("object_type")         # Neo4j node property
        or (raw_node.get("labels", [""])[0].lower() if isinstance(raw_node.get("labels"), list) else "")
        or "unknown"
    ).lower()

    # Find the primary key: try known PK fields in priority order
    entity_id: str = raw_node.get("entityId") or raw_node.get("entity_id") or ""
    if not entity_id:
        for pk_field in _PK_FIELDS:
            val = raw_node.get(pk_field)
            if val:
                entity_id = str(val)
                break
    entity_id = entity_id or "unknown"
    node_key = _node_id(entity_type, entity_id)

    # For Neo4j flat property nodes, there's no "properties" wrapper
    props: Dict = raw_node.get("properties") or raw_node.get("data") or raw_node
    name: str = (
        props.get("name")
        or props.get("company_name")
        or props.get("director_name")
        or props.get("project_name")
        or entity_id
    )
    label = name[:20] + ("…" if len(name) > 20 else "")

    risk_score: int = int(
        props.get("riskScore", props.get("risk_score", raw_node.get("riskScore", 0))) or 0
    )
    raw_flags = props.get("riskFlags", props.get("risk_flags", raw_node.get("riskFlags", [])))
    if isinstance(raw_flags, str):
        risk_flags: List[str] = [f for f in raw_flags.split(",") if f]
    else:
        risk_flags = list(raw_flags) if raw_flags else []
    is_anomalous: bool = any(
        a.get("severity") in ("HIGH", "CRITICAL")
        for a in raw_node.get("activeAlerts", [])
    ) or raw_node.get("isAnomalous", False)

    betweenness: float = 0.5
    if centrality_map and node_key in centrality_map:
        betweenness = float(centrality_map[node_key])
    elif centrality_map and entity_id in centrality_map:
        betweenness = float(centrality_map[entity_id])

    return {
        "data": {
            "id": node_key,
            "label": label,
            "entityType": entity_type,
            "riskScore": risk_score,
            "riskBand": _risk_band(risk_score),
            "riskFlags": risk_flags,
            "betweennessCentrality": betweenness,
            "isAnomalous": is_anomalous,
            "properties": props,
            "size": _node_size(betweenness),
        }
    }


def _build_edge(raw_edge: Dict, idx: int) -> Dict:
    """Convert a raw L3/L4 edge dict into a Cytoscape edge element."""
    # Prefer new L3 coalesce format (sourceLabel/sourcePK) over old Palantir-style fields
    source_type: str = (
        raw_edge.get("sourceType")
        or raw_edge.get("source_type")
        or (raw_edge.get("sourceLabel", "").lower() or None)
        or "unknown"
    )
    source_id: str = (
        raw_edge.get("sourceId")
        or raw_edge.get("source_id")
        or raw_edge.get("sourcePK")
        or str(raw_edge.get("source", "unknown"))
    )
    target_type: str = (
        raw_edge.get("targetType")
        or raw_edge.get("target_type")
        or (raw_edge.get("targetLabel", "").lower() or None)
        or "unknown"
    )
    target_id: str = (
        raw_edge.get("targetId")
        or raw_edge.get("target_id")
        or raw_edge.get("targetPK")
        or str(raw_edge.get("target", "unknown"))
    )

    source_key = _node_id(source_type, source_id)
    target_key = _node_id(target_type, target_id)

    link_type: str = (
        raw_edge.get("linkType")
        or raw_edge.get("link_type")
        or raw_edge.get("type")
        or raw_edge.get("relationshipType")
        or "RELATED_TO"
    )
    is_inferred: bool = raw_edge.get("isInferred", raw_edge.get("is_inferred", False))
    edge_props: Dict = raw_edge.get("properties", {})

    edge_id = f"{source_key}-{target_key}-{link_type}-{idx}"

    return {
        "data": {
            "id": edge_id,
            "source": source_key,
            "target": target_key,
            "linkType": link_type,
            "isInferred": is_inferred,
            "properties": edge_props,
            "label": _LINK_LABEL_MAP.get(link_type, link_type.replace("_", " ").title()),
        }
    }


def _sanitize_graph(nodes: List[Dict], edges: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    """Deduplicate nodes and remove edges whose endpoints are unavailable."""
    unique_nodes: Dict[str, Dict] = {}
    for node in nodes:
        unique_nodes.setdefault(node["data"]["id"], node)
    nodes = list(unique_nodes.values())
    node_ids = {n["data"]["id"] for n in nodes}
    valid: List[Dict] = []
    removed: List[Dict] = []
    for edge in edges:
        src = edge["data"].get("source", "")
        tgt = edge["data"].get("target", "")
        if src in node_ids and tgt in node_ids:
            valid.append(edge)
        else:
            removed.append(edge)
    if removed:
        logger.warning(
            "Dropped %d edges with missing nodes: %s",
            len(removed),
            [f"{e['data'].get('source')}→{e['data'].get('target')}" for e in removed[:5]],
        )
    return nodes, valid


# ---------------------------------------------------------------------------
# Fallback single-node network
# ---------------------------------------------------------------------------

def _minimal_network(entity_type: str, entity_id: str) -> Dict:
    """Return a network containing only the requested entity (both layers failed)."""
    node_key = _node_id(entity_type, entity_id)
    return {
        "nodes": [
            {
                "data": {
                    "id": node_key,
                    "label": entity_id[:20],
                    "entityType": entity_type,
                    "riskScore": 0,
                    "riskBand": "NONE",
                    "riskFlags": [],
                    "betweennessCentrality": 0.5,
                    "isAnomalous": False,
                    "properties": {},
                    "size": 35.0,
                }
            }
        ],
        "edges": [],
        "metadata": {
            "entityCount": 1,
            "relationshipCount": 0,
            "maxDepth": 0,
        },
    }


# ---------------------------------------------------------------------------
# Main aggregator
# ---------------------------------------------------------------------------

async def build_network(
    clients: LayerClients,
    entity_type: str,
    entity_id: str,
    depth: int = 2,
    client_id: str = "PLATFORM_GLOBAL",
) -> Dict:
    """
    Fetch network data from Layer 4 (preferred) and Layer 3 (fallback),
    then convert to Cytoscape.js format.
    """
    l4_network, l3_network = await asyncio.gather(
        clients.get_l4_network(entity_type, entity_id, client_id=client_id),
        clients.get_network(entity_type, entity_id, depth, client_id=client_id),
        return_exceptions=False,
    )

    # Prefer L4 (pre-computed), fall back to L3, then use minimal stub
    raw: Optional[Dict] = l4_network or l3_network
    if raw is None:
        logger.info(
            "Both L4 and L3 network unavailable for %s/%s — returning minimal network.",
            entity_type,
            entity_id,
        )
        return _minimal_network(entity_type, entity_id)

    source_label = "layer4" if l4_network else "layer3"

    # Build centrality lookup from L4 if available
    centrality_map: Optional[Dict[str, float]] = None
    if l4_network and "centrality" in l4_network:
        centrality_map = l4_network["centrality"]
    elif l4_network and "nodes" in l4_network:
        centrality_map = {
            _node_id(
                n.get("entityType", n.get("entity_type", "unknown")),
                n.get("entityId", n.get("entity_id", "unknown")),
            ): float(n.get("betweenness_centrality", n.get("betweennessCentrality", 0.5)))
            for n in l4_network.get("nodes", [])
        }

    raw_nodes: List[Dict] = raw.get("nodes", [])
    raw_edges: List[Dict] = raw.get("edges", raw.get("relationships", []))

    # Build Cytoscape elements
    cyto_nodes = [_build_node(n, centrality_map) for n in raw_nodes]
    cyto_edges = [_build_edge(e, idx) for idx, e in enumerate(raw_edges)]

    # Ensure the root entity always appears as a node
    root_key = _node_id(entity_type, entity_id)
    if not any(n["data"]["id"] == root_key for n in cyto_nodes):
        cyto_nodes.insert(
            0,
            {
                "data": {
                    "id": root_key,
                    "label": entity_id[:20],
                    "entityType": entity_type,
                    "riskScore": 0,
                    "riskBand": "LOW",
                    "riskFlags": [],
                    "betweennessCentrality": 1.0,
                    "isAnomalous": False,
                    "properties": {},
                    "size": 50.0,
                }
            },
        )

    # Drop edges that reference a node not in the nodes list — Cytoscape.js will crash otherwise
    cyto_nodes, cyto_edges = _sanitize_graph(cyto_nodes, cyto_edges)

    return {
        "nodes": cyto_nodes,
        "edges": cyto_edges,
        "metadata": {
            "entityCount": len(cyto_nodes),
            "relationshipCount": len(cyto_edges),
            "maxDepth": depth,
        },
    }
