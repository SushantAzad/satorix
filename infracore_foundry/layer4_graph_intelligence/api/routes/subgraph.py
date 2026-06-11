from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from typing import Optional

from api.middleware.auth import verify_api_key
from subgraph.extractor import SubgraphExtractor
from subgraph.templates import get_template, list_templates
from subgraph.differ import SubgraphDiffer
from subgraph.exporter import SubgraphExporter

router = APIRouter(prefix="/subgraph", tags=["subgraph"])
_extractor = SubgraphExtractor()
_differ = SubgraphDiffer()
_exporter = SubgraphExporter()


class CreateSubgraphRequest(BaseModel):
    name: str
    seed_entity_id: str
    seed_entity_type: str = "Company"
    hops: int = 2
    node_types: list[str] = []
    edge_types: list[str] = []
    template: Optional[str] = None


@router.get("/templates")
async def get_templates(_key: str = Depends(verify_api_key)):
    """List available subgraph extraction templates."""
    return {"templates": list_templates()}


@router.post("/define")
async def define_subgraph(
    req: CreateSubgraphRequest,
    _key: str = Depends(verify_api_key),
):
    """Create a subgraph definition (persisted, snapshotted on demand)."""
    if req.template:
        tmpl = get_template(req.template)
        if not tmpl:
            raise HTTPException(status_code=400, detail=f"Unknown template: {req.template}")
        node_types = tmpl.node_types
        edge_types = tmpl.edge_types
        hops = tmpl.hops
    else:
        node_types = req.node_types
        edge_types = req.edge_types
        hops = req.hops

    subgraph_id = await _extractor.create_definition(
        name=req.name,
        seed_entity_id=req.seed_entity_id,
        seed_entity_type=req.seed_entity_type,
        hops=hops,
        node_types=node_types or None,
        edge_types=edge_types or None,
    )
    return {"subgraph_id": subgraph_id}


@router.post("/{subgraph_id}/snapshot")
async def take_snapshot(subgraph_id: str, _key: str = Depends(verify_api_key)):
    """Extract a new snapshot of the subgraph."""
    result = await _extractor.extract_snapshot(subgraph_id)
    return result


@router.get("/{subgraph_id}/diff")
async def diff_snapshots(
    subgraph_id: str,
    snapshot_a: str = Query(...),
    snapshot_b: str = Query(...),
    _key: str = Depends(verify_api_key),
):
    """Compare two snapshots of the same subgraph."""
    diff = await _differ.diff_snapshots(snapshot_a, snapshot_b)
    return {
        "snapshot_a": diff.snapshot_a,
        "snapshot_b": diff.snapshot_b,
        "nodes_added": diff.nodes_added,
        "nodes_removed": diff.nodes_removed,
        "edges_added": diff.edges_added,
        "edges_removed": diff.edges_removed,
        "net_node_delta": diff.net_node_delta,
        "net_edge_delta": diff.net_edge_delta,
    }


@router.get("/{snapshot_id}/export")
async def export_snapshot(
    snapshot_id: str,
    fmt: str = Query("cytoscape_json", enum=["cytoscape_json", "adjacency_list", "csv"]),
    _key: str = Depends(verify_api_key),
):
    """Export a snapshot in the specified format."""
    content = await _exporter.export(snapshot_id=snapshot_id, fmt=fmt)
    if fmt == "csv":
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(content, media_type="text/csv")
    return {"format": fmt, "content": content}
