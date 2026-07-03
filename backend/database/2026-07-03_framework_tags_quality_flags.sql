-- Per-claim regulatory framework tags (GRI/ESRS/TCFD clause IDs) + quality-gate flags.
-- Idempotent; safe to run on the live DB any time. Ingest writes these columns when
-- present and gracefully retries without them when absent, so ordering is flexible —
-- but apply before the next ingest to persist the new fields.
ALTER TABLE claims ADD COLUMN IF NOT EXISTS framework_tags TEXT[] DEFAULT '{}';
ALTER TABLE claims ADD COLUMN IF NOT EXISTS quality_flags  TEXT[] DEFAULT '{}';

COMMENT ON COLUMN claims.framework_tags IS
  'Disclosure-framework clause IDs the claim reports against, e.g. {GRI 305-1, ESRS E1-6}. Deterministic (extractors/frameworks.py).';
COMMENT ON COLUMN claims.quality_flags IS
  'Post-extraction quality-gate corrections/suspicions, e.g. {scope_fixed, value_not_in_source} (extractors/quality_gate.py).';
