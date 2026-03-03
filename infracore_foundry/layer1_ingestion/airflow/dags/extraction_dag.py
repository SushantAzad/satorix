"""
Airflow DAG for scheduled data extraction pipelines.
Dynamically generates tasks per registered data source.
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago


default_args = {
    "owner": "infracore",
    "depends_on_past": False,
    "email_on_failure": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


def run_extraction(source_id: str, sync_type: str = "incremental", **kwargs):
    """Execute extraction for a single data source."""
    import logging
    from layer1_ingestion.core.database import get_db_context
    from layer1_ingestion.registry.source_registry import SourceRegistry
    from layer1_ingestion.sync.sync_engine import SyncEngine
    from layer1_ingestion.core.config import get_settings
    from layer1_ingestion.health.alert_manager import AlertManager

    logger = logging.getLogger(__name__)
    settings = get_settings()

    with get_db_context() as db:
        registry = SourceRegistry(db)
        source = registry.get_source(source_id)
        if source is None:
            raise ValueError(f"Data source {source_id} not found")

        connector_cls = settings.get_connector_class(source.source_type)
        if connector_cls is None:
            raise ValueError(f"No connector for type: {source.source_type}")

        connector = connector_cls(str(source.id), source.config or {})
        engine = SyncEngine(db)
        run = engine.run_sync(source, connector, sync_type=sync_type)

        alert_mgr = AlertManager(db)
        alert_mgr.check_and_alert_on_sync(
            source.id, run.status,
            error=run.error_details,
            records=run.records_extracted or 0,
        )

        if run.status == "failed":
            raise Exception(f"Sync failed: {run.error_details}")

        logger.info(
            "DAG extraction complete: source=%s, records=%d",
            source_id, run.records_extracted or 0,
        )
        return {"source_id": source_id, "records": run.records_extracted, "status": run.status}


def run_health_checks(**kwargs):
    """Run health checks on all active data sources."""
    import logging
    from layer1_ingestion.core.database import get_db_context
    from layer1_ingestion.registry.source_registry import SourceRegistry
    from layer1_ingestion.health.monitor import ConnectionHealthMonitor
    from layer1_ingestion.health.alert_manager import AlertManager
    from layer1_ingestion.core.config import get_settings

    logger = logging.getLogger(__name__)
    settings = get_settings()

    with get_db_context() as db:
        registry = SourceRegistry(db)
        sources = registry.list_sources(is_active=True)
        monitor = ConnectionHealthMonitor(db)
        alert_mgr = AlertManager(db)
        results = []

        for source in sources:
            try:
                connector_cls = settings.get_connector_class(source.source_type)
                if connector_cls is None:
                    continue
                connector = connector_cls(str(source.id), source.config or {})
                health = monitor.check_health(source, connector)
                alert_mgr.check_and_alert_on_health(source.id, health.status, health.error_message)
                results.append({"source_id": str(source.id), "status": health.status})
            except Exception as e:
                logger.warning("Health check failed for %s: %s", source.id, str(e))
                results.append({"source_id": str(source.id), "status": "error", "error": str(e)})

        logger.info("Health checks complete: %d sources checked", len(results))
        return results


# --- Main extraction DAG ---
with DAG(
    dag_id="layer1_data_extraction",
    default_args=default_args,
    description="Scheduled data extraction from all registered sources",
    schedule_interval="0 */6 * * *",  # Every 6 hours
    start_date=days_ago(1),
    catchup=False,
    max_active_runs=1,
    tags=["layer1", "extraction", "infracore"],
) as extraction_dag:

    extract_task = PythonOperator(
        task_id="run_all_extractions",
        python_callable=run_extraction,
        op_kwargs={"source_id": "{{ dag_run.conf.get('source_id', '') }}", "sync_type": "{{ dag_run.conf.get('sync_type', 'incremental') }}"},
    )


# --- Health check DAG ---
with DAG(
    dag_id="layer1_health_checks",
    default_args=default_args,
    description="Periodic health checks on all data source connections",
    schedule_interval="*/30 * * * *",  # Every 30 minutes
    start_date=days_ago(1),
    catchup=False,
    max_active_runs=1,
    tags=["layer1", "health", "infracore"],
) as health_dag:

    health_task = PythonOperator(
        task_id="run_all_health_checks",
        python_callable=run_health_checks,
    )
