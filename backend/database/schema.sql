-- ══════════════════════════════════════════════
-- ESGenuine: PostgreSQL Vector Store Schema
-- ══════════════════════════════════════════════
-- Features:
-- 1. pgvector for semantic search over claim embeddings
-- 2. PARTITION BY LIST (metric_family) for 5-10x speedup
-- 3. HNSW indices per partition for massive scale

CREATE EXTENSION IF NOT EXISTS vector;

-- 0. Destroy the old Week 3 table if it exists
DROP TABLE IF EXISTS claims CASCADE;

-- 1. Create the partitioned parent table
CREATE TABLE IF NOT EXISTS claims (
    claim_id UUID,
    doc_id TEXT,
    page_number INT,
    chunk_id TEXT,
    
    source_sentence TEXT,
    
    aspect TEXT,
    normalized_aspect TEXT,
    
    metric_family TEXT,
    metric_key TEXT,
    
    metric_value FLOAT,
    metric_unit TEXT,
    metric_direction TEXT,
    
    time_start DATE,
    time_end DATE,
    time_bucket TEXT,
    
    location_text TEXT,
    location_scope TEXT,
    
    claim_type TEXT,
    vagueness_score FLOAT,
    groundability_score FLOAT,
    
    claim_signature TEXT,
    
    embedding VECTOR(768),
    PRIMARY KEY (claim_id, metric_family)
) PARTITION BY LIST (metric_family);
-- 2. Create the Partitions (The 5-10x speed trick)
CREATE TABLE IF NOT EXISTS claims_environment 
PARTITION OF claims 
FOR VALUES IN ('environment.emissions', 'environment.energy', 'environment.water', 'environment.waste', 'environment.biodiversity');

CREATE TABLE IF NOT EXISTS claims_social 
PARTITION OF claims 
FOR VALUES IN ('social.diversity', 'social.health_safety', 'social.workforce', 'social.training');

CREATE TABLE IF NOT EXISTS claims_governance 
PARTITION OF claims 
FOR VALUES IN ('governance.board', 'governance.ethics');

CREATE TABLE IF NOT EXISTS claims_uncategorized
PARTITION OF claims
FOR VALUES IN ('uncategorized');

CREATE TABLE IF NOT EXISTS claims_default
PARTITION OF claims
DEFAULT;  -- Catch-all for any other metric families (e.g. emissions.scope1)

-- 3. Create Vector Indexes per partition (HNSW for extreme scale)
CREATE INDEX IF NOT EXISTS claims_environment_embedding_idx 
ON claims_environment USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS claims_social_embedding_idx 
ON claims_social USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS claims_governance_embedding_idx 
ON claims_governance USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS claims_uncategorized_embedding_idx
ON claims_uncategorized USING hnsw (embedding vector_cosine_ops);

-- The DEFAULT partition was missing its embedding index — yet it is the catch-all for
-- families like emissions.scope1 (the most material) and is currently the LARGEST
-- partition. Without this, semantic search seq-scans claims_default at scale while the
-- other partitions use ANN. (Confirmed via verify_search_claims_index.sql on the live DB.)
CREATE INDEX IF NOT EXISTS claims_default_embedding_idx
ON claims_default USING hnsw (embedding vector_cosine_ops);

-- 4. Create the high-speed Signature Index for Bucket blocking
CREATE INDEX IF NOT EXISTS claims_signature_idx 
ON claims (claim_signature);

-- ══════════════════════════════════════════════
-- Phase 3: Cross-Report Columns
-- Enables multi-company, multi-year analysis
-- ══════════════════════════════════════════════

-- 5. Add cross-report identity columns to the claims table
ALTER TABLE claims ADD COLUMN IF NOT EXISTS company_id    TEXT;
ALTER TABLE claims ADD COLUMN IF NOT EXISTS company_name  TEXT;
ALTER TABLE claims ADD COLUMN IF NOT EXISTS report_year   INT;
ALTER TABLE claims ADD COLUMN IF NOT EXISTS report_id     TEXT;

-- 5b. Persist the verification-routing signal the extractor already computes.
-- Values: 'directly_observable' | 'reported_metric' | 'optical_possible' | 'not_observable'.
-- The frontend reads this instead of re-deriving routing from a duplicated keyword list.
ALTER TABLE claims ADD COLUMN IF NOT EXISTS observability_type TEXT;

-- 6. Cross-report compound index  (company + year + signature for fast bucketing)
CREATE INDEX IF NOT EXISTS claims_cross_report_idx
ON claims (company_id, report_year, claim_signature);

-- 7. New reports metadata table
CREATE TABLE IF NOT EXISTS reports (
    report_id         TEXT PRIMARY KEY,
    company_id        TEXT NOT NULL,
    company_name      TEXT NOT NULL,
    report_year       INT  NOT NULL,
    report_type       TEXT DEFAULT 'esg',   -- 'esg' | 'annual' | 'integrated'
    source_url        TEXT,
    file_path         TEXT,
    file_hash         TEXT,                 -- full-file SHA-256; content-hash dedup key for the ingest path
    ingested_at       TIMESTAMPTZ DEFAULT NOW(),
    claim_count       INT  DEFAULT 0
);

CREATE INDEX IF NOT EXISTS reports_company_year_idx
ON reports (company_id, report_year);

-- Fast "have I already ingested this exact PDF?" probe (content-hash dedup).
CREATE INDEX IF NOT EXISTS reports_file_hash_idx
ON reports (file_hash);

-- 8. Human-in-the-loop flag reviews. A reviewer dismisses a false-positive flag (or
-- confirms a valid one); build_report() honors 'dismissed' verdicts to adjust the score
-- (the raw machine score is still recomputed alongside). subject_id is polymorphic:
-- claim_id (per-claim flags) | contradiction hash (CONTRADICTION) | '__report__' (report-level).
CREATE TABLE IF NOT EXISTS claim_reviews (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id      TEXT NOT NULL,
    subject_id  TEXT NOT NULL,
    flag_type   TEXT NOT NULL,
    verdict     TEXT NOT NULL,            -- 'dismissed' | 'confirmed'
    note        TEXT,
    reviewer    TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (doc_id, subject_id, flag_type)
);

CREATE INDEX IF NOT EXISTS claim_reviews_doc_idx ON claim_reviews (doc_id);

-- App uses the anon/publishable key; grant it table privileges (RLS stays disabled).
GRANT SELECT, INSERT, UPDATE, DELETE ON claim_reviews TO anon, authenticated;

-- 9. Durable ingest-job state (was an in-memory dict that died on restart). `detail`
-- holds the full flat job payload the API returns; status/error mirrored for queryability.
CREATE TABLE IF NOT EXISTS jobs (
    job_id       TEXT PRIMARY KEY,
    report_id    TEXT,
    company_name TEXT,
    report_year  INT,
    status       TEXT NOT NULL DEFAULT 'queued',
    error        TEXT,
    detail       JSONB,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS jobs_status_idx ON jobs (status);

GRANT SELECT, INSERT, UPDATE, DELETE ON jobs TO anon, authenticated;

-- 10. Auth users (gates the write endpoints). SECURITY: holds bcrypt password hashes;
-- accessed ONLY by the backend via DATABASE_URL (psycopg2), NEVER the anon key — so anon
-- is explicitly REVOKED (unlike every other table) and the hashes can't be read with the
-- browser-side key.
CREATE TABLE IF NOT EXISTS users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'user',
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

REVOKE ALL ON users FROM anon, authenticated;
