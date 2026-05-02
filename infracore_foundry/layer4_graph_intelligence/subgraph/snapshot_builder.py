"""
SnapshotBuilder — batch snapshot runner used by the nightly Airflow DAG.
Refreshes all defined subgraphs in parallel.
"""
import asyncio
import logging

from core.database import get_pool
from .extractor import SubgraphExtractor

logger = logging.getLogger(__name__)


class SnapshotBuilder:
    def __init__(self) -> None:
        self._extractor = SubgraphExtractor()

    async def rebuild_all(self, batch_run_id: str, concurrency: int = 5) -> dict:
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT subgraph_id FROM l4_subgraph_definitions")

        subgraph_ids = [r["subgraph_id"] for r in rows]
        logger.info("Rebuilding %d subgraph snapshots", len(subgraph_ids))

        sem = asyncio.Semaphore(concurrency)
        results: list[dict] = []
        errors: list[str] = []

        async def _build(sid: str) -> None:
            async with sem:
                try:
                    snap = await self._extractor.extract_snapshot(sid)
                    results.append(snap)
                except Exception as exc:
                    errors.append(f"{sid}: {exc}")
                    logger.error("Snapshot failed for %s: %s", sid, exc)

        await asyncio.gather(*[_build(sid) for sid in subgraph_ids])
        return {"built": len(results), "failed": len(errors), "errors": errors}
