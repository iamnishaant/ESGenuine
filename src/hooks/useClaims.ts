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
  status: 'verified' | 'review' | 'gap';
  confidence: number;
  sector: string;
  riskLevel: 'low' | 'medium' | 'high';
  verifiabilityClass: string;
  page?: number;
  metricKey?: string;
  metricValue?: number;
  metricUnit?: string;
}

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
  
  let status: 'verified' | 'review' | 'gap' = 'review';
  if (gScore > 0.8) status = 'verified';
  else if (gScore < 0.4) status = 'gap';

  return {
    id: dbRow.claim_id,
    company: dbRow.company_name || 'Unknown Corp',
    claim: dbRow.source_sentence,
    location: dbRow.location_text || 'Unspecified',
    date: dbRow.time_start || '2024-01-01',
    status: status,
    confidence: Math.round(gScore * 100),
    sector: dbRow.metric_family?.split('.')[0] || 'Uncategorized',
    riskLevel: gScore > 0.7 ? 'low' : gScore > 0.4 ? 'medium' : 'high',
    verifiabilityClass: dbRow.claim_type || 'General',
    page: dbRow.page_number,
    metricKey: dbRow.metric_family,
    metricValue: dbRow.metric_value ? parseFloat(dbRow.metric_value) : undefined,
    metricUnit: dbRow.metric_unit
  };
};

// Global state cache to prevent re-fetching on every page navigation
let globalClaimsCache: Claim[] | null = null;
let globalConflictsCache: Conflict[] | null = null;
let globalCompaniesCache: any[] | null = null;
const fetchPromises: { current: Promise<void> | null } = { current: null };

export function useClaims() {
  const [claims, setClaims] = useState<Claim[]>(globalClaimsCache || []);
  const [conflicts, setConflicts] = useState<Conflict[]>(globalConflictsCache || []);
  const [companies, setCompanies] = useState<any[]>(globalCompaniesCache || []);
  const [loading, setLoading] = useState<boolean>(!globalClaimsCache);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    // If data is already cached and we're not currently fetching, do nothing
    if (globalClaimsCache && !fetchPromises.current) {
      setLoading(false);
      return;
    }

    async function fetchData() {
      try {
        const { data: claimsData, error: claimsError } = await supabase
          .from('claims')
          .select('*')
          .order('groundability_score', { ascending: false });

        if (claimsError) throw claimsError;
        
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

          // Compute company aggregations for the portfolio view
          const companyMap = new Map();
          mappedClaims.forEach(claim => {
            if (!companyMap.has(claim.company)) {
              companyMap.set(claim.company, {
                id: claim.company.replace(/\s+/g, '-').toLowerCase(),
                name: claim.company,
                sector: claim.sector,
                integrityScoreSum: 0,
                claimsCount: 0,
                claims: { verified: 0, review: 0, gap: 0 },
                locations: new Set(),
              });
            }
            const comp = companyMap.get(claim.company);
            comp.integrityScoreSum += claim.confidence;
            comp.claimsCount += 1;
            comp.claims[claim.status] += 1;
            if (claim.location && claim.location !== 'Unspecified') {
              comp.locations.add(claim.location);
            }
          });

          mappedCompanies = Array.from(companyMap.values()).map(comp => {
            const avgScore = Math.round(comp.integrityScoreSum / comp.claimsCount);
            return {
              ...comp,
              integrityScore: avgScore,
              trend: 'stable',
              locations: Array.from(comp.locations),
              riskLevel: avgScore >= 70 ? 'low' : avgScore >= 40 ? 'medium' : 'high'
            };
          });
        }

        // Update global cache
        globalClaimsCache = mappedClaims;
        globalConflictsCache = mappedConflicts;
        globalCompaniesCache = mappedCompanies;

        // Update local state
        setClaims(mappedClaims);
        setConflicts(mappedConflicts);
        setCompanies(mappedCompanies);
        setError(null);
      } catch (err: any) {
        console.error('Error fetching data:', err);
        setError(err);
      } finally {
        setLoading(false);
      }
    }

    if (!fetchPromises.current) {
      setLoading(true);
      fetchPromises.current = fetchData().finally(() => {
        fetchPromises.current = null;
      });
    }
  }, []);

  return { claims, conflicts, companies, loading, error };
}
