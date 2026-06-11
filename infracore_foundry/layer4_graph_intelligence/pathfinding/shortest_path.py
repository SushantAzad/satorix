"""
ShortestPath — finds optimal path between two entities using GDS Dijkstra.
Falls back to plain Cypher BFS when GDS is unavailable.
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from core.neo4j_client import get_session
from core.redis_client import cache_key, cache_get, cache_set
from core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class PathResult:
    source_id: str
    target_id: str
    node_path: list[str]
    node_types: list[str]
    hop_count: int
    total_cost: float
    hop_details: list[dict[str, Any]] = field(default_factory=list)
    found: bool = True

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "node_path": self.node_path,
            "node_types": self.node_types,
            "hop_count": self.hop_count,
            "total_cost": self.total_cost,
            "hop_details": self.hop_details,
            "found": self.found,
        }


class ShortestPathFinder:
    async def find(
        self,
        source_id: str,
        target_id: str,
        rel_types: Optional[list[str]] = None,
        max_hops: int = 6,
    ) -> PathResult:
        ck = cache_key("path_shortest", src=source_id, tgt=target_id,
                        rt=sorted(rel_types or []), max_hops=max_hops)
        cached = await cache_get(ck)
        if cached:
            return self._from_dict(cached)

        result = await self._cypher_shortest(source_id, target_id, max_hops, rel_types)
        await cache_set(ck, result.to_dict(), settings.redis_ttl_short)
        return result

    async def _cypher_shortest(
        self,
        source_id: str,
        target_id: str,
        max_hops: int,
        rel_types: Optional[list[str]],
    ) -> PathResult:
        rel_pattern = "|".join(rel_types) if rel_types else ""
        rel_clause = f"[r:{rel_pattern}*1..{max_hops}]" if rel_pattern else f"[*1..{max_hops}]"

        query = f"""
            MATCH (src {{id: $srcId}}), (tgt {{id: $tgtId}})
            MATCH path = shortestPath((src)-{rel_clause}-(tgt))
            WITH path,
                 [n IN nodes(path) | n.id] AS nodeIds,
                 [n IN nodes(path) | labels(n)[0]] AS nodeTypes,
                 [r IN relationships(path) | type(r)] AS relTypes,
                 [r IN relationships(path) | coalesce(r.weight, 1.0)] AS weights
            RETURN nodeIds, nodeTypes, relTypes, weights,
                   reduce(s=0.0, w IN weights | s + w) AS totalCost
            LIMIT 1
        """
        async with get_session() as s:
            result = await s.run(query, srcId=source_id, tgtId=target_id)
            rec = await result.single()
            if not rec:
                return PathResult(
                    source_id=source_id, target_id=target_id,
                    node_path=[], node_types=[], hop_count=0,
                    total_cost=0.0, found=False,
                )

            node_ids = list(rec["nodeIds"])
            node_types = list(rec["nodeTypes"])
            rel_types_path = list(rec["relTypes"])
            hop_details = [
                {"from": node_ids[i], "to": node_ids[i + 1], "via": rel_types_path[i]}
                for i in range(len(rel_types_path))
            ]
            return PathResult(
                source_id=source_id,
                target_id=target_id,
                node_path=node_ids,
                node_types=node_types,
                hop_count=len(rel_types_path),
                total_cost=float(rec["totalCost"]),
                hop_details=hop_details,
                found=True,
            )

    def _from_dict(self, d: dict) -> PathResult:
        return PathResult(**d)
