-- ══════════════════════════════════════════════
-- ESGenuine: Vector Similarity Search RPC
-- ══════════════════════════════════════════════
-- Description:
-- Performs Stanford Metric Signature Blocking by searching
-- for similar embeddings ONLY within a predefined metric_family.
--
-- NOTE (#1/#7): the return set now includes the numeric/temporal/scope fields
-- (metric_key, metric_value, metric_unit, metric_direction, time_bucket,
-- location_scope) that the contradiction engine needs. The previous version
-- returned only source_sentence/vagueness/claim_type, starving _numeric_conflict
-- of the values it compares.
--
-- Usage: Called from Python via Supabase:
-- supabase.rpc('match_claims', {'query_embedding': [...], 'filter_family': 'emissions', ...})

CREATE OR REPLACE FUNCTION match_claims(
  query_embedding VECTOR(768),
  filter_family TEXT,
  match_threshold FLOAT,
  match_count INT,
  exclude_claim_id UUID DEFAULT NULL
)
RETURNS TABLE (
  claim_id UUID,
  doc_id TEXT,
  metric_family TEXT,
  metric_key TEXT,
  source_sentence TEXT,
  metric_value DOUBLE PRECISION,
  metric_unit TEXT,
  metric_direction TEXT,
  time_bucket TEXT,
  location_scope TEXT,
  vagueness_score DOUBLE PRECISION,
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
    c.metric_family,
    c.metric_key,
    c.source_sentence,
    c.metric_value,
    c.metric_unit,
    c.metric_direction,
    c.time_bucket,
    c.location_scope,
    c.vagueness_score,
    c.claim_type,
    (1 - (c.embedding <=> query_embedding))::double precision AS similarity
  FROM claims c
  WHERE
    -- 1. Apply Stanford Signature Blocking Trick (only compare within the bucket)
    c.metric_family = filter_family

    -- 2. Prevent the claim from matching with itself
    AND (exclude_claim_id IS NULL OR c.claim_id != exclude_claim_id)

    -- 3. Only return high semantic matches
    AND 1 - (c.embedding <=> query_embedding) > match_threshold
  ORDER BY similarity DESC
  LIMIT match_count;
END;
$$;
