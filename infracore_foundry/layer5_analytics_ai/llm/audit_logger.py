"""
Logs every LLM call to l5_llm_audit. Called by LLMOrchestrator — never called directly.
"""
import hashlib
import json
import logging
from datetime import datetime, timezone

from core.database import get_pool

logger = logging.getLogger(__name__)


async def log_llm_call(
    workflow_type: str,
    actor_id: str,
    actor_role: str,
    model_used: str,
    prompt_text: str,
    prompt_tokens: int,
    completion_tokens: int,
    objects_accessed: list[str],
    output_disposition: str,
    success: bool,
    latency_ms: int,
    error_message: str | None = None,
) -> None:
    prompt_hash = hashlib.sha256(prompt_text.encode()).hexdigest()[:64]
    pool = get_pool()
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO l5_llm_audit
                    (workflow_type, actor_id, actor_role, model_used,
                     prompt_tokens, completion_tokens, objects_accessed,
                     output_disposition, prompt_hash, success, latency_ms, error_message)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9, $10, $11, $12)
                """,
                workflow_type, actor_id, actor_role, model_used,
                prompt_tokens, completion_tokens,
                json.dumps(objects_accessed),
                output_disposition, prompt_hash,
                success, latency_ms, error_message,
            )
    except Exception as exc:
        logger.warning("LLM audit log write failed: %s", exc)
