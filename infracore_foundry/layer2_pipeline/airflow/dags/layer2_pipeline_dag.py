"""
Layer 2 Airflow DAG.
Listens for Layer 1 completion events via Redis and runs all active pipelines
for the relevant client/batch.

Trigger modes:
  1. Scheduled: polls for recent Layer 1 batches every 15 minutes
  2. Event-driven: triggered by Airflow REST API when Layer 1 publishes
     to Redis channel 'layer1:sync:complete'
  3. Manual: dag_run.conf = {"client_id": "...", "batch_id": "...", "input_path": "..."}
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from airflow.decorators import dag, task
from airflow.models import Variable

logger = logging.getLogger(__name__)

DEFAULT_ARGS = {
    "owner": "satorix",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=30),
    "depends_on_past": False,
}


@dag(
    dag_id="layer2_pipeline",
    description="Layer 2 transformation pipeline — triggered by Layer 1 completion",
    schedule_interval="*/15 * * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=4,
    default_args=DEFAULT_ARGS,
    tags=["layer2", "pipeline", "satorix"],
)
def layer2_pipeline_dag():

    @task
    def get_pending_batches(**context) -> list[dict]:
        """
        Returns a list of {client_id, batch_id, input_path, pipeline_def_id} dicts
        to process in this DAG run.

        Source priority:
          1. dag_run.conf (manual/event trigger)
          2. Redis 'layer1:sync:complete' queue (LPOP up to 10 items)
          3. DB query for recently completed Layer 1 runs not yet processed by Layer 2
        """
        conf = context["dag_run"].conf or {}

        # Manual / event-driven trigger
        if conf.get("batch_id"):
            return _resolve_pipelines_for_batch(conf)

        # Redis queue
        batches = _poll_redis_queue(max_items=10)
        if batches:
            return batches

        # DB fallback — find Layer 1 runs from last 30 min with no corresponding L2 run
        return _find_unprocessed_batches(lookback_minutes=30)

    @task
    def run_pipeline(batch: dict) -> dict:
        """Execute one pipeline run for a single batch payload."""
        import sys
        sys.path.insert(0, "/opt/airflow")

        from layer1_ingestion.core.config import _auto_register_connectors
        _auto_register_connectors()

        from layer1_ingestion.core.database import SessionLocal
        from layer1_ingestion.core.storage import get_minio_client
        from layer2_pipeline.models.db_models import PipelineDefinition
        from layer2_pipeline.core.executor import PipelineExecutor

        pipeline_def_id = batch.get("pipeline_def_id")
        if not pipeline_def_id:
            logger.warning("No pipeline_def_id in batch payload: %s", batch)
            return {"status": "skipped", "reason": "no pipeline_def_id"}

        with SessionLocal() as db:
            pipeline_def = db.query(PipelineDefinition).get(pipeline_def_id)
            if pipeline_def is None or not pipeline_def.is_active:
                return {"status": "skipped", "reason": "pipeline not found or inactive"}

            executor = PipelineExecutor(db, get_minio_client())
            run = executor.execute(
                pipeline_def,
                input_batch_id=batch.get("batch_id"),
                input_path=batch.get("input_path"),
                triggered_by="layer1_event",
            )
            return {
                "status": run.status,
                "run_id": run.run_id,
                "records_input": run.records_input,
                "records_output": run.records_output,
                "records_failed": run.records_failed,
            }

    batches = get_pending_batches()
    run_pipeline.expand(batch=batches)


_PROCESSING_KEY = "layer1:sync:processing"


def _poll_redis_queue(max_items: int = 10) -> list[dict]:
    """
    Atomically move items from 'layer1:sync:complete' → 'layer1:sync:processing'
    using RPOPLPUSH for at-least-once delivery. Removes from processing queue
    only after successful parse and resolution.
    """
    try:
        import redis as redis_lib
        from layer1_ingestion.core.config import get_settings
        settings = get_settings()
        r = redis_lib.from_url(settings.redis_url)
        items = []
        for _ in range(max_items):
            raw = r.rpoplpush("layer1:sync:complete", _PROCESSING_KEY)
            if raw is None:
                break
            try:
                payload = json.loads(raw)
                resolved = _resolve_pipelines_for_batch(payload)
                items.extend(resolved if isinstance(resolved, list) else [resolved])
                r.lrem(_PROCESSING_KEY, 1, raw)
            except Exception as exc:
                logger.warning("Bad Redis payload discarded: %s — %s", raw, exc)
                r.lrem(_PROCESSING_KEY, 1, raw)
        return items
    except Exception as exc:
        logger.warning("Redis poll failed: %s — falling back to DB query", exc)
        return []


def _find_unprocessed_batches(lookback_minutes: int = 30) -> list[dict]:
    """
    Query Layer 1 sync_runs completed in the last N minutes that have no
    corresponding Layer 2 pipeline run.
    """
    try:
        from datetime import timezone
        from layer1_ingestion.core.database import SessionLocal
        from layer1_ingestion.registry.models import SyncRun, DataSource
        from layer2_pipeline.models.db_models import PipelineRun, PipelineDefinition

        cutoff = datetime.now(timezone.utc) - timedelta(minutes=lookback_minutes)
        with SessionLocal() as db:
            # Find recently completed L1 runs
            l1_runs = (
                db.query(SyncRun, DataSource)
                .join(DataSource, SyncRun.source_id == DataSource.id)
                .filter(
                    SyncRun.status == "completed",
                    SyncRun.completed_at >= cutoff,
                )
                .all()
            )
            # For each, find active pipelines for that client
            batches = []
            for sync_run, source in l1_runs:
                pipelines = (
                    db.query(PipelineDefinition)
                    .filter(
                        PipelineDefinition.client_id == source.client_id,
                        PipelineDefinition.is_active == True,
                    )
                    .all()
                )
                for p in pipelines:
                    # Check no L2 run already exists for this batch
                    existing = (
                        db.query(PipelineRun)
                        .filter(
                            PipelineRun.input_batch_id == sync_run.batch_id,
                            PipelineRun.pipeline_definition_id == p.id,
                            PipelineRun.status.in_(["completed", "running"]),
                        )
                        .first()
                    )
                    if existing is None:
                        batches.append({
                            "client_id": source.client_id,
                            "batch_id": sync_run.batch_id,
                            "input_path": sync_run.output_path,
                            "pipeline_def_id": str(p.id),
                        })
        return batches
    except Exception as exc:
        logger.error("DB batch discovery failed: %s", exc)
        return []


def _resolve_pipelines_for_batch(payload: dict) -> list[dict]:
    """
    Given a Layer 1 event payload {client_id, batch_id, output_path},
    find all active pipelines for that client and return one item per pipeline.
    """
    try:
        from layer1_ingestion.core.database import SessionLocal
        from layer2_pipeline.models.db_models import PipelineDefinition

        client_id = payload.get("client_id", "")
        with SessionLocal() as db:
            pipelines = (
                db.query(PipelineDefinition)
                .filter(
                    PipelineDefinition.client_id == client_id,
                    PipelineDefinition.is_active == True,
                )
                .all()
            )
            return [
                {
                    "client_id": client_id,
                    "batch_id": payload.get("batch_id"),
                    "input_path": payload.get("output_path") or payload.get("input_path"),
                    "pipeline_def_id": str(p.id),
                }
                for p in pipelines
            ]
    except Exception as exc:
        logger.error("Failed to resolve pipelines for payload %s: %s", payload, exc)
        return []


layer2_pipeline_dag()
