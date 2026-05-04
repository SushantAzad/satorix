"""
Operational routes — system health, Kafka, pipeline, and model observability.
"""
import logging
from typing import Dict, List

from fastapi import APIRouter, Depends, Query

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

# All operational endpoints require at least platform_administrator or data_steward
_OPS_ROLES = RoleChecker(
    ["platform_administrator", "data_steward", "ontology_designer", "compliance_head"]
)


@router.get("/system-health")
async def system_health(
    current_user: Dict = Depends(_OPS_ROLES),
) -> List[Dict]:
    """Return the service status grid for all Docker services."""
    return await get_system_health()


@router.get("/kafka-topics")
async def kafka_topics(
    current_user: Dict = Depends(_OPS_ROLES),
) -> List[Dict]:
    """Return Kafka topic metrics."""
    return await get_kafka_topics(layer_clients)


@router.get("/source-health")
async def source_health(
    current_user: Dict = Depends(_OPS_ROLES),
) -> List[Dict]:
    """Return health status for all configured data sources."""
    return await get_source_health(layer_clients)


@router.get("/ingestion-queue")
async def ingestion_queue(
    current_user: Dict = Depends(_OPS_ROLES),
) -> Dict:
    """Return current pipeline batches in flight from Layer 1 + Layer 2 + Layer 3."""
    return await get_ingestion_queue(layer_clients)


@router.get("/ontology-health")
async def ontology_health(
    current_user: Dict = Depends(_OPS_ROLES),
) -> Dict:
    """Return ontology coverage and quality metrics from Layer 3."""
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
