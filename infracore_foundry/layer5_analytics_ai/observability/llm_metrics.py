"""LLM usage metrics — token costs, failure rates, latency distribution."""
import logging
from core.database import get_pool

logger = logging.getLogger(__name__)


async def get_llm_usage_summary(days: int = 7) -> list[dict]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                workflow_type,
                count(*) AS call_count,
                sum(prompt_tokens + completion_tokens) AS total_tokens,
                avg(latency_ms) AS avg_latency_ms,
                sum(CASE WHEN NOT success THEN 1 ELSE 0 END) AS failure_count,
                round(100.0 * sum(CASE WHEN NOT success THEN 1 ELSE 0 END) / count(*), 2) AS failure_rate_pct
            FROM l5_llm_audit
            WHERE created_at > NOW() - ($1 * INTERVAL '1 day')
            GROUP BY workflow_type
            ORDER BY total_tokens DESC
            """,
            days,
        )
        return [dict(r) for r in rows]


async def get_daily_token_usage(days: int = 30) -> list[dict]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                date_trunc('day', created_at) AS day,
                sum(prompt_tokens + completion_tokens) AS total_tokens,
                count(*) AS call_count
            FROM l5_llm_audit
            WHERE created_at > NOW() - ($1 * INTERVAL '1 day')
            GROUP BY 1
            ORDER BY 1
            """,
            days,
        )
        return [dict(r) for r in rows]
