-- Migration 002: Multi-tenancy client isolation
-- Adds client_id to ontology_objects and ontology_links so each tenant's
-- data is stored and queried in complete isolation.
--
-- PLATFORM_GLOBAL rows (public Indian registry data: MCA21, IBBI, GSTN, etc.)
-- are readable by every client — see neo4j_store.py for the query pattern.

-- ── ontology_objects ────────────────────────────────────────────────────────

ALTER TABLE ontology_objects
    ADD COLUMN IF NOT EXISTS client_id VARCHAR(100) NOT NULL DEFAULT 'PLATFORM_GLOBAL';

-- Replace the old (object_type, primary_key) unique constraint with the
-- tenant-aware triple so two clients can each hold the same CIN/DIN.
ALTER TABLE ontology_objects
    DROP CONSTRAINT IF EXISTS ontology_objects_object_type_primary_key_key;

ALTER TABLE ontology_objects
    ADD CONSTRAINT IF NOT EXISTS ontology_objects_tenant_pk_unique
    UNIQUE (object_type, primary_key, client_id);

CREATE INDEX IF NOT EXISTS idx_objects_client_id
    ON ontology_objects (client_id);

CREATE INDEX IF NOT EXISTS idx_objects_type_client
    ON ontology_objects (object_type, client_id);

-- ── ontology_links ───────────────────────────────────────────────────────────

ALTER TABLE ontology_links
    ADD COLUMN IF NOT EXISTS client_id VARCHAR(100) NOT NULL DEFAULT 'PLATFORM_GLOBAL';

CREATE INDEX IF NOT EXISTS idx_links_client_id
    ON ontology_links (client_id);
