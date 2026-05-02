"""
GDS (Graph Data Science) client.
All GDS procedures run as explicit Cypher calls so we never need the GDS Python client library.
This keeps the dependency tree clean and works with Neo4j GDS plugin 2.x.
"""
import logging
from typing import Any

from .neo4j_client import get_session
from .config import settings

logger = logging.getLogger(__name__)

PROJECTION_NAME = settings.gds_projection_name

# Node labels included in the full projection
PROJECTED_NODE_LABELS = ["Company", "Director", "Address", "RegulatoryAction", "LegalCase"]

# Relationship types included
PROJECTED_REL_TYPES = [
    "DIRECTED", "OWNS", "SUBSIDIARY_OF", "REGISTERED_AT",
    "SHARES_DIRECTOR_WITH", "SHARES_ADDRESS_WITH", "COMMON_BENEFICIAL_OWNER",
    "HAS_REGULATORY_ACTION", "HAS_LEGAL_CASE",
]


async def ensure_projection_dropped() -> None:
    """Drop projection if it exists — used at start of batch to reclaim memory."""
    async with get_session() as s:
        result = await s.run(
            "CALL gds.graph.exists($name) YIELD exists RETURN exists",
            name=PROJECTION_NAME,
        )
        rec = await result.single()
        if rec and rec["exists"]:
            await s.run("CALL gds.graph.drop($name)", name=PROJECTION_NAME)
            logger.info("GDS projection '%s' dropped", PROJECTION_NAME)


async def create_projection() -> dict[str, Any]:
    """Create the full satorix-full projection for batch runs."""
    await ensure_projection_dropped()
    async with get_session() as s:
        result = await s.run(
            """
            CALL gds.graph.project(
                $name,
                $nodeLabels,
                $relTypes,
                {
                    nodeProperties: ['riskScore'],
                    relationshipProperties: ['weight']
                }
            )
            YIELD graphName, nodeCount, relationshipCount
            RETURN graphName, nodeCount, relationshipCount
            """,
            name=PROJECTION_NAME,
            nodeLabels=PROJECTED_NODE_LABELS,
            relTypes=PROJECTED_REL_TYPES,
        )
        rec = await result.single()
        stats = dict(rec) if rec else {}
        logger.info(
            "GDS projection '%s' created: %d nodes, %d rels",
            PROJECTION_NAME,
            stats.get("nodeCount", 0),
            stats.get("relationshipCount", 0),
        )
        return stats


async def run_pagerank(
    projection: str = PROJECTION_NAME,
    max_iterations: int = 20,
    damping_factor: float = 0.85,
) -> list[dict]:
    async with get_session() as s:
        result = await s.run(
            """
            CALL gds.pageRank.stream($projection, {
                maxIterations: $maxIter,
                dampingFactor: $damp
            })
            YIELD nodeId, score
            RETURN gds.util.asNode(nodeId).id AS entityId,
                   labels(gds.util.asNode(nodeId))[0] AS entityType,
                   score
            ORDER BY score DESC
            """,
            projection=projection,
            maxIter=max_iterations,
            damp=damping_factor,
        )
        return [dict(r) for r in await result.fetch(10_000)]


async def run_betweenness(
    projection: str = PROJECTION_NAME,
    sampled: bool = False,
    sample_size: int = 100,
) -> list[dict]:
    proc = "gds.betweenness.stream" if not sampled else "gds.betweenness.stream"
    config: dict[str, Any] = {}
    if sampled:
        config["samplingSize"] = sample_size
        config["samplingSeed"] = 42
    async with get_session() as s:
        result = await s.run(
            f"""
            CALL {proc}($projection, $config)
            YIELD nodeId, score
            RETURN gds.util.asNode(nodeId).id AS entityId,
                   labels(gds.util.asNode(nodeId))[0] AS entityType,
                   score
            ORDER BY score DESC
            LIMIT 1000
            """,
            projection=projection,
            config=config,
        )
        return [dict(r) for r in await result.fetch(1000)]


async def run_louvain(projection: str = PROJECTION_NAME) -> list[dict]:
    async with get_session() as s:
        result = await s.run(
            """
            CALL gds.louvain.stream($projection, {
                includeIntermediateCommunities: false
            })
            YIELD nodeId, communityId
            RETURN gds.util.asNode(nodeId).id AS entityId,
                   labels(gds.util.asNode(nodeId))[0] AS entityType,
                   communityId
            """,
            projection=projection,
        )
        return [dict(r) for r in await result.fetch(100_000)]


async def run_label_propagation(projection: str = PROJECTION_NAME) -> list[dict]:
    async with get_session() as s:
        result = await s.run(
            """
            CALL gds.labelPropagation.stream($projection)
            YIELD nodeId, communityId
            RETURN gds.util.asNode(nodeId).id AS entityId,
                   labels(gds.util.asNode(nodeId))[0] AS entityType,
                   communityId
            """,
            projection=projection,
        )
        return [dict(r) for r in await result.fetch(100_000)]


async def run_wcc(projection: str = PROJECTION_NAME) -> list[dict]:
    """Weakly connected components — used for subgraph boundary detection."""
    async with get_session() as s:
        result = await s.run(
            """
            CALL gds.wcc.stream($projection)
            YIELD nodeId, componentId
            RETURN gds.util.asNode(nodeId).id AS entityId,
                   labels(gds.util.asNode(nodeId))[0] AS entityType,
                   componentId
            """,
            projection=projection,
        )
        return [dict(r) for r in await result.fetch(100_000)]


async def run_shortest_path_dijkstra(
    source_id: str,
    target_id: str,
    projection: str = PROJECTION_NAME,
) -> list[dict]:
    async with get_session() as s:
        result = await s.run(
            """
            MATCH (source {id: $sourceId}), (target {id: $targetId})
            CALL gds.shortestPath.dijkstra.stream($projection, {
                sourceNode: source,
                targetNode: target,
                relationshipWeightProperty: 'weight'
            })
            YIELD index, sourceNode, targetNode, totalCost, nodeIds, costs, path
            RETURN
                [nid IN nodeIds | gds.util.asNode(nid).id] AS nodePath,
                [nid IN nodeIds | labels(gds.util.asNode(nid))[0]] AS nodeTypes,
                totalCost,
                costs
            """,
            sourceId=source_id,
            targetId=target_id,
            projection=projection,
        )
        return [dict(r) for r in await result.fetch(10)]
