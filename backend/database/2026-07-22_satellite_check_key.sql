-- Satellite evidence survives re-ingests (existing_issues #21e).
--
-- WHY: `satellite_evidence.claim_id` referenced the claims' uuid, but every ingest
-- is delete-then-insert with a fresh uuid4 — so each re-ingest orphaned ALL stored
-- verdicts (0/50 still linked after the round-3 re-ingests), and the UI panel showed
-- stale numbers computed on claims that no longer exist.
--
-- FIX: add a stable `check_key` = sha256(report_id|normalized_aspect|location_text|
-- time_bucket)[:16] — invariant for the same semantic claim across re-ingests. The
-- runner writes it; `_satellite_for` re-links stored rows to the current claim_id via
-- it and drops rows whose claim is gone, so the panel self-heals.
--
-- Idempotent.

ALTER TABLE satellite_evidence ADD COLUMN IF NOT EXISTS check_key text;
CREATE INDEX IF NOT EXISTS satellite_evidence_check_key_idx ON satellite_evidence (check_key);

-- Purge the 141 early/test rows with no report linkage (report_id NULL) — they can
-- never attach to a report and only bloat the evidence log.
DELETE FROM satellite_evidence WHERE report_id IS NULL;
