"""
Nightly portfolio monitor DAG.
Runs PortfolioMonitorAgent for each registered client watchlist.
Schedule: daily at 06:00 IST.
"""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

default_args = {
    "owner": "satorix-l5",
    "retries": 1,
    "retry_delay": timedelta(minutes=10),
}

dag = DAG(
    "l5_portfolio_monitor",
    default_args=default_args,
    description="Nightly portfolio risk monitoring for all client watchlists",
    schedule_interval="30 0 * * *",  # 06:00 IST
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["layer5", "agents", "portfolio"],
)


def run_portfolio_monitor(**kwargs):
    import asyncio
    import sys
    sys.path.insert(0, "/app")

    from core.database import init_db_pool, close_db_pool, get_pool
    from core.neo4j_client import init_neo4j, close_neo4j
    from agents.agents.portfolio_monitor import PortfolioMonitorAgent

    async def run():
        await init_db_pool()
        await init_neo4j()
        pool = get_pool()

        # Get all tracked companies from ontology
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT DISTINCT properties->>'cin' AS cin FROM ontology_objects WHERE object_type='company' LIMIT 10000"
            )
        cins = [r["cin"] for r in rows if r["cin"]]

        agent = PortfolioMonitorAgent()
        result = await agent.run(
            input_params={"portfolio_cins": cins, "alert_threshold": 75},
            actor_id="l5_portfolio_monitor_dag",
        )
        await close_neo4j()
        await close_db_pool()
        print(f"Portfolio monitor: {result['output']}")

    asyncio.run(run())


PythonOperator(task_id="run_portfolio_monitor", python_callable=run_portfolio_monitor, dag=dag)
