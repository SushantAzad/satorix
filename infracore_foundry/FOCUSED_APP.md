# Focused Satorix

Default Development startup now runs:

- PostgreSQL (the existing satorix-development database volume)
- Entity API (Layer 3)
- Intelligence and report API (Layer 6, including rule-based intelligence)
- One dashboard, http://127.0.0.1:3000

Run from infracore_foundry:

    .\scripts\start-satorix.ps1 -Mode Development

CSV Import is now /imports in the main dashboard. Intelligence remains at
/intelligence, with recorded risk, shared-director analysis and review signals.
It explicitly distinguishes unknown risk and synthetic data. This is not an
ML prediction, LLM chat or independently verified financial assessment.

## Database reduction

Focused mode reads/writes ontology data, relationships, search, import history,
source metadata and reports in PostgreSQL. No Redis cache, Elasticsearch index,
Neo4j graph, MinIO store or Kafka broker is needed for these workflows.

Search currently uses literal case-insensitive substring matching rather than
Elasticsearch ranking/fuzzy search. Graph traversal uses a bounded in-memory
walk of tenant-visible PostgreSQL rows: maximum 5000 entities and 10000 links.
Larger datasets require indexed recursive SQL/pagination before increasing limits.
No automated centrality score is calculated by this implementation.

## Removed from the running app

Connector management, pipeline operations, streaming, separate operations/schema
dashboards, Layer 4 graph service and Layer 5 ML/LLM service are not started.
The focused API does not mount the old connector/operations/ML routes.
The intelligence UI now exposes loaded-data analysis, not unavailable ML cards.

Existing legacy code and installed package dependencies remain for a staged
migration; this is runtime consolidation, not a claim that every old module
or Python dependency has been deleted. Those modules still have import-time
dependencies which must be disentangled before slimming the images.

## Preservation and rollback

No database volumes were deleted. Extra Development containers are stopped.
PostgreSQL remains the same authoritative database; no data migration is needed.
The historical full stack can still be started explicitly with
scripts/start-development.ps1, but its Neo4j/Elasticsearch projections will need
reconciliation for writes made while focused mode was active.
Safe and Unrestricted launch scripts retain their legacy configurations.
Do not run multiple modes against the same host ports simultaneously.

CSV templates, re-import behavior, source metadata, evidence inspector,
investigation paths, reports and authentication remain supported.
