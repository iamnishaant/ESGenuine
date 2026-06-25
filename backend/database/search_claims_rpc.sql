-- ══════════════════════════════════════════════
-- ESGenuine: General Semantic Search RPC (NG4 conversational audit)
-- ══════════════════════════════════════════════
-- Unlike match_claims (which blocks by metric_family for contradiction retrieval),
-- this is an open semantic search across all claims for natural-language Q&A.
-- Optionally scoped to a single document.

CREATE OR REPLACE FUNCTION search_claims(
  query_embedding VECTOR(768),
  match_count INT,
  filter_doc TEXT DEFAULT NULL
)
RETURNS TABLE (
  claim_id UUID,
  doc_id TEXT,
  company_name TEXT,
  report_year INT,
  page_number INT,
  source_sentence TEXT,
  metric_key TEXT,
  metric_value DOUBLE PRECISION,
  metric_unit TEXT,
  claim_type TEXT,
  similarity DOUBLE PRECISION
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    c.claim_id,
    c.doc_id,
    c.company_name,
    c.report_year::int,
    c.page_number::int,
    c.source_sentence,
    c.metric_key,
    c.metric_value,
    c.metric_unit,
    c.claim_type,
    (1 - (c.embedding <=> query_embedding))::double precision AS similarity
  FROM claims c
  WHERE (filter_doc IS NULL OR c.doc_id = filter_doc)
  ORDER BY c.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;
