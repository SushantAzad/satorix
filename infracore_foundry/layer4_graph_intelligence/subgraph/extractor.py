"""
SubgraphExtractor — extracts a named subgraph around a seed entity.
Definitions stored in l4_subgraph_definitions; snapshots in l4_subgraph_snapshots.
"""
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone

from core.database import get_pool
from core.neo4j_client import get_session
from network.network_mapper import NetworkMapper, NetworkMap

logger = logging.getLogger(__name__)


class SubgraphExtractor:
    def __init__(self) -> None:
        self._mapper = NetworkMapper()

    async def create_definition(
        self,
        name: str,
        seed_entity_id: str,
        seed_entity_type: str,
        hops: int = 2,
        node_types: list[str] | None = None,
        edge_types: list[str] | None = None,
        filters: dict | None = None,
        created_by: str = "system",
    ) -> str:
        subgraph_id = f"sg-{hashlib.sha256(f'{name}{seed_entity_id}'.encode()).hexdigest()[:12]}"
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO l4_subgraph_definitions
                    (subgraph_id, name, seed_entity_id, seed_entity_type, hops,
                     node_types, edge_types, filters, created_by)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (subgraph_id) DO UPDATE SET name = EXCLUDED.name
                """,
                subgraph_id, name, seed_entity_id, seed_entity_type, hops,
                json.dumps(node_types or []), json.dumps(edge_types or []),
                json.dumps(filters or {}), created_by,
            )
        return subgraph_id

    async def extract_snapshot(self, subgraph_id: str) -> dict:
        pool = get_pool()
        async with pool.acquire() as conn:
            defn = await conn.fetchrow(
                "SELECT * FROM l4_subgraph_definitions WHERE subgraph_id = $1",
                subgraph_id,
            )
        if not defn:
            raise ValueError(f"Subgraph definition not found: {subgraph_id}")

        defn = dict(defn)
        network: NetworkMap = await self._mapper.expand(
            seed_id=defn["seed_entity_id"],
            hops=defn["hops"],
            node_types=json.loads(defn["node_types"]) or None,
            rel_types=json.loads(defn["edge_types"]) or None,
        )

        snapshot_id = f"snap-{uuid.uuid4().hex[:12]}"
        network_dict = network.to_dict()

        pool = get_pool()
        async with pool.acquire() as conn:
            prev = await conn.fetchrow(
                "SELECT nodes, edges FROM l4_subgraph_snapshots WHERE subgraph_id=$1 ORDER BY created_at DESC LIMIT 1",
                subgraph_id,
            )
            diff = self._compute_diff(prev, network_dict) if prev else None
            await conn.execute(
                """
                INSERT INTO l4_subgraph_snapshots
                    (subgraph_id, snapshot_id, node_count, edge_count, nodes, edges, diff_from_prev, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                subgraph_id, snapshot_id,
                network.node_count, network.edge_count,
                json.dumps(network_dict["nodes"]),
                json.dumps(network_dict["edges"]),
                json.dumps(diff) if diff else None,
                datetime.now(timezone.utc),
            )

        return {
            "subgraph_id": subgraph_id,
            "snapshot_id": snapshot_id,
            "node_count": network.node_count,
            "edge_count": network.edge_count,
            "has_diff": diff is not None,
        }

    def _compute_diff(self, prev_row, current: dict) -> dict:
        prev_nodes = set(n["id"] for n in json.loads(prev_row["nodes"]))
        curr_nodes = set(n["id"] for n in current["nodes"])
        return {
            "nodes_added": list(curr_nodes - prev_nodes),
            "nodes_removed": list(prev_nodes - curr_nodes),
            "node_delta": len(curr_nodes) - len(prev_nodes),
        }
