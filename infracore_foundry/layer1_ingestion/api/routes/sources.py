"""Data source CRUD routes."""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from layer1_ingestion.api.auth import require_api_key
from layer1_ingestion.core.database import get_db
from layer1_ingestion.registry.models import DataSource
from layer1_ingestion.registry.source_registry import SourceRegistry

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sources", tags=["Data Sources"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class DataSourceCreate(BaseModel):
    source_name: str = Field(..., min_length=1, max_length=500)
    source_type: str = Field(..., description="csv, excel, postgresql, rest_api, mca21, etc.")
    client_id: str = Field(default="default", max_length=255)
    config: dict = Field(default_factory=dict)
    description: Optional[str] = None


class DataSourceUpdate(BaseModel):
    source_name: Optional[str] = None
    description: Optional[str] = None
    config: Optional[dict] = None


# ---------------------------------------------------------------------------
# Serialization helper
# ---------------------------------------------------------------------------

def _to_dict(source: DataSource, registry: SourceRegistry) -> dict:
    return {
        "id": str(source.id),
        "source_name": source.source_name,
        "source_type": source.source_type,
        "client_id": source.client_id,
        "status": source.status,
        "description": source.description,
        "config": registry.mask_config(source),
        "consecutive_failures": source.consecutive_failures,
        "created_at": source.created_at.isoformat() if source.created_at else None,
        "updated_at": source.updated_at.isoformat() if source.updated_at else None,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/", status_code=201, dependencies=[Depends(require_api_key)])
def create_source(body: DataSourceCreate, db: Session = Depends(get_db)):
    """Register a new data source connector."""
    registry = SourceRegistry(db)
    source = registry.create_source(
        client_id=body.client_id,
        source_name=body.source_name,
        source_type=body.source_type,
        connection_config=body.config,
        description=body.description or "",
    )
    return _to_dict(source, registry)


@router.get("/", dependencies=[Depends(require_api_key)])
def list_sources(
    client_id: str = None,
    source_type: str = None,
    db: Session = Depends(get_db),
):
    """List all configured data sources."""
    registry = SourceRegistry(db)
    sources = registry.list_sources(client_id=client_id, source_type=source_type)
    return [_to_dict(s, registry) for s in sources]


@router.get("/{source_id}", dependencies=[Depends(require_api_key)])
def get_source(source_id: UUID, db: Session = Depends(get_db)):
    """Get a single data source by ID."""
    registry = SourceRegistry(db)
    source = registry.get_source(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Data source not found")
    return _to_dict(source, registry)


@router.patch("/{source_id}", dependencies=[Depends(require_api_key)])
def update_source(source_id: UUID, body: DataSourceUpdate, db: Session = Depends(get_db)):
    """Update an existing data source."""
    registry = SourceRegistry(db)
    source = registry.get_source(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Data source not found")
    updates = body.model_dump(exclude_none=True)
    if "config" in updates:
        updates["connection_config"] = updates.pop("config")
    registry.update_source(source_id, **updates)
    source = registry.get_source(source_id)
    return _to_dict(source, registry)


@router.post("/{source_id}/test", dependencies=[Depends(require_api_key)])
def test_source(source_id: UUID, db: Session = Depends(get_db)):
    """Validate that a data source configuration can be read."""
    registry = SourceRegistry(db)
    source = registry.get_source(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Data source not found")
    try:
        registry.get_source_config(source_id)
        return {
            "success": True,
            "message": f"Source '{source.source_name}' is configured. "
                       "Connection will be verified on first sync.",
            "source_type": source.source_type,
        }
    except Exception as exc:
        logger.warning("test_source config read failed: %s", exc)
        return {
            "success": False,
            "message": "Failed to read source configuration.",
            "error": str(exc),
        }


@router.delete("/{source_id}", status_code=204, dependencies=[Depends(require_api_key)])
def delete_source(source_id: UUID, db: Session = Depends(get_db)):
    """Soft-delete (archive) a data source."""
    registry = SourceRegistry(db)
    source = registry.get_source(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Data source not found")
    registry.delete_source(source_id)
