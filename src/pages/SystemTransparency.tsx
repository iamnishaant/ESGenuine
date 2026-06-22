import { motion } from 'framer-motion';
import { 
  ShieldCheck, 
  AlertTriangle, 
  Info, 
  BarChart3,
  Target,
  Activity,
  ChevronDown,
  ExternalLink,
  BookOpen
} from 'lucide-react';
import { AppLayout } from '@/components/AppLayout';
import { cn } from '@/lib/utils';
import { useState } from 'react';

const modelLimitations = [
  {
    title: 'Temporal Coverage Gaps',
    severity: 'medium',
    description: 'Satellite imagery may have gaps due to cloud cover, especially in tropical regions. Some claims cannot be verified during monsoon seasons.',
    mitigation: 'System automatically flags claims requiring multi-temporal verification and suggests alternative data sources (SAR, ground truth).'
  },
  {
    title: 'Resolution Constraints',
    severity: 'low',
    description: 'Sentinel-2 optical imagery at 10m resolution may not detect small-scale interventions (<0.1 hectares).',
    mitigation: 'Claims involving small areas trigger manual review and may require high-resolution commercial imagery.'
  },
  {
    title: 'Attribution Uncertainty',
    severity: 'high',
    description: 'Distinguishing between natural and anthropogenic changes can be challenging. Forest fires vs. intentional clearing may be misclassified.',
    mitigation: 'Multi-modal analysis (NDVI + SAR + thermal) improves attribution accuracy. Human validation required for ambiguous cases.'
  },
  {
    title: 'Baseline Data Quality',
    severity: 'medium',
    description: 'Historical baselines before 2015 may be incomplete or lower resolution, affecting long-term trend analysis.',
    mitigation: 'Confidence scores are adjusted based on baseline data quality. Alternative historical sources are cross-referenced when available.'
  },
];

const calibrationData = [
  { confidence: '90-100%', accuracy: 97, samples: 1234 },
  { confidence: '80-89%', accuracy: 89, samples: 2156 },
  { confidence: '70-79%', accuracy: 78, samples: 1876 },
  { confidence: '60-69%', accuracy: 65, samples: 943 },
  { confidence: '50-59%', accuracy: 54, samples: 412 },
  { confidence: '<50%', accuracy: 38, samples: 187 },
];

const verifiabilityFactors = [
  { factor: 'Claim Specificity', weight: 25, description: 'Quantifiable metrics (hectares, percentages) increase verifiability' },
  { factor: 'Geographic Precision', weight: 20, description: 'Exact coordinates vs. vague regional references' },
  { factor: 'Temporal Clarity', weight: 20, description: 'Specific dates/periods vs. general timeframes' },
  { factor: 'Data Availability', weight: 20, description: 'Satellite coverage and historical data for the region' },
  { factor: 'Physical Observability', weight: 15, description: 'Whether the claim relates to physically observable changes' },
];

const SystemTransparency = () => {
  const [expandedSection, setExpandedSection] = useState<string | null>('limitations');

  return (
    <AppLayout>
      {/* Header */}
      <motion.header 
        className="h-16 border-b border-border/30 glass-panel flex items-center justify-between px-6"
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <div>
          <h1 className="text-lg font-semibold text-foreground">System Transparency</h1>
          <p className="text-xs text-muted-foreground">Model limitations, confidence calibration, and verification methodology</p>
        </div>
        <motion.a
          href="#"
          className="flex items-center gap-2 text-sm text-primary hover:text-primary/80 transition-colors"
          whileHover={{ scale: 1.02 }}
        >
          <BookOpen className="w-4 h-4" />
          Technical Documentation
          <ExternalLink className="w-3 h-3" />
        </motion.a>
      </motion.header>

      {/* Content */}
      <div className="flex-1 p-6 overflow-auto">
        <div className="max-w-5xl mx-auto space-y-6">
          {/* Model Limitations */}
          <motion.section
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <button
              onClick={() => setExpandedSection(expandedSection === 'limitations' ? null : 'limitations')}
              className="w-full glass-panel p-4 flex items-center justify-between hover:border-primary/30 transition-colors"
            >
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-warning/20 flex items-center justify-center">
                  <AlertTriangle className="w-5 h-5 text-warning" />
                </div>
                <div className="text-left">
                  <h2 className="font-medium text-foreground">Known Model Limitations</h2>
                  <p className="text-xs text-muted-foreground">Documented constraints and mitigation strategies</p>
                </div>
              </div>
              <motion.div
                animate={{ rotate: expandedSection === 'limitations' ? 180 : 0 }}
              >
                <ChevronDown className="w-5 h-5 text-muted-foreground" />
              </motion.div>
            </button>

            {expandedSection === 'limitations' && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                className="mt-2 space-y-3"
              >
                {modelLimitations.map((limitation, i) => (
                  <motion.div
                    key={limitation.title}
                    className="glass-panel p-4"
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.1 }}
                  >
                    <div className="flex items-start gap-3">
                      <div className={cn(
                        "w-2 h-2 rounded-full mt-2 flex-shrink-0",
                        limitation.severity === 'high' ? "bg-danger" :
                        limitation.severity === 'medium' ? "bg-warning" :
                        "bg-success"
                      )} />
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1">
                          <h3 className="font-medium text-foreground">{limitation.title}</h3>
                          <span className={cn(
                            "text-[10px] px-1.5 py-0.5 rounded uppercase",
                            limitation.severity === 'high' ? "bg-danger/20 text-danger" :
                            limitation.severity === 'medium' ? "bg-warning/20 text-warning" :
                            "bg-success/20 text-success"
                          )}>
                            {limitation.severity} impact
                          </span>
                        </div>
                        <p className="text-sm text-muted-foreground mb-2">{limitation.description}</p>
                        <div className="p-2 rounded bg-muted/30 border-l-2 border-primary">
                          <span className="text-xs text-primary font-medium">Mitigation: </span>
                          <span className="text-xs text-muted-foreground">{limitation.mitigation}</span>
                        </div>
                      </div>
                    </div>
                  </motion.div>
                ))}
              </motion.div>
            )}
          </motion.section>

          {/* Claim Verifiability Estimator */}
          <motion.section
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
          >
            <button
              onClick={() => setExpandedSection(expandedSection === 'verifiability' ? null : 'verifiability')}
              className="w-full glass-panel p-4 flex items-center justify-between hover:border-primary/30 transition-colors"
            >
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-primary/20 flex items-center justify-center">
                  <Target className="w-5 h-5 text-primary" />
                </div>
                <div className="text-left">
                  <h2 className="font-medium text-foreground">Claim Verifiability Estimator</h2>
                  <p className="text-xs text-muted-foreground">How we assess whether claims can be verified with available data</p>
                </div>
              </div>
              <motion.div
                animate={{ rotate: expandedSection === 'verifiability' ? 180 : 0 }}
              >
                <ChevronDown className="w-5 h-5 text-muted-foreground" />
              </motion.div>
            </button>

            {expandedSection === 'verifiability' && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                className="mt-2 glass-panel p-6"
              >
                <p className="text-sm text-muted-foreground mb-6">
                  The Verifiability Score (0-100) estimates how reliably a claim can be assessed using satellite imagery 
                  and other available data sources. Higher scores indicate claims that are more amenable to independent verification.
                </p>
                
                <div className="space-y-4">
                  {verifiabilityFactors.map((factor, i) => (
                    <motion.div
                      key={factor.factor}
                      initial={{ opacity: 0, x: -20 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: i * 0.1 }}
                    >
                      <div className="flex items-center justify-between mb-1.5">
                        <span className="text-sm font-medium text-foreground">{factor.factor}</span>
                        <span className="text-sm font-mono text-primary">{factor.weight}%</span>
                      </div>
                      <div className="h-2 rounded-full bg-muted overflow-hidden mb-1">
                        <motion.div
                          className="h-full rounded-full bg-primary"
                          initial={{ width: 0 }}
                          animate={{ width: `${factor.weight}%` }}
                          transition={{ duration: 0.8, delay: i * 0.1 }}
                        />
                      </div>
                      <p className="text-xs text-muted-foreground">{factor.description}</p>
                    </motion.div>
                  ))}
                </div>

                <div className="mt-6 p-4 rounded-lg bg-muted/30 border border-border/50">
                  <div className="flex items-start gap-2">
                    <Info className="w-4 h-4 text-primary flex-shrink-0 mt-0.5" />
                    <div>
                      <span className="text-sm font-medium text-foreground">Score Interpretation</span>
                      <p className="text-xs text-muted-foreground mt-1">
                        <strong>80-100:</strong> High verifiability - Satellite data can provide strong evidence<br />
                        <strong>60-79:</strong> Moderate verifiability - Additional data sources may be needed<br />
                        <strong>40-59:</strong> Limited verifiability - Ground truth or third-party validation recommended<br />
                        <strong>&lt;40:</strong> Low verifiability - Claim may not be suitable for satellite-based verification
                      </p>
                    </div>
                  </div>
                </div>
              </motion.div>
            )}
          </motion.section>

          {/* Confidence Calibration */}
          <motion.section
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
          >
            <button
              onClick={() => setExpandedSection(expandedSection === 'calibration' ? null : 'calibration')}
              className="w-full glass-panel p-4 flex items-center justify-between hover:border-primary/30 transition-colors"
            >
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-success/20 flex items-center justify-center">
                  <BarChart3 className="w-5 h-5 text-success" />
                </div>
                <div className="text-left">
                  <h2 className="font-medium text-foreground">Confidence Calibration</h2>
                  <p className="text-xs text-muted-foreground">Historical accuracy of model predictions at different confidence levels</p>
                </div>
              </div>
              <motion.div
                animate={{ rotate: expandedSection === 'calibration' ? 180 : 0 }}
              >
                <ChevronDown className="w-5 h-5 text-muted-foreground" />
              </motion.div>
            </button>

            {expandedSection === 'calibration' && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                className="mt-2 glass-panel p-6"
              >
                <p className="text-sm text-muted-foreground mb-6">
                  This calibration chart shows how well our confidence scores align with actual accuracy. 
                  A well-calibrated model should have accuracy close to the stated confidence level.
                </p>

                <div className="grid grid-cols-6 gap-4 mb-6">
                  {calibrationData.map((d, i) => (
                    <motion.div
                      key={d.confidence}
                      className="text-center"
                      initial={{ opacity: 0, y: 20 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: i * 0.1 }}
                    >
                      <div className="h-40 flex flex-col items-center justify-end mb-2">
                        <div className="w-full flex justify-center gap-1">
                          {/* Expected bar */}
                          <motion.div
                            className="w-6 bg-muted/50 rounded-t"
                            initial={{ height: 0 }}
                            animate={{ height: `${parseInt(d.confidence) || 45}%` }}
                            transition={{ duration: 0.8, delay: i * 0.1 }}
                          />
                          {/* Actual bar */}
                          <motion.div
                            className={cn(
                              "w-6 rounded-t",
                              Math.abs(d.accuracy - (parseInt(d.confidence) || 45)) < 10 
                                ? "bg-success" 
                                : "bg-warning"
                            )}
                            initial={{ height: 0 }}
                            animate={{ height: `${d.accuracy}%` }}
                            transition={{ duration: 0.8, delay: i * 0.1 + 0.1 }}
                          />
                        </div>
                      </div>
                      <span className="text-[10px] text-muted-foreground block">{d.confidence}</span>
                      <span className="text-xs font-mono text-foreground">{d.accuracy}%</span>
                      <span className="text-[10px] text-muted-foreground block">n={d.samples}</span>
                    </motion.div>
                  ))}
                </div>

                <div className="flex items-center gap-6 text-xs text-muted-foreground">
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded bg-muted/50" />
                    <span>Expected Accuracy</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded bg-success" />
                    <span>Actual Accuracy (calibrated)</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 rounded bg-warning" />
                    <span>Actual Accuracy (needs calibration)</span>
                  </div>
                </div>
              </motion.div>
            )}
          </motion.section>

          {/* System Health */}
          <motion.section
            className="glass-panel-highlight p-6"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
          >
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-lg bg-success/20 flex items-center justify-center">
                <Activity className="w-5 h-5 text-success" />
              </div>
              <div>
                <h2 className="font-medium text-foreground">System Health & Version</h2>
                <p className="text-xs text-muted-foreground">Current operational status and model versions</p>
              </div>
            </div>

            <div className="grid grid-cols-4 gap-4">
              {[
                { label: 'NLP Model', value: 'v2.4.0', status: 'active' },
                { label: 'Change Detection', value: 'v2.0.0', status: 'active' },
                { label: 'Satellite Pipeline', value: 'v3.2.0', status: 'active' },
                { label: 'Last Calibration', value: '2026-04-09', status: 'recent' },
              ].map((item, i) => (
                <motion.div
                  key={item.label}
                  className="p-3 rounded-lg bg-muted/30"
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ delay: 0.4 + i * 0.1 }}
                >
                  <span className="text-xs text-muted-foreground block mb-1">{item.label}</span>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-sm text-foreground">{item.value}</span>
                    <span className="w-1.5 h-1.5 rounded-full bg-success animate-pulse" />
                  </div>
                </motion.div>
              ))}
            </div>
          </motion.section>
        </div>
      </div>
    </AppLayout>
  );
};

export default SystemTransparency;
