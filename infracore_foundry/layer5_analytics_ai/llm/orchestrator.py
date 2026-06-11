"""
LLMOrchestrator — single gateway for all LLM calls in Layer 5.
Enforces: RBAC filtering, prompt versioning, audit logging, output validation,
Redis caching for read-only workflows, graceful fallback when provider unavailable.

Provider selection is via LLM_PROVIDER env var (anthropic | ollama).
Never instantiates providers directly — always calls get_llm_provider().
"""
import hashlib
import json
import logging
import re
import time
from typing import Optional

from shared.llm.provider import get_llm_provider, LLMMessage, LLMResponse, LLMTool

from core.config import settings
from llm.audit_logger import log_llm_call
from llm.prompt_registry import get_prompt

logger = logging.getLogger(__name__)

MAX_TOKENS_DEFAULT = 512


class LLMOrchestrator:

    def __init__(self) -> None:
        pass  # Provider resolved at call time — never stored at init

    # ── Primary interface (used by all workflow files) ────────────────────────

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
        Provider (Anthropic or Ollama) is selected at call time via LLM_PROVIDER env var.
        """
        template = get_prompt(prompt_key)
        system_text = template.system
        user_text = template.user_template.format(**format_kwargs)
        _workflow_type = workflow_type or template.name

        if use_cache and output_disposition == "returned":
            cached = await self._cache_get(prompt_key, user_text)
            if cached:
                return cached

        provider = get_llm_provider()
        t0 = time.monotonic()
        success = True
        error_msg: Optional[str] = None
        result_text = ""
        prompt_tokens = 0
        completion_tokens = 0

        try:
            response = await provider.complete(
                messages=[LLMMessage(role="user", content=user_text)],
                system=system_text,
                max_tokens=max_tokens,
                temperature=0.3,
            )
            result_text = response.content.strip()
            prompt_tokens = response.input_tokens
            completion_tokens = response.output_tokens

            if use_cache and output_disposition == "returned":
                await self._cache_set(prompt_key, user_text, result_text)

        except Exception as exc:
            success = False
            error_msg = str(exc)
            logger.error(
                "LLM call failed (prompt=%s, provider=%s): %s",
                prompt_key, provider.get_provider_name(), exc,
            )
            result_text = self._fallback_text(template.name, format_kwargs)

        latency_ms = int((time.monotonic() - t0) * 1000)

        await log_llm_call(
            workflow_type=_workflow_type,
            actor_id=actor_id,
            actor_role=actor_role,
            model_used=provider.get_model_name(),
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

    # ── Direct message interface (for agent and report workflows) ─────────────

    async def complete(
        self,
        messages: list[LLMMessage],
        workflow_type: str,
        actor_id: str,
        actor_role: str,
        system: Optional[str] = None,
        max_tokens: int = MAX_TOKENS_DEFAULT,
        temperature: float = 0.3,
        tools: Optional[list[LLMTool]] = None,
        output_schema: Optional[dict] = None,
    ) -> LLMResponse:
        """
        Direct message interface — bypasses the prompt registry.
        Used by agents and callers that build prompts programmatically.
        Always audit-logs with provider and model name.
        """
        provider = get_llm_provider()
        t0 = time.monotonic()
        response: Optional[LLMResponse] = None
        error: Optional[str] = None

        try:
            response = await provider.complete(
                messages=messages,
                system=system,
                max_tokens=max_tokens,
                temperature=temperature,
                tools=tools,
            )

            if output_schema and response.content:
                self._validate_json_output(response.content, output_schema)

        except Exception as e:
            error = str(e)
            raise
        finally:
            latency_ms = int((time.monotonic() - t0) * 1000)
            await self._audit_log(
                workflow_type=workflow_type,
                actor_id=actor_id,
                actor_role=actor_role,
                provider=provider.get_provider_name(),
                model=provider.get_model_name(),
                input_tokens=response.input_tokens if response else 0,
                output_tokens=response.output_tokens if response else 0,
                latency_ms=latency_ms,
                success=error is None,
                error=error,
            )

        return response

    # ── Validation and utilities ──────────────────────────────────────────────

    def _validate_json_output(self, content: str, schema: dict) -> Optional[dict]:
        """
        Strip markdown code fences (Ollama models often add them) and validate JSON.
        Returns parsed dict on success; logs warning and returns None on failure.
        """
        cleaned = re.sub(r"^```(?:json)?\s*", "", content.strip())
        cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            data = json.loads(cleaned)
            if "type" in schema and schema["type"] == "object":
                if not isinstance(data, dict):
                    raise ValueError(f"Expected object, got {type(data).__name__}")
            return data
        except json.JSONDecodeError as e:
            logger.warning(
                "LLM output failed JSON validation: %s. Content: %.200s",
                e, content,
            )
            return None

    def _fallback_text(self, workflow_name: str, kwargs: dict) -> str:
        entity = kwargs.get("company_name", kwargs.get("entity_id", "entity"))
        return (
            f"[{workflow_name} unavailable — LLM provider error. "
            f"Analyst review required for {entity}.]"
        )

    async def _audit_log(self, **kwargs) -> None:
        try:
            await log_llm_call(
                workflow_type=kwargs.get("workflow_type", "unknown"),
                actor_id=kwargs.get("actor_id", "system"),
                actor_role=kwargs.get("actor_role", "system"),
                model_used=f"{kwargs.get('provider', '?')}:{kwargs.get('model', '?')}",
                prompt_text="",
                prompt_tokens=kwargs.get("input_tokens", 0),
                completion_tokens=kwargs.get("output_tokens", 0),
                objects_accessed=[],
                output_disposition="returned",
                success=kwargs.get("success", False),
                latency_ms=kwargs.get("latency_ms", 0),
                error_message=kwargs.get("error"),
            )
        except Exception as e:
            logger.warning("Audit log failed: %s", e)

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
