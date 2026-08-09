// Cross-company benchmark + year-over-year drift — the UX payoff of the
// canonical metric_key work: every number here is unit-gated (the backend never
// compares across canonical units) and count-weighted upstream.
import { useState } from 'react';
import { motion } from 'framer-motion';
import { useQuery } from '@tanstack/react-query';
import { BarChart3, TrendingDown, TrendingUp, Minus, AlertTriangle, Loader2 } from 'lucide-react';
import { AppLayout } from '@/components/AppLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { getCrossCompany, getTrajectory, getPortfolioIntegrity } from '@/lib/api';
import { metricLabel } from '@/lib/metricLabels';

// Curated comparison set: metrics with real cross-company surface in the corpus.
const METRICS = [
  'emissions.scope1.co2e',
  'emissions.scope2.co2e',
  'emissions.total.co2e',
  'emissions.intensity.intensity',
  'energy.renewable.power',
  'energy.total.energy',
  'water.consumption.volume',
  'waste.total.mass',
  'social.health_safety.ltifr.rate',
  'social.diversity.gender.percent',
];

const fmt = (v: number) =>
  Math.abs(v) >= 1e9 ? `${(v / 1e9).toFixed(2)}B`
  : Math.abs(v) >= 1e6 ? `${(v / 1e6).toFixed(2)}M`
  : Math.abs(v) >= 1e3 ? `${(v / 1e3).toFixed(1)}k`
  : `${Math.round(v * 1000) / 1000}`;

export default function Benchmark() {
  const [metric, setMetric] = useState(METRICS[0]);
  const [company, setCompany] = useState<string | null>(null);

  const cross = useQuery({ queryKey: ['bench', metric], queryFn: () => getCrossCompany(metric) });
  const portfolio = useQuery({ queryKey: ['portfolio'], queryFn: getPortfolioIntegrity });
  const activeCompany = company ?? cross.data?.entries?.[0]?.company ?? null;
  const traj = useQuery({
    queryKey: ['traj', activeCompany, metric],
    queryFn: () => getTrajectory(activeCompany!, metric),
    enabled: !!activeCompany,
  });

  const entries = cross.data?.entries ?? [];
  const maxVal = Math.max(...entries.map((e) => Math.abs(e.value)), 1e-9);
  const lowerBetter = cross.data?.polarity === 'lower_better';

  return (
    <AppLayout>
      <div className="p-6 space-y-6 max-w-6xl mx-auto">
        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <BarChart3 className="w-6 h-6 text-primary" /> Cross-Company Benchmark
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Latest reported figure per company on one canonical metric — units are gated, so
            intensities never silently compare against absolutes.
          </p>
        </motion.div>

        {/* metric selector */}
        <div className="flex flex-wrap gap-2">
          {METRICS.map((m) => (
            <button
              key={m}
              onClick={() => { setMetric(m); setCompany(null); }}
              className={cn(
                'px-3 py-1.5 rounded-full text-xs border transition-colors',
                m === metric
                  ? 'bg-primary text-primary-foreground border-primary'
                  : 'border-border/50 text-muted-foreground hover:border-primary/50',
              )}
            >
              {metricLabel(m)}
            </button>
          ))}
        </div>

        {/* ranked comparison */}
        <Card className="glass-panel">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground flex items-center gap-2">
              {metricLabel(metric)}
              {cross.data?.polarity && (
                <Badge variant="outline" className="text-[10px]">
                  {lowerBetter ? 'lower is better' : 'higher is better'}
                </Badge>
              )}
              {cross.data?.unit && <span className="text-[10px]">({cross.data.unit})</span>}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {cross.isLoading ? (
              <Loader2 className="animate-spin" />
            ) : entries.length === 0 ? (
              <p className="text-sm text-muted-foreground flex items-center gap-2">
                <AlertTriangle className="w-4 h-4" /> No two companies share this metric on a common
                canonical unit yet — coverage grows as reports are re-ingested.
              </p>
            ) : (
              <div className="space-y-2">
                {entries.map((e, i) => (
                  <button
                    key={e.company}
                    onClick={() => setCompany(e.company)}
                    className={cn(
                      'w-full text-left group',
                      activeCompany === e.company && 'opacity-100',
                    )}
                  >
                    <div className="flex items-center gap-3">
                      <span className="w-28 shrink-0 text-xs truncate">{e.company}</span>
                      <div className="flex-1 h-5 rounded bg-muted/30 overflow-hidden">
                        <div
                          className={cn(
                            'h-full rounded transition-all',
                            i === 0 ? (lowerBetter ? 'bg-green-500/70' : 'bg-primary/80') : 'bg-primary/40',
                            activeCompany === e.company && 'ring-1 ring-primary',
                          )}
                          style={{ width: `${Math.max(2, (Math.abs(e.value) / maxVal) * 100)}%` }}
                        />
                      </div>
                      <span className="w-24 shrink-0 text-right text-xs font-mono">
                        {fmt(e.value)}
                      </span>
                      <span className="w-10 shrink-0 text-right text-[10px] text-muted-foreground">
                        {e.year}
                      </span>
                    </div>
                  </button>
                ))}
                {(cross.data?.dropped_units ?? 0) > 0 && (
                  <p className="text-[11px] text-muted-foreground mt-1">
                    {cross.data?.dropped_units} compan{(cross.data?.dropped_units ?? 0) === 1 ? 'y' : 'ies'} excluded:
                    reported in a different canonical unit (never mixed).
                  </p>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* year-over-year drift for the selected company */}
        {activeCompany && (
          <Card className="glass-panel">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm text-muted-foreground">
                Year-over-year — {activeCompany} · {metricLabel(metric)}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {traj.isLoading ? (
                <Loader2 className="animate-spin" />
              ) : (traj.data?.series?.length ?? 0) < 2 ? (
                <p className="text-sm text-muted-foreground">
                  Only one reporting year on record for this metric — drift appears once a second
                  year is ingested.
                </p>
              ) : (
                <div className="space-y-3">
                  <div className="flex items-end gap-4 h-28">
                    {traj.data!.series.map((p) => {
                      const maxS = Math.max(...traj.data!.series.map((s) => Math.abs(s.value)), 1e-9);
                      return (
                        <div key={p.year} className="flex flex-col items-center gap-1 flex-1">
                          <span className="text-[10px] font-mono">{fmt(p.value)}</span>
                          <div
                            className="w-full max-w-16 rounded-t bg-primary/60"
                            style={{ height: `${Math.max(4, (Math.abs(p.value) / maxS) * 80)}px` }}
                          />
                          <span className="text-[10px] text-muted-foreground">{p.year}</span>
                        </div>
                      );
                    })}
                  </div>
                  {traj.data?.change_pct != null && (
                    <p className="text-xs flex items-center gap-2">
                      {traj.data.change! < 0 ? (
                        <TrendingDown className={cn('w-4 h-4', lowerBetter ? 'text-green-400' : 'text-destructive')} />
                      ) : traj.data.change! > 0 ? (
                        <TrendingUp className={cn('w-4 h-4', lowerBetter ? 'text-destructive' : 'text-green-400')} />
                      ) : (
                        <Minus className="w-4 h-4" />
                      )}
                      {traj.data.change_pct}% over the reported span
                      {Math.abs(traj.data.change_pct) >= 25 && (
                        <Badge variant="outline" className="text-[10px] text-yellow-400 border-yellow-400/40">
                          large swing — check methodology changes / restatements
                        </Badge>
                      )}
                    </p>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        )}

        <p className="text-[11px] text-muted-foreground">
          Companies in portfolio: {portfolio.data?.count ?? '—'}. Values are the extractor's
          representative figure per company-year on the canonical unit; benchmark precision inherits
          the measured extraction quality (89.7 out-of-sample).
        </p>
      </div>
    </AppLayout>
  );
}
