# Infracore Foundry — Complete Manual Testing & Operations Guide

**Stack:** Python 3.11 · FastAPI · PostgreSQL 15 · MinIO · Redis 7 · Kafka 3.6 · Airflow 2.7 · Neo4j 5.14 · Elasticsearch 8.11  
**Last validated against:** commit `6e0a58a`

---

## 1. WHAT THE SYSTEM CAN CURRENTLY DO

### Capabilities by layer

| Layer | What it does | Port |
|-------|-------------|------|
| **Layer 1 — Ingestion** | Connects to data sources, extracts raw data incrementally, lands as Parquet in MinIO, profiles quality | 8001 |
| **Layer 2 — Pipeline** | Reads Layer 1 Parquet, runs configurable transform DAGs, writes processed Parquet back to MinIO | 8002 |
| **Layer 3 — Ontology** | Maps processed data to semantic objects, builds a knowledge graph in Neo4j + Elasticsearch, runs risk scoring and inference | 8003 |

### Supported connectors (Layer 1)
`csv`, `excel`, `postgresql`, `mysql`, `rest_api`, `pdf`, `s3`, `sftp`, `google_sheets`, `mca21`, `sebi`, `rbi`, `tally`, `webhook`

### Supported transforms (Layer 2)
48 built-in transforms across 4 families:
- **Cleaning:** `normalize_cin`, `normalize_din`, `normalize_gstin`, `normalize_pan`, `normalize_state`, `parse_indian_date`, `parse_indian_number`, `parse_crore_to_rupees`, `trim_whitespace`, `normalize_case`, `fill_null_string`, `remove_special_characters`, `cast_column`, `round_decimals`, `clip_outliers`, `remove_currency_symbol`, `regex_extract`, `regex_replace`, `extract_pin_code`, `split_address_components`, `normalize_city`, `compute_age`, `compute_financial_year`, `date_difference`
- **Structural:** `select_columns`, `drop_columns`, `rename_columns`, `add_constant_column`, `add_computed_column`, `add_row_number`, `concat_columns`, `split_column`, `filter_rows`, `drop_null_rows`, `deduplicate_rows`, `sort_rows`, `sample_rows`, `aggregate`, `pivot`, `unpivot`, `inner_join`, `left_join`, `union`
- **Enrichment:** `lookup`, `reference_lookup`, `state_lookup`, `pin_code_lookup`, `nic_code_lookup`, `ifsc_lookup`

### Supported ontology object types (Layer 3)
`company`, `director`, `project`, `regulatory_action`, `legal_case`, `insolvency_proceeding`, `address`, `regulatory_body`, `government_entity`, `event`, `alert`

### Data flow
```
[CSV / API / DB / Webhook / Kafka]
        │
        ▼  Layer 1 (port 8001)
  SyncEngine → extracts → profiles → SHA-256 incremental check
        │
        ▼  MinIO bucket: raw-data
  {client_id}/{source_id}/YYYY/MM/DD/{batch_id}.parquet
        │
        ▼  Redis key: layer1:sync:complete   (lpush notification)
        │
        ▼  Layer 2 (port 8002 / Airflow DAG: layer2_pipeline)
  PipelineExecutor → loads Parquet → runs transform DAG → quality rules
        │
        ▼  MinIO bucket: processed-data
  {client_id}/{pipeline_id}/{version}/YYYY/MM/DD/{run_id}.parquet
        │
        ▼  Layer 3 (port 8003)
  BatchIngestor → ObjectDataFunnel → PostgreSQL + Neo4j + Elasticsearch + Redis
        │
        ▼  Intelligence APIs
  Risk scores · graph queries · inferred relationships · timeline · alerts
```

---

## 2. SYSTEM ARCHITECTURE FLOW (END-TO-END)

### Step-by-step data movement

**Step 1 — Input source registered**
A data source record is created in PostgreSQL (`data_sources` table). It stores connection config (encrypted), connector type, and incremental watermark state.

**Step 2 — Layer 1 sync triggered**
`SyncEngine.run_sync()` acquires a PostgreSQL advisory lock, calls `connector.extract_full()` or `connector.extract_incremental()`, then runs the data profiler.

**Step 3 — Raw Parquet written to MinIO**
Path pattern: `raw-data/{client_id}/{source_id}/YYYY/MM/DD/{batch_id}.parquet`  
The batch_id is deterministic: `SHA-256("{source_id}:{sync_type}:{YYYY-MM-DDTHH}")[:16]` — re-running within the same hour is a no-op.

**Step 4 — Redis notification**
After the MinIO upload succeeds, Layer 1 pushes `{"batch_id", "source_id", "client_id", "output_path"}` to Redis list `layer1:sync:complete`.

**Step 5 — Layer 2 triggered**
The Airflow DAG `layer2_pipeline` (schedule: every 15 min) pops from `layer1:sync:complete` via `RPOPLPUSH`, finds all active pipelines for that `client_id`, and spawns one Airflow task per pipeline.

**Step 6 — Pipeline execution**
`PipelineExecutor` loads the Parquet from `raw-data/`, normalizes column names to snake_case, runs each step in DAG topological order, runs quality validators, and writes the result to `processed-data/`.

**Step 7 — Layer 3 ingestion**
`POST /ingest/trigger` calls `BatchIngestor.ingest_from_layer2()` which reads `processed-data/` Parquets, maps rows to semantic object types, runs SHA-256 incremental filter, writes through `ObjectDataFunnel` (Postgres → events → Neo4j → Elasticsearch → Redis cache invalidation), runs inference rules, risk scoring, and anomaly detection.

---

## 3. ENVIRONMENT SETUP (DOCKER)

### Prerequisites
```bash
docker --version       # 24.x or later
docker compose version # 2.x or later
```

### Start all services
```bash
cd /opt/php74/satorix/infracore_foundry

# Start everything
docker compose up -d

# Start only infrastructure (no APIs) — useful for local dev
docker compose up -d postgres minio redis kafka neo4j elasticsearch
```

### Verify all containers are running
```bash
docker compose ps

# Expected: all containers show "running" or "healthy"
# Container names:
#   infracore_postgres        (port 5432)
#   infracore_minio           (ports 9000, 9001)
#   infracore_minio_init      (runs once, then exits — normal)
#   infracore_redis           (port 6379)
#   infracore_kafka           (port 9092)
#   infracore_neo4j           (ports 7474, 7687)
#   infracore_elasticsearch   (port 9200)
#   infracore_airflow_webserver  (port 8080)
#   infracore_airflow_scheduler
#   infracore_airflow_worker
#   infracore_airflow_init    (runs once, then exits — normal)
#   infracore_layer1_api      (port 8001)
#   infracore_layer2_api      (port 8002)
#   infracore_layer3_api      (port 8003)
#   infracore_streaming_worker
```

### Verify each service is responding
```bash
# Layer 1 API
curl -s http://localhost:8001/ping
# Expected: {"pong":true}

# Layer 2 API
curl -s http://localhost:8002/health
# Expected: {"status":"healthy"}

# Layer 3 API
curl -s http://localhost:8003/health
# Expected: {"status":"ok","services":{"neo4j":"ok","elasticsearch":"ok","redis":"ok","postgresql":"ok"}}

# PostgreSQL
docker exec infracore_postgres pg_isready -U infracore -d infracore
# Expected: /var/run/postgresql:5432 - accepting connections

# MinIO health
curl -s http://localhost:9000/minio/health/live
# Expected: HTTP 200 (empty body)

# MinIO console
# Open browser: http://localhost:9001
# Login: infracore_minio / infracore_minio_secret

# Redis
docker exec infracore_redis redis-cli ping
# Expected: PONG

# Kafka
docker exec infracore_kafka kafka-topics.sh --bootstrap-server localhost:9092 --list
# Expected: (empty or existing topics listed)

# Neo4j browser
# Open browser: http://localhost:7474
# Login: neo4j / infracore123

# Elasticsearch
curl -s http://localhost:9200/_cluster/health | python3 -m json.tool
# Expected: "status":"green" or "yellow"

# Airflow UI
# Open browser: http://localhost:8080
# Login: admin / admin
```

### Required environment variables (`.env` in project root)
All values below are the development defaults — already in `/opt/php74/satorix/infracore_foundry/.env`:

```env
# PostgreSQL
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=infracore
POSTGRES_USER=infracore
POSTGRES_PASSWORD=infracore_dev_password

# MinIO
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=infracore_minio
MINIO_SECRET_KEY=infracore_minio_secret
MINIO_RAW_BUCKET=raw-data
MINIO_SECURE=false

# Redis
REDIS_URL=redis://localhost:6379/0

# Encryption (used for connector credentials at rest)
ENCRYPTION_KEY=dGhpcyBpcyBhIDMyIGJ5dGUga2V5IGZvciBBRVM=

# API authentication
# Leave empty for local dev (auth bypassed with a warning)
API_KEY=

# Layer 3
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=infracore123
ELASTICSEARCH_URL=http://localhost:9200
LAYER3_API_PORT=8003
LOG_LEVEL=INFO
```

**To set an API key** (required for all Layer 1 and Layer 2 endpoints in non-empty mode):
```bash
# Generate a key
python3 -c "import secrets; print(secrets.token_hex(32))"
# Add to .env: API_KEY=<generated_value>
# Then restart: docker compose restart layer1-api layer2-api
```

---

## 4. REQUIRED INPUTS

### A. Batch ingestion — CSV source

**Minimum CSV structure for company master data:**
```csv
CIN,CompanyName,DateOfIncorporation,RegisteredState,Status,AuthorizedCapital,PaidUpCapital
L45201MH2003PLC142301,Infracore Systems Ltd,15/01/2003,Maharashtra,Active,50000000,25000000
U72900DL2010PTC198765,TechBridge Solutions Pvt Ltd,22/03/2010,Delhi,Active,10000000,5000000
L17110GJ1996PLC029747,Gujarat Textiles Ltd,01/04/1996,Gujarat,UnderCIRP,100000000,80000000
```

Save as: `/tmp/infracore_companies.csv`

**Minimum CSV structure for directors:**
```csv
DIN,DirectorName,DateOfBirth,Nationality,DisqualificationStatus,CompanyDIN
00112233,Rajesh Kumar Sharma,15/06/1970,Indian,None,L45201MH2003PLC142301
00445566,Victor Fernandes,28/09/1965,British,None,L45201MH2003PLC142301
00778899,Priya Mehta,10/12/1980,Indian,Disqualified,U72900DL2010PTC198765
```

Save as: `/tmp/infracore_directors.csv`

**Minimum CSV structure for projects:**
```csv
ProjectID,ProjectName,PromotingCompanyCIN,Status,PlannedCompletionDate,ActualCompletionDate,DelayMonths,CostOverrunPercent,SectorCode
PRJ001,Highway NH48 Expansion,L45201MH2003PLC142301,Under Construction,2024-03-31,,12,8,42
PRJ002,Thermal Plant Phase 2,L17110GJ1996PLC029747,Stressed,2023-06-30,,18,35,40
```

Save as: `/tmp/infracore_projects.csv`

### B. Batch ingestion — API payload

**Register a CSV data source:**
```json
{
  "name": "Company Master CSV",
  "source_type": "csv",
  "client_id": "infracore",
  "config": {
    "file_path": "/tmp/infracore_companies.csv",
    "has_header": true,
    "delimiter": ","
  },
  "description": "MCA21 company master extract"
}
```

**Register a REST API source:**
```json
{
  "name": "Sandbox MCA21 API",
  "source_type": "rest_api",
  "client_id": "infracore",
  "config": {
    "base_url": "https://api.sandbox.co.in/mca",
    "endpoint": "/company/master",
    "method": "GET",
    "params": {"cin": "L45201MH2003PLC142301"}
  },
  "credentials": {
    "api_key": "your-sandbox-api-key"
  }
}
```

### C. Streaming inputs — Kafka message format

Each Kafka message must be valid JSON. The consumer group id is `infracore-l1-streaming`.

```json
{
  "cin": "L45201MH2003PLC142301",
  "company_name": "Infracore Systems Ltd",
  "event_type": "status_change",
  "new_status": "UnderCIRP",
  "timestamp": "2025-04-25T10:30:00Z",
  "source": "mca21_webhook"
}
```

Topic naming convention: `{client_id}.{entity_type}.events`  
Example: `infracore.company.events`

### D. Pipeline configuration — YAML definition

Save the following as `pipeline_config.json` (the API accepts parsed YAML as JSON):

```json
{
  "pipeline_id": "infracore_company_normalize",
  "version": "1.0",
  "client_id": "infracore",
  "description": "Normalize company master data from MCA21",
  "steps": [
    {
      "step_id": "trim_whitespace",
      "transform_type": "trim_whitespace",
      "config": {"columns": "all"},
      "depends_on": [],
      "on_error": "warn"
    },
    {
      "step_id": "normalize_cin",
      "transform_type": "normalize_cin",
      "config": {"column": "cin"},
      "depends_on": ["trim_whitespace"],
      "on_error": "fail"
    },
    {
      "step_id": "normalize_state",
      "transform_type": "normalize_state",
      "config": {"column": "registeredstate"},
      "depends_on": ["normalize_cin"],
      "on_error": "warn"
    },
    {
      "step_id": "parse_date",
      "transform_type": "parse_indian_date",
      "config": {"column": "dateofincorporation", "output_column": "incorporation_date_iso"},
      "depends_on": ["normalize_state"],
      "on_error": "warn"
    },
    {
      "step_id": "drop_nulls",
      "transform_type": "drop_null_rows",
      "config": {"columns": ["cin", "companyname"]},
      "depends_on": ["parse_date"],
      "on_error": "warn"
    }
  ],
  "lineage_config": {
    "entity_type": "company",
    "entity_id_column": "cin"
  }
}
```

---

## 5. HOW TO RUN LAYER 1 (INGESTION)

### Step 1 — Register a data source

```bash
# Without API key (local dev, API_KEY="" in .env):
curl -s -X POST http://localhost:8001/api/v1/sources/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Company Master CSV",
    "source_type": "csv",
    "client_id": "infracore",
    "config": {
      "file_path": "/tmp/infracore_companies.csv",
      "has_header": true
    },
    "description": "MCA21 company master"
  }' | python3 -m json.tool

# With API key (production):
curl -s -X POST http://localhost:8001/api/v1/sources/ \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{ ... }' | python3 -m json.tool
```

**Expected response:**
```json
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "name": "Company Master CSV",
  "source_type": "csv",
  "client_id": "infracore",
  "config": {"file_path": "/tmp/infracore_companies.csv", "has_header": true},
  "is_active": true,
  "created_at": "2025-04-25T10:00:00Z"
}
```

**Save the returned `id`** — you'll need it for all subsequent calls.

### Step 2 — List all registered sources
```bash
curl -s "http://localhost:8001/api/v1/sources/?client_id=infracore" | python3 -m json.tool
```

### Step 3 — Test connection before syncing
```bash
SOURCE_ID="<uuid-from-step-1>"

curl -s -X POST "http://localhost:8001/api/v1/health/${SOURCE_ID}/check" \
  | python3 -m json.tool

# Expected:
# {"source_id": "...", "status": "healthy", "response_time_ms": 1.2, ...}
```

### Step 4 — Trigger a sync
```bash
SOURCE_ID="<uuid-from-step-1>"

# Full sync (extract everything)
curl -s -X POST "http://localhost:8001/api/v1/sync/${SOURCE_ID}/trigger" \
  -H "Content-Type: application/json" \
  -d '{"sync_type": "full"}' | python3 -m json.tool

# Incremental sync (skip if file checksum unchanged)
curl -s -X POST "http://localhost:8001/api/v1/sync/${SOURCE_ID}/trigger" \
  -H "Content-Type: application/json" \
  -d '{"sync_type": "incremental"}' | python3 -m json.tool
```

**Expected response:**
```json
{
  "id": "abc123...",
  "source_id": "3fa85f64-...",
  "sync_type": "full",
  "status": "completed",
  "started_at": "2025-04-25T10:05:00Z",
  "completed_at": "2025-04-25T10:05:02Z",
  "records_extracted": 3,
  "output_path": "infracore/3fa85f64-5717-4562-b3fc-2c963f66afa6/2025/04/25/a1b2c3d4e5f6g7h8.parquet"
}
```

**Save the `output_path`** — this is the raw data location for Layer 2.

### Step 5 — Check sync history
```bash
curl -s "http://localhost:8001/api/v1/sync/${SOURCE_ID}/history?limit=5" | python3 -m json.tool
```

### Expected logs (from `docker compose logs -f layer1-api`)
```
INFO  Starting Layer 1 Data Integration API...
INFO  Database tables created/verified successfully
INFO  Database connectivity verified
INFO  Settings loaded
INFO  Sync completed source_id=... records=3 duration=1.2 sync_type=full batch_id=a1b2c3d4
INFO  Uploaded Parquet to MinIO bucket=raw-data object_path=infracore/.../a1b2c3d4.parquet records=3
INFO  Profiling complete: quality_score=98.0, issues=0
```

### Where raw data is stored
```
MinIO bucket: raw-data
Path pattern: {client_id}/{source_id}/{YYYY}/{MM}/{DD}/{batch_id}.parquet

Example:
  raw-data/infracore/3fa85f64-5717-4562-b3fc-2c963f66afa6/2025/04/25/a1b2c3d4e5f6g7h8.parquet
```

### Verify Parquet files in MinIO
```bash
# Via MinIO console: http://localhost:9001
# Navigate to: Buckets → raw-data → Browse

# Via mc CLI inside container:
docker exec infracore_minio_init mc ls myminio/raw-data/infracore/ --recursive

# Via Python locally:
python3 << 'EOF'
from minio import Minio
client = Minio("localhost:9000", access_key="infracore_minio", secret_key="infracore_minio_secret", secure=False)
for obj in client.list_objects("raw-data", prefix="infracore/", recursive=True):
    print(obj.object_name, obj.size)
EOF
```

---

## 6. HOW TO RUN STREAMING INGESTION

### Start the streaming worker (already started by docker compose)
```bash
docker compose logs -f streaming-worker
# Expected: "Kafka consumer started: topic=... group=infracore-l1-streaming"
```

### Configure which Kafka topics to consume

Set `KAFKA_TOPICS` in `.env`:
```env
KAFKA_TOPICS=infracore.company.events,infracore.director.events
```
Then restart: `docker compose restart streaming-worker`

### Send test messages to Kafka
```bash
# Open a Kafka producer shell inside the container
docker exec -it infracore_kafka kafka-console-producer.sh \
  --bootstrap-server localhost:9092 \
  --topic infracore.company.events

# Type or paste one JSON message per line, then Ctrl+D to exit:
{"cin":"L45201MH2003PLC142301","company_name":"Infracore Systems Ltd","event_type":"status_change","new_status":"Active","timestamp":"2025-04-25T10:00:00Z"}
{"cin":"U72900DL2010PTC198765","company_name":"TechBridge Solutions","event_type":"filing","filing_type":"annual_return","timestamp":"2025-04-25T10:01:00Z"}
```

### Send 100 test messages with a script
```bash
python3 << 'EOF'
from kafka import KafkaProducer
import json, time

producer = KafkaProducer(
    bootstrap_servers="localhost:9092",
    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
)

for i in range(100):
    producer.send("infracore.company.events", {
        "cin": f"L{i:05d}MH2003PLC{i:06d}",
        "company_name": f"Test Company {i}",
        "event_type": "update",
        "timestamp": "2025-04-25T10:00:00Z",
    })

producer.flush()
print("Sent 100 messages")
EOF
```

### How micro-batches work
The streaming worker accumulates messages until **1000 messages** or **60 seconds** elapse (whichever comes first), then:
1. Flushes the batch as a Pandas DataFrame
2. Uploads to MinIO as Parquet under `raw-data/{client_id}/{source_id}/...`
3. Creates a `SyncRun` record in PostgreSQL
4. Pushes to Redis `layer1:sync:complete`
5. Commits Kafka offsets — messages only committed after successful MinIO upload

### Verify micro-batch was written
```bash
# Check sync runs created by the streaming worker
docker exec -it infracore_postgres psql -U infracore -d infracore \
  -c "SELECT source_id, sync_type, status, records_extracted, output_path, started_at FROM sync_runs ORDER BY started_at DESC LIMIT 5;"

# Watch streaming worker logs
docker compose logs -f streaming-worker
# Expected: "Flushing micro-batch: topic=infracore.company.events size=100 offsets=[p0@99]"
```

---

## 7. HOW TO RUN LAYER 2 (TRANSFORMATION)

### Method 1 — Register a pipeline then trigger via API

**Step 1: Register the pipeline**
```bash
curl -s -X POST http://localhost:8002/pipelines/ \
  -H "Content-Type: application/json" \
  -d '{
    "pipeline_id": "infracore_company_normalize",
    "version": "1.0",
    "client_id": "infracore",
    "description": "Normalize MCA21 company data",
    "config": {
      "pipeline_id": "infracore_company_normalize",
      "version": "1.0",
      "client_id": "infracore",
      "steps": [
        {
          "step_id": "trim",
          "transform_type": "trim_whitespace",
          "config": {"columns": "all"},
          "depends_on": [],
          "on_error": "warn"
        },
        {
          "step_id": "normalize_cin",
          "transform_type": "normalize_cin",
          "config": {"column": "cin"},
          "depends_on": ["trim"],
          "on_error": "warn"
        },
        {
          "step_id": "normalize_state",
          "transform_type": "normalize_state",
          "config": {"column": "registeredstate"},
          "depends_on": ["normalize_cin"],
          "on_error": "warn"
        }
      ]
    },
    "created_by": "developer"
  }' | python3 -m json.tool
```

**Expected response:**
```json
{
  "id": "7b1e3a9d-...",
  "pipeline_id": "infracore_company_normalize",
  "version": "1.0",
  "client_id": "infracore",
  "is_active": true,
  "step_count": 3
}
```

**Save the `id`** as `PIPELINE_DEF_ID`.

**Step 2: Trigger a run**
```bash
PIPELINE_DEF_ID="<uuid-from-step-1>"
INPUT_PATH="<output_path-from-layer1-sync>"  # e.g. infracore/.../a1b2c3d4.parquet

curl -s -X POST http://localhost:8002/runs/trigger \
  -H "Content-Type: application/json" \
  -d "{
    \"pipeline_definition_id\": \"${PIPELINE_DEF_ID}\",
    \"input_path\": \"${INPUT_PATH}\",
    \"triggered_by\": \"manual\"
  }" | python3 -m json.tool

# Expected: {"message": "Pipeline run queued", "pipeline_id": "infracore_company_normalize"}
```

**Step 3: Check run status**
```bash
# List recent runs
curl -s "http://localhost:8002/runs/?limit=5" | python3 -m json.tool

# Get steps for a specific run
RUN_ID="<uuid-from-list>"
curl -s "http://localhost:8002/runs/${RUN_ID}/steps" | python3 -m json.tool
```

### Method 2 — Trigger via Airflow (event-driven, automatic)

When Layer 1 completes a sync, it pushes to Redis. The Airflow DAG `layer2_pipeline` runs every 15 minutes and:
1. Pops from `layer1:sync:complete`
2. Finds all active pipelines for the client
3. Creates one Airflow task per pipeline

**View in Airflow UI:** http://localhost:8080 → DAGs → `layer2_pipeline`

**Manually trigger via Airflow REST API:**
```bash
curl -s -X POST http://localhost:8080/api/v1/dags/layer2_pipeline/dagRuns \
  -H "Content-Type: application/json" \
  -u admin:admin \
  -d '{
    "conf": {
      "client_id": "infracore",
      "batch_id": "<batch_id-from-layer1>",
      "input_path": "<output_path-from-layer1>"
    }
  }' | python3 -m json.tool
```

### Method 3 — Push directly to Redis to simulate Layer 1 event
```bash
docker exec infracore_redis redis-cli LPUSH layer1:sync:complete \
  '{"batch_id":"test001","source_id":"3fa85f64-5717-4562-b3fc-2c963f66afa6","client_id":"infracore","output_path":"infracore/3fa85f64.../2025/04/25/test001.parquet"}'

# Verify it was pushed
docker exec infracore_redis redis-cli LLEN layer1:sync:complete
```

### Where processed data is written
```
MinIO bucket: processed-data
Path pattern: {client_id}/{pipeline_id}/{version}/{YYYY}/{MM}/{DD}/{run_id}.parquet

Example:
  processed-data/infracore/infracore_company_normalize/1.0/2025/04/25/ab12cd34ef56.parquet
```

---

## 8. HOW TO VERIFY OUTPUT

### Read raw Parquet (Layer 1 output)
```python
# Python
import io
from minio import Minio
import pyarrow.parquet as pq

client = Minio("localhost:9000", access_key="infracore_minio",
               secret_key="infracore_minio_secret", secure=False)

object_path = "infracore/<source_id>/2025/04/25/<batch_id>.parquet"
response = client.get_object("raw-data", object_path)
data = response.read()
response.close()

table = pq.read_table(io.BytesIO(data))
df = table.to_pandas()
print(df.head())
print(f"Rows: {len(df)}, Columns: {list(df.columns)}")

# Check Parquet metadata (Infracore injects this)
print(table.schema.metadata)
# Keys: infracore_uploaded_at, infracore_record_count, infracore_columns,
#       satorix_batch_id, satorix_source_id, satorix_client_id
```

```bash
# CLI — list all raw files
docker exec infracore_minio_init mc ls myminio/raw-data --recursive

# CLI — copy a file out of MinIO
docker exec infracore_minio_init mc cp myminio/raw-data/infracore/.../abc.parquet /tmp/abc.parquet
# Then on host: python3 -c "import pandas as pd; print(pd.read_parquet('/tmp/abc.parquet'))"
```

### Read processed Parquet (Layer 2 output)
```python
# Same pattern, different bucket:
response = client.get_object("processed-data", object_path)
```

### Check PostgreSQL for sync and run state
```bash
# Connect
docker exec -it infracore_postgres psql -U infracore -d infracore

# Layer 1: all sync runs
SELECT source_id, sync_type, status, records_extracted, output_path, started_at
FROM sync_runs
ORDER BY started_at DESC
LIMIT 10;

# Layer 2: pipeline runs
SELECT run_id, status, records_input, records_output, records_failed, duration_seconds, output_path
FROM pipeline_runs
ORDER BY started_at DESC
LIMIT 10;

# Layer 2: step-level detail
SELECT step_id, transform_type, status, records_in, records_out, error_message
FROM pipeline_step_runs
WHERE run_id = '<run-uuid>'
ORDER BY started_at;

# Layer 3: ontology objects
SELECT object_type, COUNT(*) FROM ontology_objects WHERE is_deleted = FALSE GROUP BY object_type;

# Layer 3: recent events
SELECT object_type, object_id, event_type, property_name, old_value, new_value, occurred_at
FROM ontology_events
ORDER BY occurred_at DESC
LIMIT 20;

# Layer 3: audit log
SELECT actor_id, operation, object_type, object_id, timestamp
FROM ontology_audit_log
ORDER BY timestamp DESC
LIMIT 20;
```

### Verify ontology objects (Layer 3)
```bash
# List all companies
curl -s "http://localhost:8003/objects/company?limit=10" | python3 -m json.tool

# Get a specific company
curl -s "http://localhost:8003/objects/company/L45201MH2003PLC142301" | python3 -m json.tool

# Search across all types
curl -s "http://localhost:8003/search?q=Infracore" | python3 -m json.tool

# Get risk score
curl -s "http://localhost:8003/intelligence/risk/company/L45201MH2003PLC142301" | python3 -m json.tool

# Get graph network (2 hops)
curl -s "http://localhost:8003/graph/network/company/L45201MH2003PLC142301?depth=2" | python3 -m json.tool

# Verify Neo4j has nodes
curl -s -X POST http://localhost:7474/db/neo4j/tx/commit \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic bmVvNGo6aW5mcmFjb3JlMTIz" \
  -d '{"statements":[{"statement":"MATCH (n) RETURN labels(n)[0] as type, count(*) as cnt ORDER BY cnt DESC"}]}' \
  | python3 -m json.tool

# Verify Elasticsearch indices
curl -s "http://localhost:9200/_cat/indices/ontology_*?v"
```

### What correct Layer 3 output looks like

After ingesting the sample company CSV:

```bash
curl -s "http://localhost:8003/objects/company/L45201MH2003PLC142301" | python3 -m json.tool
```
```json
{
  "cin": "L45201MH2003PLC142301",
  "companyName": "Infracore Systems Ltd",
  "registeredState": "Maharashtra",
  "status": "Active",
  "riskScore": 15,
  "riskFlags": [],
  "_version": 1,
  "_updated_at": "2025-04-25T10:05:00Z"
}
```

```bash
curl -s "http://localhost:8003/intelligence/risk/company/L17110GJ1996PLC029747" | python3 -m json.tool
```
```json
{
  "object_type": "company",
  "primary_key": "L17110GJ1996PLC029747",
  "risk_score": 55,
  "risk_band": "MEDIUM",
  "risk_flags": ["CIRP_ACTIVE"],
  "color": "orange"
}
```

---

## 9. END-TO-END TEST FLOW (COMPLETE)

This runs the full pipeline: CSV → Layer 1 → MinIO → Layer 2 → MinIO → Layer 3 → Intelligence APIs.

### Step 1 — Create input data
```bash
cat > /tmp/test_companies.csv << 'EOF'
CIN,CompanyName,DateOfIncorporation,RegisteredState,Status,AuthorizedCapital
L45201MH2003PLC142301,Infracore Systems Ltd,15/01/2003,Maharashtra,Active,50000000
L17110GJ1996PLC029747,Gujarat Textiles Ltd,01/04/1996,Gujarat,UnderCIRP,100000000
U72900DL2010PTC198765,TechBridge Solutions Pvt Ltd,22/03/2010,Delhi,Active,10000000
EOF

cat > /tmp/test_directors.csv << 'EOF'
DIN,DirectorName,DateOfBirth,Nationality,DisqualificationStatus,AssociatedCIN
00112233,Rajesh Kumar Sharma,15/06/1970,Indian,None,L45201MH2003PLC142301
00445566,Victor Fernandes,28/09/1965,British,None,L45201MH2003PLC142301
00778899,Priya Mehta,10/12/1980,Indian,Disqualified,U72900DL2010PTC198765
EOF
```

### Step 2 — Register sources in Layer 1
```bash
# Register companies source
COMPANY_SOURCE=$(curl -s -X POST http://localhost:8001/api/v1/sources/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Companies CSV",
    "source_type": "csv",
    "client_id": "infracore",
    "config": {"file_path": "/tmp/test_companies.csv", "has_header": true}
  }')
echo $COMPANY_SOURCE | python3 -m json.tool
COMPANY_SOURCE_ID=$(echo $COMPANY_SOURCE | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "Company source ID: $COMPANY_SOURCE_ID"

# Register directors source
DIRECTOR_SOURCE=$(curl -s -X POST http://localhost:8001/api/v1/sources/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Directors CSV",
    "source_type": "csv",
    "client_id": "infracore",
    "config": {"file_path": "/tmp/test_directors.csv", "has_header": true}
  }')
DIRECTOR_SOURCE_ID=$(echo $DIRECTOR_SOURCE | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "Director source ID: $DIRECTOR_SOURCE_ID"
```

### Step 3 — Trigger Layer 1 ingestion
```bash
# Sync companies
COMPANY_RUN=$(curl -s -X POST "http://localhost:8001/api/v1/sync/${COMPANY_SOURCE_ID}/trigger" \
  -H "Content-Type: application/json" \
  -d '{"sync_type": "full"}')
echo $COMPANY_RUN | python3 -m json.tool
COMPANY_PATH=$(echo $COMPANY_RUN | python3 -c "import sys,json; print(json.load(sys.stdin)['output_path'])")
echo "Company Parquet: $COMPANY_PATH"

# Sync directors
DIRECTOR_RUN=$(curl -s -X POST "http://localhost:8001/api/v1/sync/${DIRECTOR_SOURCE_ID}/trigger" \
  -H "Content-Type: application/json" \
  -d '{"sync_type": "full"}')
DIRECTOR_PATH=$(echo $DIRECTOR_RUN | python3 -c "import sys,json; print(json.load(sys.stdin)['output_path'])")
echo "Director Parquet: $DIRECTOR_PATH"
```

### Step 4 — Verify Layer 1 output
```bash
# Confirm status = "completed" and records_extracted = 3
echo $COMPANY_RUN | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d['status'] == 'completed', f\"Expected completed, got {d['status']}\"
assert d['records_extracted'] == 3, f\"Expected 3, got {d['records_extracted']}\"
print('Layer 1 OK: 3 records extracted, status=completed')
"

# Confirm Parquet file exists in MinIO
docker exec infracore_minio_init mc stat myminio/raw-data/${COMPANY_PATH} 2>&1
```

### Step 5 — Register and trigger Layer 2 pipeline
```bash
# Register pipeline
PIPELINE=$(curl -s -X POST http://localhost:8002/pipelines/ \
  -H "Content-Type: application/json" \
  -d "{
    \"pipeline_id\": \"test_company_normalize\",
    \"version\": \"1.0\",
    \"client_id\": \"infracore\",
    \"description\": \"Test pipeline\",
    \"config\": {
      \"pipeline_id\": \"test_company_normalize\",
      \"version\": \"1.0\",
      \"client_id\": \"infracore\",
      \"steps\": [
        {\"step_id\":\"trim\",\"transform_type\":\"trim_whitespace\",\"config\":{\"columns\":\"all\"},\"depends_on\":[]},
        {\"step_id\":\"normalize_cin\",\"transform_type\":\"normalize_cin\",\"config\":{\"column\":\"cin\"},\"depends_on\":[\"trim\"],\"on_error\":\"warn\"},
        {\"step_id\":\"normalize_state\",\"transform_type\":\"normalize_state\",\"config\":{\"column\":\"registeredstate\"},\"depends_on\":[\"normalize_cin\"],\"on_error\":\"warn\"}
      ]
    }
  }")
PIPELINE_DEF_ID=$(echo $PIPELINE | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "Pipeline definition ID: $PIPELINE_DEF_ID"

# Trigger run
curl -s -X POST http://localhost:8002/runs/trigger \
  -H "Content-Type: application/json" \
  -d "{
    \"pipeline_definition_id\": \"${PIPELINE_DEF_ID}\",
    \"input_path\": \"${COMPANY_PATH}\",
    \"triggered_by\": \"manual_test\"
  }" | python3 -m json.tool
```

### Step 6 — Verify Layer 2 output
```bash
# Check recent runs
sleep 5  # pipeline runs in background
curl -s "http://localhost:8002/runs/?limit=3" | python3 -c "
import sys, json
runs = json.load(sys.stdin)
for r in runs:
    print(f\"run={r['run_id']} status={r['status']} in={r['records_input']} out={r['records_output']} failed={r['records_failed']}\")
"

# Confirm processed-data bucket has the output
docker exec infracore_minio_init mc ls myminio/processed-data/infracore/ --recursive
```

### Step 7 — Trigger Layer 3 ingestion
```bash
curl -s -X POST "http://localhost:8003/ingest/trigger" \
  -H "Content-Type: application/json" \
  -d '{"client_id": "infracore"}' | python3 -m json.tool
```

**Expected response:**
```json
{
  "ingest_id": "uuid...",
  "status": "completed",
  "summary": {
    "objects_processed": 3,
    "objects_created": 3,
    "objects_updated": 0,
    "objects_unchanged": 0,
    "links_created": 2,
    "inferred_links_created": 0,
    "alerts_created": 1,
    "risk_scores_updated": 3,
    "errors": [],
    "duration_seconds": 4.2
  }
}
```

### Step 8 — Verify final output
```bash
# Objects in PostgreSQL
docker exec infracore_postgres psql -U infracore -d infracore \
  -c "SELECT object_type, primary_key, properties->>'status', properties->>'riskScore' FROM ontology_objects WHERE is_deleted=FALSE ORDER BY object_type;"

# Company in API
curl -s "http://localhost:8003/objects/company/L45201MH2003PLC142301" | python3 -m json.tool

# Risk score for CIRP company
curl -s "http://localhost:8003/intelligence/risk/company/L17110GJ1996PLC029747" | python3 -m json.tool
# Expected: risk_band = "MEDIUM" or "HIGH", risk_flags contains "CIRP_ACTIVE"

# Disqualified director
curl -s "http://localhost:8003/objects/director/00778899" | python3 -m json.tool
# Expected: disqualificationStatus = "Disqualified"

# Search
curl -s "http://localhost:8003/search?q=Infracore" | python3 -m json.tool

# Timeline for a company (shows all property change events)
curl -s "http://localhost:8003/timeline/company/L45201MH2003PLC142301" | python3 -m json.tool

# Ontology health check
curl -s "http://localhost:8003/health/ontology" | python3 -m json.tool
```

---

## 10. FAILURE TESTING

### Scenario 1 — Missing required column

```bash
# Create a CSV missing the CIN column
cat > /tmp/bad_companies.csv << 'EOF'
CompanyName,DateOfIncorporation,Status
Missing CIN Corp,01/01/2020,Active
EOF

# Register it
BAD_SOURCE_ID=$(curl -s -X POST http://localhost:8001/api/v1/sources/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Bad Companies CSV",
    "source_type": "csv",
    "client_id": "infracore",
    "config": {"file_path": "/tmp/bad_companies.csv", "has_header": true}
  }' | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

# Sync it — Layer 1 succeeds (it just extracts raw data, no schema enforcement)
curl -s -X POST "http://localhost:8001/api/v1/sync/${BAD_SOURCE_ID}/trigger" \
  -H "Content-Type: application/json" \
  -d '{"sync_type": "full"}' | python3 -m json.tool
# status = "completed" — Layer 1 accepts any CSV structure

# Run it through Layer 2 pipeline with normalize_cin step
# The normalize_cin transform will warn "column 'cin' not found" and skip gracefully
# Check step runs: status = "completed" with records_failed > 0 for that step

# Layer 3 ingestion will drop rows without a valid CIN
curl -s -X POST "http://localhost:8003/ingest/trigger" \
  -H "Content-Type: application/json" \
  -d '{"client_id": "infracore"}' | python3 -m json.tool
# Expected: objects_processed = 0 or objects_unchanged = existing count
```

**Where to check:**
```bash
# Layer 2 quarantine / error log
docker exec infracore_postgres psql -U infracore -d infracore \
  -c "SELECT step_id, error_message, error_type FROM pipeline_step_runs WHERE status='failed' ORDER BY started_at DESC LIMIT 5;"

# Layer 2 errors API
curl -s "http://localhost:8002/errors/?limit=10" | python3 -m json.tool
```

### Scenario 2 — Duplicate data (idempotency test)

```bash
# Trigger the same source twice within the same hour
curl -s -X POST "http://localhost:8001/api/v1/sync/${COMPANY_SOURCE_ID}/trigger" \
  -H "Content-Type: application/json" \
  -d '{"sync_type": "full"}' | python3 -m json.tool

# Expected: second call returns the SAME run record with status="completed"
# and a log message: "Skipping sync — batch_id already completed"
# The batch_id is deterministic: SHA-256("{source_id}:full:YYYY-MM-DDTHH")[:16]

# Layer 3 is also idempotent:
curl -s -X POST "http://localhost:8003/ingest/trigger" \
  -H "Content-Type: application/json" \
  -d '{"client_id": "infracore"}' | python3 -m json.tool
# Expected: objects_created = 0, objects_unchanged = N
```

### Scenario 3 — Corrupt / unreadable file

```bash
# Create a non-CSV binary file
dd if=/dev/urandom of=/tmp/corrupt.csv bs=1024 count=1

# Register and sync
CORRUPT_ID=$(curl -s -X POST http://localhost:8001/api/v1/sources/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Corrupt File",
    "source_type": "csv",
    "client_id": "infracore",
    "config": {"file_path": "/tmp/corrupt.csv"}
  }' | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

curl -s -X POST "http://localhost:8001/api/v1/sync/${CORRUPT_ID}/trigger" \
  -H "Content-Type: application/json" \
  -d '{"sync_type": "full"}' | python3 -m json.tool
# Expected: status = "failed", error_details contains the parse error
```

**What should happen:**
- `SyncEngine` catches the exception, sets `run.status = "failed"`, `run.error_details = <error message>`
- `state_manager.mark_failed()` increments `consecutive_failures`
- After 5 consecutive failures, `source.circuit_open = True` — future syncs return HTTP 409

**Where to check:**
```bash
# Check failure in DB
docker exec infracore_postgres psql -U infracore -d infracore \
  -c "SELECT status, error_details, consecutive_failures, circuit_open FROM sync_runs sr JOIN data_sources ds ON sr.source_id = ds.id WHERE ds.name = 'Corrupt File';"

# Open alerts
curl -s "http://localhost:8001/api/v1/health/alerts/open" | python3 -m json.tool
```

### Scenario 4 — Kafka consumer retry

```bash
# Stop the streaming worker
docker compose stop streaming-worker

# Send messages while the worker is down
docker exec infracore_kafka kafka-console-producer.sh \
  --bootstrap-server localhost:9092 --topic infracore.company.events << 'EOF'
{"cin":"L99999MH2020PLC999999","company_name":"Retry Test Corp","timestamp":"2025-04-25T12:00:00Z"}
EOF

# Restart the worker — it will pick up messages from the committed offset
docker compose start streaming-worker
docker compose logs -f streaming-worker
# Expected: consumer starts from last committed offset, processes the missed message
```

**What should happen:** Since `enable_auto_commit=False` and offsets are committed only after successful MinIO upload, the message is guaranteed to be delivered at least once after the worker restarts.

---

## 11. DEBUGGING GUIDE

### Log locations

| Service | How to access |
|---------|--------------|
| Layer 1 API | `docker compose logs -f layer1-api` |
| Layer 2 API | `docker compose logs -f layer2-api` |
| Layer 3 API | `docker compose logs -f layer3-api` |
| Streaming worker | `docker compose logs -f streaming-worker` |
| Airflow webserver | `docker compose logs -f airflow-webserver` |
| Airflow scheduler | `docker compose logs -f airflow-scheduler` |
| Airflow task logs | Airflow UI → DAG → Task → Log tab |
| PostgreSQL | `docker compose logs -f postgres` |

### Enable debug logging
```bash
# In .env:
LOG_LEVEL=DEBUG

# Restart services:
docker compose restart layer1-api layer2-api layer3-api
```

### Common issues and how to detect them

**Problem: Layer 1 sync returns `status: "failed"` with `error_details: "No connector registered for source type"`**
```bash
# Check which connectors are registered
docker exec infracore_layer1_api python3 -c "
from layer1_ingestion.core.config import CONNECTOR_TYPES, _auto_register_connectors
_auto_register_connectors()
print(sorted(CONNECTOR_TYPES.keys()))
"
# Verify the source_type you used matches one of the registered names exactly
```

**Problem: MinIO upload fails — `Connection refused` or `S3Error`**
```bash
# Check MinIO is healthy
curl -s http://localhost:9000/minio/health/live
docker compose ps minio

# Check env vars for the API container
docker exec infracore_layer1_api env | grep MINIO
# Expected: MINIO_ENDPOINT=minio:9000 (inside Docker, host is 'minio', not 'localhost')
```

**Problem: Layer 2 pipeline `status: "failed"` with `Input data could not be loaded`**
```bash
# The input_path does not exist in MinIO
# Verify:
docker exec infracore_minio_init mc stat myminio/raw-data/<your-input-path>

# Common cause: you passed a path from one sync but the file was created by a different sync
# Solution: use the exact output_path from the sync run response
docker exec infracore_postgres psql -U infracore -d infracore \
  -c "SELECT output_path FROM sync_runs WHERE status='completed' ORDER BY started_at DESC LIMIT 5;"
```

**Problem: Layer 3 `/health` shows `"neo4j": "error: ..."`**
```bash
# Neo4j takes ~60s to start fully on first boot
docker compose logs neo4j | tail -20
# Wait for: "Remote interface available at http://localhost:7474/"

# Check Neo4j connectivity
docker exec infracore_neo4j cypher-shell -u neo4j -p infracore123 "RETURN 1"
```

**Problem: Layer 3 `/health` shows `"elasticsearch": "error: ..."`**
```bash
# Elasticsearch takes ~30-60s on first boot (JVM startup)
curl -s http://localhost:9200/_cluster/health
docker compose logs elasticsearch | grep -E "(started|failed|error)"
```

**Problem: Layer 3 ingest returns `objects_created: 0` even with new data**
```bash
# Cause 1: Incremental indexer sees no changes (SHA-256 hash unchanged)
# The ObjectDataFunnel computes a hash of the object's properties.
# If the Parquet data is identical to what's already stored, it skips the write.
# Solution: force a full refresh (requires platform_administrator role)
curl -s -X POST "http://localhost:8003/ingest/full-refresh?confirmed=true&actor_role=platform_administrator" | python3 -m json.tool

# Cause 2: Source files are not in the expected MinIO path prefix
# The BatchIngestor looks in: processed-data/{client_id}/
# Verify:
docker exec infracore_minio_init mc ls myminio/processed-data/infracore/ --recursive
```

**Problem: Airflow DAG `layer2_pipeline` shows tasks stuck in `queued` state**
```bash
# Check worker is up
docker compose logs -f airflow-worker | grep -E "(started|error|celery)"

# Check Redis (Celery broker)
docker exec infracore_redis redis-cli INFO | grep connected_clients

# Check Airflow scheduler
docker compose logs airflow-scheduler | tail -20
```

**Problem: Circuit breaker open — HTTP 409 on sync trigger**
```bash
# A source got 5+ consecutive failures
# Check which source is open
docker exec infracore_postgres psql -U infracore -d infracore \
  -c "SELECT id, name, consecutive_failures, circuit_open FROM data_sources WHERE circuit_open = TRUE;"

# To reset manually:
docker exec infracore_postgres psql -U infracore -d infracore \
  -c "UPDATE data_sources SET circuit_open = FALSE, consecutive_failures = 0 WHERE id = '<source-id>';"
```

**Problem: Redis `layer1:sync:complete` queue is growing — Layer 2 not consuming**
```bash
# Check queue depth
docker exec infracore_redis redis-cli LLEN layer1:sync:complete

# Inspect the items without consuming them
docker exec infracore_redis redis-cli LRANGE layer1:sync:complete 0 4

# Manually trigger Layer 2 for the stuck batches
# (use the Airflow REST API or POST /runs/trigger per the batch payload)
```

**Checking lineage for any entity:**
```bash
curl -s "http://localhost:8002/lineage/entity/company/L45201MH2003PLC142301" | python3 -m json.tool
# Shows which pipelines and transforms produced this entity's data
```

---

## 12. CURRENT LIMITATIONS

### Data size limits

| Limit | Value | Location |
|-------|-------|----------|
| Max batch size warning | 200,000 rows | `layer2_pipeline/core/executor.py:137` — Pandas in-memory limit |
| Max lineage entities per run | 10,000 | `executor.py:362` — capped to avoid OOM |
| API list endpoints | 500 items max | `objects.py` — `limit: int = Query(le=500)` |
| Elasticsearch search | 200 results max | `search.py` — `size: int = Query(le=200)` |
| Neo4j network depth | 3 hops max | `graph.py` — `depth: int = Query(ge=1, le=3)` |
| Sync history returned | 30 runs default | `sync.py:limit=30` |

### Streaming limitations
- Micro-batch window: 1,000 messages or 60 seconds — not configurable at runtime (set via env vars `KAFKA_MAX_BATCH_SIZE`, `KAFKA_MAX_BATCH_SECONDS`)
- Single consumer thread per topic — no parallel partition processing
- No dead-letter queue: malformed JSON messages are logged and discarded (not retried)
- No schema registry integration: all Kafka messages must be raw JSON

### Schema handling gaps
- Layer 1 does not enforce a schema on ingestion — any CSV with any columns will be accepted
- Schema drift is detected (via SHA-256 fingerprint) and logged but does **not** block ingestion
- Layer 3 ingestion skips rows with no valid CIN/DIN primary key silently — errors only appear in `IngestSummary.errors`
- No automatic schema evolution for Neo4j constraints if the ontology schema changes

### Layer 3 intelligence limitations
- Risk scores are computed synchronously on ingest — no background recalculation when related entities change (e.g., adding a new regulatory action does not automatically update the parent company's risk score)
- CIRP contagion risk requires Neo4j OWNS relationships to be established first — running inference before all links are written may produce incomplete results
- Inference engine is not triggered automatically on object write — must call `POST /ingest/trigger` to re-run
- `predictProjectCompletionProbability` queries Neo4j for owner risk scores, which only exist after company risk scoring has run

### Not production-ready
- `API_KEY` in `.env` defaults to empty — auth is bypassed with a warning. **Must be set before any external exposure.**
- Neo4j and Elasticsearch have no authentication (`xpack.security.enabled=false`) — suitable for local dev only
- Airflow webserver runs with `AIRFLOW__WEBSERVER__EXPOSE_CONFIG: 'true'` — exposes connection strings in the UI
- MinIO credentials are hardcoded in docker-compose.yml env block — should move to Docker secrets or Vault in production
- Layer 3 API has no authentication at all — all endpoints are public
- The `ENCRYPTION_KEY` in `.env` is a base64 placeholder — replace with a randomly generated 32-byte key for any real data
- Elasticsearch index mappings are bootstrapped at API startup — no migration path for existing index schema changes
- Audit log retention: the `ontology_audit_log` table has no automatic purge — plan for a scheduled cleanup job for data older than 7 years
