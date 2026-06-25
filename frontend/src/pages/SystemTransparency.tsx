import { motion } from 'framer-motion';
import { useMemo } from 'react';
import {
  BarChart3,
  Target,
  Activity,
  Layers,
  Cpu,
  Loader2,
} from 'lucide-react';
import { AppLayout } from '@/components/AppLayout';
import { cn } from '@/lib/utils';
import { useClaims } from '@/hooks/useClaims';
import { metricLabel } from '@/lib/metricLabels';

// Honest description of the real pipeline (no satellite/NDVI claims).
const pipelineStages = [
  { stage: 'PDF Parsing', detail: 'PyMuPDF + pdfplumber structural extraction, layout classification, section hierarchy' },
  { stage: 'Claim Extraction', detail: 'LLM-assisted (Groq llama-3.1-8b) with rule-based candidate detection fallback' },
  { stage: 'Ontology Mapping', detail: 'Claims normalized to an ESG aspect taxonomy (emissions, water, social, governance…)' },
  { stage: 'Groundability Scoring', detail: 'Rule-based scoring of specificity, measurability, and provenance' },
  { stage: 'Contradiction Reasoning', detail: 'Semantic retrieval + DistilBERT-MNLI natural language inference over claim pairs' },
];

const SystemTransparency = () => {
  const { claims, companies, conflicts, loading } = useClaims();

  const stats = useMemo(() => {
    const total = claims.length || 0;
    const high = claims.filter(c => c.confidence >= 75).length;
    const medium = claims.filter(c => c.confidence >= 50 && c.confidence < 75).length;
    const low = claims.filter(c => c.confidence < 50).length;
    const withMetric = claims.filter(c => c.metricValue !== undefined).length;
    const withLocation = claims.filter(c => c.location !== 'Unspecified').length;

    // ESG aspect breakdown (real, from normalized aspect / metric family)
    const aspectMap = new Map<string, number>();
    claims.forEach(c => {
      const key = c.normalizedAspect || c.metricKey || 'uncategorized';
      aspectMap.set(key, (aspectMap.get(key) || 0) + 1);
    });
    const aspects = Array.from(aspectMap.entries())
      .map(([k, v]) => ({ key: k, count: v }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 12);

    // Claim type distribution (real)
    const typeMap = new Map<string, number>();
    claims.forEach(c => {
      const k = c.verifiabilityClass || 'General';
      typeMap.set(k, (typeMap.get(k) || 0) + 1);
    });
    const types = Array.from(typeMap.entries())
      .map(([k, v]) => ({ key: k, count: v }))
      .sort((a, b) => b.count - a.count);

    return { total, high, medium, low, withMetric, withLocation, aspects, types };
  }, [claims]);

  if (loading) {
    return (
      <AppLayout>
        <div className="flex-1 flex items-center justify-center min-h-[60vh]">
          <Loader2 className="w-8 h-8 text-primary animate-spin" />
        </div>
      </AppLayout>
    );
  }

  const pct = (n: number) => (stats.total ? Math.round((n / stats.total) * 100) : 0);
  const maxAspect = stats.aspects[0]?.count || 1;

  return (
    <AppLayout>
      {/* Header */}
      <motion.header
        className="h-16 border-b border-border/30 glass-panel flex items-center px-6"
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <div>
          <h1 className="text-lg font-semibold text-foreground">System Transparency</h1>
          <p className="text-xs text-muted-foreground">Live methodology and data statistics from the claim database</p>
        </div>
      </motion.header>

      <div className="flex-1 p-6 overflow-auto">
        <div className="max-w-5xl mx-auto space-y-6">
          {/* Top counters */}
          <motion.div className="grid grid-cols-2 md:grid-cols-4 gap-4" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
            {[
              { label: 'Total Claims', value: stats.total },
              { label: 'Companies', value: companies.length },
              { label: 'Contradictions', value: conflicts.length },
              { label: 'With Numeric Metric', value: `${pct(stats.withMetric)}%` },
            ].map(s => (
              <div key={s.label} className="glass-panel p-4">
                <p className="counter-value text-2xl">{s.value}</p>
                <span className="text-xs text-muted-foreground">{s.label}</span>
              </div>
            ))}
          </motion.div>

          {/* Methodology */}
          <motion.section className="glass-panel p-6" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
            <h2 className="font-medium text-foreground flex items-center gap-2 mb-1">
              <Layers className="w-5 h-5 text-primary" /> Verification Pipeline
            </h2>
            <p className="text-xs text-muted-foreground mb-4">
              ESGenuine verifies <strong>textual</strong> ESG claims. It does not use satellite imagery — assessment is based on
              claim specificity, provenance, and cross-claim contradiction reasoning.
            </p>
            <div className="space-y-3">
              {pipelineStages.map((s, i) => (
                <div key={s.stage} className="flex items-start gap-3">
                  <span className="w-6 h-6 rounded-full bg-primary/15 text-primary text-xs flex items-center justify-center font-mono shrink-0 mt-0.5">
                    {i + 1}
                  </span>
                  <div>
                    <span className="text-sm font-medium text-foreground">{s.stage}</span>
                    <p className="text-xs text-muted-foreground">{s.detail}</p>
                  </div>
                </div>
              ))}
            </div>
          </motion.section>

          {/* Groundability distribution (real) */}
          <motion.section className="glass-panel p-6" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}>
            <h2 className="font-medium text-foreground flex items-center gap-2 mb-4">
              <BarChart3 className="w-5 h-5 text-success" /> Groundability Distribution
            </h2>
            <div className="space-y-3">
              {[
                { label: 'High (≥75)', value: stats.high, color: 'bg-success', text: 'text-success' },
                { label: 'Medium (50–74)', value: stats.medium, color: 'bg-warning', text: 'text-warning' },
                { label: 'Low (<50)', value: stats.low, color: 'bg-danger', text: 'text-danger' },
              ].map(row => (
                <div key={row.label}>
                  <div className="flex items-center justify-between mb-1 text-xs">
                    <span className="text-muted-foreground">{row.label}</span>
                    <span className={cn('font-mono', row.text)}>{row.value} · {pct(row.value)}%</span>
                  </div>
                  <div className="h-2 rounded-full bg-muted overflow-hidden">
                    <motion.div className={cn('h-full rounded-full', row.color)} initial={{ width: 0 }} animate={{ width: `${pct(row.value)}%` }} transition={{ duration: 0.8 }} />
                  </div>
                </div>
              ))}
            </div>
          </motion.section>

          {/* ESG aspect breakdown (real) */}
          <motion.section className="glass-panel p-6" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}>
            <h2 className="font-medium text-foreground flex items-center gap-2 mb-4">
              <Target className="w-5 h-5 text-primary" /> ESG Aspect Breakdown
            </h2>
            {stats.aspects.length === 0 ? (
              <p className="text-sm text-muted-foreground">No claims in the database yet.</p>
            ) : (
              <div className="space-y-2">
                {stats.aspects.map(a => (
                  <div key={a.key} className="flex items-center gap-3">
                    <span className="text-xs text-muted-foreground w-48 truncate" title={a.key}>{metricLabel(a.key)}</span>
                    <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
                      <motion.div className="h-full rounded-full bg-primary/70" initial={{ width: 0 }} animate={{ width: `${(a.count / maxAspect) * 100}%` }} transition={{ duration: 0.6 }} />
                    </div>
                    <span className="text-xs font-mono text-foreground w-8 text-right">{a.count}</span>
                  </div>
                ))}
              </div>
            )}
          </motion.section>

          {/* Claim type + models */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <motion.section className="glass-panel p-6" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.35 }}>
              <h2 className="font-medium text-foreground flex items-center gap-2 mb-4">
                <Activity className="w-5 h-5 text-primary" /> Claim Type Distribution
              </h2>
              <div className="space-y-2">
                {stats.types.map(t => (
                  <div key={t.key} className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground capitalize">{t.key}</span>
                    <span className="font-mono text-foreground">{t.count} · {pct(t.count)}%</span>
                  </div>
                ))}
              </div>
            </motion.section>

            <motion.section className="glass-panel p-6" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }}>
              <h2 className="font-medium text-foreground flex items-center gap-2 mb-4">
                <Cpu className="w-5 h-5 text-success" /> Models in Use
              </h2>
              <div className="space-y-3 text-sm">
                <div>
                  <span className="text-muted-foreground block text-xs">Claim Extraction</span>
                  <span className="font-mono text-foreground">Groq llama-3.1-8b-instant</span>
                </div>
                <div>
                  <span className="text-muted-foreground block text-xs">Embeddings</span>
                  <span className="font-mono text-foreground">sentence-transformers (BGE / MiniLM)</span>
                </div>
                <div>
                  <span className="text-muted-foreground block text-xs">Contradiction NLI</span>
                  <span className="font-mono text-foreground">DistilBERT-MNLI</span>
                </div>
              </div>
            </motion.section>
          </div>
        </div>
      </div>
    </AppLayout>
  );
};

export default SystemTransparency;
