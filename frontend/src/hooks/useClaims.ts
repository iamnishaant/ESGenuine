import { useState, useEffect } from 'react';
import { supabase } from '@/lib/supabase';

// -----------------------------
// TYPES & MAPPING
// -----------------------------
export interface Claim {
  id: string;
  company: string;
  claim: string;
  location: string;
  date: string;
  dateKnown: boolean;
  status: 'verified' | 'review' | 'gap';
  confidence: number;       // groundability score, 0-100
  verifiability: number;    // (1 - vagueness) * 100, 0-100
  vagueness: number;        // raw vagueness score, 0-100
  sector: string;
  riskLevel: 'low' | 'medium' | 'high';
  verifiabilityClass: string;
  page?: number;
  metricKey?: string;
  metricValue?: number;
  metricUnit?: string;
  metricDirection?: string;
  normalizedAspect?: string;
  reportYear?: number;
  timeStart?: string;
  timeEnd?: string;
  /** Which REPORT this claim came from (e.g. 'shell_2023'). The corpus holds two
   *  Shell reports and two Infosys reports, so a company name alone does not
   *  identify the source document — every claim-level view must show this. */
  docId?: string;
}

// Treats Postgres "null" string artifacts and blanks as missing.
const realOrNull = (v: any): string | null => {
  if (v === null || v === undefined) return null;
  const s = String(v).trim();
  if (!s || s.toLowerCase() === 'null' || s.toLowerCase() === 'none') return null;
  return s;
};

export interface Conflict {
  id: number;
  claim_a_id: string;
  claim_b_id: string;
  severity: string;
  conflict_type: string;
  reasoning: string;
  confidence: number;
  claim_a_text?: string;
  claim_b_text?: string;
  claim_a_page?: number;
  claim_b_doc?: string;
}

export const mapDbToClaim = (dbRow: any): Claim => {
  const gScore = dbRow.groundability_score || 0;
  const vScore = typeof dbRow.vagueness_score === 'number' ? dbRow.vagueness_score : null;

  let status: 'verified' | 'review' | 'gap' = 'review';
  if (gScore > 0.8) status = 'verified';
  else if (gScore < 0.4) status = 'gap';

  const timeStart = realOrNull(dbRow.time_start);
  const timeEnd = realOrNull(dbRow.time_end);

  return {
    id: dbRow.claim_id,
    company: realOrNull(dbRow.company_name) || 'Unknown Corp',
    claim: dbRow.source_sentence,
    location: realOrNull(dbRow.location_text) || 'Unspecified',
    date: timeStart || (dbRow.report_year ? `${dbRow.report_year}-01-01` : ''),
    dateKnown: !!timeStart,
    status: status,
    confidence: Math.round(gScore * 100),
    // Verifiability comes from the real vagueness score (1 - vagueness); falls
    // back to groundability when vagueness is absent. No fabricated values.
    verifiability: vScore !== null ? Math.round((1 - vScore) * 100) : Math.round(gScore * 100),
    vagueness: vScore !== null ? Math.round(vScore * 100) : 0,
    sector: dbRow.metric_family?.split('.')[0] || 'Uncategorized',
    riskLevel: gScore > 0.7 ? 'low' : gScore > 0.4 ? 'medium' : 'high',
    verifiabilityClass: realOrNull(dbRow.claim_type) || 'General',
    page: dbRow.page_number,
    metricKey: dbRow.metric_family,
    metricValue: dbRow.metric_value != null ? parseFloat(dbRow.metric_value) : undefined,
    metricUnit: realOrNull(dbRow.metric_unit) || undefined,
    metricDirection: realOrNull(dbRow.metric_direction) || undefined,
    normalizedAspect: realOrNull(dbRow.normalized_aspect) || undefined,
    reportYear: dbRow.report_year ?? undefined,
    timeStart: timeStart || undefined,
    timeEnd: timeEnd || undefined,
    docId: realOrNull(dbRow.doc_id) || undefined,
  };
};

/**
 * Fetch EVERY claim row, paging past PostgREST's row cap.
 *
 * Supabase caps a plain `.select()` at 1000 rows (`db-max-rows`). The corpus is 1730,
 * so an unpaginated fetch silently dropped 730 claims: the dashboard read
 * "CLAIMS ANALYZED 1000" — an exactly-round number that is itself the tell — and every
 * derived figure (company aggregates, verified/review counts, globe markers) was
 * computed on a truncated slice. Nothing errored; the data just stopped.
 *
 * Exported because ClaimExplorer previously duplicated this query and therefore
 * duplicated the bug. One implementation, one place to fix.
 */
export async function fetchAllClaimRows(): Promise<any[]> {
  const PAGE = 1000;
  const rows: any[] = [];
  for (let from = 0; ; from += PAGE) {
    const { data: page, error } = await supabase
      .from('claims')
      .select('*')
      .order('groundability_score', { ascending: false })
      .order('claim_id', { ascending: true })   // tiebreak → stable, non-overlapping pages
      .range(from, from + PAGE - 1);

    if (error) throw error;
    if (!page?.length) break;
    rows.push(...page);
    if (page.length < PAGE) break;
  }
  return rows;
}

// Global state cache to prevent re-fetching on every page navigation
let globalClaimsCache: Claim[] | null = null;
let globalConflictsCache: Conflict[] | null = null;
let globalCompaniesCache: any[] | null = null;
const fetchPromises: { current: Promise<void> | null } = { current: null };

// Drop the module cache so the next mounted consumer refetches. Call after an
// ingest lands (SubmitReport) — otherwise the UI shows pre-ingest data until a
// full page reload.
export function invalidateClaimsCache(): void {
  globalClaimsCache = null;
  globalConflictsCache = null;
  globalCompaniesCache = null;
}

export function useClaims() {
  const [claims, setClaims] = useState<Claim[]>(globalClaimsCache || []);
  const [conflicts, setConflicts] = useState<Conflict[]>(globalConflictsCache || []);
  const [companies, setCompanies] = useState<any[]>(globalCompaniesCache || []);
  const [loading, setLoading] = useState<boolean>(!globalClaimsCache);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    async function fetchData() {
      try {
        const claimsData = await fetchAllClaimRows();
        
        const { data: conflictsData, error: conflictsError } = await supabase
          .from('contradictions')
          .select('*');

        // It is fine if contradictions fails if table is missing, but log it
        if (conflictsError) console.warn("Could not fetch contradictions:", conflictsError);

        let mappedClaims: Claim[] = [];
        let mappedConflicts: Conflict[] = [];
        let mappedCompanies: any[] = [];

        if (claimsData) {
          mappedClaims = claimsData.map(mapDbToClaim);
          
          if (conflictsData) {
            mappedConflicts = conflictsData.map(c => {
              const claimA = mappedClaims.find(cl => cl.id === c.claim_a_id);
              const claimB = mappedClaims.find(cl => cl.id === c.claim_b_id);
              return {
                ...c,
                claim_a_text: claimA?.claim || "Referenced Claim A",
                claim_b_text: claimB?.claim || "Referenced Claim B",
                claim_a_page: claimA?.page || 0,
                claim_b_doc: claimB?.company || "Target"
              };
            });
          }

          // Compute company aggregations for the portfolio view.
          // NOTE: this is claim-level bookkeeping (counts, locations, groundability).
          // The company Integrity Score is NOT computed here — it comes exclusively
          // from the backend build_report() via useBackendScores, so the UI can never
          // show a homegrown number that disagrees with the Integrity Audit page.
          const companyMap = new Map();
          mappedClaims.forEach(claim => {
            if (!companyMap.has(claim.company)) {
              companyMap.set(claim.company, {
                id: claim.company.replace(/\s+/g, '-').toLowerCase(),
                name: claim.company,
                sector: claim.sector,
                groundabilitySum: 0,
                claimsCount: 0,
                claims: { verified: 0, review: 0, gap: 0 },
                locations: new Set(),
              });
            }
            const comp = companyMap.get(claim.company);
            comp.groundabilitySum += claim.confidence;
            comp.claimsCount += 1;
            comp.claims[claim.status] += 1;
            if (claim.location && claim.location !== 'Unspecified') {
              comp.locations.add(claim.location);
            }
          });

          mappedCompanies = Array.from(companyMap.values()).map(comp => {
            // Honest name: average groundability of the company's claims (a data-
            // quality signal), NOT an integrity score.
            const groundabilityAvg = Math.round(comp.groundabilitySum / comp.claimsCount);
            return {
              ...comp,
              groundabilityAvg,
              trend: 'stable',
              locations: Array.from(comp.locations),
              // Fallback risk band from groundability — superseded by the backend
              // greenwashing_risk wherever the backend is reachable.
              riskLevel: groundabilityAvg >= 70 ? 'low' : groundabilityAvg >= 40 ? 'medium' : 'high'
            };
          });
        }

        // Publish to the module cache ONLY. Local state is hydrated below, by every
        // consumer, so the component that happened to win the fetch race is not the
        // only one that ends up with data.
        globalClaimsCache = mappedClaims;
        globalConflictsCache = mappedConflicts;
        globalCompaniesCache = mappedCompanies;
        setError(null);
      } catch (err: any) {
        console.error('Error fetching data:', err);
        setError(err);
        throw err;                       // propagate so late subscribers stop loading
      }
    }

    let cancelled = false;
    const hydrate = () => {
      if (cancelled) return;
      setClaims(globalClaimsCache || []);
      setConflicts(globalConflictsCache || []);
      setCompanies(globalCompaniesCache || []);
      setLoading(false);
    };

    // Already fetched by an earlier mount — hydrate straight from the cache.
    if (globalClaimsCache && !fetchPromises.current) {
      hydrate();
      return () => { cancelled = true; };
    }

    // Start the shared fetch at most once...
    if (!fetchPromises.current) {
      setLoading(true);
      fetchPromises.current = fetchData().finally(() => {
        fetchPromises.current = null;
      });
    }

    // ...but EVERY consumer subscribes to it. This is the fix for a race that made
    // the app look half-empty: `fetchData` used to call the state setters of whichever
    // component mounted first, and any other component mounting in the same tick saw
    // `fetchPromises.current` already set, never awaited it, and kept its initial []
    // forever. Live symptom: DashboardCards showed 1730 claims while the Globe showed
    // 0 companies and rendered no HQ pins at all — same hook, same instant, different
    // data, purely decided by mount order.
    fetchPromises.current?.then(hydrate).catch(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, []);

  return { claims, conflicts, companies, loading, error };
}
