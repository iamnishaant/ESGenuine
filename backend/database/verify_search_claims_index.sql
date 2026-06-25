-- ═══════════════════════════════════════════════════════════════════════════════
-- ESGenuine — verify the ANN (HNSW) index path for semantic search
-- ═══════════════════════════════════════════════════════════════════════════════
-- Context (self_improvement.md, corrected New #4): the original review claimed
-- `search_claims` does a full scan with "no ANN index". That premise is WRONG —
-- schema.sql already creates per-partition HNSW indexes (vector_cosine_ops) that match
-- the RPC's `<=>` (cosine-distance) operator. There is nothing to *add*. What remains is
-- to CONFIRM, on the live DB, that the planner actually uses them. Run this in the
-- Supabase SQL editor (or psql). It does not modify anything.

-- ── 1. The indexes exist, with the right method + operator class ──────────────────
-- Expect one HNSW index per claims partition, all using vector_cosine_ops.
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename LIKE 'claims%'
  AND indexdef ILIKE '%hnsw%'
ORDER BY indexname;

-- ── 2. Planner choice for the body of search_claims (global / filter_doc = NULL) ──
-- WHAT TO LOOK FOR:
--   GOOD  →  "Index Scan using claims_<part>_embedding_idx" on each partition (HNSW used).
--   BAD   →  "Seq Scan on claims_<part>" followed by a "Sort" node (full scan + sort).
-- Note: a scalar-subquery probe (below) is usually treated as a constant by the planner,
-- but if you see a Seq Scan, re-run with a literal vector (psql: capture one via \gset)
-- to rule out the subquery form defeating the index.
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
WITH probe AS (SELECT embedding AS q FROM claims WHERE embedding IS NOT NULL LIMIT 1)
SELECT c.claim_id,
       c.doc_id,
       (1 - (c.embedding <=> (SELECT q FROM probe)))::float8 AS similarity
FROM claims c
ORDER BY c.embedding <=> (SELECT q FROM probe)
LIMIT 10;

-- ── 3. Doc-scoped variant (the `filter_doc = <doc>` path) ─────────────────────────
-- HNSW cannot pre-filter on doc_id, so the planner must either (a) post-filter the ANN
-- results (risking under-return when the top-k are all from other docs) or (b) fall back
-- to a filtered scan. If this path matters at scale, split search_claims into two query
-- forms (one global, one with a WHERE doc_id = ... that uses a btree on doc_id) rather
-- than the single `filter_doc IS NULL OR c.doc_id = filter_doc` predicate.
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
WITH probe AS (SELECT embedding AS q, doc_id FROM claims WHERE embedding IS NOT NULL LIMIT 1)
SELECT c.claim_id
FROM claims c, probe
WHERE c.doc_id = probe.doc_id
ORDER BY c.embedding <=> probe.q
LIMIT 10;

-- ── 4. (Optional) tune recall/latency for HNSW at query time ──────────────────────
-- Higher ef_search = better recall, slower. Default is 40. Uncomment to experiment:
-- SET hnsw.ef_search = 100;
