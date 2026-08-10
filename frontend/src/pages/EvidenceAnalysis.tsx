import { useParams, Link } from 'react-router-dom';
import { useMemo } from 'react';
import { motion } from 'framer-motion';
import {
  CheckCircle2,
  Clock,
  AlertTriangle,
  AlertCircle,
  Download,
  ChevronRight,
  MapPin,
  FileText,
  Calendar,
  Target,
  Quote,
  GitCompare,
  Loader2,
} from 'lucide-react';
import { AppLayout } from '@/components/AppLayout';
import { cn } from '@/lib/utils';
import { RegulatoryDisclaimer } from '@/components/RegulatoryDisclaimer';
import { useClaims } from '@/hooks/useClaims';
import { metricLabel } from '@/lib/metricLabels';

const statusConfig = {
  verified: { label: 'Verified', icon: CheckCircle2, class: 'status-verified' },
  review: { label: 'Under Review', icon: Clock, class: 'status-review' },
  gap: { label: 'Integrity Gap', icon: AlertTriangle, class: 'status-gap' },
};

const ScoreBar = ({ label, value, hint }: { label: string; value: number; hint?: string }) => {
  const color = value >= 70 ? 'bg-success' : value >= 40 ? 'bg-warning' : 'bg-danger';
  const text = value >= 70 ? 'text-success' : value >= 40 ? 'text-warning' : 'text-danger';
  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-xs text-muted-foreground">{label}</span>
        <span className={cn('text-xs font-mono', text)}>{value}%</span>
      </div>
      <div className="h-1.5 rounded-full bg-muted overflow-hidden">
        <motion.div
          className={cn('h-full rounded-full', color)}
          initial={{ width: 0 }}
          animate={{ width: `${value}%` }}
          transition={{ duration: 0.8 }}
        />
      </div>
      {hint && <p className="text-[10px] text-muted-foreground/70 mt-1">{hint}</p>}
    </div>
  );
};

const EvidenceAnalysis = () => {
  const { claimId } = useParams<{ claimId: string }>();
  const { claims, conflicts, loading, error } = useClaims();

  // The sidebar links here as /evidence with NO claim id, so "find by id" returned
  // undefined and a top-level nav item rendered "Claim Not Found - the requested
  // claim ID does not exist". With no id there is no request to fail: fall back to
  // the most interesting claim, the way the Audit Trail page already does.
  const currentClaim = useMemo(() => {
    if (claims.length === 0) return undefined;
    if (claimId) return claims.find((c) => c.id === claimId);
    return claims.find((c) => c.status === 'gap') ?? claims[0];
  }, [claims, claimId]);

  if (loading) {
    return (
      <AppLayout>
        <div className="flex-1 flex flex-col items-center justify-center min-h-[60vh] gap-4">
          <Loader2 className="w-8 h-8 text-primary animate-spin" />
          <p className="text-muted-foreground text-sm">Loading evidence analysis...</p>
        </div>
      </AppLayout>
    );
  }

  if (!currentClaim) {
    return (
      <AppLayout>
        <div className="flex-1 flex flex-col items-center justify-center min-h-[60vh] gap-4 px-6 text-center">
          <AlertTriangle className="w-12 h-12 text-warning" />
          {error ? (
            <>
              <h2 className="text-xl font-semibold">Could not load claims</h2>
              <p className="text-muted-foreground max-w-md">
                The claims query failed. Nothing is missing from the corpus — the fetch did not
                complete.
              </p>
              <p className="text-xs font-mono text-muted-foreground">{error.message}</p>
            </>
          ) : claims.length === 0 ? (
            <>
              <h2 className="text-xl font-semibold">No claims in the corpus yet</h2>
              <p className="text-muted-foreground max-w-md">
                Ingest an ESG report and its claims will appear here for analysis.
              </p>
              <Link to="/submit-report" className="btn-neon mt-4">Ingest a report</Link>
            </>
          ) : (
            <>
              <h2 className="text-xl font-semibold">Claim not found</h2>
              <p className="text-muted-foreground max-w-md">
                No claim with ID <span className="font-mono text-foreground">{claimId}</span> exists
                in the {claims.length.toLocaleString()} loaded claims — the link is probably stale,
                since claim IDs are regenerated when a report is re-ingested.
              </p>
              <Link to="/claims" className="btn-neon mt-4">Browse the Claim Directory</Link>
            </>
          )}
        </div>
      </AppLayout>
    );
  }

  const StatusIcon = statusConfig[currentClaim.status].icon;

  // Real contradictions involving this claim (from the contradictions table).
  const relatedConflicts = conflicts
    .filter(c => c.claim_a_id === currentClaim.id || c.claim_b_id === currentClaim.id)
    .map(c => {
      const isA = c.claim_a_id === currentClaim.id;
      return {
        id: c.id,
        otherText: isA ? c.claim_b_text : c.claim_a_text,
        severity: c.severity,
        type: c.conflict_type,
        reasoning: c.reasoning,
        confidence: c.confidence,
      };
    });

  const hasMetric = currentClaim.metricValue !== undefined;
  const timeframe = currentClaim.timeStart
    ? `${currentClaim.timeStart}${currentClaim.timeEnd ? ` → ${currentClaim.timeEnd}` : ''}`
    : currentClaim.reportYear
    ? `FY ${currentClaim.reportYear} (report year)`
    : 'Not specified';

  const exportReport = () => {
    const payload = {
      claim_id: currentClaim.id,
      company: currentClaim.company,
      report_year: currentClaim.reportYear,
      source_sentence: currentClaim.claim,
      page: currentClaim.page,
      aspect: currentClaim.normalizedAspect || currentClaim.metricKey,
      metric: hasMetric
        ? { value: currentClaim.metricValue, unit: currentClaim.metricUnit, direction: currentClaim.metricDirection }
        : null,
      location: currentClaim.location,
      timeframe,
      groundability_score: currentClaim.confidence,
      verifiability_score: currentClaim.verifiability,
      vagueness_score: currentClaim.vagueness,
      claim_type: currentClaim.verifiabilityClass,
      status: currentClaim.status,
      contradictions: relatedConflicts,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `evidence_${currentClaim.id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <AppLayout>
      {/* Breadcrumb */}
      <motion.div
        className="px-6 py-2 border-b border-border/20 flex items-center gap-2 text-xs"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
      >
        <Link to="/claims" className="text-muted-foreground hover:text-primary transition-colors">
          Claim Explorer
        </Link>
        <ChevronRight className="w-3 h-3 text-muted-foreground" />
        <span className="text-primary font-mono">{currentClaim.id.slice(0, 8)}</span>
        <ChevronRight className="w-3 h-3 text-muted-foreground" />
        <span className="text-foreground">Evidence Analysis</span>
      </motion.div>

      {/* Header */}
      <motion.header
        className="h-16 border-b border-border/30 glass-panel flex items-center justify-between px-6"
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <div className="min-w-0">
          <h1 className="text-lg font-semibold text-foreground">Evidence Analysis</h1>
          <p className="text-xs text-muted-foreground truncate max-w-[60ch]">
            {currentClaim.company} · {currentClaim.normalizedAspect || currentClaim.sector}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className={statusConfig[currentClaim.status].class}>
            <StatusIcon className="w-3.5 h-3.5" />
            {statusConfig[currentClaim.status].label}
          </span>
          <motion.button
            onClick={exportReport}
            className="btn-neon flex items-center gap-2 text-sm"
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
          >
            <Download className="w-4 h-4" />
            Export JSON
          </motion.button>
        </div>
      </motion.header>

      {/* Main Content */}
      <div className="flex-1 p-6 overflow-auto">
        <div className="grid grid-cols-12 gap-6">
          {/* Left Column */}
          <div className="col-span-12 lg:col-span-8 flex flex-col gap-6">
            {/* Source Evidence — verbatim extracted text */}
            <motion.div
              className="glass-panel p-5"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
            >
              <h3 className="text-sm font-medium text-foreground mb-3 flex items-center gap-2">
                <Quote className="w-4 h-4 text-primary" />
                Source Evidence
              </h3>
              <blockquote className="text-sm text-foreground leading-relaxed border-l-2 border-primary/40 pl-4 whitespace-pre-line">
                {currentClaim.claim}
              </blockquote>
              <div className="flex items-center gap-4 mt-4 text-xs text-muted-foreground">
                <span className="flex items-center gap-1">
                  <FileText className="w-3 h-3" /> Page {currentClaim.page ?? '—'}
                </span>
                <span className="flex items-center gap-1">
                  <MapPin className="w-3 h-3" /> {currentClaim.location}
                </span>
                <span className="flex items-center gap-1">
                  <Calendar className="w-3 h-3" /> {timeframe}
                </span>
              </div>
            </motion.div>

            {/* Extracted Structure */}
            <motion.div
              className="glass-panel p-5"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 }}
            >
              <h3 className="text-sm font-medium text-foreground mb-4 flex items-center gap-2">
                <Target className="w-4 h-4 text-primary" />
                Extracted Structure
              </h3>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
                <div>
                  <span className="text-muted-foreground block text-xs mb-1">Metric Value</span>
                  <span className="text-foreground font-mono">
                    {hasMetric ? `${currentClaim.metricValue!.toLocaleString()} ${currentClaim.metricUnit || ''}`.trim() : '—'}
                  </span>
                </div>
                <div>
                  <span className="text-muted-foreground block text-xs mb-1">Direction</span>
                  <span className="text-foreground capitalize">{currentClaim.metricDirection || '—'}</span>
                </div>
                <div>
                  <span className="text-muted-foreground block text-xs mb-1">Claim Type</span>
                  <span className="text-foreground capitalize">{currentClaim.verifiabilityClass}</span>
                </div>
                <div>
                  <span className="text-muted-foreground block text-xs mb-1">ESG Aspect</span>
                  <span className="text-foreground text-xs" title={currentClaim.metricKey || currentClaim.normalizedAspect || ''}>{currentClaim.metricKey || currentClaim.normalizedAspect ? metricLabel(currentClaim.metricKey || currentClaim.normalizedAspect) : '—'}</span>
                </div>
                <div>
                  <span className="text-muted-foreground block text-xs mb-1">Location</span>
                  <span className="text-foreground">{currentClaim.location}</span>
                </div>
                <div>
                  <span className="text-muted-foreground block text-xs mb-1">Report Year</span>
                  <span className="text-foreground">{currentClaim.reportYear ?? '—'}</span>
                </div>
              </div>
            </motion.div>

            {/* Contradictions involving this claim */}
            <motion.div
              className="glass-panel p-5"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2 }}
            >
              <h3 className="text-sm font-medium text-foreground mb-4 flex items-center gap-2">
                <GitCompare className="w-4 h-4 text-primary" />
                Contradictions
                <span className="text-xs text-muted-foreground">({relatedConflicts.length})</span>
              </h3>
              {relatedConflicts.length === 0 ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground py-2">
                  <CheckCircle2 className="w-4 h-4 text-success" />
                  No contradictions detected against this claim.
                </div>
              ) : (
                <div className="space-y-3">
                  {relatedConflicts.map(rc => (
                    <div key={rc.id} className="p-3 rounded-lg bg-danger/5 border border-danger/20">
                      <div className="flex items-center gap-2 mb-1.5">
                        <span className={cn(
                          'text-[10px] px-1.5 py-0.5 rounded uppercase font-medium',
                          rc.severity === 'Critical' || rc.severity === 'High' ? 'bg-danger/20 text-danger' : 'bg-warning/20 text-warning'
                        )}>
                          {rc.severity} · {rc.type}
                        </span>
                        <span className="text-[10px] text-muted-foreground font-mono ml-auto">
                          {Math.round((rc.confidence || 0) * 100)}% confidence
                        </span>
                      </div>
                      <p className="text-xs text-muted-foreground mb-1">{rc.reasoning}</p>
                      <p className="text-xs text-foreground/80 italic border-l-2 border-danger/30 pl-2 mt-2">
                        vs. "{rc.otherText}"
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </motion.div>
          </div>

          {/* Right Column — real integrity scores */}
          <div className="col-span-12 lg:col-span-4 flex flex-col gap-6">
            <motion.div
              className="glass-panel p-5"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.1 }}
            >
              <h3 className="text-sm font-medium text-foreground mb-4 flex items-center gap-2">
                <Target className="w-4 h-4 text-primary" />
                Integrity Scores
              </h3>
              <div className="space-y-4">
                <ScoreBar label="Groundability" value={currentClaim.confidence} hint="How specific & measurable the claim is" />
                <ScoreBar label="Verifiability" value={currentClaim.verifiability} hint="Derived from inverse vagueness" />
                <ScoreBar label="Vagueness" value={currentClaim.vagueness} hint="Higher = less concrete language" />
              </div>
            </motion.div>

            <motion.div
              className="glass-panel-highlight p-5 flex-1"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.2 }}
            >
              <h3 className="text-sm font-medium text-foreground mb-3">Assessment</h3>
              <div className={cn(
                'p-3 rounded-lg border flex items-start gap-2',
                currentClaim.status === 'gap' ? 'bg-danger/10 border-danger/30'
                  : currentClaim.status === 'review' ? 'bg-warning/10 border-warning/30'
                  : 'bg-success/10 border-success/30'
              )}>
                <AlertCircle className={cn(
                  'w-4 h-4 mt-0.5 shrink-0',
                  currentClaim.status === 'gap' ? 'text-danger' : currentClaim.status === 'review' ? 'text-warning' : 'text-success'
                )} />
                <p className="text-xs leading-relaxed text-foreground">
                  {currentClaim.status === 'verified'
                    ? 'Claim is specific and measurable with strong groundability. No contradictions block verification.'
                    : currentClaim.status === 'gap'
                    ? 'Low groundability — the claim is vague or lacks measurable backing. Manual review recommended.'
                    : 'Moderate groundability — additional context or verification is recommended before acceptance.'}
                  {relatedConflicts.length > 0 && ` ${relatedConflicts.length} contradiction(s) detected against this claim.`}
                </p>
              </div>
            </motion.div>
          </div>
        </div>
      </div>

      {/* Regulatory Disclaimer Footer */}
      <RegulatoryDisclaimer />
    </AppLayout>
  );
};

export default EvidenceAnalysis;
