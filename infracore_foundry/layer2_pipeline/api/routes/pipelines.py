"""Pipeline definition CRUD routes."""

from __future__ import annotations

import logging
from uuid import UUID

import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from layer1_ingestion.api.auth import require_api_key
from layer1_ingestion.core.database import get_db
from layer2_pipeline.core.dag import PipelineDAG
from layer2_pipeline.models.db_models import PipelineDefinition

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pipelines", tags=["Pipelines"])


class PipelineCreate(BaseModel):
    pipeline_id: str
    version: str = "1.0"
    client_id: str
    description: str = ""
    config: dict = Field(..., description="Full pipeline YAML parsed as JSON")
    created_by: str = ""


class PipelineResponse(BaseModel):
    id: UUID
    pipeline_id: str
    version: str
    client_id: str
    description: str
    is_active: bool
    step_count: int

    class Config:
        from_attributes = True


@router.post("/", status_code=201, dependencies=[Depends(require_api_key)])
def create_pipeline(body: PipelineCreate, db: Session = Depends(get_db)):
    # Validate the DAG before persisting
    errors = PipelineDAG.validate_definition(body.config)
    if errors:
        raise HTTPException(status_code=422, detail={"dag_errors": errors})

    pipeline = PipelineDefinition(
        pipeline_id=body.pipeline_id,
        version=body.version,
        client_id=body.client_id,
        description=body.description,
        config=body.config,
        created_by=body.created_by,
        is_active=True,
    )
    db.add(pipeline)
    db.commit()
    db.refresh(pipeline)
    return _to_response(pipeline)


@router.get("/", dependencies=[Depends(require_api_key)])
def list_pipelines(
    client_id: str = None,
    is_active: bool = True,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    q = db.query(PipelineDefinition).filter(PipelineDefinition.is_active == is_active)
    if client_id:
        q = q.filter(PipelineDefinition.client_id == client_id)
    pipelines = q.offset(skip).limit(limit).all()
    return [_to_response(p) for p in pipelines]


@router.get("/{pipeline_id}", dependencies=[Depends(require_api_key)])
def get_pipeline(pipeline_id: UUID, db: Session = Depends(get_db)):
    p = db.query(PipelineDefinition).get(pipeline_id)
    if p is None:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    return _to_response(p)


@router.delete("/{pipeline_id}", status_code=204, dependencies=[Depends(require_api_key)])
def deactivate_pipeline(pipeline_id: UUID, db: Session = Depends(get_db)):
    p = db.query(PipelineDefinition).get(pipeline_id)
    if p is None:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    p.is_active = False
    db.commit()


def _to_response(p: PipelineDefinition) -> dict:
    steps = p.config.get("steps", []) if isinstance(p.config, dict) else []
    return {
        "id": str(p.id),
        "pipeline_id": p.pipeline_id,
        "version": p.version,
        "client_id": p.client_id,
        "description": p.description or "",
        "is_active": p.is_active,
        "step_count": len(steps),
    }
