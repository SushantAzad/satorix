# Satorix — India's Sovereign Operational Intelligence Platform

A production-grade data platform for Indian corporate, financial, and regulatory data.
Inspired by Palantir Foundry. Built for Indian infrastructure.

---

## Architecture Overview

```
Layer 1 — Ingestion          Layer 2 — Transformation       (Future)
┌──────────────────────┐     ┌──────────────────────────┐   ┌───────────────┐
│ Connectors           │     │ Pipeline Execution Engine │   │ Layer 3       │
│  MCA21, GSTN, Tally  │ ──▶ │ Transform Library (49+)  │──▶│ Ontology      │
│  RBI, SEBI, REST     │     │ Quality Rules Engine      │   │ (Planned)     │
│  CSV, PDF, S3, SFTP  │     │ Lineage Tracker           │   └───────────────┘
│                      │     │ Error DLQ                 │
│ Streaming (Kafka)    │     │ Dataset Version Registry  │
│ Batch + CDC          │     └──────────────────────────┘
└──────────────────────┘
         │                              │
     MinIO                          MinIO
   raw-data/                     processed-data/
```

---

## Layer 1 — Ingestion

### Capabilities

| Feature | Status | Notes |
|---|---|---|
| Batch ingestion | IMPLEMENTED | CSV, Excel, PostgreSQL, MySQL, REST API, PDF, S3, SFTP, Google Sheets |
| Indian domain connectors | IMPLEMENTED | MCA21 (bulk+API+hybrid), GSTN, Tally XML, RBI, SEBI |
| Incremental sync | IMPLEMENTED | Timestamp, Sequence, FullRefreshWithDedup, CDC (WAL-based) |
| Streaming ingestion | IMPLEMENTED | Kafka micro-batch consumer → same Parquet/MinIO/SyncRun path |
| Idempotent runs | IMPLEMENTED | Deterministic batch_id = SHA256(source_id:sync_type:partition)[:16] |
| Advisory locking | IMPLEMENTED | `pg_advisory_xact_lock` per source — prevents concurrent syncs |
| Schema detection | IMPLEMENTED | Schema fingerprint on every batch; drift logged as WARNING |
| Data profiling | IMPLEMENTED | Completeness, uniqueness, distribution, anomaly detection |
| Encrypted configs | IMPLEMENTED | AES-256-GCM for connector credentials |
| Circuit breaker | IMPLEMENTED | Exponential backoff + circuit open on consecutive failures |
| Redis event notify | IMPLEMENTED | L1 publishes to `layer1:sync:complete` after every successful commit |
| Late data window | PARTIAL | Watermark-based only; no configurable late-arrival window yet |
| Streaming exactly-once | PARTIAL | At-least-once via Kafka offset commit only on success |

### Streaming Architecture

```
Kafka Topic
    │
    ▼ (micro-batch: 1000 records OR 60s, whichever first)
StreamingIngestionConsumer
    │  offset commit only after processing success
    ▼
StreamProcessor
    ├── generate deterministic batch_id (SHA256(stream:topic:offsets)[:16])
    ├── upload_parquet → MinIO raw-data/
    ├── create SyncRun record (sync_type="streaming")
    └── publish → Redis layer1:sync:complete
```

### Storage Contract

- Raw data: `raw-data/{client_id}/{source_id}/YYYY/MM/DD/{batch_id}.parquet`
- Write-once: `object_exists()` guard prevents overwrite
- Metadata embedded in Parquet file: batch_id, source_id, client_id, sync_type

---

## Layer 2 — Transformation

### Capabilities

| Feature | Status | Notes |
|---|---|---|
| Pipeline DAG execution | IMPLEMENTED | Topological sort, cycle detection, critical path |
| 49+ transforms | IMPLEMENTED | Cleaning, structural, enrichment categories |
| Quality rules engine | IMPLEMENTED | Reject / Flag / Default / Transform failure policies |
| Field-level lineage | IMPLEMENTED | Emits LineageEvents for entity_type + entity_id_column per pipeline |
| Dataset version registry | IMPLEMENTED | `l2_dataset_versions` — immutable record per successful run |
| Error DLQ | IMPLEMENTED | Quarantine / reprocess / discard lifecycle |
| Idempotent runs | IMPLEMENTED | Deterministic run_id = SHA256(pipeline_id:version:batch_id)[:16] |
| Advisory locking | IMPLEMENTED | `pg_advisory_lock` per run_id — prevents concurrent duplicate runs |
| Column normalization | IMPLEMENTED | All column names → lowercase_underscore before transforms |
| CrossBatch dedup | PARTIAL | Class exists; not wired into executor — P1 |
| Chunked large file processing | PARTIAL | Warns at >200K rows; pandas still single-process |
| Output schema fingerprint | IMPLEMENTED | SHA256[:16] of (col:dtype) pairs, stored in dataset version |

### Pipeline Lifecycle

```
YAML config (Git)
    │
    ▼ PipelineDAG.parse()
PipelineDefinitionParsed (steps in topo order, lineage_config)
    │
    ▼ PipelineExecutor.execute()
advisory_lock(run_id)
    │
    ▼ _load_input() → DataFrame
normalize column names (lowercase_underscore)
schema presence check (entity_id_column)
    │
    ▼ for each step in topo order:
       transform(df, config, ctx, step_id)
       quality rules
       step metrics → ctx
    │
    ▼ _emit_lineage() → ctx.lineage_events (≤10K per run)
    │
    ▼ _write_output() → processed-data/{client}/{pipeline}/{version}/YYYY/MM/DD/{run_id}.parquet
    │
    ▼ finally:
       lineage.flush(ctx) → l2_lineage
       quarantine.flush(ctx) → l2_error_records
       advisory_unlock()
    │
    ▼ _write_dataset_version() → l2_dataset_versions
```

### Lineage Config (YAML)

```yaml
pipeline_id: infracore_company_master
lineage_config:
  entity_type: company
  entity_id_column: cin   # column in output DataFrame
```

After each successful run, up to 10,000 unique entity IDs are recorded in `l2_lineage` with:
- `entity_type`, `entity_id` — what entity was transformed
- `pipeline_id`, `pipeline_version`, `pipeline_run_id` — which pipeline run
- `source_batch_id`, `source_path` — where raw data came from
- `step_id`, `transform_applied` — which transform was last applied

---

## Layer 1 ↔ Layer 2 Integration

| Contract | Status |
|---|---|
| L1 writes to `raw-data/`, L2 reads from `raw-data/` | IMPLEMENTED |
| L2 writes to `processed-data/` | IMPLEMENTED |
| L1 publishes `{batch_id, source_id, client_id, output_path}` to Redis | IMPLEMENTED |
| L2 Airflow DAG polls Redis with `rpoplpush` (at-least-once) | IMPLEMENTED |
| L2 falls back to DB scan if Redis empty (30-min lookback) | IMPLEMENTED |
| L2 idempotency prevents double-processing of same L1 batch | IMPLEMENTED |
| Empty L1 batches (0 new records, no output_path) handled gracefully | IMPLEMENTED |

---

## Docker Services

| Service | Port | Description |
|---|---|---|
| postgres | 5432 | PostgreSQL 15 — all state |
| minio | 9000/9001 | MinIO S3-compatible storage |
| redis | 6379 | Queue + cache |
| kafka | 9092 | KRaft-mode Kafka 3.6 (no Zookeeper) |
| airflow-webserver | 8080 | Airflow UI |
| airflow-scheduler | — | DAG scheduler |
| airflow-worker | — | Celery worker |
| layer1-api | 8001 | Layer 1 FastAPI |
| layer2-api | 8002 | Layer 2 FastAPI |
| streaming-worker | — | Kafka consumer → L1 pipeline |

### Quick Start

```bash
cp .env.example .env   # fill in secrets
docker compose up -d
```

### Kafka Streaming Configuration

```bash
# In .env:
KAFKA_TOPICS=mca21.raw:infracore:your-source-uuid,sebi.filings:infracore:another-uuid
```

Topic format: `kafka_topic_name:client_id:source_id`

---

## Database Schema

### Layer 1 Tables

| Table | Purpose |
|---|---|
| `data_sources` | Connector registry with encrypted configs |
| `sync_states` | Per-source watermarks and incremental state |
| `sync_runs` | Per-batch run history with batch_id, output_path |
| `data_source_health` | Health check history |
| `alerts` | Alert lifecycle: open → acknowledged → resolved |

### Layer 2 Tables

| Table | Purpose |
|---|---|
| `l2_pipeline_definitions` | YAML pipeline definitions stored as JSONB |
| `l2_pipeline_runs` | Per-run status, metrics, and pointers |
| `l2_pipeline_step_runs` | Per-step execution records |
| `l2_error_records` | Dead letter queue for failed records |
| `l2_lineage` | Field-level provenance: entity → pipeline → source |
| `l2_dedup_groups` | Entity resolution decisions |
| `l2_dataset_versions` | Immutable version registry (schema fingerprint, output path) |

---

## Migrations

```bash
# Layer 1 (run once at setup)
psql -U infracore -d infracore -f layer1_ingestion/migrations/001_initial.sql

# Layer 2
psql -U infracore -d infracore -f layer2_pipeline/migrations/001_l2_tables.sql
psql -U infracore -d infracore -f layer2_pipeline/migrations/002_l2_dataset_versions.sql
```

---

## Current System Status

### Completed

- Layer 1: All batch connectors, incremental strategies, advisory locking, schema fingerprinting
- Layer 1: Streaming ingestion via Kafka micro-batches
- Layer 1 → Layer 2 integration: Redis event bus + DB fallback
- Layer 2: DAG execution engine, 49+ transforms, quality rules
- Layer 2: Lineage emission for entity-aware pipelines (company, director)
- Layer 2: Immutable dataset version registry
- Layer 2: Advisory locking + try/finally guarantee for lineage/error flush
- Layer 2: Column normalization (CamelCase/MixedCase → lowercase_underscore)
- Layer 2: NormalizeCIN always returns None for invalid (no garbage strings)
- Layer 2: Idempotent output (deterministic path + object_exists guard)

### Partially Complete

- CrossBatch deduplication: class exists, not wired into executor
- Large file processing: warns at >200K rows; no chunked/distributed execution
- Late data handling: watermark-based only; no configurable late-arrival window
- Streaming exactly-once: at-least-once via Kafka offset commit on success

### Remaining Gaps (to reach Foundry-level)

- **Ontology layer** (Layer 3): typed entities, relationships, properties, semantic search
- **Distributed compute**: Dask/Spark backend for >1M row batches
- **Metadata catalog**: dataset discovery, tagging, ownership, SLAs
- **RBAC**: per-dataset, per-column, per-row access control
- **Dataset branching**: branch → reprocess → promote workflows
- **Unicode/Devanagari normalization**: regional language support

---

## Readiness Score (post-fixes)

| Dimension | Score |
|---|---|
| Data Ingestion (batch + streaming) | 72/100 |
| Lineage | 55/100 |
| Ontology | 3/100 |
| Dataset Versioning | 42/100 |
| Pipeline Orchestration | 60/100 |
| Multi-tenancy / Access Control | 22/100 |
| Compute Scale | 15/100 |
| Indian Domain Coverage | 72/100 |
| Reliability & Guarantees | 72/100 |
| Catalog / Discovery | 4/100 |

**Overall: 52 / 100 — PARTIALLY MATCHES Foundry-style**
