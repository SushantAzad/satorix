"""
Layer 5 — Analytics & AI API
Port: 8005
"""
import logging
import sys
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure the layer5 directory is on the path when running from /app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import settings
from core.database import init_db_pool, close_db_pool
from core.neo4j_client import init_neo4j, close_neo4j
from core.kafka_client import close_producer
import streaming.risk_delta_stream as risk_delta
import streaming.alert_trigger_stream as alert_trigger
import streaming.trend_update_stream as trend_update

from api.routes import predictions, reports, agents, analytics, scenarios, llm, observability

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Layer 5 API starting up (port %d)", settings.layer5_api_port)

    await init_db_pool()
    logger.info("PostgreSQL pool ready")

    await init_neo4j()
    logger.info("Neo4j read-only driver ready")

    risk_delta.start()
    alert_trigger.start()
    trend_update.start()
    logger.info("Kafka streaming workers started")

    if not settings.anthropic_api_key:
        logger.warning(
            "ANTHROPIC_API_KEY not set — LLM workflows will use fallback text. "
            "Set ANTHROPIC_API_KEY in .env to enable full AI capabilities."
        )

    if not settings.api_key:
        logger.warning("API_KEY not set — authentication disabled. Set before production deployment.")

    yield

    logger.info("Layer 5 API shutting down")
    risk_delta.stop()
    alert_trigger.stop()
    trend_update.stop()
    close_producer()
    await close_neo4j()
    await close_db_pool()


app = FastAPI(
    title="Satorix Layer 5 — Analytics & AI API",
    version="1.0.0",
    description=(
        "ML model serving, LLM orchestration, agentic workflows, trend analysis, "
        "benchmarking, scenario simulation, and model observability "
        "for the Satorix corporate intelligence platform."
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
app.include_router(predictions.router, prefix=API_PREFIX)
app.include_router(reports.router, prefix=API_PREFIX)
app.include_router(agents.router, prefix=API_PREFIX)
app.include_router(analytics.router, prefix=API_PREFIX)
app.include_router(scenarios.router, prefix=API_PREFIX)
app.include_router(llm.router, prefix=API_PREFIX)
app.include_router(observability.router, prefix=API_PREFIX)


@app.get("/health")
async def health():
    return {"status": "ok", "layer": 5, "version": "1.0.0"}


@app.get("/api/v1/health")
async def health_detailed():
    from core.database import get_pool
    from core.neo4j_client import get_session

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

    checks["anthropic_configured"] = "yes" if settings.anthropic_api_key else "no (fallback mode)"

    overall = "ok" if all(v in ("ok", "yes") or v.startswith("no") for v in checks.values()) else "degraded"
    return {"status": overall, "checks": checks, "layer": 5}


@app.get("/api/v1/features/{entity_type}/{entity_id}")
async def get_entity_features(entity_type: str, entity_id: str):
    from feature_store.feature_store import get_latest_features
    feats = await get_latest_features(entity_type, entity_id)
    if feats is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="No features found for entity")
    return {"entity_type": entity_type, "entity_id": entity_id, "features": feats}


@app.post("/api/v1/features/{entity_type}/{entity_id}/compute")
async def compute_entity_features(entity_type: str, entity_id: str):
    from feature_store.feature_computer import feature_computer
    from feature_store.feature_store import upsert_features
    if entity_type.lower() == "company":
        feats = await feature_computer.compute_company_features(entity_id)
    elif entity_type.lower() == "project":
        feats = await feature_computer.compute_project_features(entity_id)
    else:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"Unsupported entity type: {entity_type}")
    await upsert_features(entity_type, entity_id, feats)
    return {"entity_type": entity_type, "entity_id": entity_id, "features": feats, "computed": True}
