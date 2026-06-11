"""
BatchJobs — programmatic entry point called by the Airflow DAG.
Each phase is a standalone async function so Airflow tasks are independent.
"""
import asyncio
import logging
import uuid
from datetime import date, datetime, timezone

from core.config import settings
from core.database import init_db_pool, close_db_pool, get_pool
from core.neo4j_client import init_neo4j, close_neo4j
from core.redis_client import init_redis, close_redis
from core.gds_client import create_projection, ensure_projection_dropped

from influence.betweenness_centrality import BetweennessCentralityComputer
from influence.pagerank import PageRankComputer
from influence.degree_centrality import DegreeCentralityComputer
from influence.risk_weighted import RiskWeightedCentralityComputer
from influence.regulatory_exposure import RegulatoryExposureComputer

from clustering.louvain_detector import LouvainDetector
from clustering.label_propagation import LabelPropagationDetector
from clustering.address_clusters import AddressClusterDetector
from clustering.director_clusters import DirectorClusterDetector

from shared_attributes.batch_processor import SharedAttributeBatchProcessor
from temporal.precursor_model import PrecursorModel
from subgraph.snapshot_builder import SnapshotBuilder

logger = logging.getLogger(__name__)


def _run_id() -> str:
    return f"l4-{date.today().isoformat()}-{uuid.uuid4().hex[:8]}"


async def _ensure_clients() -> None:
    await init_db_pool()
    await init_neo4j()
    await init_redis()


async def _close_clients() -> None:
    await close_db_pool()
    await close_neo4j()
    await close_redis()


async def phase_create_projection(run_id: str) -> dict:
    stats = await create_projection()
    await _update_batch_run(run_id, phase="projection_created")
    return stats


async def phase_betweenness(run_id: str) -> dict:
    result = await BetweennessCentralityComputer().run_and_persist(run_id)
    await _update_batch_run(run_id, phase="betweenness_done")
    return result


async def phase_pagerank(run_id: str) -> dict:
    result = await PageRankComputer().run_and_persist(run_id)
    await _update_batch_run(run_id, phase="pagerank_done")
    return result


async def phase_degree(run_id: str) -> dict:
    result = await DegreeCentralityComputer().run_and_persist(run_id)
    await _update_batch_run(run_id, phase="degree_done")
    return result


async def phase_regulatory_exposure(run_id: str) -> dict:
    result = await RegulatoryExposureComputer().compute_and_persist(run_id)
    await _update_batch_run(run_id, phase="regulatory_exposure_done")
    return result


async def phase_risk_weighted(run_id: str) -> dict:
    result = await RiskWeightedCentralityComputer().compute_and_persist(run_id)
    await _update_batch_run(run_id, phase="risk_weighted_done")
    return result


async def phase_louvain(run_id: str) -> dict:
    result = await LouvainDetector().run_and_persist(run_id)
    await _update_batch_run(run_id, phase="louvain_done")
    return result


async def phase_label_propagation(run_id: str) -> dict:
    result = await LabelPropagationDetector().run_and_persist(run_id)
    await _update_batch_run(run_id, phase="label_propagation_done")
    return result


async def phase_address_clusters(run_id: str) -> dict:
    result = await AddressClusterDetector().run_and_persist(run_id)
    await _update_batch_run(run_id, phase="address_clusters_done")
    return result


async def phase_director_clusters(run_id: str) -> dict:
    result = await DirectorClusterDetector().run_and_persist(run_id)
    await _update_batch_run(run_id, phase="director_clusters_done")
    return result


async def phase_shared_attributes(run_id: str) -> dict:
    result = await SharedAttributeBatchProcessor().run(run_id)
    await _update_batch_run(run_id, phase="shared_attributes_done")
    return result


async def phase_precursor_model(run_id: str) -> dict:
    result = await PrecursorModel().batch_assess_and_persist(run_id)
    await _update_batch_run(run_id, phase="precursor_done")
    return result


async def phase_snapshots(run_id: str) -> dict:
    result = await SnapshotBuilder().rebuild_all(run_id)
    await _update_batch_run(run_id, phase="snapshots_done")
    return result


async def phase_drop_projection(run_id: str) -> dict:
    await ensure_projection_dropped()
    await _complete_batch_run(run_id)
    return {"projection_dropped": True}


# ──────────────────────────────────────────────────────────────────────────────
# Helpers

async def start_batch_run() -> str:
    run_id = _run_id()
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO l4_batch_runs (run_id, run_date, status, started_at) VALUES ($1, $2, 'running', $3)",
            run_id, date.today(), datetime.now(timezone.utc),
        )
    logger.info("Batch run started: %s", run_id)
    return run_id


async def _update_batch_run(run_id: str, phase: str) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE l4_batch_runs SET phase=$1 WHERE run_id=$2",
            phase, run_id,
        )


async def _complete_batch_run(run_id: str) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        start_row = await conn.fetchrow("SELECT started_at FROM l4_batch_runs WHERE run_id=$1", run_id)
        duration = None
        if start_row:
            delta = datetime.now(timezone.utc) - start_row["started_at"]
            duration = delta.total_seconds()
        await conn.execute(
            "UPDATE l4_batch_runs SET status='complete', completed_at=$1, duration_seconds=$2 WHERE run_id=$3",
            datetime.now(timezone.utc), duration, run_id,
        )
    logger.info("Batch run completed: %s (%.1fs)", run_id, duration or 0)


# ──────────────────────────────────────────────────────────────────────────────
# Sync wrappers called by Airflow PythonOperator

def run_phase(phase_name: str, **context) -> None:
    """Airflow PythonOperator callable — runs a single phase synchronously."""
    run_id = context.get("dag_run").conf.get("run_id") if context.get("dag_run") else _run_id()

    async def _inner():
        await _ensure_clients()
        try:
            fn = globals()[f"phase_{phase_name}"]
            return await fn(run_id)
        finally:
            await _close_clients()

    result = asyncio.run(_inner())
    logger.info("Phase %s result: %s", phase_name, result)
