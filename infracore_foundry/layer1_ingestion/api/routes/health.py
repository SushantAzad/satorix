"""Health check and alerting routes."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from layer1_ingestion.core.database import get_db
from layer1_ingestion.registry.source_registry import SourceRegistry
from layer1_ingestion.health.monitor import ConnectionHealthMonitor
from layer1_ingestion.health.alert_manager import AlertManager
from layer1_ingestion.api.schemas.models import HealthCheckResponse, AlertResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/health", tags=["Health"])


@router.post("/{source_id}/check", response_model=HealthCheckResponse)
def check_health(source_id: UUID, db: Session = Depends(get_db)):
    registry = SourceRegistry(db)
    source = registry.get_source(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Data source not found")

    from layer1_ingestion.core.config import get_settings
    settings = get_settings()
    connector_cls = settings.get_connector_class(source.source_type)
    if connector_cls is None:
        raise HTTPException(status_code=400, detail=f"No connector for type: {source.source_type}")

    connector = connector_cls(str(source.id), source.config or {})
    monitor = ConnectionHealthMonitor(db)
    health = monitor.check_health(source, connector)

    # Auto-alert on unhealthy
    alert_mgr = AlertManager(db)
    alert_mgr.check_and_alert_on_health(source_id, health.status, health.error_message)

    return health


@router.get("/{source_id}/history", response_model=list[HealthCheckResponse])
def health_history(source_id: UUID, limit: int = 50, db: Session = Depends(get_db)):
    monitor = ConnectionHealthMonitor(db)
    return monitor.get_health_history(source_id, limit=limit)


@router.get("/alerts/open", response_model=list[AlertResponse])
def open_alerts(db: Session = Depends(get_db)):
    alert_mgr = AlertManager(db)
    return alert_mgr.get_open_alerts()


@router.post("/alerts/{alert_id}/acknowledge", response_model=AlertResponse)
def acknowledge_alert(alert_id: UUID, db: Session = Depends(get_db)):
    alert_mgr = AlertManager(db)
    alert = alert_mgr.acknowledge_alert(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


@router.post("/alerts/{alert_id}/resolve", response_model=AlertResponse)
def resolve_alert(alert_id: UUID, db: Session = Depends(get_db)):
    alert_mgr = AlertManager(db)
    alert = alert_mgr.resolve_alert(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert
