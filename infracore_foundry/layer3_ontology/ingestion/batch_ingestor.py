import time
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any
import logging
import pandas as pd

from core.config import settings
from core.minio_client import minio_client
from storage.object_data_funnel import object_data_funnel
from storage.incremental_indexer import incremental_indexer
from .parquet_loader import ParquetLoader
from .object_mapper import object_mapper, SOURCE_NAME_ALIASES
from .relationship_mapper import relationship_mapper
from .schema_validator import schema_validator
from core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


@dataclass
class IngestSummary:
    objects_processed: int = 0
    objects_created: int = 0
    objects_updated: int = 0
    objects_unchanged: int = 0
    links_created: int = 0
    links_updated: int = 0
    inferred_links_created: int = 0
    alerts_created: int = 0
    risk_scores_updated: int = 0
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    started_at: str = ""
    completed_at: str = ""


class BatchIngestor:
    def __init__(self) -> None:
        self._loader = ParquetLoader()

    async def ingest_from_layer2(
        self,
        client_id: str = "infracore",
        source_ids: list[str] | None = None,
    ) -> IngestSummary:
        summary = IngestSummary()
        summary.started_at = datetime.now(timezone.utc).isoformat()
        start_time = time.time()

        logger.info("Starting batch ingestion for client=%s", client_id)

        # Step 1: Load Parquet files from MinIO
        all_dataframes: dict[str, pd.DataFrame] = {}
        try:
            files = self._loader.list_source_files(client_id)
            for file_path in files:
                if source_ids and not any(sid in file_path for sid in source_ids):
                    continue
                try:
                    df, _ = self._loader.load_dataframe(settings.minio_raw_bucket, file_path)
                    source_name = file_path.split("/")[-1].replace(".parquet", "")
                    all_dataframes[source_name] = df
                except Exception as e:
                    summary.errors.append(f"Load error {file_path}: {e}")
        except Exception as e:
            summary.errors.append(f"MinIO connection error: {e}")
            logger.warning("MinIO unavailable, using empty dataset: %s", e)

        # Step 2: Map objects and write through Funnel
        async with AsyncSessionLocal() as db:
            for source_name, df in all_dataframes.items():
                mapped_records = object_mapper.map_dataframe(source_name, df)
                if not mapped_records:
                    continue

                object_type = mapped_records[0].get("_object_type", "unknown")
                pk_field_map = {
                    "company": "cin", "director": "din", "project": "projectId",
                    "regulatory_action": "actionId", "insolvency_proceeding": "cirpId",
                }
                pk_field = pk_field_map.get(object_type, "id")

                # Step 3: Validate
                clean = [{k: v for k, v in r.items() if not k.startswith("_")} for r in mapped_records]
                valid, rejected = schema_validator.validate_batch(object_type, clean)
                for r in rejected:
                    summary.errors.append(f"Validation failed {object_type}: {r.get('_validation_errors')}")

                summary.objects_processed += len(valid)

                # Step 4: Incremental filter
                changed, stats = await incremental_indexer.filter_changed(db, object_type, valid, pk_field)
                summary.objects_unchanged += stats["unchanged"]

                # Step 5: Write changed objects through Funnel
                chunk_size = settings.ingest_chunk_size
                for i in range(0, len(changed), chunk_size):
                    chunk = changed[i:i + chunk_size]
                    for record in chunk:
                        result = await object_data_funnel.write_object(
                            object_type=object_type,
                            data=record,
                            source=f"batch_ingestion:{source_name}",
                            actor="system_pipeline",
                        )
                        if result.success:
                            if result.version == 1:
                                summary.objects_created += 1
                            else:
                                summary.objects_updated += 1
                        else:
                            summary.errors.extend(result.errors)

        # Step 6: Write relationships
        for source_name, df in all_dataframes.items():
            links = await self._extract_links(source_name, df)
            for link in links:
                result = await object_data_funnel.write_link(
                    link_type=link["link_type"],
                    source_type=link["source_type"],
                    source_id=link["source_id"],
                    target_type=link["target_type"],
                    target_id=link["target_id"],
                    properties=link.get("properties", {}),
                    actor="system_pipeline",
                )
                if result.success:
                    summary.links_created += 1
                else:
                    summary.errors.extend(result.errors)

        # Step 7: Run inference engine
        try:
            from intelligence.inference_engine import inference_engine
            inferred = await inference_engine.run_all()
            summary.inferred_links_created = inferred
        except Exception as e:
            logger.error("Inference engine failed: %s", e)
            summary.errors.append(f"Inference engine: {e}")

        # Step 8: Run risk scoring
        try:
            from intelligence.risk_scoring.engine import risk_scoring_engine
            updated = await risk_scoring_engine.score_all()
            summary.risk_scores_updated = updated
        except Exception as e:
            logger.error("Risk scoring failed: %s", e)
            summary.errors.append(f"Risk scoring: {e}")

        # Step 9: Run anomaly detection
        try:
            from intelligence.anomaly_detection.director_proliferation import director_proliferation_detector
            from intelligence.anomaly_detection.address_clustering import address_clustering_detector
            from intelligence.anomaly_detection.regulatory_recidivism import regulatory_recidivism_detector
            from intelligence.anomaly_detection.cirp_contagion import cirp_contagion_detector
            from intelligence.anomaly_detection.filing_compliance import filing_compliance_detector

            for detector in [
                director_proliferation_detector,
                address_clustering_detector,
                regulatory_recidivism_detector,
                cirp_contagion_detector,
                filing_compliance_detector,
            ]:
                alerts = await detector.detect()
                summary.alerts_created += alerts
        except Exception as e:
            logger.error("Anomaly detection failed: %s", e)
            summary.errors.append(f"Anomaly detection: {e}")

        summary.duration_seconds = round(time.time() - start_time, 2)
        summary.completed_at = datetime.now(timezone.utc).isoformat()
        logger.info(
            "Ingestion complete: %d objects processed, %d created, %d updated, %d errors in %.1fs",
            summary.objects_processed, summary.objects_created, summary.objects_updated,
            len(summary.errors), summary.duration_seconds,
        )

        # Publish layer3.ingest.complete — triggers Layer 4 graph recompute + cache refresh
        try:
            from core.kafka_publisher import get_ontology_publisher
            get_ontology_publisher().emit_ingest_complete({
                "client_id": client_id,
                "objects_created": summary.objects_created,
                "objects_updated": summary.objects_updated,
                "links_created": summary.links_created,
                "alerts_created": summary.alerts_created,
                "risk_scores_updated": summary.risk_scores_updated,
                "duration_seconds": summary.duration_seconds,
                "completed_at": summary.completed_at,
            })
        except Exception as _ke:
            logger.warning("Kafka ingest.complete publish failed (non-fatal): %s", _ke)

        return summary

    async def _extract_links(self, source_name: str, df: pd.DataFrame) -> list[dict]:
        links: list[dict] = []
        sn_lower = source_name.lower()
        try:
            if "director" in sn_lower:
                links.extend(relationship_mapper.map_director_links(df))
            elif "shareholding" in sn_lower or "ownership" in sn_lower:
                links.extend(relationship_mapper.map_ownership_links(df))
            elif "regulatory" in sn_lower:
                links.extend(relationship_mapper.map_regulatory_links(df))
            elif "project" in sn_lower:
                links.extend(relationship_mapper.map_project_links(df))
            elif "insolvency" in sn_lower or "cirp" in sn_lower:
                links.extend(relationship_mapper.map_insolvency_links(df))
            elif "company" in sn_lower:
                links.extend(relationship_mapper.map_address_links(df))
        except Exception as e:
            logger.error("Link extraction failed for %s: %s", source_name, e)
        return links


batch_ingestor = BatchIngestor()
