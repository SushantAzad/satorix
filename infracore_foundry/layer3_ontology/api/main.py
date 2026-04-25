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

    # Initialize Neo4j
    try:
        await neo4j_client.connect()
    except Exception as e:
        logger.error("Neo4j connect failed: %s", e)

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
    from semantic.link_types.corporate import ALL_CORPORATE_LINKS
    from semantic.link_types.regulatory import ALL_REGULATORY_LINKS
    from semantic.link_types.project import ALL_PROJECT_LINKS

    object_type_definitions = [
        COMPANY_DEFINITION, DIRECTOR_DEFINITION, PROJECT_DEFINITION,
        REGULATORY_ACTION_DEFINITION, LEGAL_CASE_DEFINITION, INSOLVENCY_PROCEEDING_DEFINITION,
        ADDRESS_DEFINITION, REGULATORY_BODY_DEFINITION, GOVERNMENT_ENTITY_DEFINITION,
        EVENT_DEFINITION, ALERT_DEFINITION,
    ]
    link_definitions = ALL_CORPORATE_LINKS + ALL_REGULATORY_LINKS + ALL_PROJECT_LINKS

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
