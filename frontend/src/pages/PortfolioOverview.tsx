import { motion } from 'framer-motion';
import { 
  Building2, 
  Globe2, 
  TrendingUp, 
  TrendingDown,
  AlertTriangle,
  CheckCircle2,
  MapPin,
  ChevronRight,
  Search,
  Loader2
} from 'lucide-react';
import { AppLayout } from '@/components/AppLayout';
import { cn } from '@/lib/utils';
import { Link } from 'react-router-dom';
import { useClaims } from '@/hooks/useClaims';
import { useMemo, useState } from 'react';
import { useBackendScores } from '@/hooks/useBackendScores';

// Backend greenwashing_risk ("Low"/"Moderate"/"High") → the UI's risk band.
const riskFromBackend = (r?: string | null): 'low' | 'medium' | 'high' =>
  r === 'Low' ? 'low' : r === 'High' ? 'high' : 'medium';

const PortfolioOverview = () => {
  const { companies, loading } = useClaims();
  // Replaces a "Filter Portfolio" button that had no onClick at all - it animated
  // on hover and press, so it read as working while doing nothing.
  const [query, setQuery] = useState('');
  const [riskFilter, setRiskFilter] = useState<'all' | 'low' | 'medium' | 'high' | 'unscored'>('all');

  // Integrity scores come EXCLUSIVELY from the backend build_report() portfolio
  // endpoint (same methodology as the Integrity Audit page). When the backend is
  // unreachable we say so and show "—" — we never substitute a homegrown number.
  const { forCompany, availability } = useBackendScores();

  const resolved = useMemo(() => companies.map((c) => {
    const b = forCompany(c.name) ?? forCompany(c.id);
    if (b && b.integrity_score != null) {
      return { ...c, integrityScore: Math.round(b.integrity_score) as number | null,
               riskLevel: riskFromBackend(b.greenwashing_risk), grade: b.grade };
    }
    return { ...c, integrityScore: null as number | null, grade: null };
  }), [companies, forCompany]);

  const scored = useMemo(() => resolved.filter((c) => c.integrityScore != null), [resolved]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return resolved.filter((c) => {
      if (q && !`${c.name} ${c.sector} ${c.locations.join(' ')}`.toLowerCase().includes(q)) return false;
      if (riskFilter === 'all') return true;
      if (riskFilter === 'unscored') return c.integrityScore == null;
      return c.integrityScore != null && c.riskLevel === riskFilter;
    });
  }, [resolved, query, riskFilter]);
  const totalClaims = resolved.reduce((acc, c) => acc + c.claims.verified + c.claims.review + c.claims.gap, 0);
  const avgScore = scored.length > 0
    ? Math.round(scored.reduce((acc, c) => acc + (c.integrityScore as number), 0) / scored.length)
    : null;
  const gapCount = resolved.reduce((acc, c) => acc + c.claims.gap, 0);

  // Group by broad region heuristically based on location string.
  // Score averages count ONLY backend-scored companies; claims count everyone.
  const regionData = useMemo(() => {
    const regions = new Map<string, { companies: Set<string>, scoreSum: number, scored: number, claims: number }>();
    const add = (region: string, company: (typeof resolved)[number]) => {
      if (!regions.has(region)) regions.set(region, { companies: new Set(), scoreSum: 0, scored: 0, claims: 0 });
      const r = regions.get(region)!;
      if (!r.companies.has(company.id)) {
        r.companies.add(company.id);
        r.claims += company.claimsCount;
        if (company.integrityScore != null) { r.scoreSum += company.integrityScore; r.scored += 1; }
      }
    };

    resolved.forEach(company => {
      // If no locations, put in Global
      if (company.locations.length === 0) {
        add('Global', company);
        return;
      }

      company.locations.forEach((loc: string) => {
        let region = 'Other';
        const l = loc.toLowerCase();
        if (l.includes('singapore') || l.includes('japan') || l.includes('india') || l.includes('australia') || l.includes('tokyo') || l.includes('sydney')) region = 'Asia Pacific';
        else if (l.includes('berlin') || l.includes('europe') || l.includes('germany') || l.includes('uk') || l.includes('oslo')) region = 'Europe';
        else if (l.includes('usa') || l.includes('united states') || l.includes('america') || l.includes('houston')) region = 'North America';
        else if (l.includes('brazil') || l.includes('são paulo') || l.includes('buenos aires')) region = 'South America';
        else if (l.includes('johannesburg') || l.includes('africa')) region = 'Africa';
        else if (l.includes('uae') || l.includes('dubai')) region = 'Middle East';
        add(region, company);
      });
    });

    return Array.from(regions.entries())
      .map(([region, data]) => ({
        region,
        companies: data.companies.size,
        avgScore: data.scored > 0 ? Math.round(data.scoreSum / data.scored) : null,
        claims: data.claims
      }))
      .sort((a, b) => b.companies - a.companies);
  }, [resolved]);

  // Risk distribution over backend-scored companies only (risk = greenwashing_risk).
  const riskDist = useMemo(() => {
    const total = scored.length || 1;
    const low = scored.filter(c => c.riskLevel === 'low').length;
    const medium = scored.filter(c => c.riskLevel === 'medium').length;
    const high = scored.filter(c => c.riskLevel === 'high').length;
    return {
      low: Math.round((low / total) * 100),
      medium: Math.round((medium / total) * 100),
      high: Math.round((high / total) * 100),
    };
  }, [scored]);

  if (loading) {
    return (
      <AppLayout>
        <div className="flex-1 flex items-center justify-center min-h-screen">
          <Loader2 className="w-8 h-8 text-primary animate-spin" />
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout>
      {/* Header */}
      <motion.header 
        className="h-16 border-b border-border/30 glass-panel flex items-center justify-between px-6"
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <div>
          <h1 className="text-lg font-semibold text-foreground">Portfolio Overview</h1>
          <p className="text-xs text-muted-foreground">Company-level integrity summary across your investment portfolio</p>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground w-4 h-4" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Filter companies..."
              className="w-56 bg-muted/50 border border-border/50 text-foreground text-sm rounded-lg pl-9 pr-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary transition-all"
            />
          </div>
          <select
            value={riskFilter}
            onChange={(e) => setRiskFilter(e.target.value as typeof riskFilter)}
            className={cn(
              'bg-muted/50 border border-border/50 text-foreground text-sm rounded-lg px-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary appearance-none',
              riskFilter !== 'all' && 'border-primary/60 text-primary',
            )}
          >
            <option value="all">All risk</option>
            <option value="low">Low risk</option>
            <option value="medium">Medium risk</option>
            <option value="high">High risk</option>
            <option value="unscored">Unscored</option>
          </select>
        </div>
      </motion.header>

      {/* Content */}
      <div className="flex-1 p-6 overflow-auto">
        {/* Honest-degradation banner: never substitute a fake score when the audit
            backend is unreachable. */}
        {availability === 'down' && (
          <motion.div
            className="mb-4 px-4 py-3 rounded-lg border border-warning/40 bg-warning/10 text-sm text-warning flex items-center gap-2"
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <AlertTriangle className="w-4 h-4 flex-shrink-0" />
            Audit backend offline — Integrity Scores unavailable. Claims data below is live; scores show “—” rather than an approximation.
          </motion.div>
        )}

        {/* Summary Stats */}
        <motion.div
          className="grid grid-cols-4 gap-4 mb-6"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
        >
          {[
            { label: 'Total Companies', value: resolved.length, icon: Building2, color: 'text-primary', tooltip: '' },
            { label: 'Average Integrity', value: avgScore != null ? `${avgScore}%` : '—', icon: CheckCircle2, color: 'text-success', tooltip: 'ESG Integrity Score (100 − greenwashing penalties) from the backend audit, averaged across companies. Same methodology as the Integrity Audit page; each company scored on its latest report.' },
            { label: 'Total Claims', value: totalClaims, icon: Globe2, color: 'text-foreground', tooltip: '' },
            { label: 'Active Gaps', value: gapCount, icon: AlertTriangle, color: 'text-danger', tooltip: '' },
          ].map((stat, i) => (
            <motion.div
              key={stat.label}
              className="glass-panel p-4 card-lift relative group"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.1 }}
            >
              <div className="flex items-center justify-between mb-2">
                <stat.icon className={cn("w-5 h-5", stat.color)} />
              </div>
              <p className="counter-value text-2xl">{stat.value}</p>
              <span className="text-xs text-muted-foreground">{stat.label}</span>
              {stat.tooltip && (
                <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 bg-popover border border-border rounded-lg shadow-lg text-xs text-muted-foreground max-w-[200px] text-center opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10">
                  {stat.tooltip}
                  <div className="absolute top-full left-1/2 -translate-x-1/2 -mt-1 border-4 border-transparent border-t-popover" />
                </div>
              )}
            </motion.div>
          ))}
        </motion.div>

        <div className="grid grid-cols-12 gap-6">
          {/* Companies List */}
          <div className="col-span-8">
            <motion.div 
              className="glass-panel"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 }}
            >
              <div className="px-4 py-3 border-b border-border/30 flex items-center justify-between">
                <h3 className="text-sm font-medium text-foreground">Portfolio Companies</h3>
                <span className="text-xs text-muted-foreground">
                  {visible.length === resolved.length
                    ? `${resolved.length} companies`
                    : `${visible.length} of ${resolved.length} companies`}
                </span>
              </div>
              <div className="divide-y divide-border/20">
                {visible.length === 0 && (
                  <div className="p-8 text-center text-sm text-muted-foreground">
                    No company matches this filter.
                  </div>
                )}
                {visible.map((company, index) => (
                  <motion.div
                    key={company.id}
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.3 + index * 0.05 }}
                  >
                    {/* The WHOLE row is the link. It already had cursor-pointer and a
                        hover state, but only the 20px chevron actually navigated - and
                        it went to the unscoped /claims, throwing away the company you
                        just clicked. Now it opens that company's drill-down. */}
                    <Link
                      to={`/claims?view=claims&company=${encodeURIComponent(company.name)}`}
                      className="flex items-center gap-4 p-4 hover:bg-muted/20 transition-colors group"
                    >
                      {/* Company Info */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-foreground">{company.name}</span>
                          {company.integrityScore != null ? (
                            <span className={cn(
                              "text-[10px] px-1.5 py-0.5 rounded uppercase font-medium",
                              company.riskLevel === 'low' ? "bg-success/20 text-success" :
                              company.riskLevel === 'medium' ? "bg-warning/20 text-warning" :
                              "bg-danger/20 text-danger"
                            )}>
                              {company.riskLevel} risk
                            </span>
                          ) : (
                            <span className="text-[10px] px-1.5 py-0.5 rounded uppercase font-medium bg-muted/40 text-muted-foreground">
                              unscored
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-3 mt-1">
                          <span className="text-xs text-muted-foreground">{company.sector}</span>
                          <span className="text-xs text-muted-foreground flex items-center gap-1">
                            <MapPin className="w-3 h-3" />
                            {company.locations.slice(0, 2).join(', ')}
                            {company.locations.length > 2 && ` +${company.locations.length - 2}`}
                          </span>
                        </div>
                      </div>

                      {/* Integrity Score (backend-only; "—" when unavailable) */}
                      <div className="flex items-center gap-3">
                        <div className="text-right">
                          <div className="flex items-center gap-1">
                            <span className={cn(
                              "font-mono text-lg font-bold",
                              company.integrityScore == null ? "text-muted-foreground" :
                              company.integrityScore >= 70 ? "text-success" :
                              company.integrityScore >= 40 ? "text-warning" :
                              "text-danger"
                            )}>
                              {company.integrityScore ?? '—'}
                            </span>
                            {company.trend === 'up' && <TrendingUp className="w-4 h-4 text-success" />}
                            {company.trend === 'down' && <TrendingDown className="w-4 h-4 text-danger" />}
                          </div>
                          <span className="text-[10px] text-muted-foreground">Integrity Score</span>
                        </div>
                        <div className="w-16 h-16 relative">
                          <svg className="w-full h-full -rotate-90">
                            <circle
                              cx="32" cy="32" r="28"
                              className="fill-none stroke-muted"
                              strokeWidth="4"
                            />
                            <motion.circle
                              cx="32" cy="32" r="28"
                              className={cn(
                                "fill-none",
                                company.integrityScore == null ? "stroke-muted" :
                                company.integrityScore >= 70 ? "stroke-success" :
                                company.integrityScore >= 40 ? "stroke-warning" :
                                "stroke-danger"
                              )}
                              strokeWidth="4"
                              strokeLinecap="round"
                              strokeDasharray={`${(company.integrityScore ?? 0) * 1.76} 176`}
                              initial={{ strokeDasharray: "0 176" }}
                              animate={{ strokeDasharray: `${(company.integrityScore ?? 0) * 1.76} 176` }}
                              transition={{ duration: 1, delay: 0.3 + index * 0.05 }}
                            />
                          </svg>
                        </div>
                      </div>

                      {/* Claims Breakdown */}
                      <div className="flex items-center gap-3 px-4 border-l border-border/30">
                        <div className="text-center">
                          <span className="text-sm font-mono text-success">{company.claims.verified}</span>
                          <span className="block text-[10px] text-muted-foreground">Verified</span>
                        </div>
                        <div className="text-center">
                          <span className="text-sm font-mono text-warning">{company.claims.review}</span>
                          <span className="block text-[10px] text-muted-foreground">Review</span>
                        </div>
                        <div className="text-center">
                          <span className="text-sm font-mono text-danger">{company.claims.gap}</span>
                          <span className="block text-[10px] text-muted-foreground">Gaps</span>
                        </div>
                      </div>

                      <ChevronRight className="w-5 h-5 text-muted-foreground group-hover:text-primary group-hover:translate-x-0.5 transition-all flex-shrink-0" />
                    </Link>
                  </motion.div>
                ))}
              </div>
            </motion.div>
          </div>

          {/* Geographic Distribution */}
          <div className="col-span-4">
            <motion.div 
              className="glass-panel h-full"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.3 }}
            >
              <div className="px-4 py-3 border-b border-border/30">
                <h3 className="text-sm font-medium text-foreground flex items-center gap-2">
                  <Globe2 className="w-4 h-4 text-primary" />
                  Geographic Distribution
                </h3>
              </div>
              <div className="p-4 space-y-4">
                {regionData.map((region, i) => (
                  <motion.div
                    key={region.region}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.4 + i * 0.1 }}
                  >
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-sm text-foreground">{region.region}</span>
                      <div className="flex items-center gap-3 text-xs">
                        <span className="text-muted-foreground">{region.companies} cos</span>
                        <span className={cn(
                          "font-mono",
                          region.avgScore == null ? "text-muted-foreground" :
                          region.avgScore >= 70 ? "text-success" :
                          region.avgScore >= 50 ? "text-warning" :
                          "text-danger"
                        )}>
                          {region.avgScore != null ? `${region.avgScore}%` : '—'}
                        </span>
                      </div>
                    </div>
                    <div className="h-2 rounded-full bg-muted overflow-hidden">
                      <motion.div
                        className={cn(
                          "h-full rounded-full",
                          region.avgScore == null ? "bg-muted" :
                          region.avgScore >= 70 ? "bg-success" :
                          region.avgScore >= 50 ? "bg-warning" :
                          "bg-danger"
                        )}
                        initial={{ width: 0 }}
                        animate={{ width: `${region.avgScore ?? 0}%` }}
                        transition={{ duration: 0.8, delay: 0.4 + i * 0.1 }}
                      />
                    </div>
                  </motion.div>
                ))}
              </div>

              {/* Risk Distribution */}
              <div className="p-4 border-t border-border/30">
                <h4 className="text-xs text-muted-foreground uppercase tracking-wider mb-3">
                  Risk Distribution{scored.length > 0 ? '' : ' (no scored companies)'}
                </h4>
                <div className="flex items-center gap-2">
                  <div className="flex-1 h-3 rounded-full overflow-hidden flex">
                    <motion.div
                      className="bg-success h-full"
                      initial={{ width: 0 }}
                      animate={{ width: `${riskDist.low}%` }}
                      transition={{ duration: 0.8, delay: 0.5 }}
                    />
                    <motion.div
                      className="bg-warning h-full"
                      initial={{ width: 0 }}
                      animate={{ width: `${riskDist.medium}%` }}
                      transition={{ duration: 0.8, delay: 0.6 }}
                    />
                    <motion.div
                      className="bg-danger h-full"
                      initial={{ width: 0 }}
                      animate={{ width: `${riskDist.high}%` }}
                      transition={{ duration: 0.8, delay: 0.7 }}
                    />
                  </div>
                </div>
                <div className="flex items-center justify-between mt-2 text-xs">
                  <span className="text-success">Low {riskDist.low}%</span>
                  <span className="text-warning">Medium {riskDist.medium}%</span>
                  <span className="text-danger">High {riskDist.high}%</span>
                </div>
              </div>
            </motion.div>
          </div>
        </div>
      </div>
    </AppLayout>
  );
};

export default PortfolioOverview;
