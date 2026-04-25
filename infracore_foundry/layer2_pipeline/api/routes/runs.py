"""Pipeline run management routes — trigger, status, list."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from layer1_ingestion.api.auth import require_api_key
from layer1_ingestion.core.database import get_db
from layer2_pipeline.core.executor import PipelineExecutor
from layer2_pipeline.models.db_models import PipelineDefinition, PipelineRun

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/runs", tags=["Pipeline Runs"])


class TriggerRequest(BaseModel):
    pipeline_definition_id: UUID
    input_batch_id: str | None = None
    input_path: str | None = None
    triggered_by: str = "manual"


class RunResponse(BaseModel):
    id: str
    run_id: str | None
    pipeline_id: str
    status: str
    triggered_by: str
    records_input: int
    records_output: int
    records_failed: int
    duration_seconds: float | None
    error_summary: str | None


def _to_response(run: PipelineRun, pipeline_id: str) -> dict:
    return {
        "id": str(run.id),
        "run_id": run.run_id,
        "pipeline_id": pipeline_id,
        "status": run.status,
        "triggered_by": run.triggered_by,
        "records_input": run.records_input or 0,
        "records_output": run.records_output or 0,
        "records_failed": run.records_failed or 0,
        "duration_seconds": run.duration_seconds,
        "error_summary": run.error_summary,
    }


@router.post("/trigger", status_code=202, dependencies=[Depends(require_api_key)])
def trigger_run(body: TriggerRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    pipeline_def = db.query(PipelineDefinition).get(body.pipeline_definition_id)
    if pipeline_def is None:
        raise HTTPException(status_code=404, detail="Pipeline definition not found")
    if not pipeline_def.is_active:
        raise HTTPException(status_code=400, detail="Pipeline is inactive")

    def _run():
        from layer1_ingestion.core.database import SessionLocal
        with SessionLocal() as session:
            from layer1_ingestion.core.storage import get_minio_client
            executor = PipelineExecutor(session, get_minio_client())
            executor.execute(
                pipeline_def,
                input_batch_id=body.input_batch_id,
                input_path=body.input_path,
                triggered_by=body.triggered_by,
            )

    background_tasks.add_task(_run)
    return {"message": "Pipeline run queued", "pipeline_id": pipeline_def.pipeline_id}


@router.get("/", dependencies=[Depends(require_api_key)])
def list_runs(
    pipeline_definition_id: UUID = None,
    status: str = None,
    client_id: str = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    q = db.query(PipelineRun, PipelineDefinition).join(
        PipelineDefinition, PipelineRun.pipeline_definition_id == PipelineDefinition.id
    )
    if pipeline_definition_id:
        q = q.filter(PipelineRun.pipeline_definition_id == pipeline_definition_id)
    if status:
        q = q.filter(PipelineRun.status == status)
    if client_id:
        q = q.filter(PipelineRun.client_id == client_id)
    rows = q.order_by(PipelineRun.started_at.desc()).offset(skip).limit(limit).all()
    return [_to_response(run, pdef.pipeline_id) for run, pdef in rows]


@router.get("/{run_id}", dependencies=[Depends(require_api_key)])
def get_run(run_id: UUID, db: Session = Depends(get_db)):
    run = db.query(PipelineRun).get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    pdef = db.query(PipelineDefinition).get(run.pipeline_definition_id)
    return _to_response(run, pdef.pipeline_id if pdef else "unknown")


@router.get("/{run_id}/steps", dependencies=[Depends(require_api_key)])
def get_run_steps(run_id: UUID, db: Session = Depends(get_db)):
    from layer2_pipeline.models.db_models import PipelineStepRun
    run = db.query(PipelineRun).get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    steps = (
        db.query(PipelineStepRun)
        .filter(PipelineStepRun.run_id == run_id)
        .order_by(PipelineStepRun.started_at)
        .all()
    )
    return [
        {
            "step_id": s.step_id,
            "transform_type": s.transform_type,
            "status": s.status,
            "records_in": s.records_in,
            "records_out": s.records_out,
            "records_failed": s.records_failed,
            "error_message": s.error_message,
            "started_at": s.started_at,
            "completed_at": s.completed_at,
        }
        for s in steps
    ]
