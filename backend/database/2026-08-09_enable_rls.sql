-- ============================================================================
-- ESGenuine — enable Row Level Security; demote anon to READ-ONLY.
-- Applied: <pending>            Closes TODO.md "Security: enable Supabase RLS".
-- ============================================================================
--
-- WHY THIS EXISTS
-- ---------------
-- The anon/publishable key is embedded in the shipped JavaScript bundle — it is a
-- PUBLIC credential by construction (it is also present in git history at commit
-- 9338e89). Until now the schema granted that public key:
--
--     claim_reviews       SELECT, INSERT, UPDATE, DELETE   (2026-06-25_claim_reviews.sql)
--     contradictions      SELECT, INSERT, DELETE           (2026-07-19_contradictions_doc_id.sql)
--     jobs                SELECT, INSERT, UPDATE, DELETE   (2026-06-26_jobs_table.sql)
--     satellite_evidence  SELECT, INSERT                   (2026-07-11_satellite_evidence.sql)
--     claims / reports    Supabase table defaults
--
-- ...with RLS never enabled on any table. So any visitor could delete every
-- contradiction, or forge `claim_reviews` rows — and reviews DIRECTLY MOVE the
-- published integrity score (build_report() honours 'dismissed' verdicts; live
-- example: Microsoft 44.0 D -> 59.4 C by dismissing 190 NON_GROUNDABLE flags).
-- For a system whose entire product is a trustworthy score, an anonymous score-
-- editing primitive is the most serious defect in the stack.
--
-- MODEL AFTER THIS MIGRATION
-- --------------------------
--   anon / authenticated  -> SELECT only, enforced by both GRANTs and RLS policies.
--   service_role          -> full access; BYPASSES RLS (Supabase built-in).
--
-- Reads are deliberately left fully open: the frontend queries `claims`,
-- `contradictions` and `reports` directly, and this is a public transparency tool.
-- `users` stays fully revoked (bcrypt hashes; 2026-06-26_users_table.sql).
--
-- PREREQUISITE — DO NOT APPLY BEFORE THIS IS SET
-- ----------------------------------------------
-- Set SUPABASE_SERVICE_ROLE_KEY in the backend environment (.env locally, Render
-- env var in deploy). Supabase Dashboard -> Project Settings -> API -> service_role.
-- The backend picks it up automatically, falling back to anon when unset:
--     src/extractors/supabase_ingest.py   (claims / reports / jobs writes)
--     src/extractors/ingest_claims.py     (legacy claims insert)
--     src/reasoning/retrieval.py          (claim_reviews upsert, contradictions r/w)
--     scripts/run_satellite_checks.py     (satellite_evidence insert)
-- NEVER expose the service-role key to the frontend — it bypasses every policy.
--
-- Idempotent: safe to re-run. Reversible — see the rollback block at the bottom.
-- ============================================================================

BEGIN;

-- ── 1. Revoke write privileges from the public roles ────────────────────────
-- RLS alone is not enough: a GRANT without a permissive policy still fails, but
-- removing the GRANT makes the intent explicit and defends if a policy is ever
-- loosened by mistake. Belt and braces.
--
-- REVOKE ALL, not "INSERT, UPDATE, DELETE" — two gaps found in the live audit
-- 2026-08-09 before this was first applied:
--
--   (a) TRUNCATE IS NOT SUBJECT TO RLS. Policies only filter SELECT/INSERT/
--       UPDATE/DELETE; TRUNCATE is a table-level privilege checked before any
--       policy runs. anon actually held TRUNCATE on all 11 tables, so revoking
--       only I/U/D would have left the public key able to wipe the entire
--       1730-claim corpus with RLS "on" and looking correct.
--   (b) REFERENCES / TRIGGER were likewise granted and are likewise unaffected
--       by RLS.
--
-- REVOKE ALL then GRANT SELECT is both stricter and simpler to reason about.
REVOKE ALL PRIVILEGES ON claims             FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON reports            FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON contradictions     FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON claim_reviews      FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON jobs               FROM anon, authenticated;
REVOKE ALL PRIVILEGES ON satellite_evidence FROM anon, authenticated;

-- PARTITIONS CARRY THEIR OWN GRANTS. A REVOKE on the `claims` parent does NOT
-- cascade — the live audit showed claims_default / _environment / _social /
-- _governance / _uncategorized each independently holding
-- DELETE,INSERT,TRUNCATE,UPDATE for anon. Writes routed through the parent are
-- stopped by RLS, but a direct TRUNCATE on a partition is not (see (a) above),
-- so each partition must be revoked explicitly.
DO $$
DECLARE part regclass;
BEGIN
    FOR part IN
        SELECT inhrelid::regclass FROM pg_inherits WHERE inhparent = 'claims'::regclass
    LOOP
        EXECUTE format('REVOKE ALL PRIVILEGES ON %s FROM anon, authenticated', part);
        EXECUTE format('GRANT SELECT ON %s TO anon, authenticated', part);
    END LOOP;
END $$;

-- Sequence USAGE was granted so anon could INSERT; it no longer can.
DO $$
DECLARE seq text;
BEGIN
    FOR seq IN
        SELECT pg_get_serial_sequence(t, 'id')
        FROM unnest(ARRAY['contradictions', 'satellite_evidence']) AS t
        WHERE pg_get_serial_sequence(t, 'id') IS NOT NULL
    LOOP
        EXECUTE format('REVOKE USAGE ON SEQUENCE %s FROM anon, authenticated', seq);
    END LOOP;
END $$;

-- Keep reads working.
GRANT SELECT ON claims, reports, contradictions,
                claim_reviews, jobs, satellite_evidence TO anon, authenticated;

-- ── 2. Enable RLS ───────────────────────────────────────────────────────────
-- NOTE ON `claims`: it is LIST-partitioned (claims_environment / _social /
-- _governance / _uncategorized / _default). Enabling RLS on the parent does NOT
-- cascade to partitions, and a query routed to a partition is checked against
-- THAT partition's RLS. Every partition must be enabled explicitly or the lock
-- is cosmetic — hence the loop over pg_inherits below.
ALTER TABLE claims             ENABLE ROW LEVEL SECURITY;
ALTER TABLE reports            ENABLE ROW LEVEL SECURITY;
ALTER TABLE contradictions     ENABLE ROW LEVEL SECURITY;
ALTER TABLE claim_reviews      ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs               ENABLE ROW LEVEL SECURITY;
ALTER TABLE satellite_evidence ENABLE ROW LEVEL SECURITY;

DO $$
DECLARE part regclass;
BEGIN
    FOR part IN
        SELECT inhrelid::regclass
        FROM pg_inherits
        WHERE inhparent = 'claims'::regclass
    LOOP
        EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', part);
        EXECUTE format(
            'DROP POLICY IF EXISTS %I ON %s',
            'public_read_' || replace(part::text, '.', '_'), part);
        EXECUTE format(
            'CREATE POLICY %I ON %s FOR SELECT TO anon, authenticated USING (true)',
            'public_read_' || replace(part::text, '.', '_'), part);
    END LOOP;
END $$;

-- ── 3. Read-only policies ───────────────────────────────────────────────────
-- FOR SELECT + USING (true) = anyone may read every row, nobody may write.
-- No INSERT/UPDATE/DELETE policy is created, so those are denied for every role
-- subject to RLS. service_role is exempt (BYPASSRLS) and keeps full access.
DROP POLICY IF EXISTS public_read_claims             ON claims;
DROP POLICY IF EXISTS public_read_reports            ON reports;
DROP POLICY IF EXISTS public_read_contradictions     ON contradictions;
DROP POLICY IF EXISTS public_read_claim_reviews      ON claim_reviews;
DROP POLICY IF EXISTS public_read_jobs               ON jobs;
DROP POLICY IF EXISTS public_read_satellite_evidence ON satellite_evidence;

CREATE POLICY public_read_claims             ON claims             FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY public_read_reports            ON reports            FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY public_read_contradictions     ON contradictions     FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY public_read_claim_reviews      ON claim_reviews      FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY public_read_jobs               ON jobs               FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY public_read_satellite_evidence ON satellite_evidence FOR SELECT TO anon, authenticated USING (true);

COMMIT;

-- ── 4. Verify (run after COMMIT; every row should read t / SELECT-only) ─────
-- SELECT c.relname, c.relrowsecurity AS rls_on
-- FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
-- WHERE n.nspname = 'public' AND c.relkind IN ('r','p')
--   AND c.relname IN ('claims','claims_environment','claims_social','claims_governance',
--                     'claims_uncategorized','claims_default','reports','contradictions',
--                     'claim_reviews','jobs','satellite_evidence')
-- ORDER BY 1;
--
-- SELECT tablename, policyname, cmd, roles FROM pg_policies
-- WHERE schemaname = 'public' ORDER BY 1, 2;
--
-- SELECT table_name, grantee, string_agg(privilege_type, ',' ORDER BY privilege_type)
-- FROM information_schema.role_table_grants
-- WHERE grantee IN ('anon','authenticated') AND table_schema = 'public'
-- GROUP BY 1, 2 ORDER BY 1, 2;   -- expect SELECT only

-- ── ROLLBACK (if a write path is found that cannot use service_role) ────────
-- BEGIN;
-- ALTER TABLE claims             DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE reports            DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE contradictions     DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE claim_reviews      DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE jobs               DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE satellite_evidence DISABLE ROW LEVEL SECURITY;
-- DO $$ DECLARE part regclass; BEGIN
--   FOR part IN SELECT inhrelid::regclass FROM pg_inherits WHERE inhparent='claims'::regclass
--   LOOP EXECUTE format('ALTER TABLE %s DISABLE ROW LEVEL SECURITY', part); END LOOP;
-- END $$;
-- -- Restore the pre-migration grants (matches what the live audit found on
-- -- 2026-08-09; note TRUNCATE, which the original per-table GRANTs implied via
-- -- Supabase table defaults):
-- GRANT SELECT, INSERT, UPDATE, DELETE ON claim_reviews, jobs TO anon, authenticated;
-- GRANT SELECT, INSERT, DELETE ON contradictions TO anon;
-- GRANT SELECT, INSERT ON satellite_evidence TO anon;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON claims, reports TO anon, authenticated;
-- DO $$ DECLARE part regclass; BEGIN
--   FOR part IN SELECT inhrelid::regclass FROM pg_inherits WHERE inhparent='claims'::regclass
--   LOOP EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON %s TO anon, authenticated', part);
--   END LOOP;
-- END $$;
-- COMMIT;
--
-- NOTE: rolling back restores an ANONYMOUS WRITE PRIMITIVE on the published
-- score. Prefer fixing the offending write path to use SUPABASE_SERVICE_ROLE_KEY.
