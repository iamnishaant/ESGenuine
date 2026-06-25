// FastAPI client for the next-gen analysis endpoints (integrity, fact-check,
// benchmarking, agentic audit). Reads VITE_API_BASE, falls back to local dev.

export const API_BASE =
  (import.meta.env.VITE_API_BASE as string) || 'http://localhost:8000';

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} on ${path}`);
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
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
export interface IntegrityReport {
  status: string;
  meta?: { company_name?: string; report_year?: number; doc_id?: string; total_claims?: number };
  integrity_score?: number; grade?: string; greenwashing_risk?: string; summary?: string;
  statistics?: Record<string, unknown>;
  flag_summary?: { total: number; by_severity: Record<string, number> };
  flags: GreenwashFlag[];
  recommendations: Array<{ severity: string; action: string; for: string }>;
}
export interface FactCheckResult {
  claim_id: string; claim_text: string; metric_key: string; reference_year: string;
  claim_value: number | null; claim_unit: string | null;
  verdict: 'SUPPORTED' | 'CONTRADICTED' | 'UNVERIFIED'; confidence: number;
  reasoning: string; evidence: Array<Record<string, unknown>>;
}
export interface FactCheckReport {
  checked: number; verdict_counts: Record<string, number>;
  credibility: number | null; results: FactCheckResult[];
}
export interface ScorecardMetric {
  metric_key: string; polarity: string; unit: string | null; value: number;
  rank: number; of: number; percentile: number; peer_median: number; verdict: string;
}
export interface Scorecard { company: string; metrics_compared: number; metrics: ScorecardMetric[]; }
export interface AskAnswer {
  question: string; answer: string; engine: string;
  citations: Array<{ n: number; company: string; year: number; page: number; doc_id: string; text: string; similarity: number }>;
}

// ── endpoint wrappers ────────────────────────────────────────────────────────
export const getIntegrityReport = (docId: string) => get<IntegrityReport>(`/reports/${docId}/integrity-report`);
export const getGreenwashingFlags = (docId: string) => get<{ total_flags: number; flags: GreenwashFlag[] }>(`/reports/${docId}/greenwashing-flags`);
export const getFactCheck = (docId: string, limit = 50) => get<FactCheckReport>(`/reports/${docId}/fact-check?limit=${limit}`);
export const getScorecard = (companyId: string) => get<Scorecard>(`/benchmark/company/${companyId}`);
export const getTrajectory = (companyId: string, metricKey: string, targetValue?: number, targetYear?: number) => {
  const q = new URLSearchParams();
  if (targetValue != null) q.set('target_value', String(targetValue));
  if (targetYear != null) q.set('target_year', String(targetYear));
  const qs = q.toString();
  return get(`/benchmark/trajectory/${companyId}/${metricKey}${qs ? `?${qs}` : ''}`);
};
export const askAudit = (question: string, docId?: string) => post<AskAnswer>('/audit/ask', { question, doc_id: docId ?? null });
export const getAuditSummary = (docId: string) => get<Record<string, unknown>>(`/audit/${docId}/summary`);

// ── verification-method router ───────────────────────────────────────────────
// IMPORTANT (per design): NOT every claim is verified the same way. Only optically
// observable environmental claims (reforestation, solar, land/water surface) are
// candidates for satellite/imagery verification. Emissions, governance, social, and
// financial claims are verified by DATA/DOCUMENT cross-checking (the fact-check
// engine), never by imagery. This router keeps the UI honest about *how* a claim
// can be checked.
const OPTICAL = [
  'reforestation', 'deforestation', 'land use', 'vegetation', 'forest', 'plantation',
  'solar', 'wind', 'water surface', 'green cover', 'mining', 'flooding', 'wetland',
  'biodiversity', 'habitat', 'mangrove', 'coral',
];
export type VerificationMethod = 'imagery' | 'data_crosscheck' | 'document_review';

export function verificationMethod(aspect?: string, hasMetric?: boolean): VerificationMethod {
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
