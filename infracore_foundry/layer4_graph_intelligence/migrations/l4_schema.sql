-- Layer 4 Graph Intelligence — PostgreSQL Schema
-- All tables prefixed l4_

CREATE TABLE IF NOT EXISTS l4_influence_scores (
    id                  BIGSERIAL PRIMARY KEY,
    entity_id           TEXT NOT NULL,
    entity_type         TEXT NOT NULL,
    betweenness         FLOAT DEFAULT 0.0,
    pagerank            FLOAT DEFAULT 0.0,
    degree_centrality   FLOAT DEFAULT 0.0,
    risk_weighted_score FLOAT DEFAULT 0.0,
    regulatory_exposure FLOAT DEFAULT 0.0,
    composite_score     FLOAT DEFAULT 0.0,
    composite_rank      INT,
    computed_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    batch_run_id        TEXT,
    UNIQUE (entity_id, entity_type)
);
CREATE INDEX IF NOT EXISTS idx_l4_influence_composite ON l4_influence_scores (composite_rank ASC);
CREATE INDEX IF NOT EXISTS idx_l4_influence_entity ON l4_influence_scores (entity_id, entity_type);

CREATE TABLE IF NOT EXISTS l4_cluster_memberships (
    id              BIGSERIAL PRIMARY KEY,
    entity_id       TEXT NOT NULL,
    entity_type     TEXT NOT NULL,
    cluster_id      TEXT NOT NULL,
    cluster_type    TEXT NOT NULL,     -- louvain | label_propagation | address | director | regulatory
    membership_score FLOAT DEFAULT 1.0,
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    batch_run_id    TEXT,
    UNIQUE (entity_id, entity_type, cluster_type)
);
CREATE INDEX IF NOT EXISTS idx_l4_cluster_id ON l4_cluster_memberships (cluster_id, cluster_type);
CREATE INDEX IF NOT EXISTS idx_l4_cluster_entity ON l4_cluster_memberships (entity_id, entity_type);

CREATE TABLE IF NOT EXISTS l4_address_clusters (
    id              BIGSERIAL PRIMARY KEY,
    cluster_id      TEXT NOT NULL UNIQUE,
    canonical_address TEXT NOT NULL,
    member_count    INT DEFAULT 0,
    company_count   INT DEFAULT 0,
    director_count  INT DEFAULT 0,
    risk_signal     FLOAT DEFAULT 0.0,
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    batch_run_id    TEXT
);

CREATE TABLE IF NOT EXISTS l4_subgraph_definitions (
    id              BIGSERIAL PRIMARY KEY,
    subgraph_id     TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    template        TEXT,
    seed_entity_id  TEXT NOT NULL,
    seed_entity_type TEXT NOT NULL,
    hops            INT DEFAULT 2,
    node_types      JSONB DEFAULT '[]',
    edge_types      JSONB DEFAULT '[]',
    filters         JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by      TEXT
);

CREATE TABLE IF NOT EXISTS l4_subgraph_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    subgraph_id     TEXT NOT NULL REFERENCES l4_subgraph_definitions(subgraph_id),
    snapshot_id     TEXT NOT NULL UNIQUE,
    node_count      INT DEFAULT 0,
    edge_count      INT DEFAULT 0,
    nodes           JSONB DEFAULT '[]',
    edges           JSONB DEFAULT '[]',
    diff_from_prev  JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_l4_snapshot_subgraph ON l4_subgraph_snapshots (subgraph_id, created_at DESC);

CREATE TABLE IF NOT EXISTS l4_precursor_assessments (
    id              BIGSERIAL PRIMARY KEY,
    entity_id       TEXT NOT NULL,
    entity_type     TEXT NOT NULL DEFAULT 'Company',
    cirp_risk_score FLOAT NOT NULL,
    signal_breakdown JSONB DEFAULT '{}',
    risk_band       TEXT NOT NULL,   -- LOW | MEDIUM | HIGH | CRITICAL
    model_version   TEXT NOT NULL DEFAULT 'rule_v1',
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    batch_run_id    TEXT,
    UNIQUE (entity_id, entity_type)
);
CREATE INDEX IF NOT EXISTS idx_l4_precursor_risk ON l4_precursor_assessments (cirp_risk_score DESC);
CREATE INDEX IF NOT EXISTS idx_l4_precursor_band ON l4_precursor_assessments (risk_band);

CREATE TABLE IF NOT EXISTS l4_batch_runs (
    id              BIGSERIAL PRIMARY KEY,
    run_id          TEXT NOT NULL UNIQUE,
    run_date        DATE NOT NULL,
    status          TEXT NOT NULL DEFAULT 'running',  -- running | complete | failed
    phase           TEXT,
    nodes_processed INT DEFAULT 0,
    edges_processed INT DEFAULT 0,
    duration_seconds FLOAT,
    error_message   TEXT,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS l4_query_log (
    id              BIGSERIAL PRIMARY KEY,
    query_id        TEXT NOT NULL UNIQUE,
    query_type      TEXT NOT NULL,
    params          JSONB DEFAULT '{}',
    result_count    INT,
    cache_hit       BOOLEAN DEFAULT FALSE,
    duration_ms     FLOAT,
    requested_by    TEXT,
    requested_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_l4_query_type ON l4_query_log (query_type, requested_at DESC);
