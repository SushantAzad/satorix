-- Layer 2 Pipeline schema migration
-- All tables use l2_ prefix to coexist with Layer 1 in the same PostgreSQL instance.
-- Run once: psql -U infracore -d infracore -f 001_l2_tables.sql

BEGIN;

-- ── Pipeline Definitions ──────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS l2_pipeline_definitions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_id         VARCHAR(200) NOT NULL,
    version             VARCHAR(50)  NOT NULL,
    client_id           VARCHAR(255) NOT NULL,
    description         TEXT,
    config              JSONB        NOT NULL,
    is_active           BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    created_by          VARCHAR(255)
);

CREATE INDEX IF NOT EXISTS ix_l2_pipeline_client_id
    ON l2_pipeline_definitions (pipeline_id, client_id);

CREATE INDEX IF NOT EXISTS ix_l2_pipeline_active
    ON l2_pipeline_definitions (pipeline_id, is_active);

-- ── Pipeline Runs ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS l2_pipeline_runs (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_definition_id  UUID        NOT NULL REFERENCES l2_pipeline_definitions(id) ON DELETE CASCADE,
    run_id                  VARCHAR(64) UNIQUE,     -- deterministic: SHA256(pipeline_id:version:input_batch_id)[:16]
    client_id               VARCHAR(255) NOT NULL,
    status                  VARCHAR(30)  NOT NULL DEFAULT 'pending',
    triggered_by            VARCHAR(50)  NOT NULL DEFAULT 'scheduler',
    input_batch_id          VARCHAR(64),
    input_path              VARCHAR(1000),
    output_path             VARCHAR(1000),
    started_at              TIMESTAMPTZ,
    completed_at            TIMESTAMPTZ,
    records_input           INTEGER      DEFAULT 0,
    records_output          INTEGER      DEFAULT 0,
    records_failed          INTEGER      DEFAULT 0,
    duration_seconds        FLOAT,
    error_summary           TEXT
);

CREATE INDEX IF NOT EXISTS ix_l2_runs_pipeline
    ON l2_pipeline_runs (pipeline_definition_id);

CREATE INDEX IF NOT EXISTS ix_l2_runs_client_status
    ON l2_pipeline_runs (client_id, status);

CREATE INDEX IF NOT EXISTS ix_l2_runs_started
    ON l2_pipeline_runs (started_at);

-- ── Pipeline Step Runs ────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS l2_pipeline_step_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          UUID        NOT NULL REFERENCES l2_pipeline_runs(id) ON DELETE CASCADE,
    step_id         VARCHAR(200) NOT NULL,
    transform_type  VARCHAR(100) NOT NULL,
    status          VARCHAR(30)  NOT NULL DEFAULT 'pending',
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    records_in      INTEGER      DEFAULT 0,
    records_out     INTEGER      DEFAULT 0,
    records_failed  INTEGER      DEFAULT 0,
    error_message   TEXT,
    config_snapshot JSONB
);

CREATE INDEX IF NOT EXISTS ix_l2_step_runs_run_step
    ON l2_pipeline_step_runs (run_id, step_id);

-- ── Error Records (Dead Letter Queue) ────────────────────────────────────────

CREATE TABLE IF NOT EXISTS l2_error_records (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          UUID        NOT NULL REFERENCES l2_pipeline_runs(id) ON DELETE CASCADE,
    step_id         VARCHAR(200) NOT NULL,
    error_type      VARCHAR(50)  NOT NULL,   -- source | transform | system
    error_subtype   VARCHAR(100) NOT NULL,
    severity        VARCHAR(20)  NOT NULL DEFAULT 'error',
    original_record JSONB,
    error_message   TEXT        NOT NULL,
    retry_count     INTEGER      NOT NULL DEFAULT 0,
    status          VARCHAR(30)  NOT NULL DEFAULT 'quarantined',  -- quarantined | reprocessed | discarded
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ,
    resolution_note TEXT
);

CREATE INDEX IF NOT EXISTS ix_l2_errors_run_type
    ON l2_error_records (run_id, error_type);

CREATE INDEX IF NOT EXISTS ix_l2_errors_status
    ON l2_error_records (status);

-- ── Lineage ───────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS l2_lineage (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type         VARCHAR(100) NOT NULL,   -- company | director | project
    entity_id           VARCHAR(255) NOT NULL,   -- CIN, DIN, etc.
    field_name          VARCHAR(200) NOT NULL,
    source_batch_id     VARCHAR(64),
    source_path         VARCHAR(1000),
    pipeline_run_id     UUID,
    pipeline_id         VARCHAR(200),
    pipeline_version    VARCHAR(50),
    step_id             VARCHAR(200),
    transform_applied   VARCHAR(100),
    loaded_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_l2_lineage_entity
    ON l2_lineage (entity_type, entity_id);

CREATE INDEX IF NOT EXISTS ix_l2_lineage_source
    ON l2_lineage (source_batch_id);

-- ── Dedup Groups ──────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS l2_dedup_groups (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          UUID        NOT NULL,
    pipeline_id     VARCHAR(200) NOT NULL,
    canonical_id    VARCHAR(255) NOT NULL,   -- the surviving record's key
    duplicate_ids   JSONB        NOT NULL,   -- list of merged record keys
    merge_strategy  VARCHAR(50)  NOT NULL,   -- latest | most_complete | highest_priority | manual
    confidence_score FLOAT,
    requires_review BOOLEAN      NOT NULL DEFAULT FALSE,
    reviewed        BOOLEAN      NOT NULL DEFAULT FALSE,
    reviewer_note   TEXT,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_l2_dedup_run
    ON l2_dedup_groups (run_id);

CREATE INDEX IF NOT EXISTS ix_l2_dedup_review
    ON l2_dedup_groups (requires_review, reviewed);

COMMIT;
