"""
NetworkMapper — expands a seed entity outward N hops, applying type/weight filters.
Returns the subgraph as node+edge lists suitable for Cytoscape.js rendering.
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from core.neo4j_client import get_session
from core.redis_client import cache_key, cache_get, cache_set
from core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class GraphNode:
    id: str
    type: str
    label: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphEdge:
    source: str
    target: str
    type: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class NetworkMap:
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    seed_id: str
    hops: int
    node_count: int = 0
    edge_count: int = 0

    def __post_init__(self):
        self.node_count = len(self.nodes)
        self.edge_count = len(self.edges)

    def to_dict(self) -> dict:
        return {
            "seed_id": self.seed_id,
            "hops": self.hops,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "nodes": [
                {"id": n.id, "type": n.type, "label": n.label, "properties": n.properties}
                for n in self.nodes
            ],
            "edges": [
                {"source": e.source, "target": e.target, "type": e.type, "properties": e.properties}
                for e in self.edges
            ],
        }


class NetworkMapper:
    ALLOWED_NODE_TYPES = {"Company", "Director", "Address", "RegulatoryAction", "LegalCase", "GovernmentEntity"}
    ALLOWED_REL_TYPES = {
        "DIRECTED", "OWNS", "SUBSIDIARY_OF", "REGISTERED_AT",
        "SHARES_DIRECTOR_WITH", "SHARES_ADDRESS_WITH", "COMMON_BENEFICIAL_OWNER",
        "HAS_REGULATORY_ACTION", "HAS_LEGAL_CASE",
    }
    MAX_HOPS = 4
    MAX_NODES = 500

    async def expand(
        self,
        seed_id: str,
        hops: int = 2,
        node_types: Optional[list[str]] = None,
        rel_types: Optional[list[str]] = None,
        min_risk_score: float = 0.0,
        exclude_ids: Optional[list[str]] = None,
    ) -> NetworkMap:
        hops = min(hops, self.MAX_HOPS)
        ck = cache_key("network_expand", seed=seed_id, hops=hops,
                        nt=sorted(node_types or []), rt=sorted(rel_types or []),
                        min_risk=min_risk_score)
        cached = await cache_get(ck)
        if cached:
            return self._from_dict(cached)

        nt_filter = [t for t in (node_types or list(self.ALLOWED_NODE_TYPES)) if t in self.ALLOWED_NODE_TYPES]
        rt_filter = [t for t in (rel_types or list(self.ALLOWED_REL_TYPES)) if t in self.ALLOWED_REL_TYPES]
        excl = set(exclude_ids or [])

        nodes: dict[str, GraphNode] = {}
        edges: list[GraphEdge] = []
        seen_edges: set[tuple] = set()

        async with get_session() as s:
            result = await s.run(
                """
                MATCH path = (seed {id: $seedId})-[*1..$hops]-(neighbor)
                WHERE labels(neighbor)[0] IN $nodeTypes
                WITH nodes(path) AS ns, relationships(path) AS rs
                UNWIND range(0, size(rs)-1) AS i
                WITH ns[i] AS a, rs[i] AS r, ns[i+1] AS b
                WHERE type(r) IN $relTypes
                RETURN
                    a.id AS sourceId, labels(a)[0] AS sourceType, a AS sourceProps,
                    b.id AS targetId, labels(b)[0] AS targetType, b AS targetProps,
                    type(r) AS relType, properties(r) AS relProps
                LIMIT $limit
                """,
                seedId=seed_id,
                hops=hops,
                nodeTypes=nt_filter,
                relTypes=rt_filter,
                limit=self.MAX_NODES * 5,
            )
            async for record in result:
                src_id = record["sourceId"]
                tgt_id = record["targetId"]
                if src_id in excl or tgt_id in excl:
                    continue

                if src_id not in nodes:
                    props = dict(record["sourceProps"])
                    risk = props.get("riskScore", 0) or 0
                    if risk < min_risk_score and src_id != seed_id:
                        continue
                    nodes[src_id] = GraphNode(
                        id=src_id, type=record["sourceType"],
                        label=props.get("name", src_id), properties=props,
                    )
                if tgt_id not in nodes:
                    props = dict(record["targetProps"])
                    risk = props.get("riskScore", 0) or 0
                    if risk < min_risk_score and tgt_id != seed_id:
                        continue
                    nodes[tgt_id] = GraphNode(
                        id=tgt_id, type=record["targetType"],
                        label=props.get("name", tgt_id), properties=props,
                    )

                edge_key = (src_id, tgt_id, record["relType"])
                if edge_key not in seen_edges and len(nodes) <= self.MAX_NODES:
                    seen_edges.add(edge_key)
                    edges.append(GraphEdge(
                        source=src_id, target=tgt_id,
                        type=record["relType"],
                        properties=dict(record["relProps"] or {}),
                    ))

        result_map = NetworkMap(
            nodes=list(nodes.values()),
            edges=edges,
            seed_id=seed_id,
            hops=hops,
        )
        await cache_set(ck, result_map.to_dict(), settings.redis_ttl_short)
        return result_map

    def _from_dict(self, d: dict) -> NetworkMap:
        nodes = [GraphNode(id=n["id"], type=n["type"], label=n["label"], properties=n["properties"]) for n in d["nodes"]]
        edges = [GraphEdge(source=e["source"], target=e["target"], type=e["type"], properties=e["properties"]) for e in d["edges"]]
        return NetworkMap(nodes=nodes, edges=edges, seed_id=d["seed_id"], hops=d["hops"])
