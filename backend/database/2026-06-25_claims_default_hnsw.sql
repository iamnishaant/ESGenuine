-- ═══════════════════════════════════════════════════════════════════════════════
-- Migration 2026-06-25 — add the missing HNSW index on the DEFAULT claims partition
-- ═══════════════════════════════════════════════════════════════════════════════
-- Found by running verify_search_claims_index.sql against the live DB: only 4 of the 5
-- claims partitions had an embedding index (environment/social/governance/uncategorized).
-- claims_default — the catch-all that holds families like emissions.scope1 and is the
-- LARGEST current partition (746 rows) — had none, so it would seq-scan under semantic
-- search at scale while its peers use ANN.
--
-- Safe + idempotent: IF NOT EXISTS, additive (no data change), reversible via DROP INDEX.
-- At current row counts the planner still prefers a seq scan (HNSW per-partition overhead
-- > linear scan on a tiny table); this index is dormant insurance that activates as the
-- partition grows, so the default partition isn't left behind.
CREATE INDEX IF NOT EXISTS claims_default_embedding_idx
ON claims_default USING hnsw (embedding vector_cosine_ops);

-- Verify (should now list 5 hnsw indexes incl. claims_default_embedding_idx):
-- SELECT indexname FROM pg_indexes
-- WHERE tablename LIKE 'claims%' AND indexdef ILIKE '%hnsw%' ORDER BY indexname;
