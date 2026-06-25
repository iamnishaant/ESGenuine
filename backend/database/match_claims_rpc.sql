-- ══════════════════════════════════════════════
-- ESGenuine: Vector Similarity Search RPC
-- ══════════════════════════════════════════════
-- Description:
-- Performs Stanford Metric Signature Blocking by searching 
-- for similar embeddings ONLY within a predefined metric_family.
-- 
-- Usage: Called from Python via Supabase:
-- supabase.rpc('match_claims', {'query_embedding': [...], 'filter_family': 'environmental.emissions'})

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
  source_sentence TEXT,
  vagueness_score FLOAT,
  claim_type TEXT,
  similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT 
    c.claim_id,
    c.doc_id,
    c.metric_family,
    c.source_sentence,
    c.vagueness_score,
    c.claim_type,
    1 - (c.embedding <=> query_embedding) AS similarity
  FROM claims c
  WHERE 
    -- 1. Apply Stanford Signature Blocking Trick (Only compare within the bucket)
    c.metric_family = filter_family
    
    -- 2. Prevent the claim from matching with itself
    AND (exclude_claim_id IS NULL OR c.claim_id != exclude_claim_id)
    
    -- 3. Only return high semantic matches
    AND 1 - (c.embedding <=> query_embedding) > match_threshold
  ORDER BY similarity DESC
  LIMIT match_count;
END;
$$;
