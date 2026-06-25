-- Migration 2026-06-25: human-in-the-loop flag review.
-- Apply against the live Supabase DB (Supabase SQL editor or psql).
--
-- Stores a reviewer's verdict on a single flagged item so the integrity score can be
-- adjusted by human judgment. `build_report(..., reviews=...)` reads these rows: a
-- 'dismissed' verdict removes that item from its flag's count (prevalence drops ->
-- penalty drops -> grade rises). The raw machine score is always recomputed too, so a
-- review can refine but never silently hide the original score.
--
-- subject_id is polymorphic by flag kind:
--   * per-claim flags (VAGUE, NON_GROUNDABLE, ...) -> the claim's claim_id (uuid as text)
--   * CONTRADICTION                                -> a short stable hash of its reasoning
--   * report-level flags (DISCLOSURE_GAP, ASPIRATIONAL_HEAVY) -> the literal '__report__'
-- The unique key lets a re-review upsert (one current verdict per item).

CREATE TABLE IF NOT EXISTS claim_reviews (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id      TEXT NOT NULL,
    subject_id  TEXT NOT NULL,
    flag_type   TEXT NOT NULL,
    verdict     TEXT NOT NULL,            -- 'dismissed' (false positive, +score) | 'confirmed' (valid)
    note        TEXT,
    reviewer    TEXT,                     -- optional free-text; no auth system in v1
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (doc_id, subject_id, flag_type)
);

CREATE INDEX IF NOT EXISTS claim_reviews_doc_idx ON claim_reviews (doc_id);

-- The app (backend + frontend) talks to Supabase with the anon/publishable key, so anon
-- needs table privileges (a fresh table grants none by default). RLS stays disabled here,
-- matching the rest of the schema (see existing_issues.md RLS note).
GRANT SELECT, INSERT, UPDATE, DELETE ON claim_reviews TO anon, authenticated;
