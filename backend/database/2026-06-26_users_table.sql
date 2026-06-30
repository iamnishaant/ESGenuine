-- Migration 2026-06-26: auth users.
-- Apply against the live Supabase DB (Supabase SQL editor or psql).
--
-- SECURITY: this table holds bcrypt password hashes. It is accessed ONLY by the backend
-- via DATABASE_URL (psycopg2), NEVER via the public anon/publishable key. So unlike the
-- other tables, anon is NOT granted access — and is explicitly revoked — so the password
-- hashes can never be read with the browser-side key.

CREATE TABLE IF NOT EXISTS users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'user',
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

REVOKE ALL ON users FROM anon, authenticated;
