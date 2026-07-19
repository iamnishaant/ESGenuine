import { useEffect, useState } from 'react';
import { getPortfolioIntegrity, type PortfolioIntegrity } from '@/lib/api';

// Single source of truth for company-level integrity scores: the backend
// build_report() portfolio endpoint. Every page/component that shows a company
// score joins through this hook, so Portfolio, Globe, and CompanyPanel can
// never disagree with the Integrity Audit page.
//
// Join key: alphanumeric fold of BOTH company_id and company_name — robust to
// "tata_power" vs "Tata Power" vs "tata-power" without any name-string fragility.
export const normCompanyKey = (s: string | null | undefined): string =>
  (s || '').toLowerCase().replace(/[^a-z0-9]/g, '');

export type BackendAvailability = 'loading' | 'up' | 'down';

let cache: Map<string, PortfolioIntegrity> | null = null;
let availability: BackendAvailability = 'loading';
let inflight: Promise<void> | null = null;
const listeners = new Set<() => void>();

function fetchScores(): Promise<void> {
  if (!inflight) {
    inflight = getPortfolioIntegrity()
      .then((res) => {
        const m = new Map<string, PortfolioIntegrity>();
        res.companies.forEach((c) => {
          m.set(normCompanyKey(c.company_id), c);
          m.set(normCompanyKey(c.company_name), c);
        });
        cache = m;
        availability = 'up';
      })
      .catch(() => {
        // Backend unreachable: report honestly instead of fabricating scores.
        cache = new Map();
        availability = 'down';
      })
      .finally(() => {
        inflight = null;
        listeners.forEach((fn) => fn());
      });
  }
  return inflight;
}

/** Force a refetch (e.g. after an ingest lands). */
export function invalidateBackendScores(): void {
  cache = null;
  availability = 'loading';
}

export function useBackendScores(): {
  scores: Map<string, PortfolioIntegrity>;
  availability: BackendAvailability;
  /** Convenience join: score record for a company by name or id (either works). */
  forCompany: (nameOrId: string | null | undefined) => PortfolioIntegrity | undefined;
} {
  const [, bump] = useState(0);

  useEffect(() => {
    const rerender = () => bump((n) => n + 1);
    listeners.add(rerender);
    if (!cache) void fetchScores();
    return () => { listeners.delete(rerender); };
  }, []);

  const scores = cache ?? new Map<string, PortfolioIntegrity>();
  return {
    scores,
    availability,
    forCompany: (nameOrId) => scores.get(normCompanyKey(nameOrId)),
  };
}
