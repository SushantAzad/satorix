from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
import sys
import os

# Ensure layer3_ontology directory is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import settings
from core.database import init_db, close_db
from core.neo4j_client import neo4j_client
from core.elasticsearch_client import es_client
from core.redis_client import redis_client
from core.minio_client import minio_client
from storage.neo4j_store import Neo4jStore
from api.routes import objects, search, graph, intelligence, actions, timeline, health, ingest, schema

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Layer 3 Ontology API starting up...")

    # Initialize PostgreSQL
    try:
        await init_db()
        logger.info("PostgreSQL initialized")
    except Exception as e:
        logger.error("PostgreSQL init failed: %s", e)

    # The ontology uses a generic SQL-backed object store rather than ORM models,
    # so Base.metadata.create_all() cannot create these tables on a fresh install.
    try:
        await _run_base_schema_migration()
    except Exception as e:
        logger.error("Base ontology schema migration failed: %s", e)

    # Run multi-tenancy migration (idempotent — ADD COLUMN IF NOT EXISTS)
    try:
        await _run_client_isolation_migration()
    except Exception as e:
        logger.error("Client isolation migration failed: %s", e)

    # Initialize Neo4j
    try:
        await neo4j_client.connect()
    except Exception as e:
        logger.error("Neo4j connect failed: %s", e)

    # Bootstrap Neo4j clientId indexes
    try:
        await Neo4jStore().setup_indexes()
    except Exception as e:
        logger.error("Neo4j index setup failed: %s", e)

    # Initialize Elasticsearch
    try:
        await es_client.connect()
    except Exception as e:
        logger.error("Elasticsearch connect failed: %s", e)

    # Initialize Redis
    try:
        await redis_client.connect()
    except Exception as e:
        logger.error("Redis connect failed: %s", e)

    # Initialize MinIO
    try:
        minio_client.connect()
    except Exception as e:
        logger.error("MinIO connect failed: %s", e)

    # Seed schema registry
    try:
        await _seed_schema()
    except Exception as e:
        logger.error("Schema seeding failed: %s", e)

    logger.info("Layer 3 API ready on port %d", settings.layer3_api_port)

    yield

    # Shutdown
    await neo4j_client.close()
    await es_client.close()
    await redis_client.close()
    await close_db()
    logger.info("Layer 3 API shutdown complete")


async def _run_client_isolation_migration() -> None:
    """Apply migration 002 — adds client_id column if it does not exist yet.

    Safe to run on every startup (all statements use IF NOT EXISTS / IF EXISTS).
    """
    from core.database import AsyncSessionLocal
    from sqlalchemy import text

    stmts = [
        # ontology_objects
        "ALTER TABLE ontology_objects ADD COLUMN IF NOT EXISTS client_id VARCHAR(100) NOT NULL DEFAULT 'PLATFORM_GLOBAL'",
        "ALTER TABLE ontology_objects DROP CONSTRAINT IF EXISTS ontology_objects_object_type_primary_key_key",
        # PostgreSQL does not support IF NOT EXISTS on ADD CONSTRAINT, so we guard with a
        # do-nothing insert into information_schema inside a function — instead use a plain
        # CREATE UNIQUE INDEX which does support IF NOT EXISTS.
        "CREATE UNIQUE INDEX IF NOT EXISTS ontology_objects_tenant_pk_unique ON ontology_objects (object_type, primary_key, client_id)",
        "CREATE INDEX IF NOT EXISTS idx_objects_client_id ON ontology_objects (client_id)",
        "CREATE INDEX IF NOT EXISTS idx_objects_type_client ON ontology_objects (object_type, client_id)",
        # ontology_links
        "ALTER TABLE ontology_links ADD COLUMN IF NOT EXISTS client_id VARCHAR(100) NOT NULL DEFAULT 'PLATFORM_GLOBAL'",
        "CREATE INDEX IF NOT EXISTS idx_links_client_id ON ontology_links (client_id)",
    ]
    async with AsyncSessionLocal() as db:
        for stmt in stmts:
            try:
                await db.execute(text(stmt))
            except Exception as exc:
                logger.debug("Migration stmt skipped (%s…): %s", stmt[:60], exc)
        await db.commit()
    logger.info("Client isolation migration applied")


async def _run_base_schema_migration() -> None:
    """Create the generic ontology tables on a fresh database."""
    from pathlib import Path
    from core.database import engine

    migration_path = (
        Path(__file__).resolve().parents[1]
        / "schema_registry"
        / "migrations"
        / "001_ontology_schema.sql"
    )
    statements = [
        statement.strip()
        for statement in migration_path.read_text(encoding="utf-8").split(";")
        if statement.strip()
    ]
    async with engine.begin() as connection:
        for statement in statements:
            await connection.exec_driver_sql(statement)
    logger.info("Base ontology schema migration applied")


async def _seed_schema() -> None:
    """Seed object type and link type definitions into the schema registry."""
    from core.database import AsyncSessionLocal
    from schema_registry.object_type_registry import object_type_registry
    from schema_registry.link_type_registry import link_type_registry
    from schema_registry.interface_registry import interface_registry
    from semantic.object_types.company import COMPANY_DEFINITION
    from semantic.object_types.director import DIRECTOR_DEFINITION
    from semantic.object_types.project import PROJECT_DEFINITION
    from semantic.object_types.regulatory_action import REGULATORY_ACTION_DEFINITION
    from semantic.object_types.legal_case import LEGAL_CASE_DEFINITION
    from semantic.object_types.insolvency_proceeding import INSOLVENCY_PROCEEDING_DEFINITION
    from semantic.object_types.address import ADDRESS_DEFINITION
    from semantic.object_types.regulatory_body import REGULATORY_BODY_DEFINITION
    from semantic.object_types.government_entity import GOVERNMENT_ENTITY_DEFINITION
    from semantic.object_types.event import EVENT_DEFINITION
    from semantic.object_types.alert import ALERT_DEFINITION
    from semantic.object_types.financial_statement import FINANCIAL_STATEMENT_DEFINITION
    from semantic.object_types.document import DOCUMENT_DEFINITION
    from semantic.link_types.corporate import ALL_CORPORATE_LINKS
    from semantic.link_types.regulatory import ALL_REGULATORY_LINKS
    from semantic.link_types.project import ALL_PROJECT_LINKS
    from semantic.link_types.financial import ALL_FINANCIAL_LINK_TYPES

    object_type_definitions = [
        COMPANY_DEFINITION, DIRECTOR_DEFINITION, PROJECT_DEFINITION,
        REGULATORY_ACTION_DEFINITION, LEGAL_CASE_DEFINITION, INSOLVENCY_PROCEEDING_DEFINITION,
        ADDRESS_DEFINITION, REGULATORY_BODY_DEFINITION, GOVERNMENT_ENTITY_DEFINITION,
        EVENT_DEFINITION, ALERT_DEFINITION,
        FINANCIAL_STATEMENT_DEFINITION, DOCUMENT_DEFINITION,
    ]
    link_definitions = ALL_CORPORATE_LINKS + ALL_REGULATORY_LINKS + ALL_PROJECT_LINKS + ALL_FINANCIAL_LINK_TYPES

    async with AsyncSessionLocal() as db:
        for defn in object_type_definitions:
            try:
                await object_type_registry.upsert(db, defn)
            except Exception as e:
                logger.warning("Object type seed failed for %s: %s", defn.get("api_name"), e)

        for defn in link_definitions:
            try:
                await link_type_registry.upsert(db, defn)
            except Exception as e:
                logger.warning("Link type seed failed for %s: %s", defn.get("api_name"), e)

        try:
            await interface_registry.seed_interfaces(db)
        except Exception as e:
            logger.warning("Interface seeding failed: %s", e)

        await db.commit()

    logger.info("Schema registry seeded with %d object types and %d link types",
                len(object_type_definitions), len(link_definitions))


app = FastAPI(
    title="Satorix — Layer 3 Ontology API",
    description="The Semantic Knowledge Graph for India's Corporate Intelligence Platform",
    version="1.0.0",
    lifespan=lifespan,
)

_cors_origins = os.environ.get(
    "CORS_ORIGINS",
    "http://localhost:3000,http://localhost:3001,http://localhost:3002,http://localhost:8006",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register all routers
app.include_router(objects.router)
app.include_router(search.router)
app.include_router(graph.router)
app.include_router(intelligence.router)
app.include_router(actions.router)
app.include_router(timeline.router)
app.include_router(health.router)
app.include_router(ingest.router)
app.include_router(schema.router)


@app.get("/")
async def root():
    return {
        "service": "Satorix Layer 3 — Ontology API",
        "version": "1.0.0",
        "description": "The semantic knowledge graph — India's Palantir Foundry Ontology Layer",
        "endpoints": {
            "objects": "/objects/{object_type}",
            "search": "/search?q=...",
            "graph": "/graph/network/{type}/{id}",
            "intelligence": "/intelligence/risk/{type}/{id}",
            "actions": "/actions/{action_type}",
            "timeline": "/timeline/{type}/{id}",
            "health": "/health",
            "ingest": "/ingest/trigger",
            "schema": "/schema/object-types",
        },
    }
