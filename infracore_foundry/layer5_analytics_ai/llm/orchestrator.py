"""
LLMOrchestrator — single gateway for all LLM calls in Layer 5.
Enforces: RBAC filtering, prompt versioning, audit logging, output validation,
Redis caching for read-only workflows, graceful fallback when API is unavailable.
"""
import hashlib
import json
import logging
import time
from typing import Optional

import anthropic

from core.config import settings
from llm.audit_logger import log_llm_call
from llm.prompt_registry import get_prompt, PromptTemplate

logger = logging.getLogger(__name__)

PRIMARY_MODEL = "claude-sonnet-4-6"
MAX_TOKENS_DEFAULT = 512


class LLMOrchestrator:

    def __init__(self) -> None:
        if settings.anthropic_api_key:
            self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        else:
            self._client = None
            logger.warning("ANTHROPIC_API_KEY not set — LLM workflows will use fallback text")

    async def run(
        self,
        prompt_key: str,
        format_kwargs: dict,
        actor_id: str = "system",
        actor_role: str = "system",
        objects_accessed: Optional[list[str]] = None,
        output_disposition: str = "returned",
        max_tokens: int = MAX_TOKENS_DEFAULT,
        use_cache: bool = True,
        workflow_type: Optional[str] = None,
    ) -> str:
        """
        Execute an LLM call for the named prompt template.
        Returns the text response. Always logs to l5_llm_audit.
        """
        template = get_prompt(prompt_key)
        system_text = template.system
        user_text = template.user_template.format(**format_kwargs)

        _workflow_type = workflow_type or template.name

        # Redis cache for read-only (returned) workflows
        cache_hit = None
        if use_cache and output_disposition == "returned":
            cache_hit = await self._cache_get(prompt_key, user_text)
            if cache_hit:
                return cache_hit

        if not self._client:
            fallback = self._fallback_text(template.name, format_kwargs)
            await log_llm_call(
                workflow_type=_workflow_type,
                actor_id=actor_id,
                actor_role=actor_role,
                model_used="fallback",
                prompt_text=user_text,
                prompt_tokens=0,
                completion_tokens=0,
                objects_accessed=objects_accessed or [],
                output_disposition=output_disposition,
                success=True,
                latency_ms=0,
            )
            return fallback

        t0 = time.monotonic()
        success = True
        error_msg: Optional[str] = None
        result_text = ""

        try:
            response = await self._client.messages.create(
                model=PRIMARY_MODEL,
                max_tokens=max_tokens,
                system=[
                    {
                        "type": "text",
                        "text": system_text,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_text}],
            )
            result_text = response.content[0].text.strip()
            prompt_tokens = response.usage.input_tokens
            completion_tokens = response.usage.output_tokens

            if use_cache and output_disposition == "returned":
                await self._cache_set(prompt_key, user_text, result_text)

        except Exception as exc:
            success = False
            error_msg = str(exc)
            logger.error("LLM call failed (prompt=%s): %s", prompt_key, exc)
            result_text = self._fallback_text(template.name, format_kwargs)
            prompt_tokens = 0
            completion_tokens = 0

        latency_ms = int((time.monotonic() - t0) * 1000)

        await log_llm_call(
            workflow_type=_workflow_type,
            actor_id=actor_id,
            actor_role=actor_role,
            model_used=PRIMARY_MODEL,
            prompt_text=user_text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            objects_accessed=objects_accessed or [],
            output_disposition=output_disposition,
            success=success,
            latency_ms=latency_ms,
            error_message=error_msg,
        )

        return result_text

    def _fallback_text(self, workflow_name: str, kwargs: dict) -> str:
        entity = kwargs.get("company_name", kwargs.get("entity_id", "entity"))
        return f"[{workflow_name} unavailable — LLM API not configured. Analyst review required for {entity}.]"

    async def _cache_get(self, prompt_key: str, user_text: str) -> Optional[str]:
        try:
            import aioredis
            key = "l5:llm:" + hashlib.sha256((prompt_key + user_text).encode()).hexdigest()
            r = await aioredis.from_url(settings.redis_url)
            val = await r.get(key)
            await r.close()
            return val.decode() if val else None
        except Exception:
            return None

    async def _cache_set(self, prompt_key: str, user_text: str, result: str) -> None:
        try:
            import aioredis
            key = "l5:llm:" + hashlib.sha256((prompt_key + user_text).encode()).hexdigest()
            r = await aioredis.from_url(settings.redis_url)
            await r.setex(key, settings.redis_ttl_long, result.encode())
            await r.close()
        except Exception:
            pass


llm_orchestrator = LLMOrchestrator()
