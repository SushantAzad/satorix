"""
Layer 4 — Graph Intelligence API
Port: 8004
"""
import logging
from contextlib import asynccontextmanager
from shared.local_safety import local_safe_mode

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import settings
from core.database import init_db_pool, close_db_pool
from core.neo4j_client import init_neo4j, close_neo4j
from core.redis_client import init_redis, close_redis
from network.network_cache import start_cache_invalidator, stop_cache_invalidator

from api.routes import network, paths, clusters, attributes, influence, subgraph, temporal, queries

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Layer 4 API starting up (port %d)", settings.layer4_api_port)

    await init_db_pool()
    logger.info("PostgreSQL pool ready")

    await init_neo4j()
    logger.info("Neo4j driver ready")

    await init_redis()
    logger.info("Redis client ready")

    if not local_safe_mode():
        await start_cache_invalidator()
        logger.info("Kafka cache invalidator started")
    else:
        logger.info("LOCAL SAFE MODE: background consumer disabled")

    if not settings.api_key:
        logger.warning(
            "API_KEY is not set — authentication is disabled. "
            "Set API_KEY in .env before deploying to production."
        )

    yield

    logger.info("Layer 4 API shutting down")
    if not local_safe_mode():
        await stop_cache_invalidator()
    await close_redis()
    await close_neo4j()
    await close_db_pool()


app = FastAPI(
    title="Satorix Layer 4 — Graph Intelligence API",
    version="1.0.0",
    description=(
        "Graph traversal, path finding, community detection, influence scoring, "
        "temporal analysis, and CIRP precursor modeling for the Satorix intelligence platform."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

API_PREFIX = "/api/v1"
app.include_router(network.router, prefix=API_PREFIX)
app.include_router(paths.router, prefix=API_PREFIX)
app.include_router(clusters.router, prefix=API_PREFIX)
app.include_router(attributes.router, prefix=API_PREFIX)
app.include_router(influence.router, prefix=API_PREFIX)
app.include_router(subgraph.router, prefix=API_PREFIX)
app.include_router(temporal.router, prefix=API_PREFIX)
app.include_router(queries.router, prefix=API_PREFIX)


@app.get("/health")
async def health():
    return {"status": "ok", "layer": 4, "version": "1.0.0"}


@app.get("/api/v1/health")
async def health_v1():
    from core.database import get_pool
    from core.neo4j_client import get_session
    from core.redis_client import get_redis

    checks: dict[str, str] = {}

    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        checks["postgres"] = "ok"
    except Exception as exc:
        checks["postgres"] = f"error: {exc}"

    try:
        async with get_session() as s:
            await s.run("RETURN 1")
        checks["neo4j"] = "ok"
    except Exception as exc:
        checks["neo4j"] = f"error: {exc}"

    try:
        r = get_redis()
        await r.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"

    overall = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return {"status": overall, "checks": checks}


@app.get("/api/v1/batch/runs")
async def list_batch_runs(limit: int = 10):
    """Last N nightly batch run records."""
    from core.database import get_pool
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT run_id, run_date, status, phase, duration_seconds, started_at, completed_at "
            "FROM l4_batch_runs ORDER BY started_at DESC LIMIT $1",
            limit,
        )
    return {"runs": [dict(r) for r in rows]}
