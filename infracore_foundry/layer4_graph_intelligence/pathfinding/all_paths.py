"""
AllPaths — enumerates up to K paths between two entities, scored by risk.
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from core.neo4j_client import get_session
from core.redis_client import cache_key, cache_get, cache_set
from core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class MultiPathResult:
    source_id: str
    target_id: str
    paths: list[dict[str, Any]]
    total_found: int

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "paths": self.paths,
            "total_found": self.total_found,
        }


class AllPathsFinder:
    MAX_PATHS = 10
    MAX_HOPS = 5

    async def find_all(
        self,
        source_id: str,
        target_id: str,
        max_hops: int = 4,
        max_paths: int = 5,
        rel_types: Optional[list[str]] = None,
    ) -> MultiPathResult:
        max_hops = min(max_hops, self.MAX_HOPS)
        max_paths = min(max_paths, self.MAX_PATHS)
        ck = cache_key("path_all", src=source_id, tgt=target_id,
                        hops=max_hops, k=max_paths, rt=sorted(rel_types or []))
        cached = await cache_get(ck)
        if cached:
            return MultiPathResult(**cached)

        rel_pattern = "|".join(rel_types) if rel_types else ""
        rel_clause = f"[r:{rel_pattern}*1..{max_hops}]" if rel_pattern else f"[*1..{max_hops}]"
        query = f"""
            MATCH (src {{id: $srcId}}), (tgt {{id: $tgtId}})
            MATCH path = (src)-{rel_clause}-(tgt)
            WITH path,
                 [n IN nodes(path) | n.id] AS nodeIds,
                 [n IN nodes(path) | labels(n)[0]] AS nodeTypes,
                 [r IN relationships(path) | type(r)] AS relTypes,
                 reduce(s=0.0, n IN nodes(path) | s + coalesce(n.riskScore, 0)) AS pathRisk
            ORDER BY pathRisk DESC
            LIMIT $limit
            RETURN nodeIds, nodeTypes, relTypes, pathRisk
        """
        paths = []
        async with get_session() as s:
            result = await s.run(query, srcId=source_id, tgtId=target_id, limit=max_paths)
            async for rec in result:
                node_ids = list(rec["nodeIds"])
                rel_types_path = list(rec["relTypes"])
                paths.append({
                    "node_path": node_ids,
                    "node_types": list(rec["nodeTypes"]),
                    "hop_count": len(rel_types_path),
                    "path_risk": float(rec["pathRisk"]),
                    "hop_details": [
                        {"from": node_ids[i], "to": node_ids[i + 1], "via": rel_types_path[i]}
                        for i in range(len(rel_types_path))
                    ],
                })

        r = MultiPathResult(
            source_id=source_id,
            target_id=target_id,
            paths=paths,
            total_found=len(paths),
        )
        await cache_set(ck, r.to_dict(), settings.redis_ttl_short)
        return r
