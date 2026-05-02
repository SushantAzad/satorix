"""
TraversalEngine — cursor-based BFS/DFS traversal with streaming support.
Useful for very large subgraphs where full expand would OOM.
"""
import asyncio
import logging
from typing import AsyncIterator, Optional
from dataclasses import dataclass

from core.neo4j_client import get_session

logger = logging.getLogger(__name__)


@dataclass
class TraversalStep:
    entity_id: str
    entity_type: str
    depth: int
    via_rel: Optional[str]
    via_entity_id: Optional[str]


class TraversalEngine:
    """
    BFS traversal yielding steps one at a time.
    Callers iterate via `async for step in engine.bfs(...)`.
    """

    async def bfs(
        self,
        seed_id: str,
        max_depth: int = 3,
        rel_types: Optional[list[str]] = None,
        node_types: Optional[list[str]] = None,
        max_nodes: int = 1000,
    ) -> AsyncIterator[TraversalStep]:
        visited: set[str] = set()
        queue: list[tuple[str, int]] = [(seed_id, 0)]
        visited.add(seed_id)
        yielded = 0

        while queue and yielded < max_nodes:
            current_id, depth = queue.pop(0)
            yield TraversalStep(
                entity_id=current_id,
                entity_type="unknown",
                depth=depth,
                via_rel=None,
                via_entity_id=None,
            )
            yielded += 1

            if depth >= max_depth:
                continue

            neighbors = await self._get_neighbors(current_id, rel_types, node_types)
            for neighbor_id, neighbor_type, rel_type in neighbors:
                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    queue.append((neighbor_id, depth + 1))
                    yield TraversalStep(
                        entity_id=neighbor_id,
                        entity_type=neighbor_type,
                        depth=depth + 1,
                        via_rel=rel_type,
                        via_entity_id=current_id,
                    )
                    yielded += 1

            await asyncio.sleep(0)  # yield event loop between batches

    async def _get_neighbors(
        self,
        entity_id: str,
        rel_types: Optional[list[str]],
        node_types: Optional[list[str]],
    ) -> list[tuple[str, str, str]]:
        rel_filter = " AND type(r) IN $relTypes" if rel_types else ""
        node_filter = " AND labels(n)[0] IN $nodeTypes" if node_types else ""
        query = f"""
            MATCH (e {{id: $id}})-[r]-(n)
            WHERE 1=1{rel_filter}{node_filter}
            RETURN n.id AS nid, labels(n)[0] AS ntype, type(r) AS rtype
            LIMIT 50
        """
        params: dict = {"id": entity_id}
        if rel_types:
            params["relTypes"] = rel_types
        if node_types:
            params["nodeTypes"] = node_types

        async with get_session() as s:
            result = await s.run(query, **params)
            return [(r["nid"], r["ntype"], r["rtype"]) for r in await result.fetch(50)]
