"""
FastAPI application entry point for the Layer 1 Data Integration API.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from layer1_ingestion.core.config import get_settings
from layer1_ingestion.core.database import init_db
from layer1_ingestion.api.routes import sources, sync, health, webhooks

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    logger.info("Starting Layer 1 Data Integration API...")
    settings = get_settings()
    await init_db()
    logger.info("Database initialized successfully")
    yield
    logger.info("Shutting down Layer 1 API...")


app = FastAPI(
    title="Infracore Foundry — Layer 1 Data Integration API",
    description="Connect to data sources, extract raw data incrementally, "
                "land as Parquet in object storage, profile quality, monitor health.",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(sources.router, prefix="/api/v1")
app.include_router(sync.router, prefix="/api/v1")
app.include_router(health.router, prefix="/api/v1")
app.include_router(webhooks.router, prefix="/api/v1")


@app.get("/", tags=["Root"])
def root():
    return {
        "service": "Infracore Foundry — Layer 1",
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/ping", tags=["Root"])
def ping():
    return {"pong": True}
