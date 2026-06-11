-- =============================================================================
-- Satorix Layer 6 — Database Schema
-- PostgreSQL 14+
--
-- Tables:
--   l6_users          Platform users (JWT auth)
--   l6_watchlists     Per-user entity watchlists
--   l6_report_cache   Cached generated reports (24h TTL)
--   l6_recent_views   Last 20 viewed entities per user
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ---------------------------------------------------------------------------
-- l6_users
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS l6_users (
    id              UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),
    email           VARCHAR(255)    NOT NULL,
    name            VARCHAR(255)    NOT NULL,
    password_hash   VARCHAR(255)    NOT NULL,
    role            VARCHAR(100)    NOT NULL DEFAULT 'analyst',
    client_id       VARCHAR(100),
    is_active       BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    last_login      TIMESTAMPTZ,

    CONSTRAINT l6_users_email_unique UNIQUE (email)
);

CREATE INDEX IF NOT EXISTS idx_l6_users_email       ON l6_users (email);
CREATE INDEX IF NOT EXISTS idx_l6_users_role        ON l6_users (role);
CREATE INDEX IF NOT EXISTS idx_l6_users_client_id   ON l6_users (client_id);

-- ---------------------------------------------------------------------------
-- l6_watchlists
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS l6_watchlists (
    id              UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID            NOT NULL REFERENCES l6_users(id) ON DELETE CASCADE,
    entity_type     VARCHAR(100)    NOT NULL,
    entity_id       VARCHAR(255)    NOT NULL,
    entity_name     VARCHAR(500),
    added_at        TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    notes           TEXT,

    CONSTRAINT uq_watchlist_entry UNIQUE (user_id, entity_type, entity_id)
);

CREATE INDEX IF NOT EXISTS idx_l6_watchlists_user_id     ON l6_watchlists (user_id);
CREATE INDEX IF NOT EXISTS idx_l6_watchlists_entity      ON l6_watchlists (entity_type, entity_id);

-- ---------------------------------------------------------------------------
-- l6_report_cache
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS l6_report_cache (
    id              UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID            NOT NULL REFERENCES l6_users(id) ON DELETE CASCADE,
    entity_type     VARCHAR(100)    NOT NULL,
    entity_id       VARCHAR(255)    NOT NULL,
    report_type     VARCHAR(100)    NOT NULL,
    report_content  JSONB,
    generated_at    TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_l6_report_cache_user_id  ON l6_report_cache (user_id);
CREATE INDEX IF NOT EXISTS idx_l6_report_cache_entity   ON l6_report_cache (entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_l6_report_cache_expires  ON l6_report_cache (expires_at);

-- ---------------------------------------------------------------------------
-- l6_recent_views
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS l6_recent_views (
    id              UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID            NOT NULL REFERENCES l6_users(id) ON DELETE CASCADE,
    entity_type     VARCHAR(100)    NOT NULL,
    entity_id       VARCHAR(255)    NOT NULL,
    entity_name     VARCHAR(500),
    risk_score      INTEGER,
    viewed_at       TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_l6_recent_views_user_id  ON l6_recent_views (user_id);
CREATE INDEX IF NOT EXISTS idx_l6_recent_views_viewed   ON l6_recent_views (user_id, viewed_at DESC);
CREATE INDEX IF NOT EXISTS idx_l6_recent_views_entity   ON l6_recent_views (entity_type, entity_id);

-- ---------------------------------------------------------------------------
-- Seed: default platform administrator
-- password: SatorixAdmin2026!
-- bcrypt hash (12 rounds): $2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TiGniYE6Vc638tFSdJX2X0Vg.rui
-- ---------------------------------------------------------------------------
INSERT INTO l6_users (id, email, name, password_hash, role, is_active, created_at)
VALUES (
    uuid_generate_v4(),
    'admin@satorix.internal',
    'Platform Administrator',
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TiGniYE6Vc638tFSdJX2X0Vg.rui',
    'platform_administrator',
    TRUE,
    NOW()
)
ON CONFLICT (email) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Optional: seed demo analyst user (password: Demo@2026)
-- bcrypt hash: $2b$12$92IXUNpkjO0rOQ5byMi.Ye4oKoEa3Ro9llC/.og/at2.uO5lp2e/a
-- ---------------------------------------------------------------------------
INSERT INTO l6_users (id, email, name, password_hash, role, is_active, created_at)
VALUES (
    uuid_generate_v4(),
    'analyst@satorix.internal',
    'Demo Analyst',
    '$2b$12$92IXUNpkjO0rOQ5byMi.Ye4oKoEa3Ro9llC/.og/at2.uO5lp2e/a',
    'analyst',
    TRUE,
    NOW()
)
ON CONFLICT (email) DO NOTHING;

-- =============================================================================
-- End of l6_schema.sql
-- =============================================================================
