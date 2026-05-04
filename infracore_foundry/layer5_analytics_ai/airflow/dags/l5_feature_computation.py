"""
Nightly feature computation DAG.
Runs before L4 batch so L4 influence scores are already available.
Schedule: daily at 01:00 IST (19:30 UTC previous day).
"""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

default_args = {
    "owner": "satorix-l5",
    "retries": 2,
    "retry_delay": timedelta(minutes=10),
    "email_on_failure": False,
}

dag = DAG(
    "l5_feature_computation",
    default_args=default_args,
    description="Compute Layer 5 feature vectors for all Company and Project entities",
    schedule_interval="30 19 * * *",  # 01:00 IST
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["layer5", "features"],
)


def compute_company_features(**kwargs):
    import asyncio
    import sys
    sys.path.insert(0, "/app")

    from core.database import init_db_pool, close_db_pool, get_pool
    from core.neo4j_client import init_neo4j, close_neo4j
    from feature_store.feature_computer import feature_computer
    from feature_store.feature_store import upsert_features

    async def run():
        await init_db_pool()
        await init_neo4j()
        pool = get_pool()

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT primary_key, properties->>'cin' AS cin FROM ontology_objects WHERE object_type='company' LIMIT 50000"
            )

        import json
        processed = 0
        for row in rows:
            cin = row["cin"] or row["primary_key"]
            try:
                feats = await feature_computer.compute_company_features(cin)
                await upsert_features("Company", cin, feats)
                processed += 1
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning("Feature compute failed for %s: %s", cin, exc)

        await close_neo4j()
        await close_db_pool()
        print(f"Computed features for {processed} companies")

    asyncio.run(run())


def compute_project_features(**kwargs):
    import asyncio
    import sys
    sys.path.insert(0, "/app")

    from core.database import init_db_pool, close_db_pool, get_pool
    from core.neo4j_client import init_neo4j, close_neo4j
    from feature_store.feature_computer import feature_computer
    from feature_store.feature_store import upsert_features

    async def run():
        await init_db_pool()
        await init_neo4j()
        pool = get_pool()

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT primary_key FROM ontology_objects WHERE object_type='project' LIMIT 20000"
            )

        processed = 0
        for row in rows:
            pid = row["primary_key"]
            try:
                feats = await feature_computer.compute_project_features(pid)
                await upsert_features("Project", pid, feats)
                processed += 1
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning("Project feature compute failed for %s: %s", pid, exc)

        await close_neo4j()
        await close_db_pool()
        print(f"Computed features for {processed} projects")

    asyncio.run(run())


t_companies = PythonOperator(
    task_id="compute_company_features",
    python_callable=compute_company_features,
    dag=dag,
)

t_projects = PythonOperator(
    task_id="compute_project_features",
    python_callable=compute_project_features,
    dag=dag,
)

t_companies >> t_projects
