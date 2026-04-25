-- Migration 002: Fix columns missing from initial schema
-- Run AFTER 001_initial_schema.sql

-- sync_runs: deterministic batch_id for idempotency
ALTER TABLE sync_runs ADD COLUMN IF NOT EXISTS batch_id VARCHAR(64) UNIQUE;

-- sync_states: store last confirmed watermarks and schema fingerprint
ALTER TABLE sync_states ADD COLUMN IF NOT EXISTS schema_fingerprint VARCHAR(64);
ALTER TABLE sync_states ADD COLUMN IF NOT EXISTS incremental_strategy VARCHAR(30) DEFAULT 'timestamp';

-- data_sources: circuit-breaker state
ALTER TABLE data_sources ADD COLUMN IF NOT EXISTS consecutive_failures INTEGER NOT NULL DEFAULT 0;
ALTER TABLE data_sources ADD COLUMN IF NOT EXISTS circuit_open BOOLEAN NOT NULL DEFAULT FALSE;

-- alerts: proper status lifecycle, acknowledgement, structured details
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS status VARCHAR(50) NOT NULL DEFAULT 'open';
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS acknowledged_at TIMESTAMPTZ;
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS details JSONB;
ALTER TABLE alerts ALTER COLUMN title DROP NOT NULL;

-- dedup index: one active alert per source per alert_type
CREATE UNIQUE INDEX IF NOT EXISTS ix_alerts_source_type_active
    ON alerts (source_id, alert_type)
    WHERE status = 'open';

CREATE INDEX IF NOT EXISTS ix_alerts_status ON alerts(status);
CREATE INDEX IF NOT EXISTS ix_sync_runs_batch_id ON sync_runs(batch_id);
