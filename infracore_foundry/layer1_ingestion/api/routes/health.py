"""Health check and alerting routes."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from layer1_ingestion.api.auth import require_api_key
from layer1_ingestion.core.config import get_connector_class
from layer1_ingestion.core.database import get_db
from layer1_ingestion.health.alert_manager import AlertManager
from layer1_ingestion.health.monitor import ConnectionHealthMonitor
from layer1_ingestion.registry.source_registry import SourceRegistry
from layer1_ingestion.sync.state_manager import SyncStateManager
from layer1_ingestion.api.schemas.models import HealthCheckResponse, AlertResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/health", tags=["Health"])


@router.post(
    "/{source_id}/check",
    response_model=HealthCheckResponse,
    dependencies=[Depends(require_api_key)],
)
def check_health(source_id: UUID, db: Session = Depends(get_db)):
    registry = SourceRegistry(db)
    source = registry.get_source(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Data source not found")

    connector_cls = get_connector_class(source.source_type)
    if connector_cls is None:
        raise HTTPException(
            status_code=400,
            detail=f"No connector registered for type: {source.source_type!r}",
        )

    decrypted_config = registry.get_source_config(source_id)
    connector = connector_cls(str(source.id), decrypted_config)

    state_mgr = SyncStateManager(db)
    previous_fp = state_mgr.get_schema_fingerprint(source.id)

    monitor = ConnectionHealthMonitor(db)
    health = monitor.check_health(source, connector, previous_schema_fingerprint=previous_fp)

    alert_mgr = AlertManager(db)
    alert_mgr.check_and_alert_on_health(
        source_id=source.id,
        is_reachable=health.is_reachable,
        error_message=health.error_message,
        schema_drift=(health.schema_matches is False),
    )

    return HealthCheckResponse(
        source_id=source.id,
        status="healthy" if health.is_reachable else "unhealthy",
        response_time_ms=health.response_time_ms or 0.0,
        error_message=health.error_message,
        checked_at=health.checked_at,
    )


@router.get(
    "/{source_id}/history",
    response_model=list[HealthCheckResponse],
    dependencies=[Depends(require_api_key)],
)
def health_history(source_id: UUID, limit: int = 50, db: Session = Depends(get_db)):
    monitor = ConnectionHealthMonitor(db)
    records = monitor.get_health_history(source_id, limit=limit)
    return [
        HealthCheckResponse(
            source_id=h.source_id,
            status="healthy" if h.is_reachable else "unhealthy",
            response_time_ms=h.response_time_ms or 0.0,
            error_message=h.error_message,
            checked_at=h.checked_at,
        )
        for h in records
    ]


@router.get(
    "/alerts/open",
    response_model=list[AlertResponse],
    dependencies=[Depends(require_api_key)],
)
def open_alerts(source_id: UUID = None, db: Session = Depends(get_db)):
    alert_mgr = AlertManager(db)
    return alert_mgr.get_open_alerts(source_id=source_id)


@router.post(
    "/alerts/{alert_id}/acknowledge",
    response_model=AlertResponse,
    dependencies=[Depends(require_api_key)],
)
def acknowledge_alert(alert_id: UUID, db: Session = Depends(get_db)):
    alert_mgr = AlertManager(db)
    alert = alert_mgr.acknowledge_alert(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found or already closed")
    return alert


@router.post(
    "/alerts/{alert_id}/resolve",
    response_model=AlertResponse,
    dependencies=[Depends(require_api_key)],
)
def resolve_alert(alert_id: UUID, db: Session = Depends(get_db)):
    alert_mgr = AlertManager(db)
    alert = alert_mgr.resolve_alert(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found or already resolved")
    return alert
