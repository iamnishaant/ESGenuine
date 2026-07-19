-- Contradictions become a maintained, per-document artifact (UI sync fix #3).
--
-- WHY: the live `contradictions` table was written ONCE by the offline
-- integration-test runner (2026-04-08, 20 rows) and never since. The frontend
-- reasoning views (ContradictionExplorer / ClaimGraph / RiskScorePanel) read it
-- directly from Supabase, so they showed pre-#18 false-positive noise
-- ("null and unknown_time") referencing long-deleted claim ids.
--
-- FIX: ingest now persists each report's deterministic numeric contradictions
-- (delete-then-insert by doc_id — same idempotency pattern as claims). This
-- migration gives the table a doc_id to key that replacement, and folds the
-- table into the schema (it was never in schema.sql — created ad hoc).
--
-- Idempotent: safe to re-run.

CREATE TABLE IF NOT EXISTS contradictions (
    id          bigserial PRIMARY KEY,
    claim_a_id  text,
    claim_b_id  text,
    severity    text,
    conflict_type text,
    reasoning   text,
    confidence  double precision,
    created_at  timestamptz DEFAULT now()
);

ALTER TABLE contradictions ADD COLUMN IF NOT EXISTS doc_id text;
CREATE INDEX IF NOT EXISTS contradictions_doc_id_idx ON contradictions (doc_id);

-- The ingest path authenticates as anon (same as claims delete-then-insert).
GRANT SELECT, INSERT, DELETE ON contradictions TO anon;
DO $$
DECLARE seq text;
BEGIN
    seq := pg_get_serial_sequence('contradictions', 'id');
    IF seq IS NOT NULL THEN
        EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE %s TO anon', seq);
    END IF;
END $$;
