"""
Pipeline execution engine.
Reads raw Parquet from MinIO → runs each step in topological order →
writes processed Parquet back to MinIO → persists run state + lineage + errors to DB.
"""

from __future__ import annotations

import hashlib
import logging
import struct
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from layer2_pipeline.core.context import ExecutionContext
from layer2_pipeline.core.dag import PipelineDAG, PipelineDefinitionParsed, StepDefinition
from layer2_pipeline.errors.classifier import classify
from layer2_pipeline.errors.quarantine import QuarantineManager
from layer2_pipeline.lineage.tracker import LineageTracker
from layer2_pipeline.models.db_models import (
    DatasetVersion,
    PipelineDefinition as DBPipelineDefinition,
    PipelineRun,
    PipelineStepRun,
)
from layer2_pipeline.quality.rules import QualityRule
from layer2_pipeline.quality.validator import DataQualityValidator
from layer2_pipeline.transforms import registry as transform_registry

logger = logging.getLogger(__name__)

# MinIO bucket for Layer 2 processed output
PROCESSED_BUCKET = "processed-data"


def _run_id_from(pipeline_id: str, version: str, input_batch_id: str) -> str:
    """Deterministic run ID — same inputs always produce the same run_id."""
    content = f"{pipeline_id}:{version}:{input_batch_id}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _advisory_lock_key(run_id: str) -> int:
    digest = hashlib.sha256(run_id.encode()).digest()[:8]
    return struct.unpack(">q", digest)[0]


def _schema_fingerprint(df: pd.DataFrame) -> str:
    schema_str = ",".join(
        f"{col}:{dtype}" for col, dtype in sorted(zip(df.columns, df.dtypes.astype(str)))
    )
    return hashlib.sha256(schema_str.encode()).hexdigest()[:16]


class PipelineExecutor:
    """
    Executes one pipeline run end-to-end.

    Usage:
        executor = PipelineExecutor(db, minio_client)
        result = executor.execute(pipeline_def_db, input_batch_id, input_path)
    """

    def __init__(self, db: Session, minio_client: Any) -> None:
        self.db = db
        self.minio = minio_client
        self._quarantine = QuarantineManager(db)
        self._lineage = LineageTracker(db)

    def execute(
        self,
        pipeline_def: DBPipelineDefinition,
        input_batch_id: Optional[str] = None,
        input_path: Optional[str] = None,
        triggered_by: str = "scheduler",
        named_frames: Optional[dict[str, pd.DataFrame]] = None,
    ) -> PipelineRun:
        """
        Run the pipeline. Returns the completed (or failed) PipelineRun row.
        Never raises — errors are captured in the DB and context.
        """
        raw_config: dict = pipeline_def.config
        dag = PipelineDAG(raw_config)
        try:
            parsed = dag.parse()
        except Exception as exc:
            logger.error("Pipeline %s DAG parse failed: %s", pipeline_def.pipeline_id, exc)
            return self._create_failed_run(pipeline_def, input_batch_id, str(exc))

        run_id_str = _run_id_from(
            parsed.pipeline_id, parsed.version, input_batch_id or "adhoc"
        )

        # Idempotency: skip if already completed
        existing = (
            self.db.query(PipelineRun)
            .filter(PipelineRun.run_id == run_id_str, PipelineRun.status == "completed")
            .first()
        )
        if existing:
            logger.info("Pipeline run %s already completed — skipping", run_id_str)
            return existing

        ctx = ExecutionContext.create(
            pipeline_id=parsed.pipeline_id,
            pipeline_version=parsed.version,
            client_id=parsed.client_id or pipeline_def.client_id,
            input_batch_id=input_batch_id,
            input_path=input_path,
            triggered_by=triggered_by,
        )

        # Advisory lock — prevents duplicate concurrent runs for the same input
        lock_key = _advisory_lock_key(run_id_str)
        try:
            self.db.execute(text("SELECT pg_advisory_lock(:key)"), {"key": lock_key})
        except Exception as exc:
            raise RuntimeError(f"Could not acquire advisory lock for run {run_id_str}") from exc

        run = self._create_run(pipeline_def, ctx, run_id_str, input_batch_id, input_path)

        try:
            # Load input DataFrame
            df = self._load_input(ctx, input_path, pipeline_def.client_id)
            if df is None:
                return self._fail_run(run, ctx, "Input data could not be loaded")

            # Warn on large batches — Pandas has an in-memory ceiling
            if len(df) > 200_000:
                logger.warning(
                    "Large batch: %d rows for pipeline %s — pandas may OOM above ~200K rows",
                    len(df), parsed.pipeline_id,
                )

            # Normalize column names to lowercase+underscore before any transforms
            df.columns = pd.Index(df.columns.str.strip().str.lower().str.replace(r"[\s]+", "_", regex=True))

            # Schema presence check for entity tracking
            lc = parsed.lineage_config
            if lc:
                eid_col = lc.get("entity_id_column", "")
                if eid_col and eid_col not in df.columns:
                    ctx.warn(
                        f"Schema check: entity_id_column {eid_col!r} not found after normalization. "
                        f"Columns: {list(df.columns)[:20]}"
                    )

            records_input = len(df)
            named_frames = named_frames or {}

            # --- Cross-batch deduplication ---
            # Prevents reprocessing records already ingested in a previous sync batch.
            # Key columns come from cross_batch_dedup.key_columns in pipeline config,
            # or fall back to lineage_config.entity_id_column (the natural PK).
            _cross_batch_removed = 0
            _new_fps: Optional[pd.Series] = None
            _cbd_key_cols = self._get_cross_batch_key_columns(parsed, raw_config)
            if _cbd_key_cols and all(c in df.columns for c in _cbd_key_cols):
                from layer2_pipeline.quality.deduplicator import CrossBatchDeduplicator
                _cbd = CrossBatchDeduplicator(key_columns=_cbd_key_cols)
                _seen_fps = self._load_seen_fingerprints(parsed.pipeline_id, ctx.client_id)
                _all_fps = _cbd.compute_fingerprints(df)
                df, _cross_batch_removed = _cbd.filter_new(df, _seen_fps)
                _new_fps = _all_fps[~_all_fps.isin(_seen_fps)].reset_index(drop=True)
                if _cross_batch_removed > 0:
                    logger.info(
                        "Cross-batch dedup: suppressed %d already-seen records (pipeline=%s)",
                        _cross_batch_removed, parsed.pipeline_id,
                    )
                    ctx.warn(f"Cross-batch dedup: {_cross_batch_removed} duplicate records suppressed")
            elif _cbd_key_cols:
                logger.debug(
                    "Cross-batch dedup skipped — key columns %s not all present in schema",
                    _cbd_key_cols,
                )

            # Execute each step in topological order
            for step_def in parsed.steps:
                df, ok = self._execute_step(df, step_def, ctx, run, named_frames)
                if not ok and step_def.on_error == "fail":
                    return self._fail_run(run, ctx, f"Step {step_def.step_id!r} failed")
                named_frames[step_def.step_id] = df

            # Emit lineage events for the output entities
            self._emit_lineage(df, ctx, parsed)

            output_path = self._write_output(df, ctx, pipeline_def.client_id, run_id_str)

            # Compute output schema fingerprint
            schema_fp = _schema_fingerprint(df) if not df.empty else None

            completed_run = self._complete_run(run, ctx, records_input, len(df), output_path)

            # Write immutable dataset version record
            self._write_dataset_version(run, ctx, parsed, run_id_str, output_path, schema_fp, len(df))

            # Persist cross-batch fingerprints so future runs skip these records
            if _new_fps is not None and len(_new_fps) > 0:
                self._persist_fingerprints(
                    fingerprints=_new_fps.tolist(),
                    pipeline_id=parsed.pipeline_id,
                    client_id=ctx.client_id,
                    batch_id=input_batch_id,
                    run_id_str=run_id_str,
                )

            # Publish layer2.clean.ready for Layer 3 ingestion trigger
            self._publish_layer2_complete(run, parsed, output_path)

            return completed_run

        finally:
            self._lineage.flush(ctx)
            self._quarantine.flush(ctx, run.id)
            self._advisory_unlock(lock_key)

    # ── private helpers ────────────────────────────────────────────────────────

    def _load_input(
        self, ctx: ExecutionContext, input_path: Optional[str], client_id: str
    ) -> Optional[pd.DataFrame]:
        from layer1_ingestion.core.storage import download_parquet, get_minio_client
        from minio.error import S3Error

        if not input_path:
            ctx.warn("No input_path provided — pipeline has no input data")
            return pd.DataFrame()

        try:
            bucket = "raw-data"
            df = download_parquet(bucket, input_path)
            logger.info("Loaded %d rows from %s/%s", len(df), bucket, input_path)
            return df
        except S3Error as exc:
            classified = classify(exc, step_id="input_load")
            ctx.add_failed_record(
                step_id="input_load",
                error_type=classified.error_type.value,
                error_subtype=classified.error_subtype.value,
                error_message=classified.message,
                severity="error",
            )
            logger.error("Failed to load input %s: %s", input_path, exc)
            return None
        except Exception as exc:
            logger.error("Unexpected error loading input %s: %s", input_path, exc)
            ctx.warn(f"Input load error: {exc}")
            return None

    def _execute_step(
        self,
        df: pd.DataFrame,
        step_def: StepDefinition,
        ctx: ExecutionContext,
        run: PipelineRun,
        named_frames: dict[str, pd.DataFrame],
    ) -> tuple[pd.DataFrame, bool]:
        transform = transform_registry.get(step_def.transform_type)
        if transform is None:
            msg = f"Unknown transform type {step_def.transform_type!r}"
            ctx.warn(msg)
            self._update_step_run(run, step_def, "failed", error_message=msg)
            return df, False

        # Inject named_frames into config for multi-frame transforms
        config = {**step_def.config, "_named_frames": named_frames}

        self._update_step_run(run, step_def, "running")

        try:
            result_df = transform(df, config, ctx, step_def.step_id)

            # Run quality rules if defined
            if step_def.quality_rules:
                rules = [QualityRule.from_dict(r) for r in step_def.quality_rules]
                validator = DataQualityValidator(named_frames=named_frames)
                result_df, _ = validator.validate(result_df, rules, ctx, step_def.step_id)

            self._update_step_run(run, step_def, "completed")
            return result_df, True

        except Exception as exc:
            classified = classify(exc, step_id=step_def.step_id)
            msg = classified.message
            logger.error("Step %s failed: %s", step_def.step_id, msg)
            self._update_step_run(run, step_def, "failed", error_message=msg)
            ctx.add_failed_record(
                step_id=step_def.step_id,
                error_type=classified.error_type.value,
                error_subtype=classified.error_subtype.value,
                error_message=msg,
                severity=classified.severity,
            )
            if step_def.on_error in ("skip", "warn"):
                ctx.warn(f"Step {step_def.step_id!r} skipped after error: {msg}")
                return df, True  # continue with original df
            return df, False

    def _write_output(
        self, df: pd.DataFrame, ctx: ExecutionContext, client_id: str, run_id_str: str
    ) -> Optional[str]:
        from layer1_ingestion.core.storage import upload_parquet, ensure_bucket_exists, object_exists

        if df.empty:
            ctx.warn("Output DataFrame is empty — skipping MinIO write")
            return None

        now = datetime.now(timezone.utc)
        object_path = (
            f"{client_id}/{ctx.pipeline_id}/{ctx.pipeline_version}"
            f"/{now.year}/{now.month:02d}/{now.day:02d}/{run_id_str}.parquet"
        )
        try:
            ensure_bucket_exists(PROCESSED_BUCKET)
            if object_exists(PROCESSED_BUCKET, object_path):
                logger.info("Output already exists at %s — skipping upload", object_path)
                return object_path
            upload_parquet(
                df, PROCESSED_BUCKET, object_path,
                extra_metadata={
                    "pipeline_id": ctx.pipeline_id,
                    "pipeline_version": ctx.pipeline_version,
                    "run_id": run_id_str,
                },
            )
            logger.info("Wrote output to %s/%s (%d rows)", PROCESSED_BUCKET, object_path, len(df))
            return object_path
        except Exception as exc:
            classified = classify(exc, step_id="output_write")
            ctx.add_failed_record(
                step_id="output_write",
                error_type=classified.error_type.value,
                error_subtype=classified.error_subtype.value,
                error_message=classified.message,
                severity="error",
            )
            logger.error("Failed to write output: %s", exc)
            return None

    def _create_run(
        self,
        pipeline_def: DBPipelineDefinition,
        ctx: ExecutionContext,
        run_id: str,
        input_batch_id: Optional[str],
        input_path: Optional[str],
    ) -> PipelineRun:
        run = PipelineRun(
            pipeline_definition_id=pipeline_def.id,
            run_id=run_id,
            client_id=ctx.client_id,
            status="running",
            triggered_by=ctx.triggered_by,
            input_batch_id=input_batch_id,
            input_path=input_path,
            started_at=ctx.started_at,
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def _create_failed_run(
        self, pipeline_def: DBPipelineDefinition, input_batch_id: Optional[str], error: str
    ) -> PipelineRun:
        run = PipelineRun(
            pipeline_definition_id=pipeline_def.id,
            run_id=None,
            client_id=pipeline_def.client_id,
            status="failed",
            triggered_by="scheduler",
            input_batch_id=input_batch_id,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            error_summary=error,
        )
        self.db.add(run)
        self.db.commit()
        return run

    def _emit_lineage(
        self,
        df: pd.DataFrame,
        ctx: ExecutionContext,
        parsed: "PipelineDefinitionParsed",
    ) -> None:
        lc = parsed.lineage_config
        if not lc or df.empty:
            return
        entity_type = lc.get("entity_type", "")
        entity_id_col = lc.get("entity_id_column", "")
        if not entity_type or not entity_id_col or entity_id_col not in df.columns:
            return
        last_step = parsed.topological_order[-1] if parsed.topological_order else "pipeline"
        # Cap at 10,000 unique entities to avoid unbounded memory use
        unique_ids = df[entity_id_col].dropna().unique()[:10_000]
        for eid in unique_ids:
            ctx.add_lineage(
                entity_type=entity_type,
                entity_id=str(eid),
                field_name="pipeline_output",
                step_id=last_step,
                transform_applied=parsed.pipeline_id,
            )
        logger.info(
            "Emitted %d lineage events: entity_type=%r pipeline=%s",
            len(unique_ids), entity_type, parsed.pipeline_id,
        )

    def _write_dataset_version(
        self,
        run: PipelineRun,
        ctx: ExecutionContext,
        parsed: "PipelineDefinitionParsed",
        run_id_str: str,
        output_path: Optional[str],
        schema_fingerprint: Optional[str],
        records_output: int,
    ) -> None:
        try:
            version = DatasetVersion(
                pipeline_run_id=run.id,
                pipeline_id=parsed.pipeline_id,
                pipeline_version=parsed.version,
                client_id=ctx.client_id,
                run_id_str=run_id_str,
                input_batch_id=ctx.input_batch_id,
                input_path=ctx.input_path,
                output_path=output_path,
                schema_fingerprint=schema_fingerprint,
                records_output=records_output,
            )
            self.db.add(version)
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            logger.warning("DatasetVersion write failed (non-fatal): %s", exc)

    def _advisory_unlock(self, lock_key: int) -> None:
        try:
            self.db.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_key})
            self.db.commit()
        except Exception as exc:
            logger.warning("Advisory unlock failed: %s", exc)

    def _fail_run(self, run: PipelineRun, ctx: ExecutionContext, reason: str) -> PipelineRun:
        now = datetime.now(timezone.utc)
        run.status = "failed"
        run.completed_at = now
        run.duration_seconds = (now - ctx.started_at).total_seconds()
        run.error_summary = reason
        self.db.commit()
        return run

    def _complete_run(
        self,
        run: PipelineRun,
        ctx: ExecutionContext,
        records_in: int,
        records_out: int,
        output_path: Optional[str],
    ) -> PipelineRun:
        now = datetime.now(timezone.utc)
        run.status = "completed"
        run.completed_at = now
        run.duration_seconds = (now - ctx.started_at).total_seconds()
        run.records_input = records_in
        run.records_output = records_out
        run.records_failed = ctx.total_records_failed
        run.output_path = output_path
        self.db.commit()
        return run

    # ── cross-batch dedup helpers ──────────────────────────────────────────────

    @staticmethod
    def _get_cross_batch_key_columns(
        parsed: "PipelineDefinitionParsed", raw_config: dict
    ) -> list[str]:
        """Return key columns for cross-batch fingerprinting, in priority order:
        1. Explicit cross_batch_dedup.key_columns in pipeline config.
        2. lineage_config.entity_id_column (the natural entity primary key).
        """
        cbd = raw_config.get("cross_batch_dedup", {})
        if cbd.get("enabled") is False:
            return []
        explicit = cbd.get("key_columns", [])
        if explicit:
            return explicit
        lc = parsed.lineage_config or {}
        eid = lc.get("entity_id_column")
        return [eid] if eid else []

    def _load_seen_fingerprints(self, pipeline_id: str, client_id: str) -> set[str]:
        """Load fingerprints seen in the last 90 days for this pipeline."""
        from layer2_pipeline.models.db_models import BatchFingerprint
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=90)
            rows = (
                self.db.query(BatchFingerprint.fingerprint)
                .filter(
                    BatchFingerprint.pipeline_id == pipeline_id,
                    BatchFingerprint.client_id == client_id,
                    BatchFingerprint.created_at >= cutoff,
                )
                .all()
            )
            return {row[0] for row in rows}
        except Exception as exc:
            logger.warning("Could not load seen fingerprints (cross-batch dedup skipped): %s", exc)
            return set()

    def _persist_fingerprints(
        self,
        fingerprints: list[str],
        pipeline_id: str,
        client_id: str,
        batch_id: Optional[str],
        run_id_str: str,
    ) -> None:
        """Batch-insert new fingerprints. ON CONFLICT DO NOTHING for idempotency."""
        if not fingerprints:
            return
        try:
            # Cap per-run inserts to prevent runaway memory on massive batches
            capped = fingerprints[:50_000]
            now = datetime.now(timezone.utc)
            self.db.execute(
                text("""
                    INSERT INTO l2_batch_fingerprints
                        (id, pipeline_id, client_id, fingerprint, first_seen_batch_id, created_at)
                    VALUES
                        (:id, :pipeline_id, :client_id, :fingerprint, :batch_id, :created_at)
                    ON CONFLICT (pipeline_id, fingerprint) DO NOTHING
                """),
                [
                    {
                        "id": str(uuid.uuid4()),
                        "pipeline_id": pipeline_id,
                        "client_id": client_id,
                        "fingerprint": fp,
                        "batch_id": batch_id,
                        "created_at": now,
                    }
                    for fp in capped
                ],
            )
            self.db.commit()
            logger.info(
                "Persisted %d cross-batch fingerprints for pipeline=%s", len(capped), pipeline_id
            )
        except Exception as exc:
            self.db.rollback()
            logger.warning("Fingerprint persistence failed (non-fatal): %s", exc)

    def _publish_layer2_complete(
        self,
        run: "PipelineRun",
        parsed: "PipelineDefinitionParsed",
        output_path: Optional[str],
    ) -> None:
        """Publish layer2.clean.ready to Kafka so Layer 3 can trigger ingestion."""
        if not output_path:
            return
        try:
            import os as _os
            from kafka import KafkaProducer
            import json as _json

            producer = KafkaProducer(
                bootstrap_servers=_os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"),
                acks="all",
                retries=2,
                value_serializer=lambda v: _json.dumps(v, default=str).encode("utf-8"),
            )
            producer.send(
                "layer2.clean.ready",
                value={
                    "run_id": run.run_id,
                    "pipeline_id": parsed.pipeline_id,
                    "client_id": run.client_id,
                    "output_path": output_path,
                    "records_output": run.records_output,
                },
            )
            producer.flush(timeout=5)
            producer.close()
            logger.info(
                "Published layer2.clean.ready: pipeline=%s output=%s",
                parsed.pipeline_id, output_path,
            )
        except Exception as exc:
            logger.warning("Kafka layer2.clean.ready publish failed (non-fatal): %s", exc)

    def _update_step_run(
        self,
        run: PipelineRun,
        step_def: StepDefinition,
        status: str,
        error_message: Optional[str] = None,
    ) -> None:
        existing = (
            self.db.query(PipelineStepRun)
            .filter(
                PipelineStepRun.run_id == run.id,
                PipelineStepRun.step_id == step_def.step_id,
            )
            .first()
        )
        now = datetime.now(timezone.utc)
        if existing is None:
            step_run = PipelineStepRun(
                run_id=run.id,
                step_id=step_def.step_id,
                transform_type=step_def.transform_type,
                status=status,
                started_at=now,
                config_snapshot=step_def.config,
            )
            self.db.add(step_run)
        else:
            existing.status = status
            if status in ("completed", "failed"):
                existing.completed_at = now
            if error_message:
                existing.error_message = error_message
        try:
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            logger.warning("Failed to update step run for %s: %s", step_def.step_id, exc)
