"""
Satorix Layer 6 — Intelligence Platform API
FastAPI application entry point with lifespan management, CORS, and route registration.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import get_settings
from core.database import init_db
from core.layer_clients import layer_clients
from core.redis_client import close_redis, get_redis

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")

settings = get_settings()

# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Startup and shutdown logic."""
    logger.info("Satorix Layer 6 API starting up…")

    # Initialise database tables
    try:
        await init_db()
        logger.info("Database initialised.")
    except Exception as exc:
        logger.error("Database init failed (continuing): %s", exc)

    # Initialise Redis
    try:
        await get_redis()
        logger.info("Redis connected.")
    except Exception as exc:
        logger.warning("Redis init failed (continuing): %s", exc)

    # Ensure default admin user exists
    try:
        from api.routes.auth import ensure_default_admin
        await ensure_default_admin()
    except Exception as exc:
        logger.warning("ensure_default_admin failed: %s", exc)

    # Start Kafka consumer background task
    from websocket.kafka_consumer import run_kafka_consumer
    kafka_task = asyncio.create_task(run_kafka_consumer())
    logger.info("Kafka consumer background task started.")

    yield  # Application is running

    # Shutdown
    logger.info("Satorix Layer 6 API shutting down…")

    from websocket.kafka_consumer import stop_kafka_consumer
    stop_kafka_consumer()
    try:
        kafka_task.cancel()
        await asyncio.wait_for(asyncio.shield(kafka_task), timeout=5.0)
    except Exception:
        pass

    await layer_clients.close()
    await close_redis()
    logger.info("Layer 6 shutdown complete.")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Satorix Layer 6 — Intelligence Platform API",
    version="1.0.0",
    description=(
        "BFF (Backend for Frontend) that aggregates data from Layers 3, 4, and 5 "
        "and serves the Satorix corporate intelligence dashboards."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

from api.routes import (  # noqa: E402  (after app is created)
    alerts,
    auth,
    entities,
    network,
    operational,
    reports,
    sources,
    watchlists,
    websocket as ws_route,
)

app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(entities.router, prefix="/api/v1/entities", tags=["entities"])
app.include_router(network.router, prefix="/api/v1/network", tags=["network"])
app.include_router(alerts.router, prefix="/api/v1/alerts", tags=["alerts"])
app.include_router(reports.router, prefix="/api/v1/reports", tags=["reports"])
app.include_router(sources.router, prefix="/api/v1/sources", tags=["sources"])
app.include_router(watchlists.router, prefix="/api/v1/watchlists", tags=["watchlists"])
app.include_router(operational.router, prefix="/api/v1/operational", tags=["operational"])
app.include_router(ws_route.router, tags=["websocket"])

# ---------------------------------------------------------------------------
# Health / root
# ---------------------------------------------------------------------------

@app.get("/health", tags=["health"])
async def health():
    return {"status": "healthy", "version": "1.0.0", "layer": 6}


@app.get("/", tags=["root"])
async def root():
    return {"service": "Satorix Layer 6 API", "docs": "/docs"}
