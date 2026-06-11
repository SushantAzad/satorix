from storage.neo4j_store import Neo4jStore
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class PathFinder:
    def __init__(self) -> None:
        self._store = Neo4jStore()

    async def find_shortest_path(
        self,
        source_type: str,
        source_id: str,
        target_type: str,
        target_id: str,
        max_depth: int = 5,
    ) -> Optional[list[dict]]:
        return await self._store.find_shortest_path(source_type, source_id, target_type, target_id, max_depth)


path_finder = PathFinder()
