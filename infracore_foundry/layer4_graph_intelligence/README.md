# Layer 4 — Graph Intelligence

Port **8004** | FastAPI 0.104 | uvicorn 4-worker

## Architecture

Layer 4 is a **read-only intelligence layer** over Layer 3's stores (Neo4j, PostgreSQL, Elasticsearch, Redis).
All write-backs go exclusively through `ObjectDataFunnel` imported from Layer 3.

### Seven Subsystems

| Subsystem | Module | Purpose |
|---|---|---|
| NetworkMapper | `network/` | N-hop graph expansion for Cytoscape.js |
| PathFinder | `pathfinding/` | Shortest/all paths + LLM narrative generation |
| ClusterDetector | `clustering/` | Louvain, LabelPropagation, address, director, regulatory, temporal |
| SharedAttributeDetector | `shared_attributes/` | Shared address/director/owner detection + write-back |
| InfluenceScorer | `influence/` | Betweenness, PageRank, degree, risk-weighted composite |
| SubgraphExtractor | `subgraph/` | Named subgraph snapshots, diffs, multi-format export |
| TemporalGraphAnalyzer | `temporal/` | Snapshot engine, change detection, velocity, rotation tracker, CIRP precursor |

### Compute Paths

**Nightly batch** (Airflow cron `0 1 * * *`):
```
GDS projection → betweenness → pagerank + degree + reg_exposure (parallel)
→ risk_weighted composite → clusters (parallel) → shared_attributes write-back
→ precursor_model → snapshots → drop_projection
```

**On-demand API**: network expand, path find, subgraph extract, influence lookup (reads pre-computed), temporal snapshots

### Kafka

- **Consumed**: `layer3.ontology.changes`, `layer3.ingest.complete` → cache invalidation
- **Produced**: `layer4.intelligence.ready`, `layer4.cache.invalidate`, `layer4.influence.updates`, `layer4.cluster.updates`

### Cache Keys

Pattern: `l4:{subsystem}:{sha256(sorted_params)[:16]}`

TTLs: short=1h (volatile), medium=6h (batch results), long=24h (LLM narratives)

## API Endpoints

```
GET  /api/v1/network/expand/{entity_id}         N-hop expansion
GET  /api/v1/network/neighbors/{entity_id}       1-hop neighbors

GET  /api/v1/paths/shortest                      Shortest path (source + target)
GET  /api/v1/paths/all                           All paths up to K
GET  /api/v1/paths/negative-space/{entity_id}    Missing expected relationships

GET  /api/v1/clusters/{entity_id}                Cluster memberships
GET  /api/v1/clusters/type/{type}/members        Cluster members
GET  /api/v1/clusters/address/top                Top address clusters by risk

GET  /api/v1/attributes/shared-address/{id}      Shared-address entities
GET  /api/v1/attributes/shared-directors/{id}    Shared-director companies
GET  /api/v1/attributes/circular-ownership       Circular ownership cycles

GET  /api/v1/influence/top                       Top-K by influence metric
GET  /api/v1/influence/{type}/{id}               Entity influence breakdown

POST /api/v1/subgraph/define                     Create subgraph definition
POST /api/v1/subgraph/{id}/snapshot              Take snapshot
GET  /api/v1/subgraph/{id}/diff                  Diff two snapshots
GET  /api/v1/subgraph/{id}/export                Export (cytoscape_json|csv|adjacency)

GET  /api/v1/temporal/entity/{id}                Entity at point in time
GET  /api/v1/temporal/director-history/{id}      Director appointment history
GET  /api/v1/temporal/changes/{id}               Recent director/ownership changes
GET  /api/v1/temporal/velocity/{id}              Anomalous rate-of-change signals
GET  /api/v1/temporal/rotating-directors         Director rotation detection
GET  /api/v1/temporal/precursor/{id}             CIRP precursor risk (rule_v1)
GET  /api/v1/temporal/timeline/{id}              Full event timeline

POST /api/v1/query/nl                            Natural language query (LLM-powered)
POST /api/v1/query/parse                         Parse NL query without executing

GET  /health                                      Health check
GET  /api/v1/health                               Detailed subsystem health
GET  /api/v1/batch/runs                           Last N batch run records
```

## 8 Acceptance Criteria (Infracore Mock Data)

1. **Victor Fernandes** (Director, DIN 00123456) → betweenness rank #1 among all directors
2. **Crestline Developers → SPV1** → 2-hop path via `DIRECTED`
3. **BKC address cluster** → ≥4 companies grouped, risk_signal > 30
4. **Gujarat Highway Construction** → CIRP precursor risk_band = CRITICAL
5. **Fernandes director timeline** → shows appointments at Crestline, SPV1, SPV2
6. **SPV1 ↔ SPV2** → SHARES_DIRECTOR_WITH link written back by shared_attributes batch
7. **Louvain** → Crestline + SPV1 + SPV2 in the same community
8. **Circular ownership** → detected if Crestline → SPV1 → Crestline in test data

## Local Development

```bash
cd infracore_foundry
docker-compose up layer4-api
# or run directly:
cd layer4_graph_intelligence
uvicorn api.main:app --host 0.0.0.0 --port 8004 --reload
```

Docs at http://localhost:8004/docs
