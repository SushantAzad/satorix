OVERVIEW

Satorix is India's sovereign Palantir Foundry alternative — a 10-layer operational intelligence platform for corporate and infrastructure
intelligence. It ingests raw data from structured and unstructured sources, transforms and validates it through a pipeline, builds a rich  
 semantic knowledge graph (ontology), and will ultimately serve intelligence dashboards to PE analysts, compliance heads, and infrastructure fund
managers.

Current build state: Layers 1, 2, and 3 are complete. Layers 4–10 are designed but not coded.

- Total codebase: 247 Python files, ~20,500 lines of code
- Infrastructure: 14 Docker services, single docker-compose up deployment
- Repository: GitLab (gitlab.com/sushantazad007/satorix)  


---

INFRASTRUCTURE — DOCKER SERVICES

All services are defined in infracore_foundry/docker-compose.yml. Single command: docker compose up.

Service Inventory

┌─────────────────────────────┬────────────────────────────────────┬──────────────────────┬─────────────────────────────────────────────────┐  
 │ Container │ Image │ Ports │ Purpose │
├─────────────────────────────┼────────────────────────────────────┼──────────────────────┼─────────────────────────────────────────────────┤
│ infracore_postgres │ postgres:15 │ 5432 │ Shared authoritative store — all 3 layers share │
│ │ │ │ one DB │
├─────────────────────────────┼────────────────────────────────────┼──────────────────────┼─────────────────────────────────────────────────┤  
 │ infracore_minio │ minio/minio:latest │ 9000 (API), 9001 │ Object storage for raw and processed Parquet │  
 │ │ │ (Console) │ files │  
 ├─────────────────────────────┼────────────────────────────────────┼──────────────────────┼─────────────────────────────────────────────────┤  
 │ infracore_minio_init │ minio/mc │ — │ One-shot: creates raw-data, processed-data, │
│ │ │ │ profiling-reports buckets │  
 ├─────────────────────────────┼────────────────────────────────────┼──────────────────────┼─────────────────────────────────────────────────┤
│ infracore_redis │ redis:7-alpine │ 6379 │ Airflow Celery broker + Layer 1→2 event bus │  
 ├─────────────────────────────┼────────────────────────────────────┼──────────────────────┼─────────────────────────────────────────────────┤
│ infracore_airflow_init │ apache/airflow:2.7.3 │ — │ One-shot DB migration, creates admin/admin user │  
 ├─────────────────────────────┼────────────────────────────────────┼──────────────────────┼─────────────────────────────────────────────────┤
│ infracore_airflow_webserver │ apache/airflow:2.7.3 │ 8080 │ DAG management UI │  
 ├─────────────────────────────┼────────────────────────────────────┼──────────────────────┼─────────────────────────────────────────────────┤
│ infracore_airflow_scheduler │ apache/airflow:2.7.3 │ — │ Triggers DAG runs on schedule │  
 ├─────────────────────────────┼────────────────────────────────────┼──────────────────────┼─────────────────────────────────────────────────┤
│ infracore_airflow_worker │ apache/airflow:2.7.3 │ — │ Celery worker executes tasks │  
 ├─────────────────────────────┼────────────────────────────────────┼──────────────────────┼─────────────────────────────────────────────────┤
│ infracore_kafka │ public.ecr.aws/bitnami/kafka:3.7.0 │ 9092 │ Event streaming — KRaft mode (no Zookeeper) │  
 ├─────────────────────────────┼────────────────────────────────────┼──────────────────────┼─────────────────────────────────────────────────┤
│ infracore_streaming_worker │ (built from Layer 1 Dockerfile) │ — │ Continuous Kafka consumer → MinIO │  
 ├─────────────────────────────┼────────────────────────────────────┼──────────────────────┼─────────────────────────────────────────────────┤  
 │ infracore_neo4j │ neo4j:5.14 │ 7474 (Browser), 7687 │ Graph database with APOC plugin │
│ │ │ (Bolt) │ │  
 ├─────────────────────────────┼────────────────────────────────────┼──────────────────────┼─────────────────────────────────────────────────┤
│ infracore_elasticsearch │ elasticsearch:8.11.0 │ 9200 │ Full-text search engine │  
 ├─────────────────────────────┼────────────────────────────────────┼──────────────────────┼─────────────────────────────────────────────────┤  
 │ infracore_layer1_api │ (built from Layer 1 Dockerfile) │ 8001 │ Layer 1 FastAPI │
├─────────────────────────────┼────────────────────────────────────┼──────────────────────┼─────────────────────────────────────────────────┤  
 │ infracore_layer2_api │ (built from Layer 2 Dockerfile) │ 8002 │ Layer 2 FastAPI │
├─────────────────────────────┼────────────────────────────────────┼──────────────────────┼─────────────────────────────────────────────────┤  
 │ infracore_layer3_api │ (built from Layer 3 Dockerfile) │ 8003 │ Layer 3 FastAPI │
└─────────────────────────────┴────────────────────────────────────┴──────────────────────┴─────────────────────────────────────────────────┘

Kafka Configuration

- Mode: KRaft (no Zookeeper) — KAFKA_CFG_PROCESS_ROLES: controller,broker
- Internal listener: kafka:9092 (PLAINTEXT)
- Topic auto-create: enabled
- Log retention: 168 hours (7 days)
- Max log segment: 1 GB
- Health check: kafka-topics.sh --bootstrap-server localhost:9092 --list

Neo4j Configuration

- Auth: neo4j / infracore123 (configurable via NEO4J_PASSWORD)
- Plugin: APOC (unrestricted procedures: apoc.\*)
- Heap: Initial 2 GB, Max 4 GB
- Access: Browser at port 7474, Bolt driver at port 7687

Elasticsearch Configuration

- Mode: Single-node
- Security: xpack disabled (dev mode)
- JVM Heap: 1 GB initial, 2 GB max  


Environment Variables (.env)

POSTGRES_HOST/PORT/DB/USER/PASSWORD
MINIO_ENDPOINT / MINIO_ACCESS_KEY / MINIO_SECRET_KEY / MINIO_RAW_BUCKET / MINIO_SECURE  
 REDIS_URL  
 ENCRYPTION_KEY # base64-encoded 32-byte AES key  
 SANDBOX_API_KEY # sandbox.co.in API key  
 GOOGLE_CREDENTIALS_PATH  
 API_KEY # Bearer token for Layer 1/2 APIs (empty = unprotected with warning)  
 NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD  
 ELASTICSEARCH_URL  
 LAYER3_API_PORT # 8003  
 SCHEMA_VERSION # 1.0.0  
 RISK_SCORE_BATCH_SIZE # 100
INGEST_CHUNK_SIZE # 1000

---

LAYER 1 — DATA INTEGRATION API

Port 8001 | ~8,300 LOC | 74 Python files

Layer 1 is the data intake boundary of the entire platform. It is the only layer that ever touches external systems. Everything below Layer 1  
 works only on data that has already been extracted, validated, and stored as Parquet.

API Surface (FastAPI v0.2.0)

App startup sequence: init_db() → \_auto_register_connectors() → warn if API_KEY empty.

CORS: Allows localhost:3000 and localhost:8001 only.

Auth: All routes require X-API-Key header (via require_api_key dependency). When API_KEY env var is empty, auth is bypassed with a startup  
 warning.

┌────────────────────────────────────────┬────────┬────────────────────────────────────────────────────────────────┐  
 │ Route │ Method │ Description │
├────────────────────────────────────────┼────────┼────────────────────────────────────────────────────────────────┤  
 │ GET / │ — │ Service info │
├────────────────────────────────────────┼────────┼────────────────────────────────────────────────────────────────┤
│ GET /ping │ — │ Health ping │
├────────────────────────────────────────┼────────┼────────────────────────────────────────────────────────────────┤  
 │ POST /api/v1/sources/ │ Auth │ Register a new data source │
├────────────────────────────────────────┼────────┼────────────────────────────────────────────────────────────────┤  
 │ GET /api/v1/sources/ │ Auth │ List sources (filterable by client_id, source_type, is_active) │
├────────────────────────────────────────┼────────┼────────────────────────────────────────────────────────────────┤  
 │ GET /api/v1/sources/{id} │ Auth │ Get one source (credentials masked) │
├────────────────────────────────────────┼────────┼────────────────────────────────────────────────────────────────┤  
 │ PATCH /api/v1/sources/{id} │ Auth │ Update source config │
├────────────────────────────────────────┼────────┼────────────────────────────────────────────────────────────────┤  
 │ DELETE /api/v1/sources/{id} │ Auth │ Soft-delete source │
├────────────────────────────────────────┼────────┼────────────────────────────────────────────────────────────────┤  
 │ POST /api/v1/sync/{id}/trigger │ Auth │ Trigger full or incremental sync │
├────────────────────────────────────────┼────────┼────────────────────────────────────────────────────────────────┤  
 │ GET /api/v1/sync/{id}/history │ Auth │ Get last N sync runs (default 30) │
├────────────────────────────────────────┼────────┼────────────────────────────────────────────────────────────────┤  
 │ GET /api/v1/health/sources │ Auth │ Health status of all sources │
├────────────────────────────────────────┼────────┼────────────────────────────────────────────────────────────────┤  
 │ POST /api/v1/health/sources/{id}/check │ Auth │ Run health check now │
├────────────────────────────────────────┼────────┼────────────────────────────────────────────────────────────────┤  
 │ POST /api/v1/webhooks/{source_id} │ Auth │ Receive push webhook payloads │
└────────────────────────────────────────┴────────┴────────────────────────────────────────────────────────────────┘

PostgreSQL Schema (Layer 1)

Table: data_sources

┌─────────────────────────┬──────────────┬─────────────────────────────────────┐  
 │ Column │ Type │ Notes │
├─────────────────────────┼──────────────┼─────────────────────────────────────┤
│ id │ UUID PK │ Auto-generated │
├─────────────────────────┼──────────────┼─────────────────────────────────────┤
│ client_id │ VARCHAR(255) │ Multi-tenant partition key │  
 ├─────────────────────────┼──────────────┼─────────────────────────────────────┤
│ source_name │ VARCHAR(500) │ Human name │  
 ├─────────────────────────┼──────────────┼─────────────────────────────────────┤  
 │ source_type │ VARCHAR(100) │ csv, excel, postgresql, mca21, etc. │
├─────────────────────────┼──────────────┼─────────────────────────────────────┤  
 │ connection_config │ TEXT │ AES-256-GCM encrypted JSON blob │
├─────────────────────────┼──────────────┼─────────────────────────────────────┤  
 │ auth_method │ VARCHAR(100) │ │
├─────────────────────────┼──────────────┼─────────────────────────────────────┤  
 │ environment │ VARCHAR(50) │ Default: production │
├─────────────────────────┼──────────────┼─────────────────────────────────────┤  
 │ status │ VARCHAR(50) │ Default: active │
├─────────────────────────┼──────────────┼─────────────────────────────────────┤  
 │ consecutive_failures │ INTEGER │ For circuit breaker │
├─────────────────────────┼──────────────┼─────────────────────────────────────┤  
 │ circuit_open │ BOOLEAN │ True after 5 consecutive failures │
├─────────────────────────┼──────────────┼─────────────────────────────────────┤  
 │ created_at / updated_at │ TIMESTAMPTZ │ │
├─────────────────────────┼──────────────┼─────────────────────────────────────┤  
 │ created_by │ VARCHAR(255) │ │
└─────────────────────────┴──────────────┴─────────────────────────────────────┘

Table: sync_states (one row per source, watermark tracking)

┌────────────────────────────────────────┬──────────────┬────────────────────────────────────────┐  
 │ Column │ Type │ Notes │
├────────────────────────────────────────┼──────────────┼────────────────────────────────────────┤
│ source_id │ UUID FK │ One-to-one with data_sources │
├────────────────────────────────────────┼──────────────┼────────────────────────────────────────┤
│ last_sync_at / last_successful_sync_at │ TIMESTAMPTZ │ │  
 ├────────────────────────────────────────┼──────────────┼────────────────────────────────────────┤
│ last_extracted_id │ VARCHAR(500) │ For sequence strategy │  
 ├────────────────────────────────────────┼──────────────┼────────────────────────────────────────┤  
 │ last_extracted_timestamp │ TIMESTAMPTZ │ For timestamp strategy │
├────────────────────────────────────────┼──────────────┼────────────────────────────────────────┤  
 │ total_records_last_run │ INTEGER │ │
├────────────────────────────────────────┼──────────────┼────────────────────────────────────────┤  
 │ status │ VARCHAR(50) │ idle, running, failed │
├────────────────────────────────────────┼──────────────┼────────────────────────────────────────┤  
 │ checksum_last_batch │ VARCHAR(128) │ SHA-256 of last batch │
├────────────────────────────────────────┼──────────────┼────────────────────────────────────────┤  
 │ schema_fingerprint │ VARCHAR(64) │ SHA-256(sorted col:dtype pairs)[:16] │
├────────────────────────────────────────┼──────────────┼────────────────────────────────────────┤  
 │ incremental_strategy │ VARCHAR(30) │ timestamp, sequence, cdc, full_refresh │
└────────────────────────────────────────┴──────────────┴────────────────────────────────────────┘

Table: sync_runs (one row per extraction run)

┌───────────────────┬────────────────────┬──────────────────────────────────────────────────────────────────┐
│ Column │ Type │ Notes │
├───────────────────┼────────────────────┼──────────────────────────────────────────────────────────────────┤
│ batch_id │ VARCHAR(64) UNIQUE │ SHA256(source_id:sync_type:YYYY-MM-DDTHH)[:16] — idempotency key │
├───────────────────┼────────────────────┼──────────────────────────────────────────────────────────────────┤
│ sync_type │ VARCHAR(50) │ full or incremental │  
 ├───────────────────┼────────────────────┼──────────────────────────────────────────────────────────────────┤  
 │ status │ VARCHAR(50) │ running, completed, failed │  
 ├───────────────────┼────────────────────┼──────────────────────────────────────────────────────────────────┤  
 │ output_path │ VARCHAR(1000) │ MinIO object path │
├───────────────────┼────────────────────┼──────────────────────────────────────────────────────────────────┤  
 │ records_extracted │ INTEGER │ │
├───────────────────┼────────────────────┼──────────────────────────────────────────────────────────────────┤  
 │ error_details │ TEXT │ │
└───────────────────┴────────────────────┴──────────────────────────────────────────────────────────────────┘

Table: data_source_health (one row per health check)

┌──────────────────┬─────────┬────────────────────────────────┐  
 │ Column │ Type │ Notes │
├──────────────────┼─────────┼────────────────────────────────┤
│ is_reachable │ BOOLEAN │ │
├──────────────────┼─────────┼────────────────────────────────┤
│ response_time_ms │ FLOAT │ │
├──────────────────┼─────────┼────────────────────────────────┤  
 │ schema_matches │ BOOLEAN │ Compared to stored fingerprint │
├──────────────────┼─────────┼────────────────────────────────┤  
 │ freshness_score │ FLOAT │ │
├──────────────────┼─────────┼────────────────────────────────┤  
 │ volume_anomaly │ BOOLEAN │ │
├──────────────────┼─────────┼────────────────────────────────┤  
 │ alert_sent │ BOOLEAN │ │
└──────────────────┴─────────┴────────────────────────────────┘

Table: alerts

┌──────────────┬──────────────┬────────────────────────────────────────────────────────────────┐  
 │ Column │ Type │ Notes │
├──────────────┼──────────────┼────────────────────────────────────────────────────────────────┤
│ alert_type │ VARCHAR(100) │ │
├──────────────┼──────────────┼────────────────────────────────────────────────────────────────┤
│ severity │ VARCHAR(50) │ │
├──────────────┼──────────────┼────────────────────────────────────────────────────────────────┤  
 │ status │ VARCHAR(50) │ open → acknowledged → resolved │
├──────────────┼──────────────┼────────────────────────────────────────────────────────────────┤  
 │ details │ JSONB │ │
├──────────────┼──────────────┼────────────────────────────────────────────────────────────────┤  
 │ Unique index │ — │ One open alert per (source_id, alert_type) — dedup at DB level │
└──────────────┴──────────────┴────────────────────────────────────────────────────────────────┘

Connector Framework

BaseConnector (abstract) — every connector inherits this.

Required abstract methods:

- test_connection() → ConnectionTestResult
- extract_schema() → SchemaDetectionResult
- extract_full(config: ExtractionConfig) → pd.DataFrame
- extract_incremental(config: IncrementalConfig) → pd.DataFrame
- get_record_count() → int  


Free concrete methods:

- validate_config() — checks REQUIRED_CONFIG_FIELDS
- to_parquet(df, client_id, batch_id, bucket) — uploads to MinIO, returns path
- compute_checksum(df) — SHA-256 of pd.util.hash_pandas_object
- log_extraction(records, duration, errors) — structured log
- \_timed_operation(name) — context manager for op timing  


Exception taxonomy (5 types):

1. ConnectionError(source_id, message, context) — extends builtins.ConnectionError
2. AuthenticationError(source_id, message, context) — credentials rejected
3. SchemaError(source_id, message, context) — unexpected data structure
4. ExtractionError(source_id, message, context) — error during pull
5. RateLimitError(source_id, message, retry_after, context) — API throttled  


Data classes:

- ConnectionTestResult: success, message, response_time_ms, schema_detected, error
- SchemaDetectionResult: columns, total_columns, detected_primary_key, indian_identifiers, timestamp_columns, record_count_estimate
- ExtractionConfig: source_id, client_id, batch_size=10000, output_bucket="raw-data"
- IncrementalConfig(ExtractionConfig): adds strategy, last_extracted_at, last_extracted_id  


Connector Registry (13 connectors total)

Auto-registered at startup via \_auto_register_connectors():

┌───────────────┬───────────────────────┬─────────────────────────────────────────────────────────┐  
 │ Key │ Class │ Source Type │
├───────────────┼───────────────────────┼─────────────────────────────────────────────────────────┤  
 │ csv │ CSVConnector │ CSV/TSV with Indian number/date handling │
├───────────────┼───────────────────────┼─────────────────────────────────────────────────────────┤
│ excel │ ExcelConnector │ Excel with merged cells, multi-sheet, multi-header │  
 ├───────────────┼───────────────────────┼─────────────────────────────────────────────────────────┤  
 │ pdf │ PDFConnector │ Digital (pdfplumber) + OCR (Tesseract + Hindi) │  
 ├───────────────┼───────────────────────┼─────────────────────────────────────────────────────────┤  
 │ postgresql │ PostgreSQLConnector │ Server-side cursors, incremental via timestamp/sequence │
├───────────────┼───────────────────────┼─────────────────────────────────────────────────────────┤  
 │ mysql │ MySQLConnector │ LIMIT/OFFSET incremental, utf8mb4 │
├───────────────┼───────────────────────┼─────────────────────────────────────────────────────────┤  
 │ rest_api │ RESTAPIConnector │ 5 auth methods, 5 pagination strategies, rate limiting │
├───────────────┼───────────────────────┼─────────────────────────────────────────────────────────┤  
 │ google_sheets │ GoogleSheetsConnector │ Service account auth, named ranges │
├───────────────┼───────────────────────┼─────────────────────────────────────────────────────────┤  
 │ s3 │ S3Connector │ S3/MinIO delta sync by object mod-time │
├───────────────┼───────────────────────┼─────────────────────────────────────────────────────────┤  
 │ sftp │ SFTPConnector │ SFTP/FTP with mod-time tracking │
├───────────────┼───────────────────────┼─────────────────────────────────────────────────────────┤  
 │ mca21 │ MCA21Connector │ MCA21 bulk + API + hybrid, Redis cache │
├───────────────┼───────────────────────┼─────────────────────────────────────────────────────────┤  
 │ sebi │ SEBIConnector │ SEBI EDGAR HTML scraper │
├───────────────┼───────────────────────┼─────────────────────────────────────────────────────────┤  
 │ rbi │ RBIConnector │ RBI statistical releases parser │
├───────────────┼───────────────────────┼─────────────────────────────────────────────────────────┤  
 │ tally │ TallyConnector │ TallyPrime XML server (version-aware 3.x/4.x) │
└───────────────┴───────────────────────┴─────────────────────────────────────────────────────────┘

Note: webhook_connector.py exists in the codebase (WebhookReceiver for push-based sources) but is handled through the  
 /api/v1/webhooks/{source_id} route rather than the pull-based registry.

Sync Engine (SyncEngine)

Guarantee chain on every run:

1. Stale run cleanup — marks any stuck running runs as failed
2. Deterministic batch_id — SHA256(source_id:sync_type:YYYY-MM-DDTHH)[:16] — same hour = same ID = idempotent re-runs
3. Idempotency check — if batch_id already completed in DB, returns existing run immediately
4. PostgreSQL advisory lock — pg_advisory_xact_lock(SHA256(source_id)[:8 bytes as int64]) — prevents concurrent syncs for the same source
5. Extraction — calls extract_full() or extract_incremental() based on sync_type
6. Empty batch handling — if df.empty, marks completed with 0 records, no MinIO write
7. Schema fingerprint — SHA256(sorted col:dtype pairs)[:16] — logs warning on schema drift
8. MinIO upload — raw-data/{client_id}/{source_id}/{YYYY}/{MM}/{DD}/{batch_id}.parquet — checks existence before upload (idempotent)
9. Parquet metadata — embeds satorix_batch_id, satorix_source_id, satorix_client_id, satorix_sync_type, satorix_schema_fingerprint
10. Watermark extraction — finds updated_at / modified_at / created_at column for timestamp strategy, or id / seq column for sequence strategy;
    advances only after successful upload
11. Profiling — runs DataProfiler.profile() on every batch (non-fatal on failure)
12. Redis notify — LPUSH layer1:sync:complete {batch_id, source_id, client_id, output_path} — signals Layer 2 (non-fatal if Redis unavailable)
13. State update — advances watermarks in sync_states  


Circuit breaker: Opens after 5 consecutive failures (CIRCUIT_BREAKER_THRESHOLD = 5). Recovers after 2 consecutive successes  
 (CIRCUIT_RECOVERY_THRESHOLD = 2). Syncs blocked while circuit is open (returns 409).

Streaming Path (StreamingIngestionConsumer)

For Kafka topics (real-time push sources):

- Library: kafka-python==2.0.2
- Pattern: Background thread per topic, runs \_consume_loop() with 10s retry on error
- Offset commit: Manual (enable_auto_commit=False), committed only after successful batch processing — at-least-once delivery guarantee
- MicroBatch: Accumulates until max_size=1000 records OR max_seconds=60 — whichever comes first
- Idempotency: batch_id = SHA256("stream:{topic}:{p@offset,...}")[:16]
- Shutdown: Gracefully flushes remaining records before stopping
- Worker: streaming_worker.py runs as a separate Docker container (infracore_streaming_worker)
- Config via env: KAFKA_BOOTSTRAP_SERVERS, KAFKA_TOPICS (format: topic:client_id:source_id), KAFKA_GROUP_ID=infracore-l1-streaming,  
  KAFKA_MAX_BATCH_SIZE=1000, KAFKA_MAX_BATCH_SECONDS=60  


Data Profiling Engine

DataProfiler.profile(df, source_id) → ProfileReport

ProfileReport structure:  
 source_id, profiled_at, total_records, total_columns
column_profiles: {col → ColumnProfile}  
 cross_field_issues: [ConsistencyIssue]  
 overall_quality_score: float (0-100)  
 recommendations: [str] # max 20

Quality score formula:

- Completeness: 40% weight (avg null rate across all columns)
- Uniqueness: 20% weight
- Pattern conformance: 20% weight (only for identified Indian identifier columns)
- Consistency: 20% weight (penalized by critical violations × 0.2, warning × 0.05)  


5 profiling modules:

1. completeness.py — null/missing rate, detects representations like "N/A", "-", "NULL"
2. uniqueness.py — duplicate detection per column
3. distribution.py — min, max, mean, top 5 values, statistical distribution
4. anomaly_detector.py — Z-score + IQR outlier detection per column
5. consistency_rules.py — 14 cross-field Indian business rules (e.g., paidUpCapital ≤ authorizedCapital, cessationDate > appointmentDate)  


Indian Domain Support

Identifier validators (indian_identifiers.py):

┌────────────┬────────────────────────────────────────────────────┬─────────────────────────────────────────────────────────────────────────┐  
 │ Identifier │ Format │ Validation │
├────────────┼────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────┤  
 │ CIN │ L/U + 5digits + 2letters + 4digits + 3letters + │ 21 chars, component extraction (listing status, NIC code, state code, │
│ │ 6digits │ year, type, seq) │
├────────────┼────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────┤  
 │ DIN │ 8 digits │ Format check │
├────────────┼────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────┤  
 │ GSTIN │ 2digits + PAN + 1letter + 1alphanumeric + Z + │ Checksum validation, state code extraction, PAN embedding check │
│ │ 1alphanumeric │ │  
 ├────────────┼────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────┤
│ PAN │ 5letters + 4digits + 1letter │ Format check │  
 ├────────────┼────────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────┤  
 │ IFSC │ 4letters + 0 + 6alphanumeric │ Format check │
└────────────┴────────────────────────────────────────────────────┴─────────────────────────────────────────────────────────────────────────┘

Indian number parser: Handles ₹1,24,50,000 → 12450000.0, crore/lakh notation (e.g., "2.5 crore" → 25000000.0)

Indian date parser: 8+ format variants → ISO 8601, Indian financial year computation (April–March)

Encryption (core/encryption.py)

Algorithm: AES-256-GCM  
 Key: 32-byte key from ENCRYPTION_KEY env var (base64-encoded)
Nonce: 96-bit (12 bytes), fresh random per encryption  
 Storage format: base64(nonce + ciphertext + 16-byte GCM tag)  
 Guarantee: Authentication tag prevents ciphertext tampering  
 Key generation: generate_key() → secrets.token_bytes(32) → base64

All connection_config JSON blobs in data_sources are encrypted with this scheme. Credentials are never logged.

Storage (core/storage.py)

- Client: minio==7.2.0
- Upload: upload_parquet(df, bucket, object_path, extra_metadata) — Snappy compression, Parquet metadata dict embedded
- Path format: {client_id}/{source_id}/{year}/{month}/{day}/{batch_id}.parquet
- Idempotency: object_exists(bucket, path) checked before upload  


Airflow DAGs (Layer 1)

- extraction_dag.py — Main extraction DAG, scheduled sync triggers per source
- health_check_dag.py — Health checks every 15 minutes
- Custom operators: infracore_hooks.py  


---

LAYER 2 — PIPELINE (TRANSFORMATION)

Port 8002 | ~4,500 LOC | 45 Python files

Layer 2 takes raw Parquet files from MinIO (Layer 1 output), runs them through a configurable transformation pipeline, validates data quality,  
 tracks provenance, and writes processed Parquet back to MinIO.

How Layer 2 Is Triggered

Primary path (event-driven):  
 Layer 1 pushes {batch_id, source_id, client_id, output_path} to Redis key layer1:sync:complete via LPUSH. Layer 2 polls with RPOPLPUSH
(at-least-once).

Fallback path:  
 Layer 2 scans the sync_completions DB table with a 30-minute lookback.

Idempotency: Layer 2 refuses to re-process a batch_id that already has a completed run.

API Surface (FastAPI)

┌────────────────────┬───────────────────────────────┐  
 │ Route prefix │ Purpose │
├────────────────────┼───────────────────────────────┤
│ /api/v1/pipelines/ │ CRUD for pipeline definitions │
├────────────────────┼───────────────────────────────┤
│ /api/v1/runs/ │ Trigger runs, check status │  
 ├────────────────────┼───────────────────────────────┤  
 │ /api/v1/lineage/ │ Query field-level provenance │  
 ├────────────────────┼───────────────────────────────┤  
 │ /api/v1/errors/ │ Dead letter queue inspection │
└────────────────────┴───────────────────────────────┘

Pipeline Definition Format (YAML/JSONB)

pipeline_id: company_master_clean  
 version: "1.0"  
 client_id: pe_fund_alpha  
 description: Clean MCA21 company master data
lineage_config:  
 entity_type: company
entity_id_column: cin  
 steps:  
 - step_id: normalize_cin  
 transform_type: normalize_cin
depends_on: []  
 config: {column: "cin"}
on_error: fail  
 - step_id: clean_name
transform_type: trim  
 depends_on: [normalize_cin]
config: {column: "company_name"}  
 on_error: skip
quality_rules: - rule_id: cin_not_null
rule_type: not_null
column: cin  
 failure_policy: reject

DAG Engine (PipelineDAG)

- Parses YAML definition into PipelineDefinitionParsed
- Topological sort: Uses NetworkX nx.topological_sort if available, falls back to Kahn's algorithm (BFS)
- Cycle detection: nx.find_cycle(g) — raises PipelineDAGError with cycle details
- Critical path: Longest dependency chain by step count (proxy for execution time)
- Duplicate step_id detection before execution
- Unknown dependency detection — validates all depends_on references exist  


Pipeline Executor (PipelineExecutor)

Execution sequence:

1. Parse DAG → validate
2. Deterministic run_id = SHA256(pipeline_id:version:input_batch_id)[:16]
3. Idempotency check — skip if run already completed
4. Create ExecutionContext (lineage, metrics, quarantine accumulator)
5. pg_advisory_lock(run_id) — prevents duplicate concurrent runs
6. Create PipelineRun DB record
7. Load input Parquet from MinIO raw-data/
8. Warn if len(df) > 200,000 (pandas memory ceiling)
9. Column normalization — strip().lower().replace(spaces, "\_") before any transforms
10. Schema presence check — warns if lineage_config.entity_id_column not found
11. Execute steps in topological order — each step passes df forward
12. Each step runs its quality_rules after the transform
13. on_error: fail stops pipeline, skip/warn continues with original df
14. Emit lineage events (capped at 10,000 unique entity IDs)
15. Write output Parquet to MinIO processed-data/{client_id}/{pipeline_id}/{version}/{YYYY/MM/DD}/{run_id}.parquet
16. Write immutable DatasetVersion record
17. pg_advisory_unlock(run_id)
18. Flush lineage and quarantine buffers  


Transform Registry (49+ transforms)

Auto-registered at import via \_auto_register():

Cleaning transforms (cleaning/):

┌──────────────────────────┬────────────────────────────────────────────────────────────────────────────────────────────────────────┐  
 │ Module │ Transforms │
├──────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────┤  
 │ string_transforms.py │ trim, uppercase, lowercase, titlecase, regex_replace, truncate, pad, strip_special_chars │
├──────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ number_transforms.py │ parse_indian_number (handles ₹, crore/lakh), parse_currency, parse_percentage, round_number, abs_value │  
 ├──────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────┤  
 │ date_transforms.py │ parse_indian_date (8+ formats), compute_indian_fy, date_diff_days, extract_year_month │  
 ├──────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────┤  
 │ address_transforms.py │ normalize_pin, normalize_state, lookup_city_district │
├──────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────┤  
 │ identifier_transforms.py │ normalize_cin, normalize_din, normalize_gstin, normalize_pan, normalize_ifsc │
└──────────────────────────┴────────────────────────────────────────────────────────────────────────────────────────────────────────┘

Structural transforms (structural/):

┌───────────────┬───────────────────────────────────────────────────────────────────────────────┐
│ Module │ Transforms │
├───────────────┼───────────────────────────────────────────────────────────────────────────────┤
│ column_ops.py │ rename_column, add_computed_column, drop_column, split_column, concat_columns │
├───────────────┼───────────────────────────────────────────────────────────────────────────────┤
│ row_ops.py │ filter_rows, dedup_by_key, sort_rows, aggregate │  
 ├───────────────┼───────────────────────────────────────────────────────────────────────────────┤  
 │ table_ops.py │ inner_join, left_join, full_join, lookup_join, union, pivot │  
 └───────────────┴───────────────────────────────────────────────────────────────────────────────┘

Enrichment transforms (enrichment/):

┌─────────────────────┬───────────────────────────────────────────────────────────────────────────────────┐
│ Module │ Transforms │
├─────────────────────┼───────────────────────────────────────────────────────────────────────────────────┤
│ reference_lookup.py │ lookup_pin_to_state_district_city (PIN code → state, district, city lookup table) │
└─────────────────────┴───────────────────────────────────────────────────────────────────────────────────┘

Quality Rules Engine

Rule types:

- not_null — column must not be NULL
- not_empty — column must not be empty string
- regex — value must match pattern
- range — value within [min, max]
- in_set — value must be in allowed list
- referential — value must exist in a reference frame
- custom_expr — pandas query expression (row-level)  


Failure policies (FailurePolicy enum):

- REJECT — drop the row entirely
- FLAG — keep row, add _failed_{rule_id} column = True
- DEFAULT — replace failing value with default_value
- TRANSFORM — apply corrective expression  


Pre-built rule sets:

- COMPANY_RULES — CIN not-null (reject), CIN regex, company_name not-null, company_status in-set, PAN/GSTIN regex (warnings), registration_date
  not-null
- DIRECTOR_RULES — DIN not-null (reject), DIN regex, director_name not-null, CIN not-null, director_status in-set
- FINANCIAL_RULES — CIN not-null (reject), financial_year not-null, paid_up_capital ≥ 0, authorised_capital ≥ 0, authorised ≥ paidUp custom  
  expression  


PostgreSQL Schema (Layer 2)

All tables prefixed l2\_ to coexist with Layer 1 in the same database.

┌─────────────────────────┬──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐  
 │ Table │ Purpose │
├─────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ l2_pipeline_definitions │ Versioned pipeline YAML stored as JSONB │
├─────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ l2_pipeline_runs │ Execution records: status, records_in/out/failed, duration, error_summary │  
 ├─────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤  
 │ l2_pipeline_step_runs │ Per-step records: status, timing, config snapshot │  
 ├─────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤  
 │ l2_error_records │ Dead letter queue: quarantined → reprocessed / discarded │
├─────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤  
 │ l2_lineage │ Field-level provenance: entity_type, entity_id, field_name, source_batch_id, pipeline_run_id, transform_applied │
├─────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤  
 │ l2_dataset_versions │ Immutable version registry: every successful output gets a row with schema fingerprint │
├─────────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤  
 │ l2_dedup_groups │ Entity resolution decisions: canonical_id, duplicate_ids, merge_strategy, confidence_score, requires_review flag │
└─────────────────────────┴──────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

Lineage Tracking

Every successful pipeline emits LineageEvent records via LineageTracker:

- entity_type + entity_id (from lineage_config in pipeline YAML)
- field_name = "pipeline_output"
- transform_applied = pipeline_id
- Capped at 10,000 unique entity IDs per run to prevent unbounded memory  


Error Classification

classify(exception, step_id) → ClassifiedError:

- error_type: source | transform | system
- error_subtype: specific exception class name
- severity: error | warning  


Airflow DAG (Layer 2)

layer2_pipeline_dag.py — Polls Redis or DB for new Layer 1 completions, triggers appropriate pipeline run.

---

LAYER 3 — ONTOLOGY (SEMANTIC INTELLIGENCE)

Port 8003 | ~7,600 LOC | 99 Python files

Layer 3 is the semantic brain of the platform. It maintains a unified knowledge graph of all Indian corporate entities, their relationships,  
 properties, histories, and computed intelligence. Every write goes through a single ObjectDataFunnel that keeps PostgreSQL, Neo4j,
Elasticsearch, and Redis in sync.

API Surface (FastAPI v1.0.0)

Startup sequence: PostgreSQL init → Neo4j connect → Elasticsearch connect → Redis connect → MinIO connect → seed schema registry from  
 object/link type definitions.

┌─────────────────────┬────────────────────────────────┬───────────────────────────────────────────────┐
│ Router │ Prefix │ Purpose │
├─────────────────────┼────────────────────────────────┼───────────────────────────────────────────────┤
│ objects.router │ /objects/{object_type} │ CRUD for ontology objects │
├─────────────────────┼────────────────────────────────┼───────────────────────────────────────────────┤
│ search.router │ /search │ Full-text + semantic search via Elasticsearch │  
 ├─────────────────────┼────────────────────────────────┼───────────────────────────────────────────────┤
│ graph.router │ /graph/network/{type}/{id} │ Graph traversal + Cypher queries │  
 ├─────────────────────┼────────────────────────────────┼───────────────────────────────────────────────┤  
 │ intelligence.router │ /intelligence/risk/{type}/{id} │ Risk scoring + anomaly detection │
├─────────────────────┼────────────────────────────────┼───────────────────────────────────────────────┤  
 │ actions.router │ /actions/{action_type} │ Execute kinetic action types │
├─────────────────────┼────────────────────────────────┼───────────────────────────────────────────────┤  
 │ timeline.router │ /timeline/{type}/{id} │ Time-series property history │
├─────────────────────┼────────────────────────────────┼───────────────────────────────────────────────┤  
 │ health.router │ /health │ Platform health checks │
├─────────────────────┼────────────────────────────────┼───────────────────────────────────────────────┤  
 │ ingest.router │ /ingest/trigger │ Batch ingestion from Layer 2 Parquet │
├─────────────────────┼────────────────────────────────┼───────────────────────────────────────────────┤  
 │ schema.router │ /schema/object-types │ Schema registry queries │
└─────────────────────┴────────────────────────────────┴───────────────────────────────────────────────┘

Object Types (Semantic Layer)

12 object types seeded at startup:

Company (PK: cin)

┌───────────────────┬─────────────────┬───────────────────────────────────────────────────────────────────────┐  
 │ Property │ Type │ Notes │
├───────────────────┼─────────────────┼───────────────────────────────────────────────────────────────────────┤  
 │ cin │ CIN_Type │ Immutable primary key, validated 21-char format │
├──────────────────────┼─────────────────┼───────────────────────────────────────────────────────────────────────┤
│ name │ str │ Required │  
 ├──────────────────────┼─────────────────┼───────────────────────────────────────────────────────────────────────┤
│ incorporationDate │ IndianDate_Type │ │  
 ├──────────────────────┼─────────────────┼───────────────────────────────────────────────────────────────────────┤  
 │ registeredState │ str │ Normalized via normalize_state() │
├──────────────────────┼─────────────────┼───────────────────────────────────────────────────────────────────────┤  
 │ companyType │ str │ Public Limited / Private Limited / LLP / OPC │
├──────────────────────┼─────────────────┼───────────────────────────────────────────────────────────────────────┤  
 │ industry │ str │ │
├──────────────────────┼─────────────────┼───────────────────────────────────────────────────────────────────────┤  
 │ authorizedCapital │ float │ INR │
├──────────────────────┼─────────────────┼───────────────────────────────────────────────────────────────────────┤  
 │ paidUpCapital │ float │ INR │
├──────────────────────┼─────────────────┼───────────────────────────────────────────────────────────────────────┤  
 │ status │ str │ Active / StrikeOff / UnderCIRP / Dormant / Archived — case-normalized │
├──────────────────────┼─────────────────┼───────────────────────────────────────────────────────────────────────┤  
 │ listedStatus │ str │ │
├──────────────────────┼─────────────────┼───────────────────────────────────────────────────────────────────────┤  
 │ registeredAddress │ str │ │
├──────────────────────┼─────────────────┼───────────────────────────────────────────────────────────────────────┤  
 │ riskScore │ int │ Derived — 0-100 │
├──────────────────────┼─────────────────┼───────────────────────────────────────────────────────────────────────┤  
 │ riskFlags │ list[str] │ Derived — e.g., CIRP_ACTIVE, OFFSHORE_DIRECTOR │
├──────────────────────┼─────────────────┼───────────────────────────────────────────────────────────────────────┤  
 │ dataQualityScore │ float │ Derived — % of critical properties present │
├──────────────────────┼─────────────────┼───────────────────────────────────────────────────────────────────────┤  
 │ subsidiaryCount │ int │ Derived at query time from graph │
├──────────────────────┼─────────────────┼───────────────────────────────────────────────────────────────────────┤  
 │ directorCount │ int │ Derived at query time from graph │
├──────────────────────┼─────────────────┼───────────────────────────────────────────────────────────────────────┤  
 │ offshoreExposureFlag │ bool │ Derived │
├──────────────────────┼─────────────────┼───────────────────────────────────────────────────────────────────────┤  
 │ groupRiskScore │ float │ Derived │
└──────────────────────┴─────────────────┴───────────────────────────────────────────────────────────────────────┘

Director (PK: din) — DIN, name, nationality, appointmentDates, isOffshore, disqualificationStatus, riskScore

Project (PK: projectId) — name, startDate, endDate, budget, contractor, status (Active/Under Construction/Stressed/Completed/Cancelled)

Address (PK: normalizedAddress) — fullAddress, PIN, state, district, city

RegulatoryAction (PK: actionId) — issuingBody, actionType, status (Ongoing/Resolved/Appealed), description, filingDate

LegalCase (PK: caseId) — court, filingDate, status, parties

InsolvencyProceeding (PK: cirpId) — ipc_number, status (Admitted/Resolved/Liquidation/Withdrawn), companyName, admissionDate

Alert (PK: alertId) — severity (HIGH/MEDIUM/LOW), alertType, title, message, affectedEntityType/Id, isActive

Event (PK: eventId) — eventType, timestamp, affectedEntity, description

RegulatoryBody (PK: bodyId) — name, jurisdiction (reference entity)

GovernmentEntity (PK: entityId) — name, jurisdiction (reference entity)

Interfaces (4): RegulatableEntity, FinancialEntity, GeographicEntity, TemporalEntity

Relationship Types (Link Types)

Corporate links (corporate.py):

┌─────────────────────────┬────────────────┬───────────────────────────────────────────────────────────┬───────────────────────────────────┐  
 │ Link │ Direction │ Properties │ Inferred? │
├─────────────────────────┼────────────────┼───────────────────────────────────────────────────────────┼───────────────────────────────────┤  
 │ DIRECTED │ Director → │ appointedDate, cessationDate, designation, isCurrent │ No │
│ │ Company │ (derived), appointingBody │ │
├─────────────────────────┼────────────────┼───────────────────────────────────────────────────────────┼───────────────────────────────────┤  
 │ OWNS │ Company → │ percentageHeld, holdingType, asOfDate, votingRights │ No │  
 │ │ Company │ │ │  
 ├─────────────────────────┼────────────────┼───────────────────────────────────────────────────────────┼───────────────────────────────────┤  
 │ SUBSIDIARY_OF │ Company → │ percentageOwned, effectiveDate │ No │
│ │ Company │ │ │  
 ├─────────────────────────┼────────────────┼───────────────────────────────────────────────────────────┼───────────────────────────────────┤
│ REGISTERED_AT │ Company → │ registrationType, since │ No │  
 │ │ Address │ │ │
├─────────────────────────┼────────────────┼───────────────────────────────────────────────────────────┼───────────────────────────────────┤  
 │ SHARES_DIRECTOR_WITH │ Company ↔ │ sharedDirectorDin, sharedDirectorName, overlapPeriod, │ Yes (infer_shares_director_with) │
│ │ Company │ inferenceConfidence │ │
├─────────────────────────┼────────────────┼───────────────────────────────────────────────────────────┼───────────────────────────────────┤
│ SHARES_ADDRESS_WITH │ Company ↔ │ sharedAddress, inferenceConfidence │ Yes (infer_shares_address_with) │
│ │ Company │ │ │  
 ├─────────────────────────┼────────────────┼───────────────────────────────────────────────────────────┼───────────────────────────────────┤
│ COMMON_BENEFICIAL_OWNER │ Company ↔ │ commonOwnerName, inferenceConfidence │ Yes │  
 │ │ Company │ │ (infer_common_beneficial_owner) │  
 ├─────────────────────────┼────────────────┼───────────────────────────────────────────────────────────┼───────────────────────────────────┤
│ HAS_EVENT │ Company → │ — │ No │  
 │ │ Event │ │ │  
 └─────────────────────────┴────────────────┴───────────────────────────────────────────────────────────┴───────────────────────────────────┘

Regulatory links (regulatory.py): SUBJECT_OF (Company → RegulatoryAction/LegalCase), ISSUED_BY (RegulatoryAction → RegulatoryBody)

Project links (project.py): OWNS_PROJECT (Company → Project with contractValue, contractor)

Object Data Funnel (object_data_funnel.py)

The single write path for all ontology data. Nothing writes to Neo4j, Elasticsearch, PostgreSQL, or Redis directly.

write_object(object_type, data, source, actor) sequence:

1. Compute data_hash = SHA256(sorted JSON)
2. Check ontology_objects table for existing row
3. If hash unchanged → return immediately (no-op, version unchanged)
4. Compute PropertyChange diff (skips lastUpdated, dataQualityScore, riskScore)
5. PostgreSQL UPSERT — ontology_objects table: (object_type, primary_key, properties JSONB, data_hash, version, updated_at) — ON CONFLICT DO  
   UPDATE
6. Event store emit — OBJECT_CREATED for new, PROPERTY_CHANGED or STATUS_CHANGED per changed property
7. Neo4j upsert — MERGE (n:ObjectType {pk: $pk}) SET n += $props
8. Elasticsearch index — document per object, all properties searchable
9. Redis invalidate — evict stale cache entry
10. Return WriteResult(success, object_type, object_id, version, changes)  


write_link(link_type, source_type, source_id, target_type, target_id, properties, actor, is_inferred) sequence:

1. PostgreSQL UPSERT into ontology_links table
2. Event store LINK_CREATED event
3. Neo4j MERGE relationship  


delete_object: Soft delete only — sets is_deleted = TRUE in ontology_objects, emits OBJECT_DELETED event, invalidates Redis cache. Never hard
deletes.

Primary key resolution:

- company → cin
- director → din
- project → projectId
- regulatory_action → actionId
- legal_case → caseId
- insolvency_proceeding → cirpId
- address → normalizedAddress
- regulatory_body → bodyId
- government_entity → entityId
- event → eventId
- alert → alertId  


Storage Backends

┌───────────────────┬───────────────────────────────────────┬──────────────────────────────────────────────────────────────────────────────┐
│ Backend │ Client library │ Purpose │  
 ├───────────────────┼───────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────┤
│ PostgreSQL 15 │ asyncpg==0.29.0 + SQLAlchemy 2.0 │ Authoritative object state in ontology_objects and ontology_links JSONB │
│ │ async │ tables │
├───────────────────┼───────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────┤  
 │ Neo4j 5.14 │ neo4j==5.14.0 │ Graph database — relationship traversal, network queries, Cypher │  
 ├───────────────────┼───────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────┤  
 │ Elasticsearch │ elasticsearch==8.11.0 │ Full-text search across all object properties │  
 │ 8.11 │ │ │
├───────────────────┼───────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────┤  
 │ Redis 7 │ redis[hiredis]==5.0.1 │ Object cache, query result cache, session state │
├───────────────────┼───────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────────┤  
 │ MinIO │ minio==7.2.0 │ Artifact storage (exports, profiling reports) │
└───────────────────┴───────────────────────────────────────┴──────────────────────────────────────────────────────────────────────────────┘

Risk Scoring

CompanyScorer.compute_score(cin, props) → (score: int 0-100, flags: list[str])

┌────────────────────────────────────┬──────────────────┬───────────────────────┐  
 │ Signal │ Points │ Flag │
├────────────────────────────────────┼──────────────────┼───────────────────────┤
│ Status = UnderCIRP │ +30 │ CIRP_ACTIVE │
├────────────────────────────────────┼──────────────────┼───────────────────────┤
│ Status = StrikeOff │ +15 │ STRUCK_OFF │  
 ├────────────────────────────────────┼──────────────────┼───────────────────────┤  
 │ Ongoing regulatory actions │ +20 each, max 40 │ ONGOING_REGULATORY │  
 ├────────────────────────────────────┼──────────────────┼───────────────────────┤  
 │ Resolved regulatory actions │ +8 each, max 16 │ │
├────────────────────────────────────┼──────────────────┼───────────────────────┤  
 │ Has offshore director │ +15 │ OFFSHORE_DIRECTOR │
├────────────────────────────────────┼──────────────────┼───────────────────────┤  
 │ Has disqualified director │ +20 │ DISQUALIFIED_DIRECTOR │
├────────────────────────────────────┼──────────────────┼───────────────────────┤  
 │ Stressed project owned │ +25 │ STRESSED_PROJECT │
├────────────────────────────────────┼──────────────────┼───────────────────────┤  
 │ Project under construction │ +10 │ │
├────────────────────────────────────┼──────────────────┼───────────────────────┤  
 │ Same address as >5 other companies │ +10 │ ADDRESS_CLUSTERING │
├────────────────────────────────────┼──────────────────┼───────────────────────┤  
 │ Cap │ 100 │ │
└────────────────────────────────────┴──────────────────┴───────────────────────┘

Additional scorers: DirectorScorer (7 signals), ProjectScorer (9 signals), GroupScorer (cascading group risk)

Anomaly Detection (5 detectors)

┌───────────────────────────┬──────────────────────────────────────────────┬────────────────────────────────┐  
 │ Detector │ Trigger │ Alert Created │
├───────────────────────────┼──────────────────────────────────────────────┼────────────────────────────────┤  
 │ address_clustering.py │ >2 unrelated companies at same address │ ADDRESS_CLUSTERING_ANOMALY │
├───────────────────────────┼──────────────────────────────────────────────┼────────────────────────────────┤
│ director_proliferation.py │ Director with >20 active appointments │ DIRECTOR_PROLIFERATION │  
 ├───────────────────────────┼──────────────────────────────────────────────┼────────────────────────────────┤  
 │ cirp_contagion.py │ Company shares directors with a CIRP company │ CIRP_CONTAGION (HIGH severity) │  
 ├───────────────────────────┼──────────────────────────────────────────────┼────────────────────────────────┤  
 │ regulatory_recidivism.py │ Repeat regulatory offender │ REGULATORY_RECIDIVISM │
├───────────────────────────┼──────────────────────────────────────────────┼────────────────────────────────┤  
 │ filing_compliance.py │ Filing delays or non-filing │ FILING_COMPLIANCE_VIOLATION │
└───────────────────────────┴──────────────────────────────────────────────┴────────────────────────────────┘

CIRP Contagion Cypher:  
 MATCH (c1:Company {status: 'UnderCIRP'})-[:SHARES_DIRECTOR_WITH]-(c2:Company)
WHERE c2.status <> 'UnderCIRP'  
 RETURN c1.cin, c1.name, c2.cin, c2.name  
 Writes alert objects through the ObjectDataFunnel (same write path as all other data).

Graph Intelligence

┌─────────────────────────────────────────────────┬──────────────────────────────────────────────────────────────────────────┐  
 │ Component │ What it does │
├─────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────┤  
 │ NetworkMapper.expand_network(type, pk, depth=2) │ Returns subgraph of depth hops around an entity │
├─────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────┤
│ PathFinder │ Shortest path + K-shortest paths between two entities via Neo4j │  
 ├─────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────┤  
 │ SharedAttributeDetector │ Finds companies sharing address/contact/director │  
 ├─────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────┤  
 │ ClusterDetector │ Community detection (Louvain via NetworkX), shell cluster identification │
├─────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────┤  
 │ InfluenceScorer │ Betweenness centrality, degree centrality, PageRank │
├─────────────────────────────────────────────────┼──────────────────────────────────────────────────────────────────────────┤  
 │ TemporalAnalyzer │ Time-based relationship changes — director join/leave timelines │
└─────────────────────────────────────────────────┴──────────────────────────────────────────────────────────────────────────┘

Kinetic Layer (Action Types + Functions)

Action Types (execute via /actions/{action_type}):

┌─────────────────────────┬───────────────────────────────────────────────────────────────────────┐  
 │ Action │ Effect │
├─────────────────────────┼───────────────────────────────────────────────────────────────────────┤
│ FlagCompanyForReview │ Creates review task, sets flag on company object │
├─────────────────────────┼───────────────────────────────────────────────────────────────────────┤
│ UpdateProjectStatus │ Updates project milestone status through funnel │  
 ├─────────────────────────┼───────────────────────────────────────────────────────────────────────┤
│ CreateIntelligenceAlert │ Writes alert object through funnel │  
 ├─────────────────────────┼───────────────────────────────────────────────────────────────────────┤  
 │ MergeCompanyObjects │ Consolidates duplicate company records, merges relationships in Neo4j │
└─────────────────────────┴───────────────────────────────────────────────────────────────────────┘

Computed Functions (on-demand, query-time):

┌──────────────────────────────────────────────────┬────────────────────────────────────────────────────────────────────────────────────────┐  
 │ Function │ Description │
├──────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤
│ computeGroupRiskScore(cin) │ Aggregates risk across the full corporate group │
├──────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤
│ computeBeneficialOwnershipChain(cin, │ Returns OwnershipNode[] chain with entity_name, entity_type, percentage, isOffshore, │  
 │ max_depth=5) │ depth │  
 ├──────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤  
 │ assessCIRPContagionRisk(cin) │ Evaluates exposure to CIRP-active entities │  
 ├──────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────────────────────────────┤  
 │ predictProjectCompletionProbability(project_id) │ ML-based probability (model not yet trained) │
└──────────────────────────────────────────────────┴────────────────────────────────────────────────────────────────────────────────────────┘

RBAC Security Model

7 roles (defined in roles.py):

┌────────────────────────┬──────────┬───────────┬───────────────────┬───────────────┬────────────┐  
 │ Role │ can_read │ can_write │ can_modify_schema │ can_sensitive │ can_delete │
├────────────────────────┼──────────┼───────────┼───────────────────┼───────────────┼────────────┤  
 │ platform_administrator │ ✅ │ ✅ │ ✅ │ ✅ │ ✅ │
├────────────────────────┼──────────┼───────────┼───────────────────┼───────────────┼────────────┤  
 │ ontology_designer │ ❌ │ ❌ │ ✅ │ ❌ │ ❌ │
├────────────────────────┼──────────┼───────────┼───────────────────┼───────────────┼────────────┤  
 │ data_steward │ ✅ │ ✅ │ ❌ │ ❌ │ ❌ │
├────────────────────────┼──────────┼───────────┼───────────────────┼───────────────┼────────────┤  
 │ analyst │ ✅ │ ❌ │ ❌ │ ❌ │ ❌ │
├────────────────────────┼──────────┼───────────┼───────────────────┼───────────────┼────────────┤  
 │ compliance_head │ ✅ │ ❌ │ ❌ │ ✅ │ ❌ │
├────────────────────────┼──────────┼───────────┼───────────────────┼───────────────┼────────────┤  
 │ restricted_viewer │ ❌ │ ❌ │ ❌ │ ❌ │ ❌ │
├────────────────────────┼──────────┼───────────┼───────────────────┼───────────────┼────────────┤  
 │ system_pipeline │ ✅ │ ✅ │ ❌ │ ❌ │ ❌ │
└────────────────────────┴──────────┴───────────┴───────────────────┴───────────────┴────────────┘

Object-level security: object_security.py — PE firm clients see only their portfolio companies (client_id filter).

Property-level security: property_security.py — masks certain properties based on role.

Audit logger: audit_logger.py — immutable audit trail of all read/write/action operations.

Timeline / Event Sourcing

- event_store.py — every Funnel write emits an immutable OntologyEvent (OBJECT_CREATED, PROPERTY_CHANGED, STATUS_CHANGED, LINK_CREATED,  
  OBJECT_DELETED)
- timeline_service.py — query historical state of any entity at any point in time
- change_detector.py — diff detection between consecutive event states  


Ontology Health Monitoring

- ontology_health.py — overall health score: coverage %, orphan %, impossible state count
- duplicate_surface.py — detect entity pairs that may be duplicates (fuzzy name + address matching)
- orphan_detector.py — entities with no relationships in the graph
- impossible_state.py — constraint violations (e.g., paidUpCapital > authorizedCapital)  


Schema Registry

4 registries managed via API:

- object_type_registry — upsert/version object type definitions
- property_registry — property definitions + validation rules
- link_type_registry — relationship type definitions
- interface_registry — interface compositions (RegulatableEntity etc.)
- version_manager — schema change versioning  


Layer 3 Dependencies (requirements.txt)

fastapi==0.104.0 / uvicorn==0.24.0
sqlalchemy[asyncio]==2.0.23 / asyncpg==0.29.0 / psycopg2-binary==2.9.9  
 pandas==2.2.2 / pyarrow==15.0.2  
 pydantic==2.5.0 / pydantic-settings==2.1.0  
 neo4j==5.14.0  
 elasticsearch==8.11.0  
 redis[hiredis]==5.0.1
minio==7.2.0  
 networkx==3.2.1
deepdiff==6.7.1
httpx==0.25.2 / python-dotenv==1.0.0

Layer 3 Dockerfile

FROM python:3.11-slim
WORKDIR /app
RUN apt-get install curl gcc libpq-dev
COPY requirements.txt + source  
 ENV PYTHONPATH=/app
EXPOSE 8003  
 CMD uvicorn api.main:app --host 0.0.0.0 --port 8003 --workers 2

---

WHAT IS NOT BUILT (Layers 4–10)

These are fully designed in the system contract but have zero implementation code:

Layer 4 — Graph Intelligence API (Port 8004)

- Advanced betweenness centrality computation (NetworkX + Neo4j GDS)
- Streaming cluster updates via Kafka (layer4.recompute.triggers)
- Selective re-computation: only structural changes (new director, ownership change) trigger full network recalculation
- Kafka cache invalidation for Redis when network topology changes  


Layer 5 — Analytics & AI API (Port 8005)

- XGBoost CIRP precursor detection model
- LangChain + Claude API (claude-sonnet-4-6) for path narrative generation
- Sentence-transformers for semantic entity resolution
- TimescaleDB for high-frequency metric storage
- pgvector for semantic search  


Layer 6 — Application Layer (Ports 8006, 8007, 3000, 3001, 3002)

- FastAPI backend on 8006 + WebSocket server on 8007
- Intelligence Dashboard (React, Port 3000) — client-facing product
- Operational Dashboard (React, Port 3001) — internal platform management
- Schema Manager (React, Port 3002) — ontology configuration interface  


Layers 7–10

- Layer 7: Workflow execution, external integrations (email, Slack, webhooks)
- Layer 8: Fine-grained row/column-level security policies
- Layer 9: Multi-tenant deployment orchestration, Kubernetes
- Layer 10: Collaboration (comments, annotations, discussions)  


---

COMPLETE PORT MAP

Internal Services:
5432 → PostgreSQL 15  
 6379 → Redis 7
9092 → Kafka broker
9200 → Elasticsearch 8.11  
 7474 → Neo4j Browser
7687 → Neo4j Bolt

Object Storage:  
 9000 → MinIO API
9001 → MinIO Console

Orchestration:  
 8080 → Airflow UI (admin/admin)

Platform APIs:
8001 → Layer 1 API (Data Integration)  
 8002 → Layer 2 API (Pipeline)  
 8003 → Layer 3 API (Ontology)
8004 → Layer 4 API (Graph Intelligence) [NOT BUILT]  
 8005 → Layer 5 API (Analytics & AI) [NOT BUILT]
8006 → Layer 6 API (Application) [NOT BUILT]  
 8007 → Layer 6 WebSocket [NOT BUILT]

Dashboards:  
 3000 → Intelligence Dashboard [NOT BUILT]  
 3001 → Operational Dashboard [NOT BUILT]
3002 → Schema Manager [NOT BUILT]

---

DATA FLOW (End to End)

External Source
│  
 ▼ (pull via connector OR push via webhook/Kafka)
Layer 1 — Extraction  
 │ ├─ AES-256-GCM decrypt credentials
│ ├─ Advisory lock per source  
 │ ├─ Incremental watermark tracking  
 │ ├─ Profile DataFrame (completeness, uniqueness, anomalies)  
 │ └─ Upload Parquet to MinIO raw-data/  
 │  
 ▼ LPUSH layer1:sync:complete → Redis  
 Layer 2 — Transformation  
 │ ├─ Download raw Parquet from MinIO
│ ├─ Column normalization (lowercase_underscore)  
 │ ├─ Execute DAG steps in topological order  
 │ ├─ Quality rules → reject / flag / default / transform  
 │ ├─ Failed records → l2_error_records (DLQ)  
 │ ├─ Field-level lineage → l2_lineage
│ └─ Upload processed Parquet to MinIO processed-data/  
 │  
 ▼ (Layer 2 API trigger or event)  
 Layer 3 — Ontology Ingestion  
 │ ├─ Load processed Parquet
│ ├─ Map rows to object types (company, director, etc.)  
 │ └─ Write through ObjectDataFunnel:
│ ├─ PostgreSQL UPSERT (authoritative)  
 │ ├─ Event store emit
│ ├─ Neo4j MERGE node/relationship  
 │ ├─ Elasticsearch index
│ └─ Redis cache invalidate  
 │  
 ▼ (intelligence runs on demand or scheduled)
Layer 3 — Intelligence  
 │ ├─ Risk scoring (company/director/project/group)  
 │ ├─ Anomaly detection (CIRP contagion, director proliferation, etc.)  
 │ └─ Graph intelligence (paths, centrality, clusters)  
 │  
 ▼ [NOT BUILT]
Layers 4–6 — Advanced Intelligence + Dashboards

---

BUILD STATUS SUMMARY

┌─────────────────────────────────────────────┬─────────────┬─────────────────────────────────┐
│ Component │ Status │ Completeness │  
 ├─────────────────────────────────────────────┼─────────────┼─────────────────────────────────┤
│ Docker infrastructure (14 services) │ ✅ Running │ 100% │
├─────────────────────────────────────────────┼─────────────┼─────────────────────────────────┤
│ Layer 1 connectors (13 total) │ ✅ Complete │ 100% │  
 ├─────────────────────────────────────────────┼─────────────┼─────────────────────────────────┤  
 │ Layer 1 sync engine │ ✅ Complete │ 100% │  
 ├─────────────────────────────────────────────┼─────────────┼─────────────────────────────────┤  
 │ Layer 1 streaming (Kafka) │ ✅ Complete │ 100% │
├─────────────────────────────────────────────┼─────────────┼─────────────────────────────────┤  
 │ Layer 1 data profiling │ ✅ Complete │ 100% │
├─────────────────────────────────────────────┼─────────────┼─────────────────────────────────┤  
 │ Layer 1 encryption (AES-256-GCM) │ ✅ Complete │ 100% │
├─────────────────────────────────────────────┼──────────────┼─────────────────────────────────┤  
 │ Layer 1 health monitoring + circuit breaker │ ✅ Complete │ 100% │
├─────────────────────────────────────────────┼──────────────┼─────────────────────────────────┤  
 │ Layer 2 DAG engine │ ✅ Complete │ 100% │
├─────────────────────────────────────────────┼──────────────┼─────────────────────────────────┤  
 │ Layer 2 transforms (49+) │ ✅ Complete │ 100% │
├─────────────────────────────────────────────┼──────────────┼─────────────────────────────────┤  
 │ Layer 2 quality rules engine │ ✅ Complete │ 100% │
├─────────────────────────────────────────────┼──────────────┼─────────────────────────────────┤  
 │ Layer 2 lineage tracking │ ✅ Complete │ 100% │
├─────────────────────────────────────────────┼──────────────┼─────────────────────────────────┤  
 │ Layer 2 dead letter queue │ ✅ Complete │ 100% │
├─────────────────────────────────────────────┼──────────────┼─────────────────────────────────┤  
 │ Layer 2 cross-batch dedup │ 🟡 Partial │ ~30% (class defined, not wired) │
├─────────────────────────────────────────────┼──────────────┼─────────────────────────────────┤  
 │ Layer 3 object types (12) │ ✅ Complete │ 95% │
├─────────────────────────────────────────────┼──────────────┼─────────────────────────────────┤  
 │ Layer 3 Object Data Funnel │ ✅ Complete │ 100% │
├─────────────────────────────────────────────┼──────────────┼─────────────────────────────────┤  
 │ Layer 3 storage (PG + Neo4j + ES + Redis) │ ✅ Complete │ 100% │
├─────────────────────────────────────────────┼──────────────┼─────────────────────────────────┤  
 │ Layer 3 risk scoring │ ✅ Complete │ 100% │
├─────────────────────────────────────────────┼──────────────┼─────────────────────────────────┤  
 │ Layer 3 anomaly detection (5) │ ✅ Complete │ 100% │
├─────────────────────────────────────────────┼──────────────┼─────────────────────────────────┤  
 │ Layer 3 graph intelligence │ ✅ Complete │ 100% │
├─────────────────────────────────────────────┼──────────────┼─────────────────────────────────┤  
 │ Layer 3 RBAC (7 roles) │ ✅ Complete │ 100% │
├─────────────────────────────────────────────┼──────────────┼─────────────────────────────────┤  
 │ Layer 3 audit log + event sourcing │ ✅ Complete │ 100% │
├─────────────────────────────────────────────┼──────────────┼─────────────────────────────────┤  
 │ Layer 3 kinetic actions (4) │ ✅ Complete │ 100% │
├─────────────────────────────────────────────┼──────────────┼─────────────────────────────────┤  
 │ Layers 4–10 │ ❌ Not built │ 0% │
└─────────────────────────────────────────────┴──────────────┴─────────────────────────────────┘

The platform is MVP-ready for single-client demo — data flows from source to semantic knowledge graph with full intelligence scoring. The only  
 thing a client cannot do yet is open a browser and see it. That requires Layer 6.
