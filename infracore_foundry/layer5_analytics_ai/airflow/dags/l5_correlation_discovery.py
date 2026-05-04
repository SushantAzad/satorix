"""
Weekly correlation discovery DAG.
Finds statistically significant feature correlations across the Company population.
Schedule: weekly on Saturdays.
"""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

default_args = {"owner": "satorix-l5", "retries": 1}

dag = DAG(
    "l5_correlation_discovery",
    default_args=default_args,
    description="Weekly cross-entity feature correlation analysis",
    schedule_interval="0 22 * * 6",  # Saturday 03:30 IST
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["layer5", "analytics"],
)


def discover_correlations(**kwargs):
    import asyncio
    import sys
    sys.path.insert(0, "/app")

    from core.database import init_db_pool, close_db_pool
    from core.neo4j_client import init_neo4j, close_neo4j
    from analytics.correlation import discover_correlations as _discover

    async def run():
        await init_db_pool()
        await init_neo4j()
        results = await _discover("Company")
        await close_neo4j()
        await close_db_pool()
        print(f"Discovered {len(results)} significant correlations")

    asyncio.run(run())


PythonOperator(task_id="discover_company_correlations", python_callable=discover_correlations, dag=dag)
