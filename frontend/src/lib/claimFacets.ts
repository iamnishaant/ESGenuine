// Faceted filtering + company/report grouping for the Claim Explorer.
//
// Kept out of the page component for two reasons: the Explorer, the globe's
// CompanyPanel and the Portfolio page all want the same "which reports does this
// company have" answer, and the filter predicate is the kind of thing that goes
// subtly wrong when it is inlined and duplicated (see the `=== 'Narrative'`
// case-sensitivity bug this file's LOWERCASE note exists to prevent).

import { Claim } from '@/hooks/useClaims';
import { metricLabel } from './metricLabels';

// ---------------------------------------------------------------- grouping ---

export interface ReportGroup {
  /** `claims.doc_id`, e.g. 'shell_2023'. The real identity of a report. */
  docId: string;
  year: number | null;
  total: number;
  verified: number;
  review: number;
  gap: number;
}

export interface CompanyGroup {
  name: string;
  total: number;
  verified: number;
  review: number;
  gap: number;
  /** Newest disclosure year first. */
  reports: ReportGroup[];
}

/**
 * Roll claims up into company -> report buckets.
 *
 * Reports are keyed by `docId`, NOT by year: a company can file more than one
 * document for the same year, and two different companies obviously share years.
 * Claims with no docId are collected under a synthetic per-year key so they stay
 * reachable in the UI instead of vanishing from the drill-down.
 */
export function groupClaimsByCompany(claims: Claim[]): CompanyGroup[] {
  const byCompany = new Map<string, CompanyGroup>();
  const reportIndex = new Map<string, ReportGroup>();

  for (const claim of claims) {
    let company = byCompany.get(claim.company);
    if (!company) {
      company = { name: claim.company, total: 0, verified: 0, review: 0, gap: 0, reports: [] };
      byCompany.set(claim.company, company);
    }
    company.total += 1;
    company[claim.status] += 1;

    const docId = claim.docId ?? `${claim.company}:${claim.reportYear ?? 'undated'}`;
    const reportKey = `${claim.company}::${docId}`;
    let report = reportIndex.get(reportKey);
    if (!report) {
      report = { docId, year: claim.reportYear ?? null, total: 0, verified: 0, review: 0, gap: 0 };
      reportIndex.set(reportKey, report);
      company.reports.push(report);
    }
    report.total += 1;
    report[claim.status] += 1;
    // A report's year is whatever its claims agree on; keep the first non-null.
    if (report.year === null && claim.reportYear != null) report.year = claim.reportYear;
  }

  const groups = Array.from(byCompany.values());
  for (const g of groups) {
    g.reports.sort((a, b) => (b.year ?? 0) - (a.year ?? 0) || a.docId.localeCompare(b.docId));
  }
  // Most-documented companies first; they are what an analyst opens.
  groups.sort((a, b) => b.total - a.total || a.name.localeCompare(b.name));
  return groups;
}

// ------------------------------------------------------------------ labels ---

// claims.claim_type is stored LOWERCASE. Always normalise before comparing.
export const CLAIM_TYPE_LABELS: Record<string, string> = {
  performance: 'Performance',
  narrative: 'Narrative',
  target: 'Target / pledge',
  general: 'Unclassified',
};

export const OBSERVABILITY_LABELS: Record<string, string> = {
  reported_metric: 'Reported metric',
  directly_observable: 'Directly observable',
  optical_possible: 'Satellite-checkable',
  not_observable: 'Not independently observable',
};

export const QUALITY_FLAG_LABELS: Record<string, string> = {
  value_not_in_source: 'Value not found in source text',
  value_not_in_table: 'Value not found in table',
  type_fixed: 'Claim type corrected',
  aspect_fixed: 'Aspect corrected',
  gender_fixed: 'Gender field corrected',
  scope_fixed: 'Emissions scope corrected',
  implausible_unit: 'Implausible unit',
};

export const SECTOR_LABELS: Record<string, string> = {
  emissions: 'Emissions',
  energy: 'Energy',
  water: 'Water',
  waste: 'Waste',
  biodiversity: 'Biodiversity',
  social: 'Social',
  governance: 'Governance',
  uncategorized: 'Uncategorized',
};

const prettify = (value: string, table: Record<string, string>) =>
  table[value.toLowerCase()] ?? value.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase());

export const claimTypeLabel = (v: string) => prettify(v, CLAIM_TYPE_LABELS);
export const observabilityLabel = (v: string) => prettify(v, OBSERVABILITY_LABELS);
export const qualityFlagLabel = (v: string) => prettify(v, QUALITY_FLAG_LABELS);
export const sectorLabel = (v: string) => prettify(v, SECTOR_LABELS);

// ------------------------------------------------------------------ facets ---

export interface ClaimFacets {
  search: string;
  status: string;         // 'all' | 'verified' | 'review' | 'gap'
  claimType: string;      // 'all' | lowercase claims.claim_type
  observability: string;  // 'all' | lowercase claims.observability_type
  sector: string;         // 'all' | top-level metric family
  metric: string;         // 'all' | full metric_family key
  framework: string;      // 'all' | framework tag, e.g. 'GRI 305-1'
  qualityFlag: string;    // 'all' | quality flag, or 'none' for clean claims
  minConfidence: number;  // 0-100
}

export const EMPTY_FACETS: ClaimFacets = {
  search: '',
  status: 'all',
  claimType: 'all',
  observability: 'all',
  sector: 'all',
  metric: 'all',
  framework: 'all',
  qualityFlag: 'all',
  minConfidence: 0,
};

/** How many facets are narrowing the result set (drives the "clear" affordance). */
export function activeFacetCount(f: ClaimFacets): number {
  let n = 0;
  if (f.search.trim()) n++;
  if (f.status !== 'all') n++;
  if (f.claimType !== 'all') n++;
  if (f.observability !== 'all') n++;
  if (f.sector !== 'all') n++;
  if (f.metric !== 'all') n++;
  if (f.framework !== 'all') n++;
  if (f.qualityFlag !== 'all') n++;
  if (f.minConfidence > 0) n++;
  return n;
}

export function applyFacets(claims: Claim[], f: ClaimFacets): Claim[] {
  const q = f.search.trim().toLowerCase();
  return claims.filter((c) => {
    if (q) {
      const haystack = `${c.claim} ${c.company} ${c.location} ${c.id} ${c.docId ?? ''}`.toLowerCase();
      if (!haystack.includes(q)) return false;
    }
    if (f.status !== 'all' && c.status !== f.status) return false;
    if (f.claimType !== 'all' && c.verifiabilityClass.toLowerCase() !== f.claimType) return false;
    if (f.observability !== 'all' && (c.observabilityType ?? '').toLowerCase() !== f.observability) return false;
    if (f.sector !== 'all' && c.sector.toLowerCase() !== f.sector) return false;
    if (f.metric !== 'all' && (c.metricKey ?? 'uncategorized') !== f.metric) return false;
    if (f.framework !== 'all' && !c.frameworkTags.includes(f.framework)) return false;
    if (f.qualityFlag === 'none') {
      if (c.qualityFlags.length > 0) return false;
    } else if (f.qualityFlag !== 'all' && !c.qualityFlags.includes(f.qualityFlag)) return false;
    if (f.minConfidence > 0 && c.confidence < f.minConfidence) return false;
    return true;
  });
}

// ----------------------------------------------------------- facet options ---

export interface FacetOption {
  value: string;
  label: string;
  count: number;
}

const tally = (
  claims: Claim[],
  pick: (c: Claim) => string | string[] | undefined,
  label: (v: string) => string,
): FacetOption[] => {
  const counts = new Map<string, number>();
  for (const c of claims) {
    const raw = pick(c);
    if (raw === undefined) continue;
    for (const v of Array.isArray(raw) ? raw : [raw]) {
      if (!v) continue;
      counts.set(v, (counts.get(v) ?? 0) + 1);
    }
  }
  return Array.from(counts.entries())
    .map(([value, count]) => ({ value, label: label(value), count }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
};

/**
 * Build the dropdown options from the claims actually in scope, so the UI never
 * offers a filter that would return nothing. `sector` narrows the metric list,
 * which is what keeps a 38-entry metric dropdown usable.
 */
export function buildFacetOptions(claims: Claim[], sector: string) {
  const inSector = sector === 'all'
    ? claims
    : claims.filter((c) => c.sector.toLowerCase() === sector);

  return {
    claimType: tally(claims, (c) => c.verifiabilityClass.toLowerCase(), claimTypeLabel),
    observability: tally(claims, (c) => c.observabilityType?.toLowerCase(), observabilityLabel),
    sector: tally(claims, (c) => c.sector.toLowerCase(), sectorLabel),
    metric: tally(inSector, (c) => c.metricKey ?? 'uncategorized', metricLabel),
    framework: tally(claims, (c) => c.frameworkTags, (v) => v),
    qualityFlag: tally(claims, (c) => c.qualityFlags, qualityFlagLabel),
  };
}
