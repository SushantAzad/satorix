"""
QueryExecutor — end-to-end handler: parse → compose → log → return.
"""
import logging
import time
import uuid
from datetime import datetime, timezone

from core.database import get_pool
from .query_parser import QueryParser
from .query_composer import QueryComposer

logger = logging.getLogger(__name__)


class QueryExecutor:
    def __init__(self) -> None:
        self._parser = QueryParser()
        self._composer = QueryComposer()

    async def execute_natural_language(
        self,
        query: str,
        requested_by: str = "anonymous",
    ) -> dict:
        query_id = f"q-{uuid.uuid4().hex[:12]}"
        start = time.monotonic()

        parsed = await self._parser.parse(query)
        result = await self._composer.execute(parsed)

        duration_ms = (time.monotonic() - start) * 1000
        await self._log(
            query_id=query_id,
            query_type=parsed.intent,
            params=parsed.to_dict(),
            result_count=self._count_result(result),
            cache_hit=False,
            duration_ms=duration_ms,
            requested_by=requested_by,
        )
        return {"query_id": query_id, "parsed": parsed.to_dict(), "result": result}

    async def _log(self, **kwargs) -> None:
        try:
            pool = get_pool()
            async with pool.acquire() as conn:
                import json
                await conn.execute(
                    """
                    INSERT INTO l4_query_log
                        (query_id, query_type, params, result_count, cache_hit, duration_ms, requested_by, requested_at)
                    VALUES ($1, $2, $3::jsonb, $4, $5, $6, $7, $8)
                    """,
                    kwargs["query_id"], kwargs["query_type"],
                    json.dumps(kwargs["params"]),
                    kwargs["result_count"], kwargs["cache_hit"],
                    kwargs["duration_ms"], kwargs["requested_by"],
                    datetime.now(timezone.utc),
                )
        except Exception as exc:
            logger.warning("Query log failed: %s", exc)

    def _count_result(self, result: dict) -> int:
        inner = result.get("result")
        if isinstance(inner, list):
            return len(inner)
        if isinstance(inner, dict):
            return inner.get("node_count", inner.get("total_found", 1))
        return 0
