import { useState, useEffect, useMemo, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  AlertTriangle, LayoutDashboard, ListFilter, LayoutGrid, ChevronRight, ArrowLeft, FileText,
} from 'lucide-react';
import { AppLayout } from '@/components/AppLayout';
import { cn } from '@/lib/utils';
import { useClaims, Claim } from '@/hooks/useClaims';
import { metricLabel } from '@/lib/metricLabels';
import {
  ClaimFacets, EMPTY_FACETS, applyFacets, groupClaimsByCompany,
} from '@/lib/claimFacets';

import { CompanyGrid } from '@/components/explorer/CompanyGrid';
import { ClaimFilters } from '@/components/explorer/ClaimFilters';
import { ClaimTable } from '@/components/explorer/ClaimTable';

import ClaimGraph from '@/components/reasoning/ClaimGraph';
import ContradictionExplorer from '@/components/reasoning/ContradictionExplorer';
import RiskScorePanel from '@/components/reasoning/RiskScorePanel';
import MetricTimeline from '@/components/reasoning/MetricTimeline';

type ViewMode = 'companies' | 'claims' | 'dashboard';
const VIEW_MODES: ViewMode[] = ['companies', 'claims', 'dashboard'];

const ClaimExplorer = () => {
  // Data comes from the shared hook. This page used to run its OWN copy of the
  // paginated fetch + conflict join, which meant every visit re-downloaded the
  // whole corpus and the page never saw invalidateClaimsCache() after an ingest.
  const { claims, conflicts, loading } = useClaims();

  // The current view and drill-down live in the URL, not in component state.
  // That is what lets every other page hand off a company ("show me Shell's
  // claims") instead of dumping the user into the unfiltered directory and
  // losing the thing they just clicked - and it makes Back work.
  const [searchParams, setSearchParams] = useSearchParams();
  const companyParam = searchParams.get('company');
  const reportParam = searchParams.get('report');
  const viewParam = searchParams.get('view') as ViewMode | null;

  const drilldown = companyParam ? { company: companyParam, docId: reportParam } : null;
  const viewMode: ViewMode =
    viewParam && VIEW_MODES.includes(viewParam) ? viewParam : companyParam ? 'claims' : 'companies';

  const navigate = useCallback(
    (next: { view: ViewMode; company?: string | null; report?: string | null }) => {
      const params = new URLSearchParams();
      params.set('view', next.view);
      if (next.company) params.set('company', next.company);
      if (next.report) params.set('report', next.report);
      setSearchParams(params);
    },
    [setSearchParams],
  );

  const [companySearch, setCompanySearch] = useState('');
  const [facets, setFacets] = useState<ClaimFacets>({ ...EMPTY_FACETS });
  const [sortField, setSortField] = useState<keyof Claim>('confidence');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc');
  const [activeNode, setActiveNode] = useState<any>(null);
  const [pinnedClaims, setPinnedClaims] = useState<string[]>([]);

  const companyGroups = useMemo(() => groupClaimsByCompany(claims), [claims]);

  // Claims the current view is about, BEFORE facets. Facet option counts are
  // derived from this, so the dropdowns describe the drill-down you are in.
  const scope = useMemo(() => {
    if (pinnedClaims.length > 0) return claims.filter((c) => pinnedClaims.includes(c.id));
    if (!drilldown) return claims;
    return claims.filter(
      (c) => c.company === drilldown.company && (drilldown.docId === null || c.docId === drilldown.docId),
    );
  }, [claims, drilldown, pinnedClaims]);

  const visibleClaims = useMemo(() => {
    const filtered = applyFacets(scope, facets);
    const dir = sortDirection === 'asc' ? 1 : -1;
    return [...filtered].sort((a, b) => {
      const av = a[sortField];
      const bv = b[sortField];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;          // missing values sink, either direction
      if (bv == null) return -1;
      if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * dir;
      return String(av).localeCompare(String(bv)) * dir;
    });
  }, [scope, facets, sortField, sortDirection]);

  // ---- risk dashboard inputs (whole corpus, not the drill-down) -------------
  const riskData = {
    greenwashing_risk: claims.length > 0
      ? (claims.filter((c) => c.status === 'gap').length / claims.length) * 0.8
        + (claims.filter((c) => c.status === 'review').length / claims.length) * 0.2
      : 0,
    status: claims.filter((c) => c.status === 'gap').length > claims.length * 0.1 ? 'High Risk' : 'Moderate Risk',
    vague_claims: claims.filter((c) => c.status === 'review').length,
    // claim_type is stored lowercase ('narrative'); the old `=== 'Narrative'`
    // test matched nothing and this counter read 0 on every corpus.
    narrative_claims: claims.filter((c) => c.verifiabilityClass.toLowerCase() === 'narrative').length,
    missing_metrics: claims.filter((c) => c.confidence < 30).length,
    contradictions: conflicts.length,
    high_severity: conflicts.filter((c) => c.severity === 'Critical' || c.severity === 'High').length,
  };

  const graphData = {
    nodes: claims.slice(0, 20).map((c) => ({
      id: c.id,
      label: c.claim.substring(0, 35) + '...',
      group: c.status === 'verified' ? 1 : c.status === 'review' ? 2 : 3,
      val: 15 + c.confidence / 10,
      details: {
        page: c.page,
        metric: c.metricKey ? metricLabel(c.metricKey) : undefined,
        value: c.metricValue,
        year: c.dateKnown ? c.date.substring(0, 4) : c.reportYear ? String(c.reportYear) : undefined,
        text: c.claim,
      },
    })),
    links: conflicts.map((c) => ({
      source: c.claim_a_id,
      target: c.claim_b_id,
      type: 'contradiction',
      severity: c.severity,
    })),
  };

  // A manual search/filter means the user has moved on from the pinned pair.
  useEffect(() => {
    if (facets.search || facets.status !== 'all') setPinnedClaims([]);
  }, [facets.search, facets.status]);

  const openReport = (company: string, docId: string | null) => {
    setPinnedClaims([]);
    setFacets({ ...EMPTY_FACETS });
    navigate({ view: 'claims', company, report: docId });
  };

  const handleConflictClick = (conflict: any) => {
    setFacets({ ...EMPTY_FACETS });
    setPinnedClaims([conflict.claim_a_id, conflict.claim_b_id]);
    navigate({ view: 'claims' });
  };

  const handleSort = (field: keyof Claim) => {
    if (sortField === field) setSortDirection((p) => (p === 'asc' ? 'desc' : 'asc'));
    else { setSortField(field); setSortDirection('desc'); }
  };

  const drilldownReport = drilldown?.docId
    ? companyGroups.find((g) => g.name === drilldown.company)?.reports.find((r) => r.docId === drilldown.docId)
    : undefined;

  const TABS: { id: ViewMode; label: string; icon: typeof LayoutGrid }[] = [
    { id: 'companies', label: 'Companies', icon: LayoutGrid },
    { id: 'claims', label: 'All Claims', icon: ListFilter },
    { id: 'dashboard', label: 'Risk Dashboard', icon: LayoutDashboard },
  ];

  return (
    <AppLayout>
      {/* Header */}
      <motion.header
        className="h-[72px] border-b border-border/30 glass-panel flex items-center justify-between px-6 shrink-0"
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <div>
          <h1 className="text-xl font-bold text-foreground text-glow-primary tracking-tight">Claim Directory</h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Browse by company, drill into a report year, then filter its claims
          </p>
        </div>

        <div className="flex bg-background/50 border border-border/50 rounded-lg p-1 backdrop-blur-md">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => {
                // "All Claims" means all of them - entering it from a drill-down
                // must drop the scope, or the tab silently lies about what it shows.
                setPinnedClaims([]);
                navigate({ view: tab.id });
              }}
              className={cn(
                'flex items-center gap-2 px-4 py-1.5 rounded-md text-sm font-medium transition-all duration-200',
                viewMode === tab.id
                  ? 'bg-primary/20 text-primary shadow-[0_0_15px_rgba(6,182,212,0.3)]'
                  : 'text-muted-foreground hover:text-foreground hover:bg-white/5',
              )}
            >
              <tab.icon className="w-4 h-4" /> {tab.label}
            </button>
          ))}
        </div>
      </motion.header>

      <div className="flex-1 overflow-auto bg-transparent relative">
        <AnimatePresence mode="wait">

          {/* ===================== COMPANY GRID (default) ===================== */}
          {viewMode === 'companies' && (
            <motion.div
              key="companies"
              className="p-6 h-full flex flex-col"
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 20 }}
              transition={{ duration: 0.2 }}
            >
              <CompanyGrid
                groups={companyGroups}
                search={companySearch}
                onSearchChange={setCompanySearch}
                onOpenReport={openReport}
                loading={loading}
              />
            </motion.div>
          )}

          {/* ===================== CLAIMS (scoped or all) ==================== */}
          {viewMode === 'claims' && (
            <motion.div
              key="claims"
              className="p-6 h-full flex flex-col"
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 20 }}
              transition={{ duration: 0.2 }}
            >
              {/* Breadcrumb - says exactly which slice of the corpus is on screen */}
              {(drilldown || pinnedClaims.length > 0) && (
                <div className="flex items-center gap-2 mb-4 text-sm">
                  <button
                    onClick={() => { setPinnedClaims([]); navigate({ view: 'companies' }); }}
                    className="flex items-center gap-1.5 text-muted-foreground hover:text-primary transition-colors"
                  >
                    <ArrowLeft className="w-4 h-4" /> Companies
                  </button>
                  {drilldown && (
                    <>
                      <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />
                      <button
                        onClick={() => navigate({ view: 'claims', company: drilldown.company })}
                        className={cn(
                          'transition-colors',
                          drilldown.docId ? 'text-muted-foreground hover:text-primary' : 'text-foreground font-medium',
                        )}
                      >
                        {drilldown.company}
                      </button>
                      {drilldown.docId && (
                        <>
                          <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />
                          <span className="flex items-center gap-1.5 text-foreground font-medium">
                            <FileText className="w-3.5 h-3.5" />
                            {drilldownReport?.year ?? drilldown.docId} report
                            <span className="font-mono text-[10px] text-muted-foreground">({drilldown.docId})</span>
                          </span>
                        </>
                      )}
                    </>
                  )}
                  {pinnedClaims.length > 0 && (
                    <>
                      <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />
                      <span className="flex items-center gap-1.5 text-warning">
                        <AlertTriangle className="w-3.5 h-3.5" />
                        The {pinnedClaims.length} claims in one contradiction
                      </span>
                      <button
                        onClick={() => setPinnedClaims([])}
                        className="ml-2 underline text-xs text-muted-foreground hover:text-foreground"
                      >
                        show all
                      </button>
                    </>
                  )}
                </div>
              )}

              <ClaimFilters
                facets={facets}
                onChange={setFacets}
                scope={scope}
                resultCount={visibleClaims.length}
              />

              <ClaimTable
                claims={visibleClaims}
                sortField={sortField}
                sortDirection={sortDirection}
                onSort={handleSort}
                emptyMessage={
                  loading ? 'Loading claims…'
                    : scope.length === 0 ? 'No claims in this report.'
                    : 'No claims match these filters.'
                }
                emptyAction={
                  !loading && scope.length > 0 ? (
                    <button
                      onClick={() => setFacets({ ...EMPTY_FACETS })}
                      className="text-xs text-primary underline hover:text-primary/80"
                    >
                      Clear all filters
                    </button>
                  ) : undefined
                }
              />
            </motion.div>
          )}

          {/* ===================== RISK DASHBOARD ============================ */}
          {viewMode === 'dashboard' && (
            <motion.div
              key="dashboard"
              className="p-6 space-y-6 max-w-[1600px] mx-auto h-full overflow-y-auto"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.2 }}
            >
              <div className="h-48">
                <RiskScorePanel data={riskData} />
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 h-[400px]">
                <div className="col-span-1 h-full flex flex-col">
                  <h2 className="text-sm font-semibold text-foreground/90 mb-3 uppercase tracking-wider flex items-center justify-between">
                    Active Contradictions
                    <span className="bg-danger/10 text-danger border border-danger/20 px-2 py-0.5 rounded text-[10px]">
                      {conflicts.length}
                    </span>
                  </h2>
                  <div className="flex-1 border border-border/50 rounded-xl shadow-sm overflow-hidden p-2 glass-panel">
                    <ContradictionExplorer
                      conflicts={conflicts}
                      onHover={() => undefined}
                      onClick={handleConflictClick}
                    />
                  </div>
                </div>

                <div className="col-span-2 h-full flex flex-col">
                  <h2 className="text-sm font-semibold text-foreground/90 mb-3 uppercase tracking-wider">
                    Semantic Claim Graph
                  </h2>
                  <div className="flex-1 border border-border/50 rounded-xl shadow-[0_0_30px_rgba(0,0,0,0.5)] relative glass-panel overflow-hidden">
                    <ClaimGraph data={graphData} onNodeClick={(n) => setActiveNode(n)} />
                  </div>
                </div>
              </div>

              <div className="h-[380px] w-full pb-6">
                <MetricTimeline title="Historical ESG Metric Trends" />
              </div>
            </motion.div>
          )}

        </AnimatePresence>
      </div>
    </AppLayout>
  );
};

export default ClaimExplorer;
