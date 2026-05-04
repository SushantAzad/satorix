"""
Weekly model training DAG.
Retrains CIRP precursor and project completion models.
Runs after nightly feature computation.
Schedule: Sundays at 03:00 IST.
"""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

default_args = {
    "owner": "satorix-l5",
    "retries": 1,
    "retry_delay": timedelta(minutes=30),
    "email_on_failure": False,
}

dag = DAG(
    "l5_model_training",
    default_args=default_args,
    description="Weekly retraining of Layer 5 ML models",
    schedule_interval="30 21 * * 0",  # Sunday 03:00 IST
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["layer5", "ml", "training"],
)


def train_cirp_model(**kwargs):
    import asyncio
    import sys
    sys.path.insert(0, "/app")

    from core.database import init_db_pool, close_db_pool, get_pool
    from core.neo4j_client import init_neo4j, close_neo4j
    from models.trainers.cirp_precursor import train

    async def run():
        await init_db_pool()
        await init_neo4j()
        pool = get_pool()

        # Load known CIRP companies from ontology
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT primary_key, properties->>'cin' AS cin,
                       (properties->>'cirpAdmissionDate')::date AS cirp_date
                FROM ontology_objects
                WHERE object_type='company'
                  AND properties->>'status' = 'UnderCIRP'
                  AND properties->>'cirpAdmissionDate' IS NOT NULL
                LIMIT 5000
                """
            )
            all_cins = await conn.fetch(
                "SELECT DISTINCT properties->>'cin' AS cin FROM ontology_objects WHERE object_type='company' LIMIT 10000"
            )

        from datetime import datetime, timezone
        positives = [
            (row["cin"] or row["primary_key"], datetime.combine(row["cirp_date"], datetime.min.time()).replace(tzinfo=timezone.utc))
            for row in rows if row["cirp_date"]
        ]
        negatives = [r["cin"] for r in all_cins if r["cin"]]

        result = await train(positives, negatives)
        await close_neo4j()
        await close_db_pool()
        print(f"CIRP model training result: {result}")

    asyncio.run(run())


def train_project_model(**kwargs):
    import asyncio
    import sys
    sys.path.insert(0, "/app")

    from core.database import init_db_pool, close_db_pool, get_pool
    from core.neo4j_client import init_neo4j, close_neo4j
    from models.trainers.project_completion import train

    async def run():
        await init_db_pool()
        await init_neo4j()
        pool = get_pool()

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT primary_key,
                       CASE WHEN properties->>'status' IN ('Completed', 'Commissioned') THEN true ELSE false END AS completed_on_time
                FROM ontology_objects
                WHERE object_type='project'
                LIMIT 10000
                """
            )
        labeled = [{"project_id": r["primary_key"], "completed_on_time": r["completed_on_time"]} for r in rows]
        result = await train(labeled)
        await close_neo4j()
        await close_db_pool()
        print(f"Project model training result: {result}")

    asyncio.run(run())


t_cirp = PythonOperator(task_id="train_cirp_precursor", python_callable=train_cirp_model, dag=dag)
t_project = PythonOperator(task_id="train_project_completion", python_callable=train_project_model, dag=dag)

t_cirp >> t_project
