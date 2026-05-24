from typing import Any
import logging
from core.elasticsearch_client import es_client, PLATFORM_GLOBAL

logger = logging.getLogger(__name__)


class ElasticsearchStore:
    async def index_object(
        self,
        object_type: str,
        primary_key: str,
        data: dict[str, Any],
        client_id: str = PLATFORM_GLOBAL,
    ) -> None:
        clean = {k: v for k, v in data.items() if v is not None}
        try:
            await es_client.index_document(object_type, primary_key, clean, client_id)
        except Exception as e:
            logger.error("ES index failed for %s/%s: %s", object_type, primary_key, e)
            raise

    async def search_objects(
        self,
        query: str,
        object_types: list[str] | None = None,
        filters: dict[str, Any] | None = None,
        size: int = 50,
        client_id: str = PLATFORM_GLOBAL,
    ) -> list[dict[str, Any]]:
        return await es_client.search(query, object_types, filters, size, client_id)

    async def delete_object(self, object_type: str, primary_key: str) -> None:
        await es_client.delete_document(object_type, primary_key)
