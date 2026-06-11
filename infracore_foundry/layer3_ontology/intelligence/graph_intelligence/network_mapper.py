from storage.neo4j_store import Neo4jStore
import logging

logger = logging.getLogger(__name__)


class NetworkMapper:
    def __init__(self) -> None:
        self._store = Neo4jStore()

    async def expand_network(
        self, object_type: str, primary_key: str, depth: int = 2
    ) -> dict:
        return await self._store.get_network(object_type, primary_key, depth)


network_mapper = NetworkMapper()
