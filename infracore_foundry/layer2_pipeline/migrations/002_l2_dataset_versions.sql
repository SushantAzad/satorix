-- Layer 2 Dataset Version Registry
-- Immutable record of every successful pipeline output.
-- Enables reproducibility, rollback tracking, and version lineage.
-- Run once: psql -U infracore -d infracore -f 002_l2_dataset_versions.sql

BEGIN;

CREATE TABLE IF NOT EXISTS l2_dataset_versions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_run_id     UUID        NOT NULL REFERENCES l2_pipeline_runs(id) ON DELETE CASCADE,
    pipeline_id         VARCHAR(200) NOT NULL,
    pipeline_version    VARCHAR(50)  NOT NULL,
    client_id           VARCHAR(255) NOT NULL,
    run_id_str          VARCHAR(64)  NOT NULL,          -- deterministic SHA256 run key
    input_batch_id      VARCHAR(64),
    input_path          VARCHAR(1000),
    output_path         VARCHAR(1000),
    schema_fingerprint  VARCHAR(64),                    -- SHA256[:16] of (col:dtype) pairs
    records_output      INTEGER,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_l2_dv_pipeline_run
    ON l2_dataset_versions (pipeline_id, run_id_str);

CREATE INDEX IF NOT EXISTS ix_l2_dv_client_created
    ON l2_dataset_versions (client_id, created_at);

CREATE INDEX IF NOT EXISTS ix_l2_dv_pipeline_run_id
    ON l2_dataset_versions (pipeline_run_id);

COMMIT;
