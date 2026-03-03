"""Sync trigger and history routes."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from layer1_ingestion.core.database import get_db
from layer1_ingestion.registry.source_registry import SourceRegistry
from layer1_ingestion.sync.sync_engine import SyncEngine
from layer1_ingestion.api.schemas.models import SyncTriggerRequest, SyncRunResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sync", tags=["Sync"])


@router.post("/{source_id}/trigger", response_model=SyncRunResponse)
def trigger_sync(source_id: UUID, body: SyncTriggerRequest, db: Session = Depends(get_db)):
    registry = SourceRegistry(db)
    source = registry.get_source(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Data source not found")

    # Dynamically instantiate the connector
    from layer1_ingestion.core.config import get_settings
    settings = get_settings()
    connector_cls = settings.get_connector_class(source.source_type)
    if connector_cls is None:
        raise HTTPException(status_code=400, detail=f"No connector for type: {source.source_type}")

    connector = connector_cls(str(source.id), source.config or {})
    engine = SyncEngine(db)
    run = engine.run_sync(source, connector, sync_type=body.sync_type)
    return run


@router.get("/{source_id}/history", response_model=list[SyncRunResponse])
def sync_history(source_id: UUID, limit: int = 30, db: Session = Depends(get_db)):
    engine = SyncEngine(db)
    return engine.get_sync_history(source_id, limit=limit)
