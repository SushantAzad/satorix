"""
Layer 4 — Nightly Intelligence Batch DAG
Schedule: 1am daily
Phases run sequentially; each is a separate task so Airflow can retry independently.
"""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

import sys
import os

sys.path.insert(0, "/app")

default_args = {
    "owner": "satorix-l4",
    "depends_on_past": False,
    "email_on_failure": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="l4_nightly_intelligence_batch",
    default_args=default_args,
    description="Layer 4: Nightly graph intelligence computation (centrality, clusters, precursor model)",
    schedule_interval="0 1 * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["layer4", "graph", "intelligence", "nightly"],
) as dag:

    def _start_run(**context):
        import asyncio
        from scheduler.batch_jobs import _ensure_clients, _close_clients, start_batch_run
        async def _inner():
            await _ensure_clients()
            run_id = await start_batch_run()
            await _close_clients()
            return run_id
        run_id = asyncio.run(_inner())
        context["task_instance"].xcom_push(key="run_id", value=run_id)

    def _make_phase(name):
        def _task(**context):
            run_id = context["task_instance"].xcom_pull(task_ids="start_run", key="run_id")
            from scheduler.batch_jobs import run_phase
            context.setdefault("dag_run", type("DR", (), {"conf": {"run_id": run_id}})())
            run_phase(name, **context)
        _task.__name__ = f"phase_{name}"
        return _task

    t_start = PythonOperator(task_id="start_run", python_callable=_start_run)

    t_projection = PythonOperator(task_id="create_projection", python_callable=_make_phase("create_projection"))
    t_betweenness = PythonOperator(task_id="betweenness", python_callable=_make_phase("betweenness"))
    t_pagerank = PythonOperator(task_id="pagerank", python_callable=_make_phase("pagerank"))
    t_degree = PythonOperator(task_id="degree", python_callable=_make_phase("degree"))
    t_reg_exposure = PythonOperator(task_id="regulatory_exposure", python_callable=_make_phase("regulatory_exposure"))
    t_risk_weighted = PythonOperator(task_id="risk_weighted", python_callable=_make_phase("risk_weighted"))

    t_louvain = PythonOperator(task_id="louvain", python_callable=_make_phase("louvain"))
    t_label_prop = PythonOperator(task_id="label_propagation", python_callable=_make_phase("label_propagation"))
    t_addr_clusters = PythonOperator(task_id="address_clusters", python_callable=_make_phase("address_clusters"))
    t_dir_clusters = PythonOperator(task_id="director_clusters", python_callable=_make_phase("director_clusters"))

    t_shared_attrs = PythonOperator(task_id="shared_attributes", python_callable=_make_phase("shared_attributes"))
    t_precursor = PythonOperator(task_id="precursor_model", python_callable=_make_phase("precursor_model"))
    t_snapshots = PythonOperator(task_id="snapshots", python_callable=_make_phase("snapshots"))
    t_drop_proj = PythonOperator(task_id="drop_projection", python_callable=_make_phase("drop_projection"))

    # DAG topology
    # start → projection → betweenness (most expensive, first)
    t_start >> t_projection >> t_betweenness

    # Betweenness done → pagerank, degree, reg_exposure in parallel
    t_betweenness >> [t_pagerank, t_degree, t_reg_exposure]

    # All three → risk_weighted composite
    [t_pagerank, t_degree, t_reg_exposure] >> t_risk_weighted

    # Cluster detection runs in parallel after projection
    t_projection >> [t_louvain, t_label_prop, t_addr_clusters, t_dir_clusters]

    # All clusters done → shared attributes write-back
    [t_louvain, t_label_prop, t_addr_clusters, t_dir_clusters] >> t_shared_attrs

    # Precursor model needs clusters + influence scores
    [t_risk_weighted, t_shared_attrs] >> t_precursor

    # Snapshots refresh after everything
    t_precursor >> t_snapshots >> t_drop_proj
