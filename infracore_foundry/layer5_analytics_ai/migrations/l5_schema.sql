-- Layer 5 Analytics & AI — PostgreSQL Schema
-- All tables prefixed l5_

CREATE TABLE IF NOT EXISTS l5_feature_store (
    id              BIGSERIAL PRIMARY KEY,
    entity_type     VARCHAR(50) NOT NULL,
    entity_id       VARCHAR(200) NOT NULL,
    feature_name    VARCHAR(100) NOT NULL,
    feature_value   FLOAT,
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    schema_version  VARCHAR(20) NOT NULL DEFAULT 'v1.0',
    UNIQUE (entity_type, entity_id, feature_name, computed_at)
);
CREATE INDEX IF NOT EXISTS idx_l5_fs_entity ON l5_feature_store (entity_type, entity_id, computed_at DESC);
CREATE INDEX IF NOT EXISTS idx_l5_fs_feature ON l5_feature_store (feature_name, computed_at DESC);

-- Latest feature snapshot per entity (materialised via trigger or nightly job)
CREATE TABLE IF NOT EXISTS l5_feature_latest (
    entity_type     VARCHAR(50) NOT NULL,
    entity_id       VARCHAR(200) NOT NULL,
    features        JSONB NOT NULL DEFAULT '{}',
    schema_version  VARCHAR(20) NOT NULL DEFAULT 'v1.0',
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (entity_type, entity_id)
);

-- Model registry
CREATE TABLE IF NOT EXISTS l5_models (
    model_id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_name              VARCHAR(100) NOT NULL,
    model_type              VARCHAR(50) NOT NULL,
    version                 VARCHAR(20) NOT NULL,
    status                  VARCHAR(20) NOT NULL DEFAULT 'challenger',
    training_date           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    feature_schema_version  VARCHAR(20) NOT NULL,
    evaluation_metrics      JSONB NOT NULL DEFAULT '{}',
    model_artifact_path     VARCHAR(500),
    hyperparameters         JSONB DEFAULT '{}',
    training_sample_size    INT,
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (model_name, version)
);
CREATE INDEX IF NOT EXISTS idx_l5_models_name_status ON l5_models (model_name, status);

-- Predictions log
CREATE TABLE IF NOT EXISTS l5_predictions (
    id                  BIGSERIAL PRIMARY KEY,
    model_id            UUID REFERENCES l5_models(model_id),
    entity_type         VARCHAR(50) NOT NULL,
    entity_id           VARCHAR(200) NOT NULL,
    prediction_value    FLOAT NOT NULL,
    confidence_lower    FLOAT,
    confidence_upper    FLOAT,
    shap_values         JSONB,
    predicted_at        TIMESTAMPTZ DEFAULT NOW(),
    feature_snapshot    JSONB NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_l5_pred_entity ON l5_predictions (entity_type, entity_id, predicted_at DESC);
CREATE INDEX IF NOT EXISTS idx_l5_pred_model ON l5_predictions (model_id, predicted_at DESC);

-- LLM audit log
CREATE TABLE IF NOT EXISTS l5_llm_audit (
    id                  BIGSERIAL PRIMARY KEY,
    workflow_type       VARCHAR(50) NOT NULL,
    actor_id            VARCHAR(100) NOT NULL,
    actor_role          VARCHAR(50) NOT NULL DEFAULT 'system',
    model_used          VARCHAR(100) NOT NULL,
    prompt_tokens       INT NOT NULL DEFAULT 0,
    completion_tokens   INT NOT NULL DEFAULT 0,
    objects_accessed    JSONB DEFAULT '[]',
    output_disposition  VARCHAR(50) NOT NULL DEFAULT 'returned',
    prompt_hash         VARCHAR(64),
    success             BOOLEAN NOT NULL DEFAULT TRUE,
    latency_ms          INT NOT NULL DEFAULT 0,
    error_message       TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_l5_llm_audit_workflow ON l5_llm_audit (workflow_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_l5_llm_audit_actor ON l5_llm_audit (actor_id, created_at DESC);

-- Agent execution runs
CREATE TABLE IF NOT EXISTS l5_agent_runs (
    id                  BIGSERIAL PRIMARY KEY,
    run_id              UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    agent_type          VARCHAR(50) NOT NULL,
    actor_id            VARCHAR(100) NOT NULL,
    input_params        JSONB NOT NULL DEFAULT '{}',
    execution_trace     JSONB NOT NULL DEFAULT '[]',
    output_summary      TEXT,
    status              VARCHAR(20) NOT NULL DEFAULT 'running',
    total_tokens        INT DEFAULT 0,
    total_latency_ms    INT DEFAULT 0,
    guardrail_triggers  JSONB DEFAULT '[]',
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    completed_at        TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_l5_agent_runs_type ON l5_agent_runs (agent_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_l5_agent_runs_actor ON l5_agent_runs (actor_id, created_at DESC);

-- Discovered correlations
CREATE TABLE IF NOT EXISTS l5_correlations (
    id                      BIGSERIAL PRIMARY KEY,
    feature_a               VARCHAR(100) NOT NULL,
    feature_b               VARCHAR(100) NOT NULL,
    correlation_coefficient FLOAT NOT NULL,
    p_value                 FLOAT NOT NULL,
    sample_size             INT NOT NULL,
    lag_periods             INT DEFAULT 0,
    entity_type             VARCHAR(50) DEFAULT 'Company',
    computed_at             TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (feature_a, feature_b, lag_periods, entity_type)
);

-- Scenario sandbox runs
CREATE TABLE IF NOT EXISTS l5_scenarios (
    id                  BIGSERIAL PRIMARY KEY,
    scenario_id         UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    scenario_name       VARCHAR(200),
    base_entity_type    VARCHAR(50),
    base_entity_id      VARCHAR(200),
    modifications       JSONB NOT NULL DEFAULT '{}',
    projected_outcomes  JSONB NOT NULL DEFAULT '{}',
    created_by          VARCHAR(100) NOT NULL DEFAULT 'system',
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Analytics: trend results
CREATE TABLE IF NOT EXISTS l5_trend_results (
    id              BIGSERIAL PRIMARY KEY,
    entity_type     VARCHAR(50) NOT NULL,
    entity_id       VARCHAR(200) NOT NULL,
    metric_name     VARCHAR(100) NOT NULL,
    direction       VARCHAR(20) NOT NULL,   -- rising | falling | stable | inflecting
    velocity        FLOAT,
    has_inflection  BOOLEAN DEFAULT FALSE,
    anomaly_score   FLOAT DEFAULT 0.0,
    data_points     JSONB DEFAULT '[]',
    computed_at     TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (entity_type, entity_id, metric_name)
);

-- Analytics: benchmark results
CREATE TABLE IF NOT EXISTS l5_benchmark_results (
    id              BIGSERIAL PRIMARY KEY,
    entity_type     VARCHAR(50) NOT NULL,
    entity_id       VARCHAR(200) NOT NULL,
    metric_name     VARCHAR(100) NOT NULL,
    entity_value    FLOAT,
    sector_p25      FLOAT,
    sector_p50      FLOAT,
    sector_p75      FLOAT,
    percentile_rank FLOAT,
    peer_group      VARCHAR(100),
    computed_at     TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (entity_type, entity_id, metric_name, peer_group)
);

-- Generated reports
CREATE TABLE IF NOT EXISTS l5_reports (
    id              BIGSERIAL PRIMARY KEY,
    report_id       UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    report_type     VARCHAR(50) NOT NULL,
    entity_type     VARCHAR(50),
    entity_id       VARCHAR(200),
    title           VARCHAR(500),
    content_json    JSONB NOT NULL DEFAULT '{}',
    generated_by    VARCHAR(100) NOT NULL DEFAULT 'system',
    agent_run_id    UUID,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_l5_reports_entity ON l5_reports (entity_type, entity_id, created_at DESC);

-- Model training batch runs
CREATE TABLE IF NOT EXISTS l5_training_runs (
    id              BIGSERIAL PRIMARY KEY,
    run_id          UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    model_name      VARCHAR(100) NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'running',
    metrics         JSONB DEFAULT '{}',
    champion_id     UUID,
    challenger_id   UUID,
    promoted        BOOLEAN DEFAULT FALSE,
    started_at      TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);
