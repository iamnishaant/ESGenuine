// FastAPI client for the next-gen analysis endpoints (integrity, fact-check,
// benchmarking, agentic audit). Reads VITE_API_BASE, falls back to local dev.

// Scheme-tolerant: a host-only value (e.g. Render's `fromService` host property,
// "esgenuine-backend.onrender.com") is upgraded to https; a full URL is used as-is;
// a trailing slash is trimmed so `${API_BASE}${path}` never double-slashes.
function resolveApiBase(v?: string): string {
  if (!v) return 'http://localhost:8000';
  const withScheme = /^https?:\/\//.test(v) ? v : `https://${v}`;
  return withScheme.replace(/\/+$/, '');
}
export const API_BASE = resolveApiBase(import.meta.env.VITE_API_BASE as string);

// ── auth token (Bearer) ──────────────────────────────────────────────────────
const TOKEN_KEY = 'esg_access_token';
export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (t: string | null) =>
  t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY);

function authHeaders(): Record<string, string> {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { headers: { ...authHeaders() } });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} on ${path}`);
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} on ${path}`);
  return res.json() as Promise<T>;
}

// ── types (loose; backend is source of truth) ────────────────────────────────
export interface GreenwashFlag {
  type: string; severity: string; title: string; description: string;
  regulations: string[]; recommendation: string;
  evidence: Array<Record<string, unknown>>; count: number;
}
export interface VerificationProfile { imagery: number; data_crosscheck: number; document_review: number; }
export interface PenaltyBreakdownItem {
  type: string; title: string; severity: string; count: number; points_deducted: number;
  prevalence?: number;   // fraction of claims that triggered the flag (drives the penalty)
}
export interface IntegrityStatistics {
  by_type?: Record<string, number>;
  with_metric?: number; with_metric_pct?: number;
  avg_groundability?: number | null; contradictions?: number;
  verification_profile?: VerificationProfile;
}
export interface SatelliteBlock {
  checked: number; supported: number; not_supported: number; inconclusive: number; bonus: number;
}
export interface IntegrityReport {
  status: string;
  meta?: { company_name?: string; report_year?: number; doc_id?: string; total_claims?: number };
  integrity_score?: number; grade?: string; greenwashing_risk?: string; summary?: string;
  // v2.3: independent satellite-observation channel (Sentinel-2 NDVI, hash-committed)
  satellite?: SatelliteBlock | null;
  // Pre-review machine score + how many reviewer dismissals moved it (raw == adjusted when 0).
  integrity_score_raw?: number; grade_raw?: string; reviews_applied?: number;
  statistics?: IntegrityStatistics;
  flag_summary?: { total: number; by_severity: Record<string, number> };
  penalty_breakdown?: PenaltyBreakdownItem[];
  flags: GreenwashFlag[];
  recommendations: Array<{ severity: string; action: string; for: string }>;
  computed_at?: string; report_version?: string;
}
export interface FactCheckResult {
  claim_id: string; claim_text: string; metric_key: string; reference_year: string;
  claim_value: number | null; claim_unit: string | null;
  observability_type?: string | null; materiality?: number;
  evidence_quality?: 'verified' | 'self_reported' | 'illustrative' | 'unverified' | null;
  verdict: 'SUPPORTED' | 'CONTRADICTED' | 'UNVERIFIED'; confidence: number;
  reasoning: string; evidence: Array<Record<string, unknown>>;
}
export interface CorpusQuality {
  total: number;
  by_quality: { verified: number; self_reported: number; illustrative: number; unverified: number };
  illustrative_only: boolean;
}
export interface FactCheckReport {
  checked: number; checkable?: number; coverage?: number | null;
  verdict_counts: Record<string, number>;
  credibility: number | null; weighted_credibility?: number | null;
  corpus_quality?: CorpusQuality;
  llm_assisted?: number; results: FactCheckResult[];
}
export interface ScorecardMetric {
  metric_key: string; polarity: string; unit: string | null; value: number;
  rank: number; of: number; percentile: number; peer_median: number; verdict: string;
}
export interface Scorecard { company: string; metrics_compared: number; metrics: ScorecardMetric[]; }
export interface PortfolioIntegrity {
  company_id: string; company_name: string; report_year: number | null; doc_id: string | null;
  integrity_score: number | null; grade: string | null; greenwashing_risk: string | null;
  total_claims: number;
}
export interface AskAnswer {
  question: string; answer: string; engine: string;
  citations: Array<{ n: number; company: string; year: number; page: number; doc_id: string; text: string; similarity: number }>;
  top_similarity?: number; low_relevance?: boolean; unsupported_citations?: number[];
}

// ── endpoint wrappers ────────────────────────────────────────────────────────
// ── auth (Bearer; gates the write endpoints) ─────────────────────────────────
export interface AuthSession {
  access_token: string; refresh_token: string; token_type: string; email: string; role: string;
}
async function _authPost(path: string, email: string, password: string): Promise<AuthSession> {
  const s = await post<AuthSession>(path, { email, password });
  setToken(s.access_token);
  return s;
}
export const login = (email: string, password: string) => _authPost('/v1/auth/login', email, password);
export const register = (email: string, password: string) => _authPost('/v1/auth/register', email, password);
export const me = () => get<{ email: string; role: string }>('/v1/auth/me');
export const logout = () => setToken(null);

// ── human-in-the-loop flag review ────────────────────────────────────────────
export interface ReviewItem {
  subject_id: string;          // claim_id | contradiction hash | '__report__'
  flag_type: string;
  kind: 'claim' | 'contradiction' | 'report';
  title: string;
  reason: string;
  source_sentence?: string | null;
  page_number?: number | null;
  verdict?: 'dismissed' | 'confirmed' | null;
  note?: string | null;
}
export interface ReviewQueue { doc_id: string; total: number; reviewed: number; items: ReviewItem[]; }
export interface ReviewInput {
  subject_id: string; flag_type: string;
  verdict: 'dismissed' | 'confirmed'; note?: string; reviewer?: string;
}
export const getReviewQueue = (docId: string) => get<ReviewQueue>(`/reports/${docId}/review-queue`);
export const postReview = (docId: string, body: ReviewInput) =>
  post<{ status: string } & ReviewInput>(`/reports/${docId}/reviews`, body);

export const getIntegrityReport = (docId: string) => get<IntegrityReport>(`/reports/${docId}/integrity-report`);
export const getGreenwashingFlags = (docId: string) => get<{ total_flags: number; flags: GreenwashFlag[] }>(`/reports/${docId}/greenwashing-flags`);
export const getFactCheck = (docId: string, limit = 50) => get<FactCheckReport>(`/reports/${docId}/fact-check?limit=${limit}`);
export const getScorecard = (companyId: string) => get<Scorecard>(`/benchmark/company/${companyId}`);
// Single source of truth for the headline Integrity Score: same build_report() the
// Integrity Audit page uses, so Portfolio and Integrity Audit never disagree.
export const getPortfolioIntegrity = () =>
  get<{ count: number; companies: PortfolioIntegrity[] }>(`/reports/portfolio/integrity`);
// ── cross-company benchmark ──────────────────────────────────────────────────
export interface BenchmarkEntry { company: string; year: number; value: number; unit: string | null; rank?: number }
export interface CrossCompany {
  metric_key: string; polarity: string; entries: BenchmarkEntry[]; n: number;
  unit?: string | null; median?: number; best?: BenchmarkEntry; worst?: BenchmarkEntry;
  dropped_units?: number;
}
export const getCrossCompany = (metricKey: string, year?: number) =>
  get<CrossCompany>(`/benchmark/metric/${metricKey}${year ? `?year=${year}` : ''}`);

export interface TrajectoryPoint { year: number; value: number; unit: string | null }
export interface Trajectory {
  company: string; metric_key: string; polarity: string;
  series: TrajectoryPoint[]; points: number;
  change?: number; change_pct?: number | null; trend?: string;
}
export const getTrajectory2 = (companyId: string, metricKey: string) =>
  get<Trajectory>(`/benchmark/trajectory/${companyId}/${metricKey}`);

export const getTrajectory = (companyId: string, metricKey: string, targetValue?: number, targetYear?: number) => {
  const q = new URLSearchParams();
  if (targetValue != null) q.set('target_value', String(targetValue));
  if (targetYear != null) q.set('target_year', String(targetYear));
  const qs = q.toString();
  return get(`/benchmark/trajectory/${companyId}/${metricKey}${qs ? `?${qs}` : ''}`);
};
export const askAudit = (question: string, docId?: string) => post<AskAnswer>('/audit/ask', { question, doc_id: docId ?? null });
export const getAuditSummary = (docId: string) => get<Record<string, unknown>>(`/audit/${docId}/summary`);
// Starter questions derived from the report's flags + stats (no LLM, pure backend).
export const getSuggestedQuestions = (docId: string) =>
  get<{ doc_id: string; questions: string[] }>(`/audit/${docId}/suggested-questions`);

// ── verification-method router ───────────────────────────────────────────────
// IMPORTANT (per design): NOT every claim is verified the same way. Only optically
// observable environmental claims (reforestation, solar, land/water surface) are
// candidates for satellite/imagery verification. Emissions, governance, social, and
// financial claims are verified by DATA/DOCUMENT cross-checking (the fact-check
// engine), never by imagery. This router keeps the UI honest about *how* a claim
// can be checked.
//
// Source of truth is the backend `observability_type` the extractor computes and now
// persists. The OPTICAL keyword list below is only a FALLBACK for legacy rows ingested
// before observability_type was persisted — do not let the two definitions drift.
const OPTICAL = [
  'reforestation', 'deforestation', 'land use', 'vegetation', 'forest', 'plantation',
  'solar', 'wind', 'water surface', 'green cover', 'mining', 'flooding', 'wetland',
  'biodiversity', 'habitat', 'mangrove', 'coral',
];
export type VerificationMethod = 'imagery' | 'data_crosscheck' | 'document_review';

export function verificationMethod(
  aspect?: string,
  hasMetric?: boolean,
  observabilityType?: string | null,
): VerificationMethod {
  // Preferred path: trust the persisted backend signal.
  switch ((observabilityType || '').toLowerCase()) {
    case 'optical_possible': return 'imagery';
    case 'directly_observable':
    case 'reported_metric': return 'data_crosscheck';
    case 'not_observable': return 'document_review';
  }
  // Fallback (legacy rows with no observability_type): keyword heuristic.
  const a = (aspect || '').toLowerCase();
  if (OPTICAL.some((k) => a.includes(k))) return 'imagery';
  if (hasMetric) return 'data_crosscheck';
  return 'document_review';
}

export const VERIFICATION_LABEL: Record<VerificationMethod, string> = {
  imagery: 'Satellite / imagery-verifiable',
  data_crosscheck: 'Data cross-check (filings · prior reports)',
  document_review: 'Document / narrative review',
};
