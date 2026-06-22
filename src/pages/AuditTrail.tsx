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
  Satellite,
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

interface AuditStep {
  id: string;
  timestamp: string;
  type: 'system' | 'ai' | 'human' | 'satellite';
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
  satellite: { icon: Satellite, color: 'text-success', bg: 'bg-success/10' },
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

    const baseTime = new Date('2024-01-15T09:00:00Z').getTime();
    
    const steps: AuditStep[] = [
      {
        id: '1',
        timestamp: new Date(baseTime).toISOString().replace('T', ' ').substring(0, 19),
        type: 'system',
        title: 'Claim Ingestion',
        description: `ESG report section extracted and parsed from ${currentClaim.company} narrative.`,
        details: [
          'Document source structured text',
          'Language detected: English',
          `Claim identified at page: ${currentClaim.page || 'Unknown'}`,
        ],
        status: 'completed',
        expandable: true
      },
      {
        id: '2',
        timestamp: new Date(baseTime + 123000).toISOString().replace('T', ' ').substring(0, 19),
        type: 'ai',
        title: 'NLP Claim Extraction',
        description: 'Vision-grounded NLP model extracted and classified the claim.',
        details: [
          'Model: PHAROS-NLP v2.3',
          `Claim extracted: "${currentClaim.claim}"`,
          `Claim metric category: ${currentClaim.sector}`,
          `Specificity classification: ${currentClaim.verifiabilityClass}`
        ],
        status: 'completed',
        expandable: true
      },
      {
        id: '3',
        timestamp: new Date(baseTime + 347000).toISOString().replace('T', ' ').substring(0, 19),
        type: 'ai',
        title: 'Integrity Scoring Assessment',
        description: 'Multi-agent reasoning evaluated the groundability of the extracted claim.',
        details: [
          `Groundability Score: ${currentClaim.confidence}/100`,
          `Risk Level: ${currentClaim.riskLevel.toUpperCase()}`,
          `Entity extracted: ${currentClaim.location}`
        ],
        status: currentClaim.status === 'gap' ? 'error' : currentClaim.status === 'review' ? 'warning' : 'completed',
        expandable: true
      }
    ];

    if (currentClaim.status === 'gap' || currentClaim.status === 'review') {
      steps.push({
        id: '4',
        timestamp: new Date(baseTime + 900000).toISOString().replace('T', ' ').substring(0, 19),
        type: 'human',
        title: 'Analyst Flag Generation',
        description: `System flagged claim for review due to ${currentClaim.riskLevel} risk assessment.`,
        details: [
          'Review status: Pending',
          'Recommended Action: Manual verification required',
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
            className="flex items-center gap-2 px-3 py-2 rounded-lg bg-muted/50 border border-border/50 text-sm text-muted-foreground hover:text-foreground hover:border-primary/50 transition-all"
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
          >
            <Eye className="w-4 h-4" />
            Preview
          </motion.button>
          <motion.button
            className="flex items-center gap-2 px-3 py-2 rounded-lg bg-muted/50 border border-border/50 text-sm text-muted-foreground hover:text-foreground hover:border-primary/50 transition-all"
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
          >
            <Printer className="w-4 h-4" />
            Print
          </motion.button>
          <motion.button
            className="flex items-center gap-2 px-3 py-2 rounded-lg bg-muted/50 border border-border/50 text-sm text-muted-foreground hover:text-foreground hover:border-primary/50 transition-all"
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
          >
            <Share2 className="w-4 h-4" />
            Share
          </motion.button>
          <motion.button
            className="btn-neon flex items-center gap-2 text-sm"
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
          >
            <Download className="w-4 h-4" />
            Export Artifacts
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
                            <span className="text-xs text-muted-foreground flex items-center gap-1">
                              <Clock className="w-3 h-3" />
                              {step.timestamp}
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

          {/* Export Section */}
          <motion.div 
            className="mt-8 glass-panel p-6"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.5 }}
          >
            <h3 className="text-sm font-medium text-foreground mb-4 flex items-center gap-2">
              <Download className="w-4 h-4 text-primary" />
              Export Audit Artifacts
            </h3>
            <div className="grid grid-cols-3 gap-4">
              {[
                { label: 'Full Audit Report', format: 'PDF', size: '2.4 MB' },
                { label: 'Evidence Package', format: 'ZIP', size: '156 MB' },
                { label: 'Machine-Readable Log', format: 'JSON', size: '45 KB' },
              ].map((artifact, i) => (
                <motion.button
                  key={artifact.label}
                  className="p-4 rounded-lg bg-muted/30 border border-border/50 hover:border-primary/50 transition-all text-left group"
                  whileHover={{ scale: 1.02, y: -2 }}
                  whileTap={{ scale: 0.98 }}
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-mono text-primary">{artifact.format}</span>
                    <Download className="w-4 h-4 text-muted-foreground group-hover:text-primary transition-colors" />
                  </div>
                  <span className="text-sm font-medium text-foreground block">{artifact.label}</span>
                  <span className="text-xs text-muted-foreground">{artifact.size}</span>
                </motion.button>
              ))}
            </div>
          </motion.div>
        </div>
      </div>
      
      {/* Regulatory Disclaimer Footer */}
      <RegulatoryDisclaimer />
    </AppLayout>
  );
};

export default AuditTrail;
