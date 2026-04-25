# CLAUDE.md — Satorix Project Intelligence File

> This file is the single source of truth for Claude Code working on this project.
> Read this entire file before touching any code, any file, or any configuration.
> Every architectural decision documented here was made deliberately. Do not override without understanding why.

---

## PROJECT IDENTITY

**Project Name:** Satorix
**Tagline:** India's First Sovereign Operational Intelligence Platform
**Vision:** A Palantir Foundry equivalent — built for India, owned by India
**Domain:** Corporate and infrastructure intelligence for Indian enterprise clients
**Stage:** Layer 1 complete. Layer 2 in progress. Layers 3-10 designed.
**Started:** February 2026 (internship project, now company-backed)

---

## THE ORIGIN STORY (Read This First)

This project started as a question: "Can AI solve political capital and regulatory navigation?" That question evolved through a series of conversations into the realization that the real gap in India is not AI for politics — it is **operational intelligence infrastructure** for Indian enterprise, equivalent to what Palantir Foundry does globally.

The pivot was critical: from a political intelligence tool (too ethically complex, too data-sparse) to a **corporate due diligence and infrastructure intelligence platform** built on publicly available Indian data (MCA21, SEBI, IBBI, RBI, GeM, Gazette).

The project was named Satorix. The platform architecture was modeled directly on Palantir Foundry's ten-layer structure, studied from Palantir's official documentation — not blog posts or third-party descriptions.

---

## WHY PALANTIR CANNOT WORK IN INDIA (The Core Market Thesis)

Palantir is a $477 billion company with virtually no operational presence in India. This is not a sales failure — it is a structural impossibility:

1. **Data sovereignty** — Palantir is US-origin, CIA-funded, proprietary closed-source code. DPDP Act 2023, RBI, SEBI, and IRDAI data localization requirements make it legally untenable for Indian enterprises to use.

2. **Vendor lock-in** — Data exists in Palantir's proprietary format. No exit path. No third-party extensions. Monopolistic pricing on renewals.

3. **Price exclusion** — Palantir minimum contract: ₹15-50 Cr annually. 99% of India's enterprise market is excluded.

4. **Zero India-native connectors** — No Tally connector. No MCA21 parser. No SEBI EDGAR integration. No GST connector. No understanding of CIN, DIN, GSTIN, IFSC formats.

5. **No India-domain intelligence** — No pre-built models for NHAI concessions, NCLT proceedings, RBI NBFC compliance, Indian corporate governance patterns.

Satorix addresses all five gaps simultaneously.

---

## THE GOVERNMENT MANDATE

The Indian government has already validated this category:

- **IndiaAI Mission** (March 2024): ₹10,371.92 Cr approved over 5 years for sovereign AI infrastructure
- **WiredLeap IRIS** (March 2026): Deployed across Bangalore, Karnataka, Bhubaneswar — described as "India's Palantir" for public safety
- **DefTech India Mission** (proposed under PMO): Multi-year government contracts for Indian-built intelligence platforms
- **China's Deepexi IPO** (October 2025): 7,500x oversubscribed — triggered direct policy response in India asking "where is India's Palantir?"
- **AIKosh Platform**: 5,500+ datasets across 20 sectors — the data foundation Satorix sits on top of

---

## WHAT SATORIX IS (Precise Technical Definition)

Satorix is an **ontology-driven operational intelligence platform** that:

1. Deploys **inside** a client's own infrastructure (data never leaves client environment)
2. Connects all their fragmented data sources (Tally, PostgreSQL, Excel, APIs, PDFs, MCA21, SEBI)
3. Builds a living semantic knowledge graph (the Ontology) of their world
4. Computes intelligence: risk scores, entity networks, regulatory exposure, anomaly flags
5. Delivers intelligence to business decision-makers without requiring data scientists or IT teams

**Critical distinction:** Satorix is NOT a dashboard tool, NOT a BI tool, NOT a data warehouse. It is an **Operational Intelligence Operating System** — the connective tissue between raw data and consequential decisions.

---

## THE TEN-LAYER ARCHITECTURE

Every layer maps directly to a Palantir Foundry equivalent. Do not collapse layers. Do not merge responsibilities across layers. Each layer has a single job.

```
LAYER 1  — Data Integration        (Palantir: Data Connection)          STATUS: COMPLETE
LAYER 2  — Data Pipeline           (Palantir: Pipeline Builder)          STATUS: IN PROGRESS
LAYER 3  — Ontology                (Palantir: Ontology Manager)          STATUS: DESIGNED
LAYER 4  — Graph Intelligence      (Palantir: Graph Analytics)           STATUS: DESIGNED
LAYER 5  — Analytics and AI        (Palantir: Quiver / AIP)             STATUS: DESIGNED
LAYER 6  — Application             (Palantir: Workshop / Slate)          STATUS: DESIGNED
LAYER 7  — Action                  (Palantir: Action Types)              STATUS: DESIGNED
LAYER 8  — Security                (Palantir: Security Model)            STATUS: DESIGNED
LAYER 9  — Deployment              (Palantir: Apollo)                    STATUS: DESIGNED
LAYER 10 — Collaboration           (Palantir: Collaboration)             STATUS: DESIGNED
```

**The most important architectural rule:** Layer 1 does not clean data. Layer 2 does not store data. Layer 3 does not compute intelligence. Each layer's responsibility is strictly bounded. Violations create cascading failures.

---

## LAYER 1: DATA INTEGRATION — COMPLETE

### What It Does
Connects to data sources, extracts raw data incrementally, lands it in MinIO as Parquet files, profiles data quality, monitors connection health. Nothing else.

### File Structure
```
infracore_foundry/
├── docker-compose.yml              # 6 services: postgres, minio, redis, airflow-web, airflow-scheduler, layer1-api
├── .env                            # All environment variables
├── requirements.txt                # All pinned dependencies
└── layer1_ingestion/
    ├── core/
    │   ├── config.py               # Pydantic BaseSettings, lru_cache, all env vars
    │   ├── encryption.py           # AES-256-GCM for credential storage
    │   ├── storage.py              # MinIO client wrapper, upload/download Parquet
    │   └── database.py             # SQLAlchemy async engine, PostgreSQL
    ├── connectors/
    │   ├── base_connector.py       # Abstract base — ALL connectors inherit this
    │   ├── csv_connector.py        # CSV/TSV, BOM handling, Indian number formats
    │   ├── excel_connector.py      # Excel with merged cells, multi-headers, formulas
    │   ├── pdf_connector.py        # Digital (pdfplumber) + scanned (Tesseract OCR)
    │   ├── postgresql_connector.py # Server-side cursors, timestamp/sequence incremental
    │   ├── mysql_connector.py      # MySQL-specific (LIMIT/OFFSET, utf8mb4, no RETURNING)
    │   ├── rest_api_connector.py   # 5 auth methods, 5 pagination strategies, rate limiting
    │   ├── google_sheets_connector.py
    │   ├── sftp_connector.py
    │   ├── s3_connector.py
    │   ├── webhook_connector.py    # NOT a BaseConnector subclass — it is a WebhookReceiver
    │   └── indian/
    │       ├── mca21_connector.py  # Bulk download + Sandbox.co.in API + Redis cache
    │       ├── sebi_connector.py   # SEBI EDGAR enforcement orders scraper
    │       ├── rbi_connector.py    # RBI statistical releases parser
    │       └── tally_connector.py  # TallyPrime XML server + offline export
    ├── sync/
    │   ├── sync_engine.py          # Core sync orchestrator
    │   ├── incremental.py          # Timestamp, sequence, CDC, full-refresh-dedup
    │   ├── state_manager.py        # Sync state persistence
    │   └── batch_processor.py      # Chunked extraction
    ├── schema/
    │   ├── detector.py             # Auto schema detection
    │   ├── normalizer.py           # Field name normalization
    │   ├── type_inferrer.py        # Data type inference
    │   └── indian_identifiers.py   # CIN, DIN, GSTIN, PAN, IFSC, PIN validators
    ├── profiling/
    │   ├── profiler.py             # Main DataProfiler, produces ProfileReport
    │   ├── completeness.py         # Null/missing analysis
    │   ├── uniqueness.py           # Duplicate detection
    │   ├── distribution.py         # Statistical distribution
    │   ├── anomaly_detector.py     # Z-score and IQR anomaly detection
    │   └── consistency_rules.py    # 14 Indian business data rules
    ├── parsers/
    │   ├── tally_xml_parser.py     # Version-aware (3.x/4.x) TallyPrime XML
    │   ├── pdf_table_parser.py     # Enhanced PDF table extraction
    │   ├── ocr_parser.py           # Tesseract with Hindi support (eng+hin)
    │   ├── xbrl_parser.py          # MCA21 XBRL financial filings
    │   └── encoding_handler.py     # chardet-based encoding detection
    ├── registry/
    │   ├── source_registry.py      # CRUD for data source catalog
    │   ├── models.py               # DataSource, SyncState, SyncRun, DataSourceHealth
    │   └── migrations/
    │       └── 001_initial_schema.sql
    ├── health/
    │   ├── monitor.py              # ConnectionHealthMonitor
    │   ├── alerts.py               # AlertManager, 7 alert types
    │   ├── freshness_checker.py    # Data freshness SLA checks
    │   └── cascade_analyzer.py     # Downstream dependency impact
    ├── api/
    │   ├── main.py                 # FastAPI app, CORS, lifespan, routers
    │   ├── Dockerfile              # python:3.11-slim, tesseract-ocr-hin, libpq-dev
    │   ├── routes/
    │   │   ├── connectors.py       # CRUD + test + schema detection
    │   │   ├── sync.py             # Trigger, status, history, reset
    │   │   ├── registry.py         # Source registry endpoints
    │   │   ├── health.py           # Health status, alerts, dashboard
    │   │   └── profiling.py        # Quality reports, consistency violations
    │   └── schemas/
    │       ├── connector_schemas.py
    │       └── sync_schemas.py
    └── airflow/
        ├── dags/
        │   ├── mca21_daily_sync.py     # 2am daily, quality gate (score < 70 = fail)
        │   ├── client_excel_sync.py
        │   └── health_check_dag.py     # Every 15 minutes
        └── plugins/
            └── infracore_operators.py
```

### Critical Architecture Rules for Layer 1

**Rule 1:** Raw data lands in MinIO as Parquet. Never in PostgreSQL. PostgreSQL is for metadata only (registry, sync state, health records).

**Rule 2:** All credentials stored AES-256-GCM encrypted. Never in plain text. Never logged.

**Rule 3:** `webhook_connector.py` is a `WebhookReceiver` class, NOT a `BaseConnector` subclass. Webhooks are push-based — they cannot implement `test_connection()` or `extract_full()`.

**Rule 4:** Every connector must handle these failure modes gracefully (no crashes, typed exceptions only): `ConnectionError`, `AuthenticationError`, `SchemaError`, `ExtractionError`, `RateLimitError`.

**Rule 5:** Parquet files use snappy compression. Object path format: `{client_id}/{source_id}/{YYYY}/{MM}/{DD}/{batch_id}.parquet`.

### Indian-Specific Implementations (Do Not Simplify)

**CIN format:** `[UL][0-9]{5}[A-Z]{2}[0-9]{4}[A-Z]{3}[0-9]{6}` — 21 chars exactly. Extract components: listing_status, NIC code, state code, year, company type, sequential number.

**GSTIN format:** `[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]` — validate checksum, extract state code and PAN component.

**Indian number parser:** `₹1,24,50,000` → `12450000.0`. Indian lakh separator pattern differs from Western thousands separator. Must handle crore/lakh notation: `₹1.2Cr` → `12000000`.

**Indian date parser:** Must handle all these formats: DD/MM/YYYY, DD-MM-YYYY, YYYY-MM-DD, DD.MM.YYYY, "15th March 2024", "Mar 15, 2024", "15-Mar-24", "Q3 FY2024". Normalize to ISO 8601. Compute Indian financial year (April-March) alongside calendar year.

**14 Consistency Rules:** PaidUpCapital ≤ AuthorizedCapital, IncorporationDate ≤ today, CessationDate > AppointmentDate, director max 20 companies (MCA limit), GSTIN state code must match registered address state, CurrentRatio > 0, DSCR < 0.8 is critical flag.

### Docker Services
```yaml
postgres:15        # Platform metadata — port 5432
minio:latest       # Raw data object storage — port 9000 (API), 9001 (console)
redis:7-alpine     # Airflow broker + health cache — port 6379
airflow-webserver  # Pipeline orchestration UI — port 8080
airflow-scheduler  # DAG execution
layer1-api         # FastAPI intelligence API — port 8001
```

Start with: `docker-compose up -d`
API docs: `http://localhost:8001/docs`
MinIO console: `http://localhost:9001`

---

## LAYER 2: DATA PIPELINE — IN PROGRESS

### What It Does
Takes raw Parquet files from Layer 1 and produces clean, validated, entity-resolved, ontology-ready data. Does NOT store to ontology. Produces clean Parquet that Layer 3 ingests.

### Core Subsystems

**1. Pipeline Execution Engine**
- DAG-based execution (each pipeline is a graph, not a sequence)
- Apache Spark for batch transforms (PySpark on single machine — no cluster needed at current scale)
- Apache Flink for streaming/micro-batch (15-60 minute intervals for most clients)
- Build system that validates schema compatibility before any data is processed

**2. Transformation Library**

String cleaning: trim, case normalize, special char removal, regex extract/replace, truncation, padding.

Number cleaning: Indian comma separators (`1,24,500` → `124500`), currency symbols, percentage conversion, lakh/crore notation.

Date cleaning: Universal Indian date parser. Indian financial year computation.

Address cleaning: PIN code extraction + validation, state name normalization (MH/Maharashtra/MAHARASHTRA → Maharashtra), city normalization.

Indian identifier normalizers: CIN, DIN, GST, PAN, IFSC — normalize then validate.

Structural transforms: rename, add computed column, drop, split, concat, pivot, unpivot, filter, dedup, sort, aggregate, inner/left/full join, lookup, union.

Enrichment transforms: reference data lookup (30,000+ PIN codes → state/district/city), LLM-powered extraction (unstructured → structured), Hindi/regional language translation.

**3. Data Quality Engine**

Validation rule types: format rules (regex), business rules (cross-field logic), referential integrity rules (foreign key existence).

Four failure policies: Reject (drop record), Flag (include with quality flag), Default (replace with configured default), Transform (attempt automatic correction).

**4. Entity Resolution Engine**

Three phases: Blocking (PIN code, name prefix, CIN prefix, phonetic), Comparison (Levenshtein, Jaro-Winkler, token sort ratio, abbreviation expansion), Classification (>0.95 auto-merge, 0.75-0.95 flag for review, <0.5 discard).

Indian-specific: "Pvt Ltd" / "Private Limited" / "(P) Ltd" normalization before comparison. CIN is ground truth — if CINs match, merge immediately.

**5. Version Control**

All pipeline definitions in Git (YAML/JSON). Master branch = production only. Feature branches for changes. Rollback any pipeline to any version in < 5 minutes.

**6. Pipeline Scheduler**

Use Apache Airflow (already in Layer 1 Docker Compose). Dependency-triggered execution (Layer 1 sync complete → Layer 2 clean → Layer 3 load). Exponential backoff retry (1min, 5min, 15min, alert). Dead letter queue for permanently failed records.

### Technology
```bash
pip install pyspark==3.4.0
pip install rapidfuzz dedupe  # Entity resolution
pip install python-stdnum     # GST, PAN validation
pip install unidecode         # Unicode normalization
pip install langdetect        # Hindi vs English detection
pip install great-expectations # Data quality testing
```

---

## LAYER 3: ONTOLOGY — DESIGNED

### What It Is
The semantic intelligence layer. Not a database. A living digital twin of the organization. Every object is a business entity. Every link is a relationship. Every property is a meaningful attribute. This is Palantir's core differentiator.

### Three Sublayers

**Semantic Layer** — What exists:
- Object Types: Company, Director, Project, Contract, RegulatoryAction, LegalCase, InsolvencyProceeding, Address, RegulatoryBody, GovernmentEntity
- Properties: typed, with Indian semantic types (CIN_Type, DIN_Type, Currency_INR, IndianDate_Type, RiskScore_Type)
- Relationships with properties: DIRECTED (with appointedDate, cessationDate, designation, isCurrent), OWNS (percentageHeld, holdingType), SUBJECT_OF, OWNS_PROJECT

**Kinetic Layer** — How it changes:
- Action Types: FlagCompanyForReview, UpdateProjectStatus, MarkRegulatoryActionResolved, CreateIntelligenceAlert, MergeCompanyObjects
- Every action has: validation rules, approval workflow, side effects, complete audit trail
- Functions: computeGroupRiskScore, computeBeneficialOwnershipChain, assessCIRPContagionRisk, predictProjectCompletionProbability

**Dynamic Layer** — Security and governance:
- Roles: Platform Administrator, Ontology Designer, Data Steward, Analyst, Compliance Head, Restricted Viewer, System Pipeline
- Property-level security: different roles see different fields of same object
- Dynamic object-level security: PE firm users only see their portfolio companies

### Storage Architecture (Multi-Index)
```
PostgreSQL    → Primary store (authoritative current state, single-object retrieval)
Neo4j         → Graph store (relationship traversal, network queries)
Elasticsearch → Search index (full-text search across all properties)
TimescaleDB   → Time-series store (historical property values, timeline view)
Redis         → Cache layer (frequently accessed objects, dashboard rendering)
```

### Critical Ontology Design Rules
1. Entities must be long-lived and meaningful — not table reflections
2. Overloading entities with too many fields causes slower queries and heavier indexing
3. Shared properties (riskScore, status, registeredState, lastUpdated) defined once, used everywhere
4. Derived properties computed at query time or pre-computed and cached
5. Inferred relationships (co-directorship, indirect ownership, regulatory contagion) labeled as derived with inference rule documented

### Object Type Groups for Infrastructure Domain
- Corporate Structure: Company, Director, Partnership, Trust, ForeignEntity
- Project Portfolio: Project, Contract, Milestone, Contractor, Subcontractor
- Financial: FinancialStatement, Transaction, Debt, Equity, GuaranteeObligation
- Regulatory: RegulatoryAction, CourtCase, InsolvencyProceeding, ComplianceRequirement
- People: Individual, BeneficialOwner, KeyManagementPersonnel
- Reference: RegulatoryBody, GovernmentAgency, Bank, Court, Industry

---

## THE MOCK COMPANY: INFRACORE DEVELOPMENTS LIMITED

This is the demonstration dataset. All 9 CSV files exist in `infracore_foundry/data/raw/`.

**Company:** Infracore Developments Limited — fictional Indian infrastructure conglomerate
**Revenue:** ₹1,200 Cr | **Founded:** 2003 | **Listed:** BSE | **HQ:** Mumbai BKC

**10 entities in the group:**
1. Infracore Developments Limited (parent, listed)
2. Infracore Highway SPV 1 Pvt Ltd (NH-48 BOT project)
3. Infracore Port Holdings Pvt Ltd (Kandla Port Phase 2)
4. Infracore Solar Energy Pvt Ltd (500MW Jodhpur solar)
5. Infracore Urban Infra Pvt Ltd (Chennai Smart City)
6. Infracore Road Projects Pvt Ltd (MP State Highway)
7. Infracore Asset Management Pvt Ltd (group treasury)
8. Infracore Gujarat Highway Pvt Ltd (**UNDER CIRP** — ₹420Cr default)
9. Crestline Holdings Pvt Ltd (offshore-connected holding vehicle)
10. Meridian Infra Consultants Pvt Ltd (related party consulting firm)

**Intelligence signals embedded in the data (what Satorix must surface automatically):**

| Signal | Detail | Severity |
|--------|--------|----------|
| CIRP Active | Gujarat Highway SPV — ₹420Cr default to SBI | CRITICAL |
| ED FEMA Investigation | Crestline Holdings — Mauritius remittances | HIGH |
| Offshore Director | Victor Fernandes (Mauritius) sits on 3 entities | HIGH |
| Disqualified Director | Ramesh Bhatia — Sec 164(2) disqualification | HIGH |
| Address Clustering | 6 of 10 companies share same BKC Mumbai address | MEDIUM |
| Unapproved RPTs | 3 of 5 transactions not arm's-length certified | MEDIUM |
| Project Delay | Chennai Smart City — 28 months overdue, 22% overrun | MEDIUM |
| Offshore Ownership | Mauritius trust owns 26% of Port Holdings | HIGH |

**Mock data files:**
```
01_companies.csv          — 10 group companies with CINs, statuses, addresses
02_directors.csv          — 8 directors including Victor Fernandes (Mauritius) and disqualified Ramesh Bhatia
03_director_mappings.csv  — 21 company-director relationships with appointment/cessation dates
04_shareholding.csv       — Ownership structure showing Mauritius connection
05_projects.csv           — 6 projects with delays, cost overruns, key risks
06_financials.csv         — 3-year financials showing Gujarat Highway deterioration
07_regulatory_actions.csv — SEBI SCN, NHAI penalty, MNRE dispute, NCLT CIRP, MCA disqualification, ED FEMA probe
08_related_party_transactions.csv — 5 RPTs, 3 without audit committee approval
09_events_timeline.csv    — 10 dated events from 2020-2024
```

---

## CONNECTOR STATUS: WHAT IS AND IS NOT AVAILABLE

### Fully Open Source — Zero Build Effort
| Connector | Library | Notes |
|-----------|---------|-------|
| CSV/TSV | `pandas` | Complete |
| Excel | `openpyxl xlrd` | Including merged cells |
| PDF | `pdfplumber PyMuPDF pytesseract` | Digital + OCR |
| PostgreSQL | `sqlalchemy psycopg2-binary` | Server-side cursors |
| MySQL | `sqlalchemy pymysql` | LIMIT/OFFSET, utf8mb4 |
| REST API | `httpx requests` | 5 auth, 5 pagination |
| Google Sheets | `gspread google-auth` | OAuth2 |
| S3/MinIO | `boto3 minio` | Delta sync |
| SFTP/FTP | `paramiko` | Mod-time incremental |
| Kafka | `confluent-kafka` | Consumer groups |
| Webhook | `fastapi` | Already running |
| Oracle | `cx_Oracle sqlalchemy` | Requires Oracle Instant Client |

### Requires Wrapper Work (2-4 weeks each)
| Connector | Available | Gap |
|-----------|-----------|-----|
| Tally Live | `tally-integration` pip | Version differences, offline/online modes |
| SAP Export | `pyrfc zeep` | IDOC format parser, field name mapping |
| SharePoint | `Office365-REST-Python-Client` | Delta sync, permission flow |
| Email | `imaplib2 exchangelib` | Routing rules, dedup |
| Zoho | `zohocrmsdk` | Rate limits, field mapping |
| MCA21 | Sandbox.co.in API (₹1-3/call) | Rate limiting, Redis cache, bulk fallback |

### Must Build From Scratch
| Connector | Status | Timeline |
|-----------|--------|----------|
| GSTN | Requires GSP licensing | 4-5 weeks + licensing |
| SEBI EDGAR | HTML scraper | 6-8 weeks |
| RBI Data | Excel/HTML parser | 4-5 weeks |
| GeM Portal | Playwright scraper (JS-heavy) | 5-6 weeks |
| Tally XML Export | Version-detecting parser | 3 weeks |
| IndiaStack | Requires UIDAI/RBI licensing | 6+ months |

---

## COMPETITIVE POSITIONING

### The One-Sentence Distinction
Data fabric platforms (Microsoft Fabric, Snowflake, Databricks, Informatica, SAP HANA) ask: "How do I connect and access data?" Satorix asks: "What does the data mean, what risks does it reveal, and what should the organization do?"

### The Capability Matrix
| Capability | Satorix | MS Fabric | Snowflake | Databricks | Informatica | SAP HANA |
|------------|---------|-----------|-----------|------------|-------------|----------|
| India-native connectors | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Tally ERP integration | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Semantic ontology layer | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Domain risk scoring built-in | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |
| DPDP Act 2023 compliant | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |
| Mid-market pricing (< ₹1 Cr) | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |
| No IT team required | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |

---

## DOMAIN SELECTION AND ENTRY STRATEGY

**Selected entry domain:** Corporate Due Diligence Intelligence for PE/VC firms and compliance teams

**Why this domain wins for solo/small founder:**
- Most data publicly available (MCA21 alone gives working demo in 2 weeks)
- Target client is accessible (PE associates, VC analysts on LinkedIn)
- Problem is visually demonstrable (graph showing hidden connections = immediate "wow")
- Sales cycle is shortest (PE doing diligence needs intelligence NOW)
- Cybersecurity background is credible (data security, encrypted pipelines matter to PE/M&A)

**The Palantir Playbook applied:**
1. Build on public data → demonstrate capability
2. Attract first anchor client → embed via FDE methodology
3. Extract domain knowledge → productize learnings
4. Expand domain by domain

**First client profile:**
- Active deal flow: multiple DD exercises per year
- Mid-size: ₹500Cr-₹5000Cr AUM
- India-focused fund
- Accessible decision-maker (partner/VP reachable on LinkedIn)

---

## BUSINESS MODEL

**Setup fee:** ₹25-100 lakhs (one-time, covers configuration, deployment, training)
**Annual subscription:** ₹8-30 lakhs per year (ongoing intelligence, updates, support)

**Revenue projections (conservative):**
| Year | Clients | ARR |
|------|---------|-----|
| 1 | 1-2 | ₹25-30 L |
| 2 | 5-8 | ₹1.5-2 Cr |
| 3 | 15-20 | ₹5-7 Cr |
| 4 | 35-50 | ₹15-20 Cr |
| 5 | 80-120 | ₹40-60 Cr |

---

## TECHNOLOGY STACK

### Current (Layer 1)
```
Python 3.11
FastAPI 0.104.0 + Uvicorn 0.24.0
SQLAlchemy 2.0.23 + PostgreSQL 15
MinIO 7.2.0 (S3-compatible object storage)
Apache Airflow 2.7.3 [celery,postgres,redis]
Apache Parquet via PyArrow 14.0.0
Redis 7
Docker + Docker Compose
AES-256-GCM (cryptography library)
```

### Planned (Layers 2-3)
```
Apache Spark 3.4.0 (batch pipeline execution)
Apache Flink (streaming/micro-batch)
Neo4j 5.x (graph database — ontology)
Elasticsearch 8.x (full-text search)
TimescaleDB (time-series / timeline view)
rapidfuzz (entity resolution — fuzzy matching)
Git (pipeline version control)
```

### Frontend (Layer 6)
```
React (dashboard builder)
D3.js or Cytoscape.js (graph visualization)
FastAPI backend (already running)
```

---

## FORWARD DEPLOYED ENGINEERING (FDE) METHODOLOGY

This is how Satorix acquires and serves clients — not through traditional software sales.

**What FDE means:** Engineers embed inside the client organization for 2-4 weeks. They observe actual workflows, extract domain knowledge, map data sources, and build the platform configuration for that client's specific environment.

**Why this matters:** It bypasses enterprise procurement (consulting engagement, not software purchase). It extracts tribal knowledge that no questionnaire captures. It produces a platform configuration that is deeply specific to the client's actual pain — not a generic deployment.

**The 6-stage FDE process:**
1. Organizational intelligence (Days 1-3): Decision architecture, information flow, shadow data systems
2. System archaeology (Days 3-7): System inventory, data lineage, actual vs documented schemas
3. Data profiling (Days 5-12): Completeness, uniqueness, distribution, cross-system entity resolution
4. Workflow extraction (Days 7-14): Shadow actual analysts, screen-record (with permission), map every step
5. Domain knowledge extraction: Tribal knowledge about data quality, business rules, signal identification
6. Output and decision mapping (Days 12-20): Every report, every recurring decision, every latency gap

**For the current stage (no client yet):** Substitute FDE discovery with systematic public research — MCA21 archaeology, SEBI order corpus, parliamentary committee reports, LinkedIn content from practitioners, job posting workflow analysis.

---

## TESTING STATUS

Layer 1 testing has been designed across 5 phases:

**Phase 1 — Infrastructure Verification:**
- All 5 Docker containers show `Up`
- 4 database tables exist (DataSource, SyncState, SyncRun, DataSourceHealth)
- 2 MinIO buckets exist (raw-data, processed-data)
- Redis responds to PING
- API `/docs` loads at http://localhost:8001/docs

**Phase 2 — Unit Tests:**
- Indian identifier validation (CIN, DIN, GST, PAN, IFSC)
- CSV connector: clean file, encoding issues, Indian numbers
- Data profiler: completeness scores, consistency rule violations
- Encryption: roundtrip, tamper detection

**Phase 3 — Integration Tests:**
- CSV → DataFrame → Parquet → MinIO roundtrip
- Connector registration with encrypted credentials
- Health check persists to database

**Phase 4 — Real Data Tests:**
- All 4 Infracore mock sources register and sync
- CIN column auto-detected as Indian identifier
- Profiling report shows correct quality metrics

**Phase 5 — Failure Tests:**
- Unreachable source returns graceful error (not crash)
- Empty file returns 0 records
- 100,000 row file completes in < 60 seconds

---

## WHAT THE PROJECT PROPOSAL COVERS

A complete project proposal (satorix_proposal.docx) has been generated for company approval. It covers:
- Executive summary with market gap framing
- Why Palantir cannot work in India (5 structural reasons)
- Indian government mandate and validation (IndiaAI Mission, WiredLeap IRIS, DefTech)
- Satorix solution with 10-layer architecture
- What has already been built (Layer 1 complete, 81 files, 22+ connectors)
- Market opportunity (₹18,000 Cr TAM by 2028)
- Revenue projections
- Execution plan
- What the company's support is needed for (cloud infrastructure, domain introductions, formal association)

---

## RULES FOR CLAUDE CODE

### Before touching any file:
1. Read the relevant layer's section in this CLAUDE.md
2. Understand which layer you are in and what its single responsibility is
3. Check that your change does not violate any layer boundary

### When writing code:
- Full type hints everywhere. No untyped function signatures.
- Pydantic models or dataclasses for all data structures
- Every connector method raises typed exceptions: `ConnectionError`, `AuthenticationError`, `SchemaError`, `ExtractionError`, `RateLimitError`
- Never log credentials, never log PII, never log decrypted values
- All monetary amounts stored as float in rupees (not lakhs/crores)
- All dates stored as ISO 8601 (YYYY-MM-DD)
- Indian financial year computed and stored alongside calendar dates
- State codes normalized to full state names using lookup table

### When adding connectors:
- Inherit from `BaseConnector` for all pull-based connectors
- `WebhookReceiver` is NOT a connector — it is a separate class
- Test with deliberately bad data before testing with good data
- Indian number and date formats must be handled from day one, not retrofitted

### When modifying the ontology (Layer 3 and above):
- Schema changes are versioned like software releases
- Breaking changes (delete/rename object types, change primary keys) require migration plan
- Additive changes (new object types, new properties) are backward compatible
- Never store derived properties — compute at query time or cache separately

### Performance requirements:
- CSV/Excel extraction: 500,000 rows in < 60 seconds
- Database extraction: stream with server-side cursors, never load entire table
- Parquet files use snappy compression
- Profile reports complete in < 30 seconds for datasets up to 1M rows
- All ontology queries: < 3 seconds for standard network traversals

---

## NEXT IMMEDIATE PRIORITIES

### Priority 1: Complete Layer 1 Testing
Run the 5-phase test plan documented in the Testing Status section above.
Start with `docker-compose up -d` and verify all containers are healthy.
Then run `pytest tests/ -v --tb=short` for unit tests.

### Priority 2: Build Layer 2 Core
Implement in this order:
1. Transformation library (string, number, Indian date cleaning)
2. Indian identifier validators integrated into transforms
3. Validation rule engine with 4 failure policies
4. Basic deduplication (exact and key-based)
5. Pipeline scheduler (Airflow DAGs for Layer 2)
6. Entity resolution engine (start with name-only matching, add fields iteratively)

### Priority 3: Load Real MCA21 Data
Download MCA company master file from mca.gov.in/content/mca/global/en/mca/master-data/MDS.html
Replace Infracore mock data with real MCA data for 10 companies.
This transforms the demonstration from fictional to verifiable.

### Priority 4: Build the Neo4j Graph
Set up Neo4j Community Edition.
Load company and director nodes.
Load DIRECTED, OWNS, SUBJECT_OF relationships.
Run the Victor Fernandes detection query to prove graph intelligence works.

---

## KEY CYPHER QUERIES FOR NEO4J (Once Layer 3 is running)

```cypher
-- Full company network (2 degrees)
MATCH path=(c:Company {cin:'L45201MH2003PLC142301'})-[*1..2]-(n)
RETURN path LIMIT 100

-- All offshore directors and their companies
MATCH (d:Director {isOffshore: true})-[:DIRECTED]->(c:Company)
RETURN d.name, d.nationality, collect(c.name) AS companies

-- Companies connected through Victor Fernandes
MATCH (d:Director {din:'00778899'})-[:DIRECTED]->(c:Company)
RETURN d.name AS director, c.name AS company, c.riskScore AS risk

-- Ongoing regulatory actions
MATCH (c:Company)-[:SUBJECT_OF]->(r:RegulatoryAction {status:'Ongoing'})
RETURN c.name, r.issuingBody, r.actionType, r.description

-- Shell company indicator: shared addresses
MATCH (c1:Company), (c2:Company)
WHERE c1.registeredAddress = c2.registeredAddress AND c1.cin <> c2.cin
RETURN c1.name, c2.name, c1.registeredAddress

-- Companies ranked by risk score
MATCH (c:Company)
RETURN c.name, c.status, c.riskScore, c.riskFlags
ORDER BY c.riskScore DESC
```

---

## ENVIRONMENT VARIABLES (.env)

```bash
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=infracore
POSTGRES_USER=infracore
POSTGRES_PASSWORD=infracore_dev_password
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=infracore_minio
MINIO_SECRET_KEY=infracore_minio_secret
MINIO_RAW_BUCKET=raw-data
MINIO_SECURE=false
REDIS_URL=redis://localhost:6379/0
ENCRYPTION_KEY=<32-byte-base64-key>
SANDBOX_API_KEY=<sandbox.co.in-key>
GOOGLE_CREDENTIALS_PATH=./credentials/google_service_account.json
API_HOST=0.0.0.0
API_PORT=8001
LOG_LEVEL=INFO
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=infracore123
```

---

## QUICK START COMMANDS

```bash
# Start all Layer 1 services
docker-compose up -d

# Verify all containers running
docker-compose ps

# Check API is alive
curl http://localhost:8001/health

# Generate mock data
cd infracore_foundry/data/raw && python generate_mock_data.py

# Load mock data into Neo4j (once Layer 3 Neo4j is running)
cd infracore_foundry/ingestion && python load_to_neo4j.py

# Start Layer 1 API in development mode
uvicorn layer1_ingestion.api.main:app --reload --port 8001

# Run all tests
pytest tests/ -v --tb=short

# Run only unit tests (no Docker needed)
pytest tests/layer1/ -v -m "not integration"

# Run integration tests (Docker must be running)
pytest tests/layer1/test_integration/ -v -m integration
```

---

*Last updated: April 2026*
*Document version: 1.0*
*Total conversation context: ~150,000 words of design, architecture, and implementation decisions*
