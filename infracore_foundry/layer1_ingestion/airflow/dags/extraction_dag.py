"""
Airflow DAGs for Layer 1 data extraction and health monitoring.

extraction_dag  — runs every 6 hours, processes ALL active sources concurrently.
health_dag      — runs every 30 minutes, checks connectivity of all active sources.
cleanup_dag     — runs every hour, reaps stale 'running' sync_run records.
"""

import logging
from datetime import datetime, timedelta

from airflow import DAG
from airflow.decorators import task
from airflow.utils.dates import days_ago

logger = logging.getLogger(__name__)

DEFAULT_ARGS = {
    "owner": "infracore",
    "depends_on_past": False,
    "email_on_failure": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=30),
}


# ---------------------------------------------------------------------------
# Helpers — imported lazily inside task functions so Airflow does not execute
# them at DAG parse time (which has no DB access).
# ---------------------------------------------------------------------------

def _get_connector(source, settings):
    """Return an instantiated, configured connector for a DataSource."""
    from layer1_ingestion.core.config import get_connector_class
    from layer1_ingestion.registry.source_registry import SourceRegistry
    from layer1_ingestion.core.database import get_db_context

    connector_cls = get_connector_class(source.source_type)
    if connector_cls is None:
        raise ValueError(f"No connector registered for type: {source.source_type!r}")

    # Decrypt connection config — never pass the encrypted blob to the connector.
    with get_db_context() as db:
        registry = SourceRegistry(db)
        decrypted_config = registry.get_source_config(source.id)

    return connector_cls(str(source.id), decrypted_config)


# ---------------------------------------------------------------------------
# Extraction DAG
# ---------------------------------------------------------------------------

with DAG(
    dag_id="layer1_data_extraction",
    default_args=DEFAULT_ARGS,
    description="Scheduled data extraction from all registered active sources",
    schedule_interval="0 */6 * * *",
    start_date=days_ago(1),
    catchup=False,
    max_active_runs=1,
    tags=["layer1", "extraction"],
) as extraction_dag:

    @task(dag=extraction_dag)
    def get_active_source_ids() -> list[str]:
        """Query DB for all active source IDs. Runs at task-execution time, not parse time."""
        from layer1_ingestion.core.database import get_db_context
        from layer1_ingestion.registry.source_registry import SourceRegistry

        with get_db_context() as db:
            sources = SourceRegistry(db).get_active_sources()

        ids = [str(s.id) for s in sources if not s.circuit_open]
        logger.info("Found %d active sources for extraction", len(ids))
        return ids

    @task(dag=extraction_dag)
    def extract_source(source_id: str) -> dict:
        """Extract data for a single source. One Airflow task instance per source."""
        from layer1_ingestion.core.database import get_db_context
        from layer1_ingestion.core.config import get_settings
        from layer1_ingestion.registry.source_registry import SourceRegistry
        from layer1_ingestion.registry.models import DataSource
        from layer1_ingestion.sync.sync_engine import SyncEngine
        from layer1_ingestion.health.alert_manager import AlertManager

        settings = get_settings()

        with get_db_context() as db:
            source = db.query(DataSource).filter(DataSource.id == source_id).first()
            if source is None:
                raise ValueError(f"Source {source_id} not found in registry")

            if source.circuit_open:
                logger.warning("Skipping source %s — circuit is open", source_id)
                return {"source_id": source_id, "status": "skipped", "records": 0}

            # Build connector using decrypted config
            from layer1_ingestion.core.config import get_connector_class
            connector_cls = get_connector_class(source.source_type)
            if connector_cls is None:
                raise ValueError(f"No connector for type: {source.source_type!r}")

            registry = SourceRegistry(db)
            decrypted_config = registry.get_source_config(source.id)
            connector = connector_cls(str(source.id), decrypted_config)

            engine = SyncEngine(db)
            run = engine.run_sync(source, connector, sync_type="incremental")

            alert_mgr = AlertManager(db)
            alert_mgr.check_and_alert_on_sync(
                source_id=source.id,
                status=run.status,
                error=run.error_details,
                records=run.records_extracted or 0,
            )

        logger.info(
            "Extraction complete: source=%s records=%d status=%s",
            source_id, run.records_extracted or 0, run.status,
        )

        if run.status == "failed":
            raise RuntimeError(f"Sync failed for source {source_id}: {run.error_details}")

        return {
            "source_id": source_id,
            "status": run.status,
            "records": run.records_extracted or 0,
            "batch_id": run.batch_id,
        }

    # Dynamic task mapping: one task per active source
    source_ids = get_active_source_ids()
    extract_source.expand(source_id=source_ids)


# ---------------------------------------------------------------------------
# Health Check DAG
# ---------------------------------------------------------------------------

with DAG(
    dag_id="layer1_health_checks",
    default_args=DEFAULT_ARGS,
    description="Periodic health checks on all data source connections",
    schedule_interval="*/30 * * * *",
    start_date=days_ago(1),
    catchup=False,
    max_active_runs=1,
    tags=["layer1", "health"],
) as health_dag:

    @task(dag=health_dag)
    def run_all_health_checks() -> list[dict]:
        from layer1_ingestion.core.database import get_db_context
        from layer1_ingestion.core.config import get_connector_class
        from layer1_ingestion.registry.source_registry import SourceRegistry
        from layer1_ingestion.sync.state_manager import SyncStateManager
        from layer1_ingestion.health.monitor import ConnectionHealthMonitor
        from layer1_ingestion.health.alert_manager import AlertManager

        results = []

        with get_db_context() as db:
            registry = SourceRegistry(db)
            sources = registry.get_active_sources()
            monitor = ConnectionHealthMonitor(db)
            alert_mgr = AlertManager(db)
            state_mgr = SyncStateManager(db)

            for source in sources:
                try:
                    connector_cls = get_connector_class(source.source_type)
                    if connector_cls is None:
                        logger.warning("No connector for type %s, skipping health check", source.source_type)
                        continue

                    decrypted_config = registry.get_source_config(source.id)
                    connector = connector_cls(str(source.id), decrypted_config)

                    previous_fp = state_mgr.get_schema_fingerprint(source.id)
                    health = monitor.check_health(source, connector, previous_schema_fingerprint=previous_fp)

                    alert_mgr.check_and_alert_on_health(
                        source_id=source.id,
                        is_reachable=health.is_reachable,
                        error_message=health.error_message,
                        schema_drift=(health.schema_matches is False),
                    )

                    results.append({
                        "source_id": str(source.id),
                        "reachable": health.is_reachable,
                        "response_ms": health.response_time_ms,
                    })
                except Exception as exc:
                    logger.warning(
                        "Health check failed for source %s: %s", source.id, str(exc)
                    )
                    results.append({
                        "source_id": str(source.id),
                        "reachable": False,
                        "error": str(exc),
                    })

        logger.info("Health checks complete: %d sources checked", len(results))
        return results

    run_all_health_checks()


# ---------------------------------------------------------------------------
# Stale Run Cleanup DAG
# ---------------------------------------------------------------------------

with DAG(
    dag_id="layer1_cleanup_stale_runs",
    default_args=DEFAULT_ARGS,
    description="Reap sync_run records stuck in 'running' state",
    schedule_interval="0 * * * *",   # hourly
    start_date=days_ago(1),
    catchup=False,
    max_active_runs=1,
    tags=["layer1", "maintenance"],
) as cleanup_dag:

    @task(dag=cleanup_dag)
    def cleanup_stale_runs() -> dict:
        from layer1_ingestion.core.database import get_db_context
        from layer1_ingestion.sync.state_manager import SyncStateManager

        with get_db_context() as db:
            mgr = SyncStateManager(db)
            cleaned = mgr.cleanup_stale_runs()   # cleans ALL sources

        logger.info("Stale run cleanup: %d run(s) marked failed", cleaned)
        return {"cleaned": cleaned}

    cleanup_stale_runs()
