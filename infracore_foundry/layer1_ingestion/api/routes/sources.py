"""Data source CRUD routes."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from layer1_ingestion.api.auth import require_api_key
from layer1_ingestion.core.database import get_db
from layer1_ingestion.registry.source_registry import SourceRegistry
from layer1_ingestion.api.schemas.models import (
    DataSourceCreate, DataSourceUpdate, DataSourceResponse, DataSourceListResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sources", tags=["Data Sources"])


@router.post("/", response_model=DataSourceResponse, status_code=201, dependencies=[Depends(require_api_key)])
def create_source(body: DataSourceCreate, db: Session = Depends(get_db)):
    registry = SourceRegistry(db)
    source = registry.register_source(
        name=body.name, source_type=body.source_type,
        client_id=body.client_id, config=body.config,
        credentials=body.credentials, description=body.description,
        sync_schedule=body.sync_schedule, tags=body.tags,
    )
    return registry.get_source_masked(source.id)


@router.get("/", response_model=DataSourceListResponse, dependencies=[Depends(require_api_key)])
def list_sources(
    client_id: str = None, source_type: str = None,
    is_active: bool = True, skip: int = 0, limit: int = 50,
    db: Session = Depends(get_db),
):
    registry = SourceRegistry(db)
    sources = registry.list_sources(
        client_id=client_id, source_type=source_type,
        is_active=is_active, skip=skip, limit=limit,
    )
    return DataSourceListResponse(
        total=len(sources),
        items=[registry.get_source_masked(s.id) for s in sources],
    )


@router.get("/{source_id}", response_model=DataSourceResponse, dependencies=[Depends(require_api_key)])
def get_source(source_id: UUID, db: Session = Depends(get_db)):
    registry = SourceRegistry(db)
    source = registry.get_source_masked(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Data source not found")
    return source


@router.patch("/{source_id}", response_model=DataSourceResponse, dependencies=[Depends(require_api_key)])
def update_source(source_id: UUID, body: DataSourceUpdate, db: Session = Depends(get_db)):
    registry = SourceRegistry(db)
    source = registry.update_source(source_id, **body.model_dump(exclude_none=True))
    if source is None:
        raise HTTPException(status_code=404, detail="Data source not found")
    return registry.get_source_masked(source.id)


@router.delete("/{source_id}", status_code=204, dependencies=[Depends(require_api_key)])
def delete_source(source_id: UUID, db: Session = Depends(get_db)):
    registry = SourceRegistry(db)
    success = registry.soft_delete_source(source_id)
    if not success:
        raise HTTPException(status_code=404, detail="Data source not found")
