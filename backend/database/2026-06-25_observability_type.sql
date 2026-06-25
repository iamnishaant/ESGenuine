-- Migration 2026-06-25: persist observability_type on claims.
-- Apply against the live Supabase DB (Supabase SQL editor or psql) BEFORE the next
-- ingest — PostgREST rejects inserts that reference a column the table doesn't have,
-- so ingest will 400 until this runs.
--
-- The extractor (GroundabilityClassifier.score) already computes observability_type
-- per claim; it was being thrown away. The frontend verification-method router now
-- reads this column instead of re-deriving routing from a duplicated keyword list.
-- Values: 'directly_observable' | 'reported_metric' | 'optical_possible' | 'not_observable'.

ALTER TABLE claims ADD COLUMN IF NOT EXISTS observability_type TEXT;
