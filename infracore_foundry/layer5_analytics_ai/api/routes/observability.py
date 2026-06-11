"""Model and system observability endpoints."""
from fastapi import APIRouter, Query
from typing import Optional

from observability.model_metrics import get_model_health_summary, get_prediction_distribution
from observability.llm_metrics import get_llm_usage_summary, get_daily_token_usage
from observability.feature_health import get_feature_health, get_stale_entities
from models.registry import model_registry

router = APIRouter(prefix="/observability", tags=["observability"])


@router.get("/models/health")
async def model_health():
    return {"models": await get_model_health_summary()}


@router.get("/models/distribution/{model_name}")
async def model_distribution(model_name: str, days: int = 7):
    return await get_prediction_distribution(model_name, days)


@router.get("/models/registry")
async def list_models(model_name: Optional[str] = None):
    return {"models": await model_registry.list_models(model_name)}


@router.get("/llm/usage")
async def llm_usage(days: int = 7):
    return {"usage": await get_llm_usage_summary(days)}


@router.get("/llm/tokens/daily")
async def llm_daily_tokens(days: int = 30):
    return {"daily": await get_daily_token_usage(days)}


@router.get("/features/health")
async def feature_health():
    return {"features": await get_feature_health()}


@router.get("/features/stale")
async def stale_features(max_age_hours: int = 26):
    return {"stale_entities": await get_stale_entities(max_age_hours)}
