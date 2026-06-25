import { useState, useMemo } from 'react';
import { useParams, Link } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  ClipboardList, 
  Download, 
  ChevronDown, 
  ChevronRight,
  Clock,
  User,
  Bot,
  FileText,
  CheckCircle2,
  AlertCircle,
  Eye,
  Printer,
  Share2,
  Loader2,
  AlertTriangle
} from 'lucide-react';
import { AppLayout } from '@/components/AppLayout';
import { cn } from '@/lib/utils';
import { RegulatoryDisclaimer } from '@/components/RegulatoryDisclaimer';
import { useClaims } from '@/hooks/useClaims';
import { metricLabel } from '@/lib/metricLabels';

interface AuditStep {
  id: string;
  type: 'system' | 'ai' | 'human';
  title: string;
  description: string;
  details?: string[];
  status: 'completed' | 'warning' | 'error';
  expandable?: boolean;
}

const typeConfig = {
  system: { icon: FileText, color: 'text-muted-foreground', bg: 'bg-muted/50' },
  ai: { icon: Bot, color: 'text-primary', bg: 'bg-primary/10' },
  human: { icon: User, color: 'text-warning', bg: 'bg-warning/10' },
};

const AuditTrail = () => {
  const { claimId } = useParams<{ claimId: string }>();
  const { claims, loading } = useClaims();
  
  // Find claim or default to the first one that is a gap, or just the first one
  const currentClaim = useMemo(() => {
    if (claims.length === 0) return null;
    if (claimId) return claims.find(c => c.id === claimId) || null;
    return claims.find(c => c.status === 'gap') || claims[0];
  }, [claims, claimId]);

  const auditSteps = useMemo<AuditStep[]>(() => {
    if (!currentClaim) return [];

    const metricStr = currentClaim.metricValue !== undefined
      ? `${currentClaim.metricValue.toLocaleString()} ${currentClaim.metricUnit || ''}`.trim()
      : 'none extracted';

    const steps: AuditStep[] = [
      {
        id: '1',
        type: 'system',
        title: 'Claim Ingestion',
        description: `ESG report parsed from ${currentClaim.company}${currentClaim.reportYear ? ` (FY ${currentClaim.reportYear})` : ''}.`,
        details: [
          'Parser: PyMuPDF + pdfplumber structural extraction',
          `Source page: ${currentClaim.page ?? 'Unknown'}`,
          `Location reference: ${currentClaim.location}`,
        ],
        status: 'completed',
        expandable: true
      },
      {
        id: '2',
        type: 'ai',
        title: 'Claim Extraction',
        description: 'LLM-assisted extraction classified the claim and its structured fields.',
        details: [
          'Model: Groq llama-3.1-8b-instant',
          `Source sentence: "${currentClaim.claim}"`,
          `ESG aspect: ${currentClaim.metricKey || currentClaim.normalizedAspect ? metricLabel(currentClaim.metricKey || currentClaim.normalizedAspect) : currentClaim.sector}`,
          `Extracted metric: ${metricStr}`,
          `Claim type: ${currentClaim.verifiabilityClass}`,
        ],
        status: 'completed',
        expandable: true
      },
      {
        id: '3',
        type: 'ai',
        title: 'Integrity Scoring',
        description: 'Rule-based groundability scoring evaluated specificity and measurability.',
        details: [
          `Groundability score: ${currentClaim.confidence}/100`,
          `Verifiability score: ${currentClaim.verifiability}/100`,
          `Vagueness score: ${currentClaim.vagueness}/100`,
          `Risk level: ${currentClaim.riskLevel.toUpperCase()}`,
        ],
        status: currentClaim.status === 'gap' ? 'error' : currentClaim.status === 'review' ? 'warning' : 'completed',
        expandable: true
      }
    ];

    if (currentClaim.status === 'gap' || currentClaim.status === 'review') {
      steps.push({
        id: '4',
        type: 'human',
        title: 'Flagged for Review',
        description: `Claim flagged due to ${currentClaim.riskLevel} risk (low groundability).`,
        details: [
          'Review status: Pending',
          'Recommended action: Manual verification required',
        ],
        status: 'warning',
        expandable: true
      });
    }

    return steps;
  }, [currentClaim]);

  const [expandedSteps, setExpandedSteps] = useState<Set<string>>(new Set(['3', '4']));

  const toggleStep = (id: string) => {
    setExpandedSteps(prev => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const exportJson = () => {
    if (!currentClaim) return;
    const payload = {
      claim_id: currentClaim.id,
      company: currentClaim.company,
      report_year: currentClaim.reportYear,
      source_sentence: currentClaim.claim,
      page: currentClaim.page,
      status: currentClaim.status,
      groundability_score: currentClaim.confidence,
      verifiability_score: currentClaim.verifiability,
      vagueness_score: currentClaim.vagueness,
      audit_steps: auditSteps.map(s => ({
        title: s.title,
        description: s.description,
        details: s.details,
        status: s.status,
      })),
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `audit_${currentClaim.id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (loading) {
    return (
      <AppLayout>
        <div className="flex-1 flex flex-col items-center justify-center min-h-[60vh] gap-4">
          <Loader2 className="w-8 h-8 text-primary animate-spin" />
        </div>
      </AppLayout>
    );
  }

  if (!currentClaim) {
    return (
      <AppLayout>
        <div className="flex-1 flex flex-col items-center justify-center min-h-[60vh] gap-4">
          <AlertTriangle className="w-12 h-12 text-warning" />
          <h2 className="text-xl font-semibold">No Claims Available</h2>
          <p className="text-muted-foreground">Could not find any claims for the audit trail.</p>
        </div>
      </AppLayout>
    );
  }

  const statusColor = currentClaim.status === 'gap' ? 'text-danger' : currentClaim.status === 'review' ? 'text-warning' : 'text-success';
  const statusLabel = currentClaim.status === 'gap' ? 'Integrity Gap' : currentClaim.status === 'review' ? 'Under Review' : 'Verified';

  return (
    <AppLayout>
      {/* Header */}
      <motion.header 
        className="h-16 border-b border-border/30 glass-panel flex items-center justify-between px-6"
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <div>
          <h1 className="text-lg font-semibold text-foreground">Audit Trail & Explainability</h1>
          <p className="text-xs text-muted-foreground">Complete decision log for {currentClaim.id} • {currentClaim.company}</p>
        </div>
        <div className="flex items-center gap-2">
          <motion.button
            onClick={() => window.print()}
            className="flex items-center gap-2 px-3 py-2 rounded-lg bg-muted/50 border border-border/50 text-sm text-muted-foreground hover:text-foreground hover:border-primary/50 transition-all"
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
          >
            <Printer className="w-4 h-4" />
            Print
          </motion.button>
          <motion.button
            onClick={exportJson}
            className="btn-neon flex items-center gap-2 text-sm"
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
          >
            <Download className="w-4 h-4" />
            Export JSON
          </motion.button>
        </div>
      </motion.header>

      {/* Content */}
      <div className="flex-1 p-6 overflow-auto">
        <div className="max-w-4xl mx-auto">
          {/* Summary Card */}
          <motion.div 
            className="glass-panel-highlight p-6 mb-8"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <div className="grid grid-cols-4 gap-6">
              <div>
                <span className="text-xs text-muted-foreground uppercase tracking-wider">Claim ID</span>
                <p className="font-mono text-lg text-primary mt-1">{currentClaim.id}</p>
              </div>
              <div>
                <span className="text-xs text-muted-foreground uppercase tracking-wider">Total Steps</span>
                <p className="font-mono text-lg text-foreground mt-1">{auditSteps.length}</p>
              </div>
              <div>
                <span className="text-xs text-muted-foreground uppercase tracking-wider">Confidence</span>
                <p className="font-mono text-lg text-foreground mt-1">{currentClaim.confidence}%</p>
              </div>
              <div>
                <span className="text-xs text-muted-foreground uppercase tracking-wider">Final Status</span>
                <span className={cn("mt-1 inline-flex p-1 rounded font-medium", 
                  currentClaim.status === 'gap' ? 'bg-danger/10 text-danger border-danger/20' : 
                  currentClaim.status === 'review' ? 'bg-warning/10 text-warning border-warning/20' : 
                  'bg-success/10 text-success border-success/20')}>
                  <AlertCircle className="w-3.5 h-3.5 mr-1 mt-[2px]" />
                  {statusLabel}
                </span>
              </div>
            </div>
          </motion.div>

          {/* Timeline */}
          <div className="relative">
            {/* Vertical spine */}
            <div className="absolute left-[19px] top-0 bottom-0 w-0.5 bg-gradient-to-b from-primary via-primary/50 to-primary/20" />

            <div className="space-y-4">
              {auditSteps.map((step, index) => {
                const TypeIcon = typeConfig[step.type].icon;
                const isExpanded = expandedSteps.has(step.id);

                return (
                  <motion.div
                    key={step.id}
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: index * 0.1 }}
                    className="relative pl-12"
                  >
                    {/* Timeline node */}
                    <div className={cn(
                      "absolute left-0 w-10 h-10 rounded-full flex items-center justify-center border-2",
                      step.status === 'error' 
                        ? "border-danger bg-danger/20" 
                        : step.status === 'warning'
                        ? "border-warning bg-warning/20"
                        : "border-primary/50 bg-card"
                    )}>
                      <TypeIcon className={cn(
                        "w-4 h-4",
                        step.status === 'error' 
                          ? "text-danger" 
                          : step.status === 'warning'
                          ? "text-warning"
                          : typeConfig[step.type].color
                      )} />
                    </div>

                    {/* Content card */}
                    <div 
                      className={cn(
                        "glass-panel p-4 cursor-pointer transition-all",
                        step.expandable && "hover:border-primary/30",
                        step.status === 'error' && "border-danger/30",
                        step.status === 'warning' && "border-warning/30"
                      )}
                      onClick={() => step.expandable && toggleStep(step.id)}
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-1">
                            <span className={cn(
                              "text-xs px-2 py-0.5 rounded",
                              typeConfig[step.type].bg,
                              typeConfig[step.type].color
                            )}>
                              {step.type.toUpperCase()}
                            </span>
                          </div>
                          <h3 className="font-medium text-foreground">{step.title}</h3>
                          <p className="text-sm text-muted-foreground mt-1">{step.description}</p>
                        </div>
                        {step.expandable && (
                          <motion.div
                            animate={{ rotate: isExpanded ? 90 : 0 }}
                            transition={{ duration: 0.2 }}
                          >
                            <ChevronRight className="w-5 h-5 text-muted-foreground" />
                          </motion.div>
                        )}
                      </div>

                      {/* Expanded details */}
                      <AnimatePresence>
                        {step.expandable && isExpanded && step.details && (
                          <motion.div
                            initial={{ height: 0, opacity: 0 }}
                            animate={{ height: 'auto', opacity: 1 }}
                            exit={{ height: 0, opacity: 0 }}
                            transition={{ duration: 0.2 }}
                            className="overflow-hidden"
                          >
                            <div className="mt-4 pt-4 border-t border-border/30 space-y-2">
                              {step.details.map((detail, i) => (
                                <motion.div
                                  key={i}
                                  initial={{ opacity: 0, x: -10 }}
                                  animate={{ opacity: 1, x: 0 }}
                                  transition={{ delay: i * 0.05 }}
                                  className="flex items-start gap-2 text-sm"
                                >
                                  <span className="text-primary">•</span>
                                  <span className="text-muted-foreground font-mono text-xs">{detail}</span>
                                </motion.div>
                              ))}
                            </div>
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </div>
                  </motion.div>
                );
              })}
            </div>
          </div>

          {/* Export */}
          <motion.div
            className="mt-8 glass-panel p-6 flex items-center justify-between"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.5 }}
          >
            <div>
              <h3 className="text-sm font-medium text-foreground flex items-center gap-2">
                <Download className="w-4 h-4 text-primary" />
                Machine-Readable Audit Log
              </h3>
              <p className="text-xs text-muted-foreground mt-1">
                Download the claim, scores, and decision steps as JSON.
              </p>
            </div>
            <motion.button
              onClick={exportJson}
              className="btn-neon flex items-center gap-2 text-sm"
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              <Download className="w-4 h-4" />
              Export JSON
            </motion.button>
          </motion.div>
        </div>
      </div>
      
      {/* Regulatory Disclaimer Footer */}
      <RegulatoryDisclaimer />
    </AppLayout>
  );
};

export default AuditTrail;
