# LAYER 1: FOUNDATION — Data Integration
## Satorix Platform · Specification v2.0

---

## 1. LAYER CONTRACT

### 1.1 Single Responsibility
Layer 1 is the **Extract and Land** layer. Its only job is to move raw data from external sources into the internal data lake with full provenance tracking. It does not transform, clean, enrich, resolve, or store business entities.

**Accepts:** External data sources (databases, files, APIs, webhooks, government portals)
**Produces:** Immutable, compressed, schema-annotated Parquet files in MinIO + sync metadata in PostgreSQL

### 1.2 Hard Boundary Rules

| Rule | Statement | Violation Consequence |
|------|-----------|----------------------|
| R-01 | Raw data lands in MinIO only. PostgreSQL is metadata-only. | Data in PostgreSQL means Layer 2 loses its authoritative source |
| R-02 | Layer 1 does NOT clean data. It profiles and flags only. | Cleaning in L1 corrupts the raw record — Layer 2 loses audit trail |
| R-03 | Layer 1 does NOT write to the Ontology (Layer 3+). | Ontology contamination from unvalidated data |
| R-04 | All credentials encrypted AES-256-GCM before PostgreSQL storage. Never logged. Never decrypted outside SyncEngine scope. | Security breach |
| R-05 | Parquet files are immutable after write. No in-place updates. | Data integrity and audit trail break |
| R-06 | Every extraction must be idempotent per `batch_id`. Re-running the same batch_id must produce the same file at the same path. | Double-write corrupts downstream state |

### 1.3 Output Contract (What Layer 2 Consumes)

Every Layer 1 output MUST conform to this contract. Layer 2 builds against this contract — any deviation is a breaking change.

**File Path Format:**
```
s3://raw-data/{client_id}/{source_id}/{YYYY}/{MM}/{DD}/{batch_id}.parquet
```

**Parquet File Schema Metadata (required KV pairs in PyArrow schema metadata):**
```json
{
  "satorix_layer": "1",
  "client_id": "<uuid>",
  "source_id": "<uuid>",
  "source_type": "<connector_type>",
  "extraction_mode": "full | incremental | webhook",
  "extraction_timestamp_utc": "<ISO8601>",
  "batch_id": "<uuid>",
  "row_count": "<int>",
  "schema_fingerprint": "<sha256 of column name+type list>",
  "watermark_column": "<column_name | null>",
  "watermark_value": "<value | null>",
  "compression": "snappy",
  "quality_score": "<float 0-100 | null if profiling skipped>",
  "has_quality_violations": "<bool>"
}
```

**Completion Event (Layer 1→2 Handoff):**
After each successful sync, Layer 1 writes one record to PostgreSQL `sync_completions` table AND publishes to Redis channel `layer1:sync:complete`:
```json
{
  "event": "sync_complete",
  "batch_id": "<uuid>",
  "client_id": "<uuid>",
  "source_id": "<uuid>",
  "parquet_path": "s3://raw-data/...",
  "row_count": "<int>",
  "schema_fingerprint": "<sha256>",
  "quality_score": "<float>",
  "timestamp_utc": "<ISO8601>"
}
```
Layer 2 subscribes to `layer1:sync:complete` to trigger pipeline execution. This is the ONLY handoff mechanism. File system polling is prohibited.

---

## 2. POSTGRESQL METADATA SCHEMA

PostgreSQL stores ONLY these four table families. Nothing else.

### 2.1 `data_sources` — Source Registry
```sql
CREATE TABLE data_sources (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id       UUID NOT NULL,
    name            VARCHAR(255) NOT NULL,
    source_type     VARCHAR(50) NOT NULL,   -- 'csv', 'postgresql', 'mca21', etc.
    config          JSONB NOT NULL,          -- Non-sensitive config only
    credentials     TEXT NOT NULL,          -- AES-256-GCM encrypted blob
    is_active       BOOLEAN DEFAULT TRUE,
    is_deleted      BOOLEAN DEFAULT FALSE,  -- Soft delete — never hard delete
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
```

### 2.2 `sync_states` — Watermark Tracking
```sql
CREATE TABLE sync_states (
    source_id           UUID PRIMARY KEY REFERENCES data_sources(id),
    last_watermark      TEXT,               -- Last cursor value (timestamp, sequence, etc.)
    watermark_type      VARCHAR(30),        -- 'timestamp' | 'sequence' | 'cdc_offset' | 'full_refresh'
    last_sync_batch_id  UUID,
    last_sync_at        TIMESTAMPTZ,
    last_row_count      INTEGER,
    last_schema_fp      VARCHAR(64)         -- sha256 of last known schema fingerprint
);
```

### 2.3 `sync_runs` — Execution History
```sql
CREATE TABLE sync_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id       UUID NOT NULL REFERENCES data_sources(id),
    batch_id        UUID NOT NULL UNIQUE,   -- Idempotency key
    status          VARCHAR(20) NOT NULL,   -- 'running' | 'complete' | 'failed' | 'partial'
    extraction_mode VARCHAR(20) NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL,
    completed_at    TIMESTAMPTZ,
    row_count       INTEGER,
    parquet_path    TEXT,
    error_type      VARCHAR(50),            -- Typed exception class name
    error_message   TEXT,
    retry_count     INTEGER DEFAULT 0
);
```

### 2.4 `source_health` — Connection Monitoring
```sql
CREATE TABLE source_health (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id       UUID NOT NULL REFERENCES data_sources(id),
    checked_at      TIMESTAMPTZ NOT NULL,
    is_reachable    BOOLEAN NOT NULL,
    latency_ms      INTEGER,
    schema_changed  BOOLEAN DEFAULT FALSE,
    schema_diff     JSONB,                  -- {added: [], removed: [], renamed: []}
    alert_fired     BOOLEAN DEFAULT FALSE
);
```

---

## 3. CONNECTOR ARCHITECTURE

### 3.1 BaseConnector Contract

Every pull-based connector MUST implement this interface exactly. No connector may add public methods not defined here.

```python
from abc import ABC, abstractmethod
from typing import Iterator
import pandas as pd
from dataclasses import dataclass

@dataclass
class ExtractionConfig:
    source_id: str
    client_id: str
    batch_id: str
    mode: str                    # 'full' | 'incremental'
    watermark_column: str | None
    last_watermark: str | None
    chunk_size: int = 50_000     # rows per chunk

@dataclass
class ExtractionChunk:
    data: pd.DataFrame
    chunk_index: int
    row_count: int
    max_watermark: str | None    # highest watermark value in this chunk

class BaseConnector(ABC):

    @abstractmethod
    def test_connection(self) -> bool:
        """Verify connectivity. Raises ConnectionError or AuthenticationError."""

    @abstractmethod
    def detect_schema(self) -> dict:
        """Return column name → inferred type mapping. No data extraction."""

    @abstractmethod
    def extract_full(self, config: ExtractionConfig) -> Iterator[ExtractionChunk]:
        """Yield chunks of the full dataset. Never materialize entire dataset in RAM."""

    @abstractmethod
    def extract_incremental(self, config: ExtractionConfig) -> Iterator[ExtractionChunk]:
        """Yield only records modified since last_watermark. Raises if watermark_column is None."""

    def compute_checksum(self, df: pd.DataFrame) -> str:
        """SHA-256 of sorted column names + dtypes. Default impl provided."""
        import hashlib, json
        schema = sorted([(c, str(t)) for c, t in zip(df.columns, df.dtypes)])
        return hashlib.sha256(json.dumps(schema).encode()).hexdigest()
```

**Critical:** `extract_full` and `extract_incremental` MUST be generators (`Iterator[ExtractionChunk]`). Loading an entire table into RAM is a prohibited implementation pattern.

### 3.2 Exception Taxonomy

All connector exceptions inherit from `SatorixConnectorError`. No connector may raise bare Python exceptions.

```
SatorixConnectorError
├── ConnectionError         — Network unreachable, DNS failure, timeout
├── AuthenticationError     — Invalid credentials, token expired, IP not whitelisted
├── SchemaError             — Source schema changed, column missing, type mismatch
├── ExtractionError         — Data read failed mid-stream, cursor lost, query timeout
├── RateLimitError          — API quota exceeded (include retry_after_seconds attribute)
└── PartialExtractionError  — Extraction succeeded for N of M chunks (include completed_chunks)
```

`PartialExtractionError` is critical for large dataset recovery: the SyncEngine must checkpoint completed chunks to MinIO before raising, so re-runs resume from the failed chunk index, not from zero.

### 3.3 WebhookReceiver — Not a Connector

`WebhookReceiver` is a separate class hierarchy. It is a push-based receiver, not a pull-based connector.

```
WebhookReceiver
├── test_connection()     → NOT DEFINED (webhooks are push — no outbound connection to test)
├── extract_full()        → NOT DEFINED (no historical backfill)
├── receive(payload)      → validates, deserializes, and queues payload
└── get_schema_hint()     → returns known schema if pre-configured, else None
```

Health monitoring for WebhookReceivers uses **liveness timeout** (alert if no event received in N hours), not connectivity ping.

Registry behavior: WebhookReceiver sources have `source_type = 'webhook'` and `extraction_mode = 'push'` in their sync_state. Their `sync_states.watermark_type = 'event_id'`.

### 3.4 Connector Registry

| Connector | Class | Mode | Incremental Strategy |
|-----------|-------|------|---------------------|
| `csv` | CSVConnector | pull | full-refresh-dedup (no native cursor) |
| `excel` | ExcelConnector | pull | full-refresh-dedup |
| `pdf` | PDFConnector | pull | full-refresh (binary files — no cursor) |
| `postgresql` | PostgreSQLConnector | pull | timestamp or sequence |
| `mysql` | MySQLConnector | pull | timestamp (LIMIT/OFFSET — no server cursor) |
| `rest_api` | RESTAPIConnector | pull | timestamp or page cursor |
| `google_sheets` | GoogleSheetsConnector | pull | full-refresh-dedup |
| `s3` | S3Connector | pull | modified-time |
| `sftp` | SFTPConnector | pull | modified-time |
| `webhook` | WebhookReceiver | push | event_id |
| `mca21` | MCA21Connector | pull | bulk-download + delta |
| `sebi` | SEBIConnector | pull | publication-date |
| `rbi` | RBIConnector | pull | publication-date |
| `tally` | TallyConnector | pull | voucher-sequence |

---

## 4. SYNC ENGINE — EXECUTION PROTOCOL

### 4.1 Execution Sequence (Pull Mode)

```
1. LOCK:         Acquire advisory lock on source_id (prevent concurrent runs)
2. RESOLVE:      Decrypt credentials, instantiate connector
3. SCHEMA CHECK: detect_schema() → compare against last_schema_fp
                 If schema_changed: write to source_health, trigger SchemaChangeAlert
                 If new columns added: proceed (additive — safe)
                 If columns removed: write PartialSchemaError, halt (breaking change)
4. EXTRACT:      Call extract_full() or extract_incremental() → Iterator[ExtractionChunk]
5. PER CHUNK:
   a. Profile:   Run DataProfiler on chunk (completeness, Indian identifier detection)
   b. Upload:    storage.upload_parquet_chunk(chunk, path, append=True)
   c. Checkpoint: Update sync_runs.row_count += chunk.row_count
   d. Update:    Update sync_states.last_watermark = max(chunk.max_watermark)
6. FINALIZE:     Mark sync_runs.status = 'complete', write sync_completions record
7. PUBLISH:      Redis PUBLISH layer1:sync:complete <event_json>
8. RELEASE:      Release advisory lock
```

### 4.2 Failure & Recovery Protocol

| Failure Point | Recovery Action |
|--------------|----------------|
| Pre-extraction | Mark sync_run 'failed'. No MinIO write. Retry from scratch. |
| Mid-extraction (chunk N fails) | Mark sync_run 'partial'. Chunks 0..N-1 preserved in MinIO. Retry resumes from chunk N via checkpoint. |
| MinIO write failure | Retry chunk upload 3× with exponential backoff. If all fail: PartialExtractionError. |
| Redis publish failure | Log warning only. Layer 2 also polls sync_completions table as fallback. |
| Advisory lock timeout | Skip run. Log. Next scheduled run will execute normally. |

### 4.3 Idempotency Guarantee

`batch_id` is generated deterministically: `SHA-256(source_id + extraction_date + run_sequence)`. If a sync_run record with `batch_id` exists and `status = 'complete'`, the SyncEngine exits immediately without re-extraction. This guarantees at-most-once-per-batch delivery at the MinIO layer.

### 4.4 Schema Evolution Handling

| Change Type | Classification | Action |
|-------------|---------------|--------|
| New column added | Additive | Proceed. New column appears in Parquet. Layer 2 handles gracefully. |
| Column removed | Breaking | Halt extraction. Raise SchemaError. Fire alert. Require manual acknowledgment. |
| Column renamed | Breaking (treat as remove+add) | Halt. Alert. |
| Type widened (int→float) | Additive | Proceed with warning. |
| Type narrowed (float→int) | Breaking | Halt. Alert. |

---

## 5. INDIAN-SPECIFIC PRIMITIVES

These are non-negotiable from Day 1. They cannot be retrofitted — they affect Parquet schema metadata.

### 5.1 Identifier Formats and Validators

```python
# CIN: [UL][0-9]{5}[A-Z]{2}[0-9]{4}[A-Z]{3}[0-9]{6}
# Components: listing_status | NIC_code(5) | state_code(2) | incorporation_year(4) | company_type(3) | seq(6)
CIN_PATTERN = r'^[UL][0-9]{5}[A-Z]{2}[0-9]{4}[A-Z]{3}[0-9]{6}$'

# GSTIN: state_code(2) | PAN(10) | entity_number(1) | Z | checksum(1)
GSTIN_PATTERN = r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$'
# Validation: GSTIN checksum uses Luhn-variant; extract and cross-validate PAN component

# DIN: exactly 8 digits
DIN_PATTERN = r'^[0-9]{8}$'

# PAN: [A-Z]{5}[0-9]{4}[A-Z]
PAN_PATTERN = r'^[A-Z]{5}[0-9]{4}[A-Z]$'

# IFSC: [A-Z]{4}0[A-Z0-9]{6}
IFSC_PATTERN = r'^[A-Z]{4}0[A-Z0-9]{6}$'
```

Auto-detection: `indian_identifiers.py` scans every string column on first extraction. If ≥70% of non-null values match a known pattern, the column is tagged with `satorix_semantic_type` in Parquet metadata.

### 5.2 Number Formats

```python
# Input variations all resolve to float (rupees, never lakhs/crores)
"₹1,24,50,000"  → 12450000.0
"₹1.2Cr"        → 12000000.0
"₹45L"          → 4500000.0
"1,24,500"      → 124500.0   # Indian lakh separator
"12,000"        → 12000.0    # Ambiguous — treat as Indian (safe default)
```

All monetary values stored as `float64` in rupees. No intermediate lakh/crore representation in Parquet.

### 5.3 Date Formats

All dates normalized to ISO 8601 (`YYYY-MM-DD`) in Parquet. Indian financial year computed and stored as a separate column alongside every date column detected as a business date.

```python
# Accepted input formats:
# DD/MM/YYYY, DD-MM-YYYY, YYYY-MM-DD, DD.MM.YYYY
# "15th March 2024", "Mar 15, 2024", "15-Mar-24"
# "Q3 FY2024" → {start: "2023-10-01", end: "2023-12-31"}
# Financial year computation: April 1 = FY start
# April 2023 → April 2024 = FY2024
```

### 5.4 14 Consistency Rules (Profiler — detect only, never mutate)

| Rule ID | Rule | Severity |
|---------|------|----------|
| IN-01 | PaidUpCapital ≤ AuthorizedCapital | HIGH |
| IN-02 | IncorporationDate ≤ today | HIGH |
| IN-03 | CessationDate > AppointmentDate | HIGH |
| IN-04 | Director max 20 active company directorships (MCA Sec 165) | HIGH |
| IN-05 | GSTIN state_code matches registered_address state | HIGH |
| IN-06 | CurrentRatio > 0 | MEDIUM |
| IN-07 | DSCR < 0.8 → flag as critical stress indicator | HIGH |
| IN-08 | CIN incorporation_year ≤ current year | HIGH |
| IN-09 | DIN is 8 digits exactly | MEDIUM |
| IN-10 | PAN embedded in GSTIN matches standalone PAN field | HIGH |
| IN-11 | RevenueFromOperations > 0 for active companies | MEDIUM |
| IN-12 | NetWorth > 0 unless under CIRP/winding-up | MEDIUM |
| IN-13 | ProjectCompletionDate > ProjectStartDate | MEDIUM |
| IN-14 | RPT value < 10% of consolidated turnover (threshold flag) | HIGH |

---

## 6. DATA PROFILING

Profiling runs **per chunk** during extraction, not post-load. Results accumulate into a `ProfileReport` stored in MinIO at:
```
s3://profiling-reports/{client_id}/{source_id}/{batch_id}/profile.json
```

Profiling is **read-only** — it annotates, never mutates.

### Profile Report Schema
```json
{
  "batch_id": "<uuid>",
  "source_id": "<uuid>",
  "row_count": 0,
  "quality_score": 0.0,
  "columns": {
    "<column_name>": {
      "null_rate": 0.0,
      "unique_count": 0,
      "top_values": [],
      "detected_type": "<string|numeric|date|identifier>",
      "satorix_semantic_type": "<CIN|GSTIN|DIN|PAN|IFSC|INR|IndianDate|null>",
      "anomaly_count": 0,
      "anomaly_method": "<zscore|iqr|null>"
    }
  },
  "consistency_violations": [
    {"rule_id": "IN-01", "count": 0, "sample_row_ids": []}
  ],
  "schema_fingerprint": "<sha256>"
}
```

Quality score formula: `(1 - weighted_null_rate) × (1 - consistency_violation_rate) × 100`

---

## 7. HEALTH MONITORING

### 7.1 Connection Health Monitor

Runs every 15 minutes via Airflow `health_check_dag.py`. Tests all active sources.

For pull-based connectors: calls `test_connection()` → records latency, updates `source_health`.
For WebhookReceiver sources: checks `time_since_last_event` against configured `liveness_timeout`.

### 7.2 Seven Alert Types

| Alert ID | Trigger | Severity |
|----------|---------|---------|
| ALT-01 | Source unreachable for 3+ consecutive checks | CRITICAL |
| ALT-02 | Authentication failure | CRITICAL |
| ALT-03 | Schema breaking change detected | HIGH |
| ALT-04 | Quality score dropped > 15 points vs. prior batch | HIGH |
| ALT-05 | Sync duration exceeded 3× rolling average | MEDIUM |
| ALT-06 | Data freshness SLA breached (no sync in N hours) | HIGH |
| ALT-07 | Downstream impact: N Layer 2 pipelines blocked | HIGH |

Alerts are stored in `source_health.alert_fired = TRUE` and published to Redis channel `layer1:alerts`.

---

## 8. STORAGE ARCHITECTURE

### 8.1 MinIO Bucket Layout

```
raw-data/                           ← Immutable raw Parquet (Layer 1 writes)
  {client_id}/
    {source_id}/
      {YYYY}/{MM}/{DD}/
        {batch_id}.parquet          ← Primary data file
        {batch_id}.metadata.json    ← Mirrors Parquet schema metadata as JSON (for inspection)

profiling-reports/                  ← Profile JSON per batch (Layer 1 writes)
  {client_id}/
    {source_id}/
      {batch_id}/
        profile.json

processed-data/                     ← Layer 2 writes here (Layer 1 never touches)
```

### 8.2 Parquet Configuration

- Compression: `snappy` (fast decompression for Layer 2 reads)
- Row group size: 50,000 rows (matches ExtractionChunk default)
- File format: Parquet v2
- Null encoding: explicit null (not empty string)

---

## 9. INFRASTRUCTURE

### 9.1 Docker Services

| Service | Image | Port | Role |
|---------|-------|------|------|
| `infracore_postgres` | postgres:15 | 5432 | Metadata store |
| `infracore_minio` | minio/minio:latest | 9000 (API), 9001 (console) | Raw data lake |
| `infracore_redis` | redis:7-alpine | 6379 | Airflow broker + Layer 1→2 event bus |
| `infracore_airflow_webserver` | apache/airflow:2.7.3 | 8080 | Orchestration UI |
| `infracore_airflow_scheduler` | apache/airflow:2.7.3 | — | DAG execution |
| `infracore_layer1_api` | python:3.11-slim (custom) | 8001 | Control plane |

### 9.2 Airflow DAGs

| DAG | Schedule | Purpose |
|-----|----------|---------|
| `mca21_daily_sync` | `0 2 * * *` | MCA21 bulk download. Quality gate: score < 70 = fail |
| `client_excel_sync` | `0 6 * * *` | Client file syncs |
| `health_check_dag` | `*/15 * * * *` | Connection health for all active sources |
| `layer1_generic_sync` | Triggered | One-off and manual sync execution |

### 9.3 Airflow–API Decoupling (Required)

Airflow DAGs MUST NOT import from `layer1_ingestion` directly. DAGs call the Layer 1 API via HTTP:

```python
# CORRECT — Airflow DAG
from airflow.providers.http.operators.http import SimpleHttpOperator
trigger_sync = SimpleHttpOperator(
    task_id='trigger_sync',
    method='POST',
    http_conn_id='layer1_api',
    endpoint=f'/api/v1/sync/{source_id}/trigger',
    headers={"Content-Type": "application/json"},
)

# PROHIBITED — Airflow DAG
from layer1_ingestion.sync.sync_engine import SyncEngine  # DO NOT DO THIS
```

This decoupling allows independent deployment and scaling of the Airflow and API containers.

---

## 10. PERFORMANCE REQUIREMENTS

| Operation | Requirement | Enforcement |
|-----------|-------------|-------------|
| CSV/Excel extraction | 500K rows in < 60 seconds | Phase 5 test |
| Database streaming | Server-side cursor mandatory; no full-table `SELECT *` in RAM | Code review |
| Parquet write throughput | ≥ 100K rows/second | Phase 5 test |
| Profile report | < 30 seconds for datasets up to 1M rows | Phase 5 test |
| Health check per source | < 5 seconds per source | Airflow task timeout |
| API response (all endpoints) | < 500ms P95 | Monitoring |

---

## 11. SECURITY CONSTRAINTS

- Credentials: AES-256-GCM encrypted. Key stored in env var `ENCRYPTION_KEY` (32-byte base64). Never derive from password.
- Logging: Never log credentials, decrypted values, PII, or Parquet data contents. Log only: source_id, batch_id, row_count, status, error_type.
- API auth: All `/api/v1/` endpoints require `Authorization: Bearer <token>`. UUID-guessing is not an access control mechanism.
- MinIO access: Layer 1 API has read+write on `raw-data` and `profiling-reports`. Read-only on `processed-data`. No cross-client access.
- Soft deletes only: `data_sources.is_deleted = TRUE`. Hard deletes prohibited. Audit trail must be permanent.

---

## 12. TESTING PROTOCOL

### Phase 1 — Infrastructure
- All 6 Docker containers show `Up` and pass health checks
- 4 PostgreSQL tables exist with correct schemas
- 3 MinIO buckets exist: `raw-data`, `processed-data`, `profiling-reports`
- Redis responds to `PING`
- API `/docs` loads at http://localhost:8001/docs
- Redis pub/sub functional: publish test event, confirm receipt

### Phase 2 — Unit Tests
- Indian identifier validation: CIN, DIN, GSTIN, PAN, IFSC — valid and invalid cases
- Number parser: ₹1,24,50,000 → 12450000.0, ₹1.2Cr → 12000000.0
- Date parser: all 8 format variants → ISO 8601
- Consistency rules: all 14 rules fire on crafted violations
- Encryption: roundtrip encrypt→decrypt, tamper detection raises ValueError
- Idempotency: duplicate batch_id → no re-extraction

### Phase 3 — Integration Tests
- CSV → DataFrame chunks → Parquet → MinIO → metadata in PostgreSQL roundtrip
- Connector registration with encrypted credentials → test_connection() passes
- Schema change detection: alter source schema, confirm SchemaError raised and alert fired
- Redis event published after successful sync

### Phase 4 — Real Data Tests
- All 9 Infracore mock CSV files register and sync
- CIN column auto-detected with `satorix_semantic_type = 'CIN'`
- Quality score computed correctly
- consistency_violation for IN-04 fires (Ramesh Bhatia disqualification)

### Phase 5 — Failure & Performance Tests
- Unreachable source: typed `ConnectionError`, graceful response, alert fired, no crash
- Empty file: 0 rows, valid Parquet with schema metadata, quality_score = 100.0
- 100,000 row file: completes in < 60 seconds
- Mid-extraction failure simulation: partial chunks preserved, run marked 'partial', retry resumes from checkpoint
- Concurrent sync of same source: advisory lock prevents second run

---

*Specification version: 2.0*
*Layer: 1 — Foundation / Data Integration*
*Status: Complete (implementation) | v2.0 (specification)*
*Supersedes: Layer 1 section in claude.md v1.0*
