from elasticsearch import AsyncElasticsearch
from typing import Any, Optional
import logging
from .config import settings

logger = logging.getLogger(__name__)

PLATFORM_GLOBAL = "PLATFORM_GLOBAL"

OBJECT_TYPE_INDICES = [
    "company", "director", "project", "regulatory_action",
    "legal_case", "insolvency_proceeding", "address",
    "regulatory_body", "government_entity", "event", "alert",
]

# clientId field is included in every index so tenant-scoped searches are O(1).
_CLIENT_ID_FIELD: dict = {"clientId": {"type": "keyword"}}

INDEX_MAPPINGS: dict[str, dict] = {
    "company": {
        "mappings": {
            "properties": {
                "cin": {"type": "keyword"},
                "name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "status": {"type": "keyword"},
                "registeredState": {"type": "keyword"},
                "riskScore": {"type": "integer"},
                "companyType": {"type": "keyword"},
                "industry": {"type": "text"},
                "registeredAddress": {"type": "text"},
                "lastUpdated": {"type": "date"},
                **_CLIENT_ID_FIELD,
            }
        }
    },
    "director": {
        "mappings": {
            "properties": {
                "din": {"type": "keyword"},
                "name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "nationality": {"type": "keyword"},
                "city": {"type": "keyword"},
                "disqualificationStatus": {"type": "keyword"},
                "riskScore": {"type": "integer"},
                "isOffshore": {"type": "boolean"},
                **_CLIENT_ID_FIELD,
            }
        }
    },
    "project": {
        "mappings": {
            "properties": {
                "projectId": {"type": "keyword"},
                "name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "status": {"type": "keyword"},
                "state": {"type": "keyword"},
                "projectType": {"type": "keyword"},
                "riskScore": {"type": "integer"},
                **_CLIENT_ID_FIELD,
            }
        }
    },
    "regulatory_action": {
        "mappings": {
            "properties": {
                "actionId": {"type": "keyword"},
                "issuingBody": {"type": "keyword"},
                "actionType": {"type": "keyword"},
                "status": {"type": "keyword"},
                "description": {"type": "text"},
                **_CLIENT_ID_FIELD,
            }
        }
    },
    "alert": {
        "mappings": {
            "properties": {
                "alertId": {"type": "keyword"},
                "severity": {"type": "keyword"},
                "alertType": {"type": "keyword"},
                "title": {"type": "text"},
                "message": {"type": "text"},
                "isActive": {"type": "boolean"},
                "createdAt": {"type": "date"},
                **_CLIENT_ID_FIELD,
            }
        }
    },
}


class ElasticsearchClient:
    def __init__(self) -> None:
        self._client: Optional[AsyncElasticsearch] = None

    async def connect(self) -> None:
        self._client = AsyncElasticsearch(
            [settings.elasticsearch_url],
            retry_on_timeout=True,
            max_retries=3,
        )
        info = await self._client.info()
        logger.info("Elasticsearch connected: version %s", info["version"]["number"])
        await self._setup_indices()

    async def _setup_indices(self) -> None:
        for index_name in OBJECT_TYPE_INDICES:
            exists = await self._client.indices.exists(index=f"ontology_{index_name}")
            if not exists:
                mapping = INDEX_MAPPINGS.get(index_name, {})
                await self._client.indices.create(index=f"ontology_{index_name}", body=mapping)
                logger.info("Created ES index: ontology_%s", index_name)

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            logger.info("Elasticsearch connection closed")

    @property
    def client(self) -> AsyncElasticsearch:
        if not self._client:
            raise RuntimeError("Elasticsearch client not initialized")
        return self._client

    def index_name(self, object_type: str) -> str:
        return f"ontology_{object_type.lower()}"

    async def index_document(
        self,
        object_type: str,
        doc_id: str,
        body: dict[str, Any],
        client_id: str = PLATFORM_GLOBAL,
    ) -> None:
        document = {**body, "clientId": client_id}
        await self.client.index(
            index=self.index_name(object_type),
            id=doc_id,
            document=document,
        )

    async def search(
        self,
        query: str,
        object_types: list[str] | None = None,
        filters: dict[str, Any] | None = None,
        size: int = 50,
        client_id: str = PLATFORM_GLOBAL,
    ) -> list[dict[str, Any]]:
        indices = (
            [self.index_name(ot) for ot in object_types]
            if object_types
            else [self.index_name(ot) for ot in OBJECT_TYPE_INDICES]
        )

        must_clauses: list[dict] = [
            {
                "multi_match": {
                    "query": query,
                    "fields": ["name^3", "description^2", "*"],
                    "type": "best_fields",
                    "fuzziness": "AUTO",
                }
            }
        ]

        # Tenant isolation: match caller's clientId OR PLATFORM_GLOBAL documents.
        filter_clauses: list[dict] = [
            {
                "bool": {
                    "should": [
                        {"term": {"clientId": client_id}},
                        {"term": {"clientId": PLATFORM_GLOBAL}},
                    ],
                    "minimum_should_match": 1,
                }
            }
        ]
        if filters:
            for field, value in filters.items():
                if value is not None:
                    filter_clauses.append({"term": {field: value}})

        es_query: dict[str, Any] = {
            "query": {
                "bool": {
                    "must": must_clauses,
                    "filter": filter_clauses,
                }
            },
            "highlight": {
                "fields": {"name": {}, "description": {}, "title": {}},
                "pre_tags": ["<em>"],
                "post_tags": ["</em>"],
            },
            "size": size,
        }

        response = await self.client.search(index=",".join(indices), body=es_query)
        results = []
        for hit in response["hits"]["hits"]:
            results.append({
                "id": hit["_id"],
                "index": hit["_index"],
                "score": hit["_score"],
                "source": hit["_source"],
                "highlights": hit.get("highlight", {}),
            })
        return results

    async def delete_document(self, object_type: str, doc_id: str) -> None:
        try:
            await self.client.delete(index=self.index_name(object_type), id=doc_id)
        except Exception:
            pass


es_client = ElasticsearchClient()
