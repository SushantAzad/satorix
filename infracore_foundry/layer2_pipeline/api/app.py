"""Layer 2 Pipeline API — FastAPI application on port 8002."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from layer2_pipeline.api.routes import pipelines, runs, lineage, errors

logging.basicConfig(level="INFO")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Satorix Layer 2 Pipeline API",
    description="Pipeline execution engine, lineage, and error management",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(pipelines.router)
app.include_router(runs.router)
app.include_router(lineage.router)
app.include_router(errors.router)


@app.get("/", tags=["Root"])
def root():
    return {"service": "satorix-layer2", "status": "ok"}


@app.get("/health", tags=["Health"])
def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("layer2_pipeline.api.app:app", host="0.0.0.0", port=8002, reload=False)
