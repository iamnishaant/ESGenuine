-- Satellite Evidence v2: one row per satellite verification run of a claim.
-- The bundle is the committed evidence (scene IDs, pixel-array hashes, params,
-- numbers, verdict); bundle_sha256 is reproducible by re-running the pipeline
-- on the same scenes. Idempotent; safe on the live DB any time.
CREATE TABLE IF NOT EXISTS satellite_evidence (
    id           BIGSERIAL PRIMARY KEY,
    claim_id     UUID NOT NULL,
    report_id    TEXT,
    verdict      TEXT NOT NULL CHECK (verdict IN ('supported', 'not_supported', 'inconclusive')),
    reason       TEXT,
    ndvi_delta   DOUBLE PRECISION,
    z_score      DOUBLE PRECISION,
    bundle       JSONB NOT NULL,
    bundle_sha256 CHAR(64) NOT NULL,
    checked_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS satellite_evidence_claim_idx ON satellite_evidence (claim_id);
CREATE INDEX IF NOT EXISTS satellite_evidence_report_idx ON satellite_evidence (report_id);
GRANT SELECT, INSERT ON satellite_evidence TO anon;
GRANT USAGE ON SEQUENCE satellite_evidence_id_seq TO anon;
