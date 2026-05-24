"""
Operational routes — system health, Kafka, pipeline, model observability, and LLM provider management.
"""
import logging
import os
import time
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Body, Depends, Query

from aggregators.operational import (
    get_alert_analytics,
    get_ingestion_queue,
    get_kafka_topics,
    get_model_performance,
    get_ontology_health,
    get_source_health,
    get_system_health,
)
from core.auth import RoleChecker, get_current_user
from core.layer_clients import layer_clients

logger = logging.getLogger(__name__)

router = APIRouter()

_OPS_ROLES = RoleChecker(
    ["platform_administrator", "data_steward", "ontology_designer", "compliance_head"]
)


@router.get("/system-health")
async def system_health() -> Dict:
    """Return the service status grid for all Docker services. No auth — internal monitoring."""
    return await get_system_health()


@router.get("/kafka-topics")
async def kafka_topics(
    current_user: Dict = Depends(_OPS_ROLES),
) -> Dict:
    """Return Kafka topic metrics."""
    return await get_kafka_topics(layer_clients)


@router.get("/source-health")
async def source_health(
    current_user: Dict = Depends(_OPS_ROLES),
) -> Dict:
    """Return health status for all configured data sources."""
    return await get_source_health(layer_clients)


@router.get("/ingestion-queue")
async def ingestion_queue(
    current_user: Dict = Depends(_OPS_ROLES),
) -> Dict:
    """Return current pipeline batches in flight from Layer 1 + Layer 2 + Layer 3."""
    return await get_ingestion_queue(layer_clients)


@router.get("/ontology-health")
async def ontology_health() -> Dict:
    """Return ontology coverage and quality metrics. No auth — internal monitoring."""
    return await get_ontology_health(layer_clients)


@router.get("/model-performance")
async def model_performance(
    current_user: Dict = Depends(_OPS_ROLES),
) -> Dict:
    """Return ML model performance stats from Layer 5."""
    return await get_model_performance(layer_clients)


@router.get("/alert-analytics")
async def alert_analytics(
    days: int = Query(30, ge=1, le=365),
    current_user: Dict = Depends(get_current_user),
) -> Dict:
    """Return alert volume over time, grouped by severity."""
    return await get_alert_analytics(layer_clients, days=days)


# ── LLM Provider Management ─────────────────────────────────────────────────
# Routes below are at /api/v1/operational/llm/*
# The schema manager frontend calls these for provider status and test completions.

def _get_llm_config() -> Dict[str, str]:
    return {
        "provider": os.environ.get("LLM_PROVIDER", "anthropic"),
        "ollama_base_url": os.environ.get("OLLAMA_BASE_URL", "http://ollama:11434"),
        "ollama_model": os.environ.get("OLLAMA_MODEL", "qwen3:8b"),
        "anthropic_model": os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
        "anthropic_key_set": bool(os.environ.get("ANTHROPIC_API_KEY", "")),
    }


@router.get("/llm/status")
async def llm_status() -> Dict:
    """Return current LLM provider health. Actual endpoint: /api/v1/operational/llm/status"""
    cfg = _get_llm_config()
    provider = cfg["provider"]
    t0 = time.monotonic()

    if provider == "ollama":
        ollama_url = cfg["ollama_base_url"].rstrip("/")
        model = cfg["ollama_model"]
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{ollama_url}/api/tags")
                resp.raise_for_status()
                tags_data = resp.json()
            local_models = [m["name"] for m in tags_data.get("models", [])]
            model_available = any(
                model in m or m.startswith(model.split(":")[0])
                for m in local_models
            )
            latency_ms = round((time.monotonic() - t0) * 1000, 1)
            if not model_available:
                return {
                    "provider": "ollama",
                    "model": model,
                    "healthy": False,
                    "latency_ms": latency_ms,
                    "available_models": local_models,
                    "error": f"Model '{model}' not pulled. Run: ollama pull {model}",
                }
            return {
                "provider": "ollama",
                "model": model,
                "healthy": True,
                "latency_ms": latency_ms,
                "available_models": local_models,
                "error": None,
            }
        except httpx.ConnectError:
            return {
                "provider": "ollama",
                "model": model,
                "healthy": False,
                "latency_ms": None,
                "available_models": [],
                "error": f"Cannot connect to Ollama at {ollama_url}. Is Ollama running?",
            }
        except Exception as exc:
            return {
                "provider": "ollama",
                "model": model,
                "healthy": False,
                "latency_ms": None,
                "available_models": [],
                "error": str(exc),
            }
    else:
        model = cfg["anthropic_model"]
        key_set = cfg["anthropic_key_set"]
        if not key_set:
            return {
                "provider": "anthropic",
                "model": model,
                "healthy": False,
                "latency_ms": None,
                "available_models": [model],
                "error": "ANTHROPIC_API_KEY not set.",
            }
        return {
            "provider": "anthropic",
            "model": model,
            "healthy": True,
            "latency_ms": None,
            "available_models": [model],
            "error": None,
        }


@router.get("/llm/models")
async def llm_models() -> Dict:
    """Return available models for the configured provider. Endpoint: /api/v1/operational/llm/models"""
    cfg = _get_llm_config()
    provider = cfg["provider"]

    if provider == "ollama":
        ollama_url = cfg["ollama_base_url"].rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{ollama_url}/api/tags")
                resp.raise_for_status()
                tags_data = resp.json()
            raw_models = tags_data.get("models", [])
            available = [
                {
                    "name": m["name"],
                    "size_gb": round(m.get("size", 0) / 1e9, 1),
                    "family": m["name"].split(":")[0],
                }
                for m in raw_models
            ]
            return {
                "provider": "ollama",
                "current_model": cfg["ollama_model"],
                "available_models": available,
            }
        except Exception as exc:
            return {
                "provider": "ollama",
                "current_model": cfg["ollama_model"],
                "available_models": [],
                "error": str(exc),
            }
    else:
        model = cfg["anthropic_model"]
        return {
            "provider": "anthropic",
            "current_model": model,
            "available_models": [{"name": model, "size_gb": None, "family": "claude"}],
        }


@router.post("/llm/test")
async def llm_test(
    body: Dict = Body(...),
) -> Dict:
    """Run a quick test completion. Endpoint: /api/v1/operational/llm/test"""
    prompt: str = body.get("prompt", "Explain what CIRP means in Indian corporate law in 2 sentences.")
    cfg = _get_llm_config()
    provider = cfg["provider"]
    t0 = time.monotonic()

    if provider == "ollama":
        ollama_url = cfg["ollama_base_url"].rstrip("/")
        model = cfg["ollama_model"]
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    f"{ollama_url}/v1/chat/completions",
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 200,
                        "temperature": 0.3,
                        "stream": False,
                    },
                    headers={"Authorization": "Bearer ollama"},
                )
                resp.raise_for_status()
                data = resp.json()
            content = data["choices"][0]["message"].get("content", "")
            usage = data.get("usage", {})
            latency_ms = round((time.monotonic() - t0) * 1000)
            return {
                "provider": "ollama",
                "model": model,
                "response": content,
                "latency_ms": latency_ms,
                "tokens_used": usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0),
            }
        except Exception as exc:
            return {
                "provider": "ollama",
                "model": model,
                "response": None,
                "latency_ms": round((time.monotonic() - t0) * 1000),
                "error": str(exc),
            }
    else:
        # For Anthropic, delegate to Layer 5 to avoid managing the key in Layer 6
        try:
            result = await layer_clients.l5_client.post(
                "/api/v1/llm/test",
                json={"prompt": prompt},
            )
            if result.status_code < 400:
                data = result.json()
                latency_ms = round((time.monotonic() - t0) * 1000)
                return {
                    "provider": "anthropic",
                    "model": cfg["anthropic_model"],
                    "response": data.get("response", ""),
                    "latency_ms": latency_ms,
                    "tokens_used": data.get("tokens_used", 0),
                }
        except Exception:
            pass
        return {
            "provider": "anthropic",
            "model": cfg["anthropic_model"],
            "response": None,
            "latency_ms": round((time.monotonic() - t0) * 1000),
            "error": "Anthropic test requires Layer 5 API to be available.",
        }
