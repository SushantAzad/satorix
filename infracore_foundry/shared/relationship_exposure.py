"""Recorded direct-company exposure, never a replacement for personal risk."""
import math


def relationship_exposure(entity_type, entity_id, graph):
    result = {"method": "direct-company-exposure/v1", "status": "available",
              "scope": "Recorded direct DIRECTED/OWNS links to companies; both directions.",
              "notice": "Relationship exposure is not personal risk or evidence of wrongdoing.",
              "companies": [], "high_count": 0, "medium_count": 0,
              "low_count": 0, "unknown_count": 0, "max_recorded_score": None}
    if graph is None:
        return {**result, "status": "unavailable"}
    root = (entity_type, entity_id)
    nodes = {}
    for n in graph.get("nodes", []):
        kind = n.get("object_type") or n.get("entityType")
        pk = n.get("entityId") or n.get("cin") or n.get("din") or n.get("projectId")
        nodes[(kind, pk)] = n.get("properties") or n
    companies = {}
    for edge in graph.get("edges", []):
        if edge.get("type") not in ("DIRECTED", "OWNS") or edge.get("isInferred", edge.get("is_inferred", False)):
            continue
        src = (str(edge.get("sourceLabel", "")).lower(), edge.get("sourcePK"))
        dst = (str(edge.get("targetLabel", "")).lower(), edge.get("targetPK"))
        other = dst if src == root else src if dst == root else None
        if not other or other == root or other[0] != "company" or other not in nodes:
            continue
        props = nodes[other]
        score = props.get("riskScore")
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 100:
            score = None
        band = "NONE" if score is None else "HIGH" if score >= 70 else "MEDIUM" if score >= 40 else "LOW"
        company = companies.setdefault(other[1], {"entity_id": other[1],
            "name": props.get("name", other[1]), "score": score, "band": band,
            "synthetic": bool(props.get("synthetic")), "relationships": []})
        evidence = {"type": edge["type"], "source_type": src[0], "source_id": src[1],
                    "target_type": dst[0], "target_id": dst[1], "properties": edge.get("properties") or {}}
        if evidence not in company["relationships"]:
            company["relationships"].append(evidence)
    result["companies"] = sorted(companies.values(), key=lambda c: (-(c["score"] if c["score"] is not None else -1), c["entity_id"]))
    for c in result["companies"]:
        result["unknown_count" if c["band"] == "NONE" else c["band"].lower() + "_count"] += 1
    scores = [c["score"] for c in result["companies"] if c["score"] is not None]
    result["max_recorded_score"] = max(scores) if scores else None
    return result
