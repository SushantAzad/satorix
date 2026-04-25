-- Layer 3 Ontology Schema Migration 001
-- Creates all PostgreSQL tables for the ontology layer

CREATE TABLE IF NOT EXISTS ontology_object_types (
    api_name VARCHAR(100) PRIMARY KEY,
    display_name VARCHAR(200) NOT NULL,
    plural_name VARCHAR(200) NOT NULL,
    description TEXT,
    primary_key_field VARCHAR(100) NOT NULL,
    datasource_mapping JSONB DEFAULT '{}',
    properties JSONB DEFAULT '[]',
    interfaces JSONB DEFAULT '[]',
    version VARCHAR(20) DEFAULT '1.0.0',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS ontology_property_definitions (
    id SERIAL PRIMARY KEY,
    object_type VARCHAR(100) NOT NULL,
    property_name VARCHAR(100) NOT NULL,
    display_name VARCHAR(200),
    data_type VARCHAR(50) NOT NULL,
    is_required BOOLEAN DEFAULT FALSE,
    is_immutable BOOLEAN DEFAULT FALSE,
    is_derived BOOLEAN DEFAULT FALSE,
    is_user_editable BOOLEAN DEFAULT TRUE,
    allowed_values JSONB,
    default_value TEXT,
    description TEXT,
    security_classification VARCHAR(50) DEFAULT 'standard',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(object_type, property_name)
);

CREATE TABLE IF NOT EXISTS ontology_link_types (
    api_name VARCHAR(100) PRIMARY KEY,
    display_name VARCHAR(200) NOT NULL,
    source_object_type VARCHAR(100) NOT NULL,
    target_object_type VARCHAR(100) NOT NULL,
    is_directed BOOLEAN DEFAULT TRUE,
    is_inferred BOOLEAN DEFAULT FALSE,
    inference_rule TEXT,
    properties JSONB DEFAULT '[]',
    cardinality VARCHAR(20) DEFAULT 'many-to-many',
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ontology_interfaces (
    api_name VARCHAR(100) PRIMARY KEY,
    display_name VARCHAR(200) NOT NULL,
    implementing_types JSONB DEFAULT '[]',
    shared_properties JSONB DEFAULT '[]',
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ontology_schema_versions (
    id SERIAL PRIMARY KEY,
    version VARCHAR(20) NOT NULL,
    major INTEGER NOT NULL,
    minor INTEGER NOT NULL,
    patch INTEGER NOT NULL,
    changelog TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by VARCHAR(100),
    is_current BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS ontology_datasource_mappings (
    id SERIAL PRIMARY KEY,
    object_type VARCHAR(100) NOT NULL,
    source_id VARCHAR(200) NOT NULL,
    column_mappings JSONB NOT NULL,
    transform_rules JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(object_type, source_id)
);

-- Object instance store (one generic table, typed by object_type)
CREATE TABLE IF NOT EXISTS ontology_objects (
    id SERIAL PRIMARY KEY,
    object_type VARCHAR(100) NOT NULL,
    primary_key VARCHAR(500) NOT NULL,
    properties JSONB NOT NULL DEFAULT '{}',
    data_hash VARCHAR(64),
    version INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    is_deleted BOOLEAN DEFAULT FALSE,
    UNIQUE(object_type, primary_key)
);

CREATE INDEX IF NOT EXISTS idx_objects_type ON ontology_objects(object_type);
CREATE INDEX IF NOT EXISTS idx_objects_type_pk ON ontology_objects(object_type, primary_key);
CREATE INDEX IF NOT EXISTS idx_objects_updated ON ontology_objects(updated_at);

-- Link instance store
CREATE TABLE IF NOT EXISTS ontology_links (
    id SERIAL PRIMARY KEY,
    link_type VARCHAR(100) NOT NULL,
    source_type VARCHAR(100) NOT NULL,
    source_id VARCHAR(500) NOT NULL,
    target_type VARCHAR(100) NOT NULL,
    target_id VARCHAR(500) NOT NULL,
    properties JSONB DEFAULT '{}',
    is_inferred BOOLEAN DEFAULT FALSE,
    inferred_by VARCHAR(200),
    inference_confidence FLOAT,
    version INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    is_deleted BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_links_type ON ontology_links(link_type);
CREATE INDEX IF NOT EXISTS idx_links_source ON ontology_links(source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_links_target ON ontology_links(target_type, target_id);

-- Event store (append-only)
CREATE TABLE IF NOT EXISTS ontology_events (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    object_type VARCHAR(100) NOT NULL,
    object_id VARCHAR(500) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    property_name VARCHAR(200),
    old_value JSONB,
    new_value JSONB,
    actor_id VARCHAR(200) NOT NULL,
    source VARCHAR(200) NOT NULL,
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_events_object ON ontology_events(object_type, object_id);
CREATE INDEX IF NOT EXISTS idx_events_occurred ON ontology_events(occurred_at);
CREATE INDEX IF NOT EXISTS idx_events_type ON ontology_events(event_type);

-- Audit log (immutable, write-only from application)
CREATE TABLE IF NOT EXISTS ontology_audit_log (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actor_id VARCHAR(200) NOT NULL,
    actor_role VARCHAR(100),
    action_type VARCHAR(100) NOT NULL,
    object_type VARCHAR(100),
    object_id VARCHAR(500),
    properties_accessed JSONB,
    old_value JSONB,
    new_value JSONB,
    ip_address VARCHAR(50),
    session_id VARCHAR(200),
    success BOOLEAN NOT NULL DEFAULT TRUE,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_actor ON ontology_audit_log(actor_id);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON ontology_audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_object ON ontology_audit_log(object_type, object_id);

-- Action history
CREATE TABLE IF NOT EXISTS ontology_action_history (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    action_type VARCHAR(100) NOT NULL,
    actor_id VARCHAR(200) NOT NULL,
    actor_role VARCHAR(100),
    parameters JSONB DEFAULT '{}',
    result JSONB DEFAULT '{}',
    status VARCHAR(50) NOT NULL,
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    error_message TEXT,
    approval_required BOOLEAN DEFAULT FALSE,
    approved_by VARCHAR(200),
    approved_at TIMESTAMPTZ
);

-- Object sets
CREATE TABLE IF NOT EXISTS ontology_object_sets (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    name VARCHAR(300) NOT NULL,
    description TEXT,
    set_type VARCHAR(20) NOT NULL CHECK (set_type IN ('static', 'dynamic')),
    object_type VARCHAR(100) NOT NULL,
    filter_definition JSONB,
    static_members JSONB,
    created_by VARCHAR(200),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Insert initial schema version
INSERT INTO ontology_schema_versions (version, major, minor, patch, changelog, created_by)
VALUES ('1.0.0', 1, 0, 0, 'Initial Layer 3 Ontology schema', 'system')
ON CONFLICT DO NOTHING;
