"""
PruningEngine — removes low-signal nodes/edges from a NetworkMap.
Applied after expansion to keep Cytoscape.js rendering tractable.
"""
import logging
from .network_mapper import NetworkMap, GraphNode, GraphEdge

logger = logging.getLogger(__name__)


class PruningEngine:
    def prune(
        self,
        network: NetworkMap,
        max_nodes: int = 200,
        min_degree: int = 1,
        min_risk_score: float = 0.0,
    ) -> NetworkMap:
        degree: dict[str, int] = {}
        for edge in network.edges:
            degree[edge.source] = degree.get(edge.source, 0) + 1
            degree[edge.target] = degree.get(edge.target, 0) + 1

        # Always keep seed
        keep_ids: set[str] = {network.seed_id}
        for node in network.nodes:
            risk = node.properties.get("riskScore", 0) or 0
            deg = degree.get(node.id, 0)
            if deg >= min_degree and risk >= min_risk_score:
                keep_ids.add(node.id)

        # If still too many, sort by risk DESC and keep top N
        if len(keep_ids) > max_nodes:
            scored = sorted(
                [n for n in network.nodes if n.id in keep_ids],
                key=lambda n: (n.properties.get("riskScore") or 0),
                reverse=True,
            )
            keep_ids = {network.seed_id} | {n.id for n in scored[:max_nodes - 1]}

        nodes = [n for n in network.nodes if n.id in keep_ids]
        edges = [e for e in network.edges if e.source in keep_ids and e.target in keep_ids]

        logger.debug(
            "Pruned network %s: %d→%d nodes, %d→%d edges",
            network.seed_id,
            network.node_count, len(nodes),
            network.edge_count, len(edges),
        )
        return NetworkMap(nodes=nodes, edges=edges, seed_id=network.seed_id, hops=network.hops)
