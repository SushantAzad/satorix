"""
FastAPI application entry point for the Layer 1 Data Integration API.
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from layer1_ingestion.core.config import get_settings, _auto_register_connectors
from layer1_ingestion.core.database import init_db
from layer1_ingestion.api.routes import sources, sync, health, webhooks, fixtures

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Layer 1 Data Integration API...")
    settings = get_settings()
    init_db()
    _auto_register_connectors()
    logger.info("Database initialized and connectors registered")

    if not settings.api_key:
        logger.warning(
            "API_KEY is not configured — all endpoints are unprotected. "
            "Set API_KEY in .env immediately for any non-local deployment."
        )

    yield
    logger.info("Shutting down Layer 1 API...")


app = FastAPI(
    title="Infracore Foundry — Layer 1 Data Integration API",
    description=(
        "Connect to data sources, extract raw data incrementally, "
        "land as Parquet in object storage, profile quality, monitor health."
    ),
    version="0.2.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Dev: all layer API ports (8001-8007) and dashboard ports (3000-3002).
# Production: set ALLOWED_ORIGINS env var to a comma-separated list of allowed origins.
_DEV_ORIGINS = [
    "http://localhost:3000", "http://localhost:3001", "http://localhost:3002",
    "http://localhost:8001", "http://localhost:8002", "http://localhost:8003",
    "http://localhost:8004", "http://localhost:8005", "http://localhost:8006",
    "http://localhost:8007", "http://localhost:8080", "http://localhost:8090",
    "http://localhost:9001",
]
_ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", ",".join(_DEV_ORIGINS)).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)

app.include_router(sources.router, prefix="/api/v1")
app.include_router(sync.router, prefix="/api/v1")
app.include_router(health.router, prefix="/api/v1")
app.include_router(webhooks.router, prefix="/api/v1")
app.include_router(fixtures.router, prefix="/api/v1")


@app.get("/", tags=["Root"])
def root():
    return {
        "service": "Infracore Foundry — Layer 1",
        "version": "0.2.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/ping", tags=["Root"])
def ping():
    return {"pong": True}
