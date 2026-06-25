-- Migration 2026-06-25: content-hash dedup for the ingest path.
-- Apply against the live Supabase DB (Supabase SQL editor or psql) BEFORE the next
-- ingest. The ingest path now (a) records the full-file SHA-256 on the reports row and
-- (b) short-circuits a re-upload of the identical PDF instead of duplicating claims.
-- PostgREST rejects upserts that reference a column the table doesn't have, so the
-- reports upsert will 400 until this runs.
--
-- file_hash is the same digest Step0_IngestTriage already computes per PDF
-- (sha256 of the whole file). The index makes the "have I seen this exact file?"
-- lookup an index probe rather than a table scan.

ALTER TABLE reports ADD COLUMN IF NOT EXISTS file_hash TEXT;

CREATE INDEX IF NOT EXISTS reports_file_hash_idx ON reports (file_hash);
