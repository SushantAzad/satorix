-- Initial schema migration for Infracore Foundry Layer 1
-- Creates all tables for data source registry, sync state, health monitoring

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Data source registry
CREATE TABLE IF NOT EXISTS data_sources (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id VARCHAR(255) NOT NULL,
    source_name VARCHAR(500) NOT NULL,
    source_type VARCHAR(100) NOT NULL,
    description TEXT,
    connection_config TEXT NOT NULL,
    auth_method VARCHAR(100),
    environment VARCHAR(50) NOT NULL DEFAULT 'production',
    status VARCHAR(50) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by VARCHAR(255)
);

CREATE INDEX IF NOT EXISTS ix_data_sources_client_id ON data_sources(client_id);
CREATE INDEX IF NOT EXISTS ix_data_sources_source_type ON data_sources(source_type);
CREATE INDEX IF NOT EXISTS ix_data_sources_status ON data_sources(status);
CREATE INDEX IF NOT EXISTS ix_data_sources_client_status ON data_sources(client_id, status);

-- Sync state tracking
CREATE TABLE IF NOT EXISTS sync_states (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_id UUID NOT NULL UNIQUE REFERENCES data_sources(id) ON DELETE CASCADE,
    last_sync_at TIMESTAMPTZ,
    last_successful_sync_at TIMESTAMPTZ,
    last_extracted_id VARCHAR(500),
    last_extracted_timestamp TIMESTAMPTZ,
    total_records_last_run INTEGER,
    failed_records_last_run INTEGER DEFAULT 0,
    sync_duration_seconds DOUBLE PRECISION,
    status VARCHAR(50) NOT NULL DEFAULT 'idle',
    error_message TEXT,
    checksum_last_batch VARCHAR(128)
);

CREATE INDEX IF NOT EXISTS ix_sync_states_source_id ON sync_states(source_id);

-- Sync run audit log
CREATE TABLE IF NOT EXISTS sync_runs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_id UUID NOT NULL REFERENCES data_sources(id) ON DELETE CASCADE,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    records_extracted INTEGER DEFAULT 0,
    records_failed INTEGER DEFAULT 0,
    output_path VARCHAR(1000),
    sync_type VARCHAR(50) NOT NULL DEFAULT 'full',
    status VARCHAR(50) NOT NULL DEFAULT 'running',
    error_details TEXT
);

CREATE INDEX IF NOT EXISTS ix_sync_runs_source_id ON sync_runs(source_id);
CREATE INDEX IF NOT EXISTS ix_sync_runs_status ON sync_runs(status);
CREATE INDEX IF NOT EXISTS ix_sync_runs_source_started ON sync_runs(source_id, started_at);

-- Data source health checks
CREATE TABLE IF NOT EXISTS data_source_health (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_id UUID NOT NULL REFERENCES data_sources(id) ON DELETE CASCADE,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_reachable BOOLEAN NOT NULL DEFAULT FALSE,
    response_time_ms DOUBLE PRECISION,
    schema_matches BOOLEAN,
    freshness_score DOUBLE PRECISION,
    volume_anomaly BOOLEAN NOT NULL DEFAULT FALSE,
    alert_sent BOOLEAN NOT NULL DEFAULT FALSE,
    alert_type VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS ix_health_source_id ON data_source_health(source_id);
CREATE INDEX IF NOT EXISTS ix_health_source_checked ON data_source_health(source_id, checked_at);

-- Alerts
CREATE TABLE IF NOT EXISTS alerts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_id VARCHAR(255) NOT NULL,
    alert_type VARCHAR(100) NOT NULL,
    severity VARCHAR(50) NOT NULL,
    title VARCHAR(500) NOT NULL,
    message TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    resolved_by VARCHAR(255),
    resolution_note TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS ix_alerts_source_id ON alerts(source_id);
CREATE INDEX IF NOT EXISTS ix_alerts_source_active ON alerts(source_id, is_active);
CREATE INDEX IF NOT EXISTS ix_alerts_severity_active ON alerts(severity, is_active);
CREATE INDEX IF NOT EXISTS ix_alerts_alert_type ON alerts(alert_type);

-- Auto-update updated_at trigger
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_data_sources_updated_at
    BEFORE UPDATE ON data_sources
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
