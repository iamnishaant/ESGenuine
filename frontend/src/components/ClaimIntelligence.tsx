import { motion, AnimatePresence } from 'framer-motion';
import { TrendingUp, TrendingDown, AlertTriangle, CheckCircle2, Eye, MapPin, BarChart3, Minus, ArrowLeft } from 'lucide-react';
import { ClaimVerifiabilityPanel } from './ClaimVerifiabilityPanel';
import { HumanEscalationPanel } from './HumanEscalationPanel';
import { useClaims, Claim } from '@/hooks/useClaims';
import { metricLabel } from '@/lib/metricLabels';

interface ClaimIntelligenceProps {
  selectedClaim: string | null;
  // When provided and a claim is shown, renders a back affordance (used to return
  // to the company's claim list after drilling in from a globe marker).
  onBack?: () => void;
}

const RadialGauge = ({ value, max, color, label }: { value: number; max: number; color: string; label: string }) => {
  const percentage = (value / max) * 100;
  const circumference = 2 * Math.PI * 40;
  const strokeDashoffset = circumference - (percentage / 100) * circumference;

  return (
    <div className="relative flex flex-col items-center">
      <svg width="100" height="100" className="-rotate-90">
        {/* Background ring */}
        <circle
          cx="50"
          cy="50"
          r="40"
          fill="none"
          stroke="hsl(var(--muted))"
          strokeWidth="8"
        />
        {/* Progress ring */}
        <motion.circle
          cx="50"
          cy="50"
          r="40"
          fill="none"
          stroke={color}
          strokeWidth="8"
          strokeLinecap="round"
          className="gauge-ring"
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset }}
          transition={{ duration: 1, ease: 'easeOut' }}
          style={{ strokeDasharray: circumference }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <motion.span 
          className="text-2xl font-bold font-mono"
          style={{ color }}
          initial={{ opacity: 0, scale: 0.5 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.5 }}
        >
          {value}%
        </motion.span>
      </div>
      <span className="text-xs text-muted-foreground mt-2">{label}</span>
    </div>
  );
};

const AnimatedBar = ({ value, color, label }: { value: number; color: string; label: string }) => {
  return (
    <div className="space-y-2">
      <div className="flex justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-mono" style={{ color }}>{value}%</span>
      </div>
      <div className="h-2 bg-muted rounded-full overflow-hidden">
        <motion.div
          className="h-full rounded-full relative overflow-hidden"
          style={{ backgroundColor: color }}
          initial={{ width: 0 }}
          animate={{ width: `${value}%` }}
          transition={{ duration: 1, ease: 'easeOut' }}
        >
          <div className="absolute inset-0 shimmer" />
        </motion.div>
      </div>
    </div>
  );
};

// Shows the real extracted metric for the claim (value, unit, direction).
// No fabricated time series — only what the extractor actually produced.
const MetricDetailCard = ({ claim }: { claim: Claim }) => {
  if (claim.metricValue === undefined) return null;
  const dir = (claim.metricDirection || '').toLowerCase();
  const DirIcon = dir.includes('increase') || dir.includes('rise')
    ? TrendingUp
    : dir.includes('decrease') || dir.includes('reduce') || dir.includes('drop')
    ? TrendingDown
    : Minus;

  return (
    <div className="space-y-3">
      <span className="text-xs text-muted-foreground flex items-center gap-1.5">
        <BarChart3 className="w-3.5 h-3.5 text-primary" />
        Extracted Metric
      </span>
      <div className="flex items-baseline gap-2">
        <span className="text-2xl font-bold font-mono text-foreground">
          {claim.metricValue.toLocaleString()}
        </span>
        <span className="text-sm text-muted-foreground">{claim.metricUnit || ''}</span>
        {dir && (
          <span className="ml-auto text-xs flex items-center gap-1 text-muted-foreground capitalize">
            <DirIcon className="w-3.5 h-3.5" />
            {claim.metricDirection}
          </span>
        )}
      </div>
      <div className="text-xs text-muted-foreground">
        Aspect: <span className="text-foreground/80" title={claim.metricKey || claim.normalizedAspect || ''}>{claim.metricKey || claim.normalizedAspect ? metricLabel(claim.metricKey || claim.normalizedAspect) : '—'}</span>
      </div>
    </div>
  );
};

export const ClaimIntelligence = ({ selectedClaim, onBack }: ClaimIntelligenceProps) => {
  const { claims } = useClaims();
  const claim = selectedClaim ? claims.find(c => c.id === selectedClaim) : null;
  
  const details = claim ? {
    integrityScore: claim.confidence,
    verifiabilityScore: claim.verifiability,
    confidenceLevel: claim.confidence >= 80 ? 'high' as const : claim.confidence >= 50 ? 'medium' as const : 'low' as const,
    // Evidence signals are the real provenance/structure the extractor produced.
    evidence: [
      claim.page ? `Source located on page ${claim.page}` : null,
      claim.metricValue !== undefined
        ? `Quantified metric: ${claim.metricValue.toLocaleString()} ${claim.metricUnit || ''}`.trim()
        : null,
      claim.location !== 'Unspecified' ? `Location referenced: ${claim.location}` : null,
      claim.normalizedAspect ? `ESG aspect: ${claim.normalizedAspect}` : `Category: ${claim.sector}`,
      claim.reportYear ? `Report year: ${claim.reportYear}` : null,
    ].filter(Boolean) as string[],
    recommendation: claim.status === 'verified'
      ? 'Claim supported by strong evidence chain. No further automated escalation required.'
      : claim.status === 'gap' 
      ? 'Critical integrity gap detected. Immediate human review recommended.' 
      : 'Claim requires additional manual verification.'
  } : null;

  const getScoreColor = (score: number) => {
    if (score >= 80) return 'hsl(var(--success))';
    if (score >= 50) return 'hsl(var(--warning))';
    return 'hsl(var(--danger))';
  };

  return (
    <motion.div 
      className="h-full flex flex-col glass-panel"
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.5 }}
    >
      {/* Header */}
      <div className="p-4 border-b border-border/50">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-primary/20 flex items-center justify-center">
            <Eye className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h2 className="font-semibold text-foreground">Claim Intelligence</h2>
            <p className="text-xs text-muted-foreground">Claim integrity analysis</p>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4">
        <AnimatePresence mode="wait">
          {claim && details ? (
            <motion.div
              key={claim.id}
              className="space-y-6"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              transition={{ duration: 0.3 }}
            >
              {onBack && (
                <button
                  onClick={onBack}
                  className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors -mt-1"
                >
                  <ArrowLeft className="w-3.5 h-3.5" />
                  Back to company claims
                </button>
              )}

              {/* Claim text */}
              <div className="glass-panel p-4 gradient-border">
                <p className="text-sm text-foreground leading-relaxed">{claim.claim}</p>
                <div className="flex items-center gap-2 mt-3">
                  <MapPin className="w-4 h-4 text-primary" />
                  <span className="text-xs text-primary">{claim.location}</span>
                </div>
              </div>

              {/* Scores */}
              <div className="grid grid-cols-2 gap-4">
                <div className="glass-panel p-4 flex flex-col items-center card-lift">
                  <RadialGauge
                    value={details.integrityScore}
                    max={100}
                    color={getScoreColor(details.integrityScore)}
                    label="Integrity Score"
                  />
                </div>
                <div className="glass-panel p-4 space-y-4 card-lift">
                  <AnimatedBar
                    value={details.verifiabilityScore}
                    color={getScoreColor(details.verifiabilityScore)}
                    label="Verifiability"
                  />
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">Confidence</span>
                    <span className={`text-xs font-medium capitalize ${
                      details.confidenceLevel === 'high' ? 'text-success' :
                      details.confidenceLevel === 'medium' ? 'text-warning' : 'text-danger'
                    }`}>
                      {details.confidenceLevel}
                    </span>
                  </div>
                </div>
              </div>

              {/* Real extracted metric (shown when the claim has a quantified value) */}
              {claim.metricValue !== undefined && (
                <motion.div
                  className="glass-panel p-4"
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ delay: 0.2 }}
                >
                  <MetricDetailCard claim={claim} />
                </motion.div>
              )}

              {/* Evidence */}
              <div className="space-y-3">
                <h3 className="text-sm font-medium text-foreground flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-primary" />
                  Evidence Signals
                </h3>
                <motion.ul 
                  className="space-y-2"
                  initial="hidden"
                  animate="visible"
                  variants={{
                    hidden: {},
                    visible: { transition: { staggerChildren: 0.1 } },
                  }}
                >
                  {details.evidence.map((item, i) => (
                    <motion.li
                      key={i}
                      className="text-xs text-muted-foreground flex items-start gap-2 p-2 rounded-lg hover:bg-muted/30 transition-colors"
                      variants={{
                        hidden: { opacity: 0, x: -10 },
                        visible: { opacity: 1, x: 0 },
                      }}
                    >
                      <span className="w-1.5 h-1.5 rounded-full bg-primary mt-1.5 flex-shrink-0" />
                      {item}
                    </motion.li>
                  ))}
                </motion.ul>
              </div>

              {/* Claim Verifiability Panel */}
              <ClaimVerifiabilityPanel selectedClaim={selectedClaim} />

              {/* Human Escalation Panel - for gap and review claims */}
              <HumanEscalationPanel claimId={claim.id} status={claim.status} />

              {/* Recommendation */}
              <motion.div 
                className={`p-4 rounded-lg border ${
                  claim.status === 'verified' 
                    ? 'bg-success/10 border-success/30' 
                    : claim.status === 'gap'
                    ? 'bg-danger/10 border-danger/30'
                    : 'bg-warning/10 border-warning/30'
                }`}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.4 }}
              >
                <div className="flex items-start gap-2">
                  <AlertTriangle className={`w-4 h-4 mt-0.5 ${
                    claim.status === 'verified' ? 'text-success' :
                    claim.status === 'gap' ? 'text-danger' : 'text-warning'
                  }`} />
                  <p className="text-xs leading-relaxed text-foreground">
                    {details.recommendation}
                  </p>
                </div>
              </motion.div>
            </motion.div>
          ) : (
            <motion.div
              className="h-full flex flex-col items-center justify-center text-center px-6"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
            >
              <div className="w-16 h-16 rounded-full bg-muted/50 flex items-center justify-center mb-4">
                <Eye className="w-8 h-8 text-muted-foreground" />
              </div>
              <h3 className="text-sm font-medium text-foreground mb-2">Select a Claim</h3>
              <p className="text-xs text-muted-foreground leading-relaxed">
                Click on any highlighted claim in the document viewer or a marker on the globe to view detailed intelligence analysis.
              </p>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  );
};
