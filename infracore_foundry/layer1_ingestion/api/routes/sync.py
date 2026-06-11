"""Sync trigger and history routes."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from layer1_ingestion.api.auth import require_api_key
from layer1_ingestion.core.config import get_connector_class
from layer1_ingestion.core.database import get_db
from layer1_ingestion.registry.source_registry import SourceRegistry
from layer1_ingestion.sync.sync_engine import SyncEngine
from layer1_ingestion.api.schemas.models import SyncTriggerRequest, SyncRunResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sync", tags=["Sync"])


@router.post(
    "/{source_id}/trigger",
    response_model=SyncRunResponse,
    dependencies=[Depends(require_api_key)],
)
def trigger_sync(
    source_id: UUID,
    body: SyncTriggerRequest,
    db: Session = Depends(get_db),
):
    registry = SourceRegistry(db)
    source = registry.get_source(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Data source not found")

    if source.circuit_open:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Circuit is open for source {source_id} after "
                f"{source.consecutive_failures} consecutive failures. "
                "Resolve the connection issue before triggering a sync."
            ),
        )

    connector_cls = get_connector_class(source.source_type)
    if connector_cls is None:
        raise HTTPException(
            status_code=400,
            detail=f"No connector registered for source type: {source.source_type!r}",
        )

    decrypted_config = registry.get_source_config(source_id)
    connector = connector_cls(str(source.id), decrypted_config)

    engine = SyncEngine(db)
    run = engine.run_sync(source, connector, sync_type=body.sync_type)
    return run


@router.get(
    "/{source_id}/history",
    response_model=list[SyncRunResponse],
    dependencies=[Depends(require_api_key)],
)
def sync_history(
    source_id: UUID,
    limit: int = 30,
    db: Session = Depends(get_db),
):
    engine = SyncEngine(db)
    return engine.get_sync_history(source_id, limit=limit)
