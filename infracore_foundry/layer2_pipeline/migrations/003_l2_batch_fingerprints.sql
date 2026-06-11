-- Migration 003: Cross-batch deduplication fingerprint store
-- Stores SHA-256 fingerprints of ingested records per pipeline.
-- PipelineExecutor uses this to filter records already seen in previous batches.

CREATE TABLE IF NOT EXISTS l2_batch_fingerprints (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_id         VARCHAR(200) NOT NULL,
    client_id           VARCHAR(255) NOT NULL,
    fingerprint         VARCHAR(64)  NOT NULL,
    first_seen_batch_id VARCHAR(64),
    first_seen_run_id   UUID,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Unique per pipeline+fingerprint — ON CONFLICT DO NOTHING for idempotent inserts
CREATE UNIQUE INDEX IF NOT EXISTS ix_l2_fp_pipeline_fingerprint
    ON l2_batch_fingerprints (pipeline_id, fingerprint);

CREATE INDEX IF NOT EXISTS ix_l2_fp_client_pipeline
    ON l2_batch_fingerprints (client_id, pipeline_id);

-- Range index to support the 90-day lookback window query efficiently
CREATE INDEX IF NOT EXISTS ix_l2_fp_created_at
    ON l2_batch_fingerprints (created_at);

COMMENT ON TABLE l2_batch_fingerprints IS
    'Cross-batch deduplication fingerprints. Each row = one record seen in a previous batch. '
    'Fingerprint = SHA-256[:16] of concatenated key column values. '
    '90-day lookback window applied at query time for performance.';
