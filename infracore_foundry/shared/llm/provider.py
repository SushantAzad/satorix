"""
Satorix LLM Provider Abstraction
Supports Anthropic (production) and Ollama (local dev/offline)
Switched by LLM_PROVIDER environment variable.
"""

import json
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class LLMProviderType(str, Enum):
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"


@dataclass
class LLMToolCall:
    """A single tool call requested by the LLM."""
    id: str           # tool_use_id for tracking
    name: str         # tool name
    input: dict       # parsed input arguments


@dataclass
class LLMToolResult:
    """Result returned to the LLM after executing a tool call."""
    tool_use_id: str
    content: str      # JSON-serialised result


@dataclass
class LLMMessage:
    role: str  # "user", "assistant"
    content: str = ""
    tool_calls: Optional[list["LLMToolCall"]] = None    # assistant → tool_use blocks
    tool_results: Optional[list["LLMToolResult"]] = None  # user → tool_result blocks


@dataclass
class LLMResponse:
    content: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    raw: dict
    tool_calls: Optional[list["LLMToolCall"]] = None  # populated when LLM requests tool use


@dataclass
class LLMTool:
    name: str
    description: str
    input_schema: dict  # JSON Schema format


class BaseLLMProvider(ABC):

    @abstractmethod
    async def complete(
        self,
        messages: list[LLMMessage],
        system: Optional[str] = None,
        max_tokens: int = 2000,
        temperature: float = 0.3,
        tools: Optional[list[LLMTool]] = None,
    ) -> LLMResponse:
        """Core completion — all providers must implement this."""
        ...

    @abstractmethod
    async def health_check(self) -> dict:
        """Returns: {healthy: bool, model: str, provider: str, latency_ms: float}"""
        ...

    @abstractmethod
    def get_model_name(self) -> str:
        ...

    @abstractmethod
    def get_provider_name(self) -> str:
        ...


class AnthropicProvider(BaseLLMProvider):
    """
    Calls Anthropic API using the anthropic Python SDK.
    Requires: ANTHROPIC_API_KEY environment variable.
    Default model: claude-sonnet-4-6

    Automatically applies ephemeral cache_control to the system prompt
    to take advantage of Anthropic's prompt caching (up to 90% cost reduction).
    """

    def __init__(self) -> None:
        try:
            import anthropic
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            if not api_key:
                logger.warning("ANTHROPIC_API_KEY not set — Anthropic calls will fail at runtime")
            self._client = anthropic.AsyncAnthropic(api_key=api_key)
        except ImportError:
            raise RuntimeError(
                "anthropic package not installed. Run: pip install anthropic"
            )
        self._model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

    def get_model_name(self) -> str:
        return self._model

    def get_provider_name(self) -> str:
        return "anthropic"

    async def complete(
        self,
        messages: list[LLMMessage],
        system: Optional[str] = None,
        max_tokens: int = 2000,
        temperature: float = 0.3,
        tools: Optional[list[LLMTool]] = None,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [],  # filled below after tools are added
        }

        # Use cache_control on system prompt to activate Anthropic prompt caching
        if system:
            kwargs["system"] = [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ]

        if tools:
            kwargs["tools"] = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.input_schema,
                }
                for t in tools
            ]

        # Build Anthropic-format messages supporting tool_use / tool_result blocks
        anthropic_messages = self._build_anthropic_messages(messages)
        kwargs["messages"] = anthropic_messages

        response = await self._client.messages.create(**kwargs)

        content = ""
        tool_calls: list[LLMToolCall] = []
        for block in response.content:
            if hasattr(block, "text"):
                content += block.text
            elif block.type == "tool_use":
                tool_calls.append(LLMToolCall(
                    id=block.id,
                    name=block.name,
                    input=block.input or {},
                ))

        return LLMResponse(
            content=content,
            model=self._model,
            provider="anthropic",
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            raw={},  # avoid serialising large raw response
            tool_calls=tool_calls if tool_calls else None,
        )

    @staticmethod
    def _build_anthropic_messages(messages: list[LLMMessage]) -> list[dict]:
        """Convert LLMMessage list (including tool calls/results) to Anthropic format."""
        result = []
        for m in messages:
            if m.tool_calls:
                # Assistant message with tool_use blocks
                content_blocks = []
                if m.content:
                    content_blocks.append({"type": "text", "text": m.content})
                for tc in m.tool_calls:
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": tc.input,
                    })
                result.append({"role": "assistant", "content": content_blocks})
            elif m.tool_results:
                # User message with tool_result blocks
                content_blocks = []
                if m.content:
                    content_blocks.append({"type": "text", "text": m.content})
                for tr in m.tool_results:
                    content_blocks.append({
                        "type": "tool_result",
                        "tool_use_id": tr.tool_use_id,
                        "content": tr.content,
                    })
                result.append({"role": "user", "content": content_blocks})
            else:
                result.append({"role": m.role, "content": m.content})
        return result

    async def health_check(self) -> dict:
        start = time.monotonic()
        try:
            response = await self.complete(
                messages=[LLMMessage(role="user", content="ping")],
                max_tokens=5,
            )
            latency_ms = (time.monotonic() - start) * 1000
            return {
                "healthy": True,
                "model": self._model,
                "provider": "anthropic",
                "latency_ms": round(latency_ms, 1),
            }
        except Exception as e:
            return {
                "healthy": False,
                "model": self._model,
                "provider": "anthropic",
                "error": str(e),
                "latency_ms": None,
            }


class OllamaProvider(BaseLLMProvider):
    """
    Calls a local Ollama instance via its OpenAI-compatible endpoint.
    Requires: Ollama running at OLLAMA_BASE_URL (default: http://localhost:11434)
    Default model: qwen3:8b (best multilingual reasoning under 8B params)

    Ollama's /v1/chat/completions endpoint is OpenAI-compatible.
    The Authorization header is required by the schema but ignored by Ollama.

    Hardware guidance (set OLLAMA_MODEL in .env accordingly):
      4-8GB RAM   → phi4-mini:3.8b
      8-16GB RAM  → qwen3:8b          ← default
      16-32GB RAM → qwen3:14b or deepseek-r1:14b
      32GB+ RAM   → qwen3:30b (best for complex extraction)
    """

    def __init__(self) -> None:
        self._base_url = os.environ.get(
            "OLLAMA_BASE_URL", "http://localhost:11434"
        ).rstrip("/")
        self._model = os.environ.get("OLLAMA_MODEL", "qwen3:8b")
        self._timeout = float(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "120"))
        self._api_url = f"{self._base_url}/v1/chat/completions"

    def get_model_name(self) -> str:
        return self._model

    def get_provider_name(self) -> str:
        return "ollama"

    async def _list_local_models(self) -> list[str]:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{self._base_url}/api/tags")
            resp.raise_for_status()
            data = resp.json()
            return [m["name"] for m in data.get("models", [])]

    async def complete(
        self,
        messages: list[LLMMessage],
        system: Optional[str] = None,
        max_tokens: int = 2000,
        temperature: float = 0.3,
        tools: Optional[list[LLMTool]] = None,
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": self._build_ollama_messages(messages, system),
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }

        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.input_schema,
                    },
                }
                for t in tools
            ]

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                self._api_url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer ollama",
                },
            )

            if resp.status_code != 200:
                raise RuntimeError(
                    f"Ollama API error {resp.status_code}: {resp.text}"
                )

            data = resp.json()

        choice = data["choices"][0]
        content: str = choice["message"].get("content", "") or ""

        # Parse tool calls from Ollama's OpenAI-compatible format
        parsed_tool_calls: list[LLMToolCall] = []
        raw_tool_calls = choice["message"].get("tool_calls", [])
        for i, tc in enumerate(raw_tool_calls):
            fn = tc.get("function", {})
            try:
                input_args = json.loads(fn.get("arguments", "{}"))
            except json.JSONDecodeError:
                input_args = {}
            parsed_tool_calls.append(LLMToolCall(
                id=tc.get("id", f"ollama_tc_{i}"),
                name=fn.get("name", ""),
                input=input_args,
            ))

        usage = data.get("usage", {})
        return LLMResponse(
            content=content,
            model=self._model,
            provider="ollama",
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            raw={},
            tool_calls=parsed_tool_calls if parsed_tool_calls else None,
        )

    @staticmethod
    def _build_ollama_messages(messages: list[LLMMessage], system: Optional[str]) -> list[dict]:
        """Convert LLMMessage list to OpenAI-compatible format for Ollama."""
        result = []
        if system:
            result.append({"role": "system", "content": system})
        for m in messages:
            if m.tool_calls:
                # Assistant message with tool calls
                tc_list = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": json.dumps(tc.input)},
                    }
                    for tc in m.tool_calls
                ]
                result.append({"role": "assistant", "content": m.content or None, "tool_calls": tc_list})
            elif m.tool_results:
                # Tool results — one message per result in OpenAI format
                for tr in m.tool_results:
                    result.append({"role": "tool", "tool_call_id": tr.tool_use_id, "content": tr.content})
            else:
                result.append({"role": m.role, "content": m.content})
        return result

    async def health_check(self) -> dict:
        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self._base_url}/api/tags")
                resp.raise_for_status()

            local_models = await self._list_local_models()
            model_available = any(
                self._model in m or m.startswith(self._model.split(":")[0])
                for m in local_models
            )

            latency_ms = (time.monotonic() - start) * 1000

            if not model_available:
                return {
                    "healthy": False,
                    "model": self._model,
                    "provider": "ollama",
                    "error": (
                        f"Model '{self._model}' not pulled. "
                        f"Run: ollama pull {self._model}. "
                        f"Available: {local_models}"
                    ),
                    "available_models": local_models,
                    "latency_ms": round(latency_ms, 1),
                }

            return {
                "healthy": True,
                "model": self._model,
                "provider": "ollama",
                "available_models": local_models,
                "latency_ms": round(latency_ms, 1),
            }

        except httpx.ConnectError:
            return {
                "healthy": False,
                "model": self._model,
                "provider": "ollama",
                "error": (
                    f"Cannot connect to Ollama at {self._base_url}. "
                    "Is Ollama running? Start with: ollama serve"
                ),
                "latency_ms": None,
            }
        except Exception as e:
            return {
                "healthy": False,
                "model": self._model,
                "provider": "ollama",
                "error": str(e),
                "latency_ms": None,
            }


class LLMProviderFactory:
    """
    Singleton factory. Call get_provider() anywhere in the codebase.

    Configuration via environment variables:
      LLM_PROVIDER=anthropic   → uses Anthropic API (default)
      LLM_PROVIDER=ollama      → uses local Ollama

    Provider-specific env vars:
      ANTHROPIC_API_KEY        → required for anthropic
      ANTHROPIC_MODEL          → default: claude-sonnet-4-6
      OLLAMA_BASE_URL          → default: http://localhost:11434
      OLLAMA_MODEL             → default: qwen3:8b
      OLLAMA_TIMEOUT_SECONDS   → default: 120
    """

    _instance: Optional[BaseLLMProvider] = None

    @classmethod
    def get_provider(cls) -> BaseLLMProvider:
        if cls._instance is None:
            provider_type = os.environ.get(
                "LLM_PROVIDER", LLMProviderType.ANTHROPIC
            ).lower()

            if provider_type == LLMProviderType.OLLAMA:
                cls._instance = OllamaProvider()
                logger.info(
                    "LLM Provider: Ollama (local) — model: %s",
                    cls._instance.get_model_name(),
                )
            else:
                cls._instance = AnthropicProvider()
                logger.info(
                    "LLM Provider: Anthropic — model: %s",
                    cls._instance.get_model_name(),
                )

        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Force re-initialisation (used in tests and when env vars change at runtime)."""
        cls._instance = None


def get_llm_provider() -> BaseLLMProvider:
    return LLMProviderFactory.get_provider()
