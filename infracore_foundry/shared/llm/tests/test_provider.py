"""
Provider abstraction tests — run without Ollama or Anthropic running.
All external calls are mocked.
"""
import json
import os
import re
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from shared.llm.provider import (
    LLMMessage,
    LLMResponse,
    AnthropicProvider,
    OllamaProvider,
    LLMProviderFactory,
    get_llm_provider,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_ollama_response(content: str, prompt_tokens: int = 10, completion_tokens: int = 20) -> dict:
    return {
        "choices": [
            {
                "message": {"role": "assistant", "content": content, "tool_calls": []},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        },
        "model": "qwen3:8b",
    }


def _make_httpx_response(status_code: int, json_data: dict) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = json_data
    mock_resp.text = json.dumps(json_data)
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


# ── OllamaProvider tests ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ollama_provider_formats_messages_correctly():
    """Verify the payload sent to Ollama has correct OpenAI message format."""
    response_data = _make_ollama_response("CIRP stands for Corporate Insolvency Resolution Process.")
    captured_payload = {}

    async def mock_post(url, json=None, headers=None):
        captured_payload.update(json or {})
        return _make_httpx_response(200, response_data)

    with patch.dict(os.environ, {"OLLAMA_MODEL": "qwen3:8b"}):
        provider = OllamaProvider()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(side_effect=mock_post)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await provider.complete(
            messages=[LLMMessage(role="user", content="test")],
            system="You are an analyst.",
            max_tokens=100,
        )

    assert captured_payload["model"] == "qwen3:8b"
    assert captured_payload["stream"] is False
    assert captured_payload["max_tokens"] == 100
    # System prompt is prepended as a system message
    messages = captured_payload["messages"]
    assert messages[0] == {"role": "system", "content": "You are an analyst."}
    assert messages[1] == {"role": "user", "content": "test"}
    assert isinstance(result, LLMResponse)
    assert result.provider == "ollama"


@pytest.mark.asyncio
async def test_ollama_strips_markdown_fences_from_json():
    """OllamaProvider returns markdown-wrapped JSON; orchestrator strips it correctly."""
    raw_content = '```json\n{"key": "value"}\n```'
    response_data = _make_ollama_response(raw_content)

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=_make_httpx_response(200, response_data))

    with patch("httpx.AsyncClient", return_value=mock_client):
        with patch.dict(os.environ, {"OLLAMA_MODEL": "qwen3:8b"}):
            provider = OllamaProvider()
            result = await provider.complete(
                messages=[LLMMessage(role="user", content="extract")],
            )

    # The provider returns content as-is; stripping happens at orchestrator level
    assert result.content == raw_content

    # Simulate orchestrator's _validate_json_output stripping logic
    cleaned = re.sub(r"^```(?:json)?\s*", "", result.content.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)
    parsed = json.loads(cleaned)
    assert parsed == {"key": "value"}


@pytest.mark.asyncio
async def test_anthropic_provider_formats_messages_correctly():
    """Mock Anthropic SDK response and verify messages are passed correctly."""
    mock_usage = MagicMock()
    mock_usage.input_tokens = 50
    mock_usage.output_tokens = 30

    mock_content_block = MagicMock()
    mock_content_block.text = "Test response"

    mock_response = MagicMock()
    mock_response.content = [mock_content_block]
    mock_response.usage = mock_usage
    mock_response.model_dump.return_value = {"model": "claude-sonnet-4-6"}

    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key", "ANTHROPIC_MODEL": "claude-sonnet-4-6"}):
        with patch("anthropic.AsyncAnthropic") as mock_anthropic_cls:
            mock_anthropic_instance = AsyncMock()
            mock_anthropic_instance.messages = AsyncMock()
            mock_anthropic_instance.messages.create = AsyncMock(return_value=mock_response)
            mock_anthropic_cls.return_value = mock_anthropic_instance

            provider = AnthropicProvider()
            result = await provider.complete(
                messages=[LLMMessage(role="user", content="What is CIRP?")],
                system="You are an analyst.",
                max_tokens=200,
            )

    call_kwargs = mock_anthropic_instance.messages.create.call_args[1]
    assert call_kwargs["model"] == "claude-sonnet-4-6"
    assert call_kwargs["max_tokens"] == 200
    assert call_kwargs["messages"] == [{"role": "user", "content": "What is CIRP?"}]
    # System prompt should include cache_control for prompt caching
    system_arg = call_kwargs["system"]
    assert isinstance(system_arg, list)
    assert system_arg[0]["text"] == "You are an analyst."
    assert system_arg[0]["cache_control"] == {"type": "ephemeral"}

    assert isinstance(result, LLMResponse)
    assert result.content == "Test response"
    assert result.provider == "anthropic"
    assert result.input_tokens == 50
    assert result.output_tokens == 30


def test_factory_returns_ollama_when_env_set():
    LLMProviderFactory.reset()
    with patch.dict(os.environ, {"LLM_PROVIDER": "ollama"}):
        provider = get_llm_provider()
    assert isinstance(provider, OllamaProvider)
    LLMProviderFactory.reset()


def test_factory_returns_anthropic_by_default():
    LLMProviderFactory.reset()
    env = {k: v for k, v in os.environ.items() if k != "LLM_PROVIDER"}
    env.pop("LLM_PROVIDER", None)
    with patch.dict(os.environ, env, clear=True):
        with patch("anthropic.AsyncAnthropic"):
            provider = get_llm_provider()
    assert isinstance(provider, AnthropicProvider)
    LLMProviderFactory.reset()


@pytest.mark.asyncio
async def test_ollama_health_check_connection_refused():
    with patch.dict(os.environ, {"OLLAMA_BASE_URL": "http://localhost:11434"}):
        provider = OllamaProvider()

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(side_effect=Exception("ConnectError: Connection refused"))

    import httpx
    with patch("httpx.AsyncClient", return_value=mock_client):
        with patch.object(provider, "_list_local_models", side_effect=httpx.ConnectError("refused")):
            # Patch the inner client used in health_check
            with patch("httpx.AsyncClient") as mock_cls:
                inner_client = AsyncMock()
                inner_client.__aenter__ = AsyncMock(return_value=inner_client)
                inner_client.__aexit__ = AsyncMock(return_value=None)
                inner_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
                mock_cls.return_value = inner_client
                result = await provider.health_check()

    assert result["healthy"] is False
    assert "ollama serve" in result["error"]


@pytest.mark.asyncio
async def test_ollama_health_check_model_not_pulled():
    with patch.dict(os.environ, {"OLLAMA_MODEL": "qwen3:8b"}):
        provider = OllamaProvider()

    tags_response = _make_httpx_response(200, {"models": []})

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.get = AsyncMock(return_value=tags_response)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await provider.health_check()

    assert result["healthy"] is False
    assert "ollama pull" in result["error"]
    assert result["available_models"] == []
