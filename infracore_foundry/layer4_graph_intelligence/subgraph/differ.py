"""
SubgraphDiffer — computes structural differences between two subgraph snapshots.
"""
import json
import logging
from dataclasses import dataclass

from core.database import get_pool

logger = logging.getLogger(__name__)


@dataclass
class SnapshotDiff:
    snapshot_a: str
    snapshot_b: str
    nodes_added: list[str]
    nodes_removed: list[str]
    edges_added: list[dict]
    edges_removed: list[dict]
    net_node_delta: int
    net_edge_delta: int


class SubgraphDiffer:
    async def diff_snapshots(self, snapshot_id_a: str, snapshot_id_b: str) -> SnapshotDiff:
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT snapshot_id, nodes, edges FROM l4_subgraph_snapshots WHERE snapshot_id = ANY($1)",
                [snapshot_id_a, snapshot_id_b],
            )

        snaps = {r["snapshot_id"]: r for r in rows}
        if snapshot_id_a not in snaps or snapshot_id_b not in snaps:
            raise ValueError(f"Snapshot not found: {snapshot_id_a} or {snapshot_id_b}")

        nodes_a = {n["id"] for n in json.loads(snaps[snapshot_id_a]["nodes"])}
        nodes_b = {n["id"] for n in json.loads(snaps[snapshot_id_b]["nodes"])}

        def edge_key(e: dict) -> str:
            return f"{e['source']}__{e['target']}__{e['type']}"

        edges_a = {edge_key(e): e for e in json.loads(snaps[snapshot_id_a]["edges"])}
        edges_b = {edge_key(e): e for e in json.loads(snaps[snapshot_id_b]["edges"])}

        return SnapshotDiff(
            snapshot_a=snapshot_id_a,
            snapshot_b=snapshot_id_b,
            nodes_added=list(nodes_b - nodes_a),
            nodes_removed=list(nodes_a - nodes_b),
            edges_added=[edges_b[k] for k in (edges_b.keys() - edges_a.keys())],
            edges_removed=[edges_a[k] for k in (edges_a.keys() - edges_b.keys())],
            net_node_delta=len(nodes_b) - len(nodes_a),
            net_edge_delta=len(edges_b) - len(edges_a),
        )
