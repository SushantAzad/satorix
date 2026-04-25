"""Lineage query routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from layer1_ingestion.api.auth import require_api_key
from layer1_ingestion.core.database import get_db
from layer2_pipeline.lineage.tracker import LineageTracker

router = APIRouter(prefix="/lineage", tags=["Lineage"])


@router.get("/entity/{entity_type}/{entity_id}", dependencies=[Depends(require_api_key)])
def get_entity_lineage(
    entity_type: str,
    entity_id: str,
    field_name: str = None,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    tracker = LineageTracker(db)
    records = tracker.get_lineage_for_entity(entity_type, entity_id, field_name, limit)
    return [
        {
            "id": str(r.id),
            "entity_type": r.entity_type,
            "entity_id": r.entity_id,
            "field_name": r.field_name,
            "source_batch_id": r.source_batch_id,
            "pipeline_id": r.pipeline_id,
            "pipeline_version": r.pipeline_version,
            "step_id": r.step_id,
            "transform_applied": r.transform_applied,
            "loaded_at": r.loaded_at,
        }
        for r in records
    ]
