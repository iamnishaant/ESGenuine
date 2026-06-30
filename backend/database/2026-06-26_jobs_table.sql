-- Migration 2026-06-26: persist ingest job state.
-- Apply against the live Supabase DB (Supabase SQL editor or psql).
--
-- The /v1/reports/ingest endpoint spawns a background job and reports progress via
-- /v1/jobs/{job_id}. That state lived only in an in-memory dict, so it vanished on a
-- server restart and could not be shared across worker processes. This table makes job
-- state durable + multi-worker-safe. `detail` holds the full flat job payload (the exact
-- shape the API returns); status/error are mirrored to columns for queryability.

CREATE TABLE IF NOT EXISTS jobs (
    job_id       TEXT PRIMARY KEY,
    report_id    TEXT,
    company_name TEXT,
    report_year  INT,
    status       TEXT NOT NULL DEFAULT 'queued',
    error        TEXT,
    detail       JSONB,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS jobs_status_idx ON jobs (status);

-- App talks to Supabase with the anon/publishable key; grant it table privileges
-- (RLS stays disabled, matching the rest of the schema).
GRANT SELECT, INSERT, UPDATE, DELETE ON jobs TO anon, authenticated;
