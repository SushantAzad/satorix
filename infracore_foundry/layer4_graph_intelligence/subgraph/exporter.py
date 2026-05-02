"""
SubgraphExporter — serializes snapshots to multiple formats.
Formats: cytoscape_json | graphml | adjacency_list | csv
"""
import csv
import io
import json
import logging
from typing import Any

from core.database import get_pool

logger = logging.getLogger(__name__)


class SubgraphExporter:
    async def export(self, snapshot_id: str, fmt: str = "cytoscape_json") -> str:
        pool = get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT nodes, edges FROM l4_subgraph_snapshots WHERE snapshot_id = $1",
                snapshot_id,
            )
        if not row:
            raise ValueError(f"Snapshot not found: {snapshot_id}")

        nodes = json.loads(row["nodes"])
        edges = json.loads(row["edges"])

        if fmt == "cytoscape_json":
            return self._to_cytoscape(nodes, edges)
        elif fmt == "adjacency_list":
            return self._to_adjacency(nodes, edges)
        elif fmt == "csv":
            return self._to_csv(nodes, edges)
        else:
            raise ValueError(f"Unsupported export format: {fmt}")

    def _to_cytoscape(self, nodes: list[dict], edges: list[dict]) -> str:
        elements = []
        for n in nodes:
            elements.append({"group": "nodes", "data": {"id": n["id"], "label": n.get("label", n["id"]), "type": n.get("type", ""), **n.get("properties", {})}})
        for e in edges:
            elements.append({"group": "edges", "data": {"source": e["source"], "target": e["target"], "type": e.get("type", ""), **e.get("properties", {})}})
        return json.dumps({"elements": elements}, default=str)

    def _to_adjacency(self, nodes: list[dict], edges: list[dict]) -> str:
        adj: dict[str, list[str]] = {n["id"]: [] for n in nodes}
        for e in edges:
            adj.get(e["source"], []).append(e["target"])
        lines = [f"{src}: {', '.join(tgts)}" for src, tgts in adj.items()]
        return "\n".join(lines)

    def _to_csv(self, nodes: list[dict], edges: list[dict]) -> str:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["source", "target", "type"])
        for e in edges:
            writer.writerow([e["source"], e["target"], e.get("type", "")])
        return buf.getvalue()
