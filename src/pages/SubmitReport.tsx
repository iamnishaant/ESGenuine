import { motion, AnimatePresence } from 'framer-motion';
import { AppLayout } from '@/components/AppLayout';
import { 
  FilePlus, 
  Upload, 
  Building2, 
  MapPin, 
  Calendar,
  FileText,
  Link as LinkIcon,
  AlertCircle,
  CheckCircle2,
  Loader2,
  Sparkles,
  ShieldAlert,
  Target,
  Eye,
  TrendingUp,
  AlertTriangle,
  Plus,
  Trash2,
  Link2,
  Unlink2,
  Copy,
  GitCompare
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { 
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useState, useCallback } from 'react';
import { cn } from '@/lib/utils';
import { supabase } from '@/integrations/supabase/client';
import { useToast } from '@/hooks/use-toast';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';

const sectors = [
  'Energy',
  'Materials',
  'Industrials',
  'Consumer Discretionary',
  'Consumer Staples',
  'Healthcare',
  'Financials',
  'Technology',
  'Telecommunications',
  'Utilities',
  'Real Estate'
];

interface Claim {
  id: string;
  text: string;
  sourceUrl?: string;
  targetDate?: string;
}

interface ClaimAnalysis {
  id: string;
  claimType: string;
  specificityScore: number;
  verifiabilityScore: number;
  keyMetrics: string[];
  redFlags: string[];
  riskLevel: 'Low' | 'Medium' | 'High';
  summary: string;
}

interface Relationship {
  claimIds: string[];
  description: string;
  severity?: 'High' | 'Medium' | 'Low';
}

interface ReportAnalysis {
  claims: ClaimAnalysis[];
  relationships: {
    contradictions: Relationship[];
    supporting: Relationship[];
    duplicates: Relationship[];
    inconsistencies: Relationship[];
  };
  overallRiskLevel: 'Low' | 'Medium' | 'High';
  reportSummary: string;
}

const generateId = () => Math.random().toString(36).substring(2, 9);

const SubmitReport = () => {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [analysis, setAnalysis] = useState<ReportAnalysis | null>(null);
  const { toast } = useToast();
  
  const [companyInfo, setCompanyInfo] = useState({
    companyName: '',
    sector: '',
    location: '',
    additionalNotes: ''
  });

  const [claims, setClaims] = useState<Claim[]>([
    { id: generateId(), text: '', sourceUrl: '', targetDate: '' }
  ]);

  const addClaim = useCallback(() => {
    setClaims(prev => [...prev, { id: generateId(), text: '', sourceUrl: '', targetDate: '' }]);
    setAnalysis(null);
  }, []);

  const removeClaim = useCallback((id: string) => {
    setClaims(prev => prev.filter(c => c.id !== id));
    setAnalysis(null);
  }, []);

  const updateClaim = useCallback((id: string, field: keyof Claim, value: string) => {
    setClaims(prev => prev.map(c => c.id === id ? { ...c, [field]: value } : c));
    setAnalysis(null);
  }, []);

  const analyzeClaimsWithAI = async () => {
    const validClaims = claims.filter(c => c.text.trim());
    
    if (validClaims.length === 0) {
      toast({
        title: "No claims to analyze",
        description: "Please enter at least one claim statement.",
        variant: "destructive"
      });
      return;
    }

    setIsAnalyzing(true);
    setAnalysis(null);

    try {
      const { data, error } = await supabase.functions.invoke('analyze-claims', {
        body: {
          claims: validClaims.map(c => ({ id: c.id, text: c.text })),
          companyName: companyInfo.companyName,
          sector: companyInfo.sector
        }
      });

      if (error) throw error;

      if (data.analysis) {
        setAnalysis(data.analysis);
        toast({
          title: `${validClaims.length} claim${validClaims.length > 1 ? 's' : ''} analyzed`,
          description: "AI has detected relationships between claims.",
        });
      }
    } catch (error) {
      console.error('Analysis error:', error);
      toast({
        title: "Analysis failed",
        description: error instanceof Error ? error.message : "Could not analyze claims.",
        variant: "destructive"
      });
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!analysis) {
      toast({
        title: "Analyze first",
        description: "Please analyze the claims before submitting.",
        variant: "destructive"
      });
      return;
    }

    setIsSubmitting(true);
    await new Promise(resolve => setTimeout(resolve, 1500));
    
    setIsSubmitting(false);
    setSubmitted(true);
    
    toast({
      title: "Report submitted",
      description: `${claims.filter(c => c.text.trim()).length} claims queued for verification.`,
    });
    
    setTimeout(() => {
      setSubmitted(false);
      setAnalysis(null);
      setClaims([{ id: generateId(), text: '', sourceUrl: '', targetDate: '' }]);
      setCompanyInfo({
        companyName: '',
        sector: '',
        location: '',
        additionalNotes: ''
      });
    }, 3000);
  };

  const getRiskColor = (risk: string) => {
    switch (risk) {
      case 'Low': return 'text-success border-success/30 bg-success/10';
      case 'Medium': return 'text-warning border-warning/30 bg-warning/10';
      case 'High': return 'text-danger border-danger/30 bg-danger/10';
      default: return 'text-muted-foreground border-border bg-muted/50';
    }
  };

  const getScoreColor = (score: number) => {
    if (score >= 7) return 'text-success';
    if (score >= 4) return 'text-warning';
    return 'text-danger';
  };

  const getClaimAnalysis = (claimId: string) => {
    return analysis?.claims.find(c => c.id === claimId);
  };

  const getClaimIndex = (claimId: string) => {
    return claims.findIndex(c => c.id === claimId) + 1;
  };

  return (
    <AppLayout>
      <div className="p-6 space-y-6 max-w-7xl mx-auto">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="space-y-2"
        >
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-primary/10 border border-primary/20">
              <FilePlus className="w-6 h-6 text-primary" />
            </div>
            <div>
              <h1 className="text-2xl font-semibold text-foreground">Submit New Report</h1>
              <p className="text-sm text-muted-foreground">
                Add multiple ESG claims — AI will analyze relationships & contradictions
              </p>
            </div>
          </div>
        </motion.div>

        {/* Success Message */}
        <AnimatePresence>
          {submitted && (
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="glass-panel p-6 border-success/30 bg-success/5"
            >
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-full bg-success/20">
                  <CheckCircle2 className="w-6 h-6 text-success" />
                </div>
                <div>
                  <h3 className="font-medium text-success">Report Submitted Successfully</h3>
                  <p className="text-sm text-muted-foreground">
                    Your claims have been queued for verification analysis
                  </p>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
          {/* Form Column */}
          <motion.form
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
            onSubmit={handleSubmit}
            className="xl:col-span-2 space-y-6"
          >
            {/* Company Information */}
            <div className="glass-panel p-6 space-y-4">
              <h2 className="text-lg font-medium text-foreground flex items-center gap-2">
                <Building2 className="w-5 h-5 text-primary" />
                Company Information
              </h2>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="companyName">Company Name *</Label>
                  <Input
                    id="companyName"
                    placeholder="e.g., Acme Corporation"
                    value={companyInfo.companyName}
                    onChange={(e) => setCompanyInfo(prev => ({ ...prev, companyName: e.target.value }))}
                    required
                    className="bg-muted/50 border-border/50 focus:border-primary"
                  />
                </div>
                
                <div className="space-y-2">
                  <Label htmlFor="sector">Industry Sector *</Label>
                  <Select
                    value={companyInfo.sector}
                    onValueChange={(value) => setCompanyInfo(prev => ({ ...prev, sector: value }))}
                    required
                  >
                    <SelectTrigger className="bg-muted/50 border-border/50 focus:border-primary">
                      <SelectValue placeholder="Select sector" />
                    </SelectTrigger>
                    <SelectContent>
                      {sectors.map((sector) => (
                        <SelectItem key={sector} value={sector}>
                          {sector}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="location">Geographic Location</Label>
                <div className="relative">
                  <MapPin className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  <Input
                    id="location"
                    placeholder="e.g., United States, Europe, Global"
                    value={companyInfo.location}
                    onChange={(e) => setCompanyInfo(prev => ({ ...prev, location: e.target.value }))}
                    className="pl-10 bg-muted/50 border-border/50 focus:border-primary"
                  />
                </div>
              </div>
            </div>

            {/* Claims Section */}
            <div className="glass-panel p-6 space-y-4">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-medium text-foreground flex items-center gap-2">
                  <FileText className="w-5 h-5 text-primary" />
                  Claims
                  <Badge variant="secondary" className="ml-2">
                    {claims.filter(c => c.text.trim()).length} active
                  </Badge>
                </h2>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={addClaim}
                  className="gap-1.5"
                >
                  <Plus className="w-4 h-4" />
                  Add Claim
                </Button>
              </div>

              <div className="space-y-4">
                <AnimatePresence mode="popLayout">
                  {claims.map((claim, index) => {
                    const claimAnalysis = getClaimAnalysis(claim.id);
                    return (
                      <motion.div
                        key={claim.id}
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: 'auto' }}
                        exit={{ opacity: 0, height: 0 }}
                        layout
                        className={cn(
                          "p-4 rounded-lg border transition-all",
                          claimAnalysis 
                            ? `border-l-4 ${claimAnalysis.riskLevel === 'High' ? 'border-l-danger border-danger/20 bg-danger/5' : claimAnalysis.riskLevel === 'Medium' ? 'border-l-warning border-warning/20 bg-warning/5' : 'border-l-success border-success/20 bg-success/5'}`
                            : "border-border/50 bg-muted/30"
                        )}
                      >
                        <div className="flex items-start gap-3">
                          <div className="flex-shrink-0 w-8 h-8 rounded-full bg-primary/10 border border-primary/20 flex items-center justify-center text-sm font-medium text-primary">
                            {index + 1}
                          </div>
                          
                          <div className="flex-1 space-y-3">
                            <div className="flex items-start justify-between gap-2">
                              <Textarea
                                placeholder="Enter the ESG claim statement..."
                                value={claim.text}
                                onChange={(e) => updateClaim(claim.id, 'text', e.target.value)}
                                rows={2}
                                className="flex-1 bg-background/50 border-border/50 focus:border-primary resize-none text-sm"
                              />
                              {claims.length > 1 && (
                                <Button
                                  type="button"
                                  variant="ghost"
                                  size="icon"
                                  onClick={() => removeClaim(claim.id)}
                                  className="text-muted-foreground hover:text-danger flex-shrink-0"
                                >
                                  <Trash2 className="w-4 h-4" />
                                </Button>
                              )}
                            </div>

                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                              <div className="relative">
                                <LinkIcon className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                                <Input
                                  type="url"
                                  placeholder="Source URL"
                                  value={claim.sourceUrl}
                                  onChange={(e) => updateClaim(claim.id, 'sourceUrl', e.target.value)}
                                  className="pl-8 h-8 text-xs bg-background/50 border-border/50"
                                />
                              </div>
                              <div className="relative">
                                <Calendar className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                                <Input
                                  type="date"
                                  placeholder="Target date"
                                  value={claim.targetDate}
                                  onChange={(e) => updateClaim(claim.id, 'targetDate', e.target.value)}
                                  className="pl-8 h-8 text-xs bg-background/50 border-border/50"
                                />
                              </div>
                            </div>

                            {/* Inline analysis preview */}
                            {claimAnalysis && (
                              <motion.div
                                initial={{ opacity: 0, y: -10 }}
                                animate={{ opacity: 1, y: 0 }}
                                className="flex items-center gap-3 text-xs pt-1"
                              >
                                <Badge className={cn("text-xs", getRiskColor(claimAnalysis.riskLevel))}>
                                  {claimAnalysis.riskLevel} Risk
                                </Badge>
                                <span className="text-muted-foreground">{claimAnalysis.claimType}</span>
                                <span className={cn("font-mono", getScoreColor(claimAnalysis.specificityScore))}>
                                  S:{claimAnalysis.specificityScore}
                                </span>
                                <span className={cn("font-mono", getScoreColor(claimAnalysis.verifiabilityScore))}>
                                  V:{claimAnalysis.verifiabilityScore}
                                </span>
                              </motion.div>
                            )}
                          </div>
                        </div>
                      </motion.div>
                    );
                  })}
                </AnimatePresence>
              </div>

              {/* Analyze Button */}
              <div className="space-y-2">
                <Button
                  type="button"
                  onClick={analyzeClaimsWithAI}
                  disabled={isAnalyzing || claims.filter(c => c.text.trim()).length === 0}
                  className="w-full bg-gradient-to-r from-primary/80 to-primary hover:from-primary hover:to-primary/90 text-primary-foreground"
                >
                  {isAnalyzing ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      Analyzing {claims.filter(c => c.text.trim()).length} claims...
                    </>
                  ) : (
                    <>
                      <Sparkles className="w-4 h-4 mr-2" />
                      Analyze All Claims
                    </>
                  )}
                </Button>
                <p className="text-xs text-muted-foreground text-center">
                  This triggers automated claim extraction, contradiction analysis, and conditional geospatial verification.
                </p>
              </div>
            </div>

            {/* Additional Notes */}
            <div className="glass-panel p-6 space-y-4">
              <h2 className="text-lg font-medium text-foreground flex items-center gap-2">
                <FileText className="w-5 h-5 text-primary" />
                Additional Information
              </h2>
              
              <div className="space-y-2">
                <Label htmlFor="additionalNotes">Notes</Label>
                <Textarea
                  id="additionalNotes"
                  placeholder="Any additional context about this report..."
                  value={companyInfo.additionalNotes}
                  onChange={(e) => setCompanyInfo(prev => ({ ...prev, additionalNotes: e.target.value }))}
                  rows={2}
                  className="bg-muted/50 border-border/50 focus:border-primary resize-none"
                />
              </div>

              {/* Document Upload Placeholder */}
              <div className="space-y-2">
                <Label>Supporting Documents</Label>
                <div className="border-2 border-dashed border-border/50 rounded-lg p-4 text-center hover:border-primary/50 transition-colors cursor-pointer">
                  <Upload className="w-5 h-5 text-muted-foreground mx-auto mb-1" />
                  <p className="text-xs text-muted-foreground">
                    Drag and drop files (PDF, DOCX up to 10MB)
                  </p>
                </div>
              </div>
            </div>

            {/* Submit Button */}
            <div className="flex justify-end gap-3">
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setClaims([{ id: generateId(), text: '', sourceUrl: '', targetDate: '' }]);
                  setCompanyInfo({
                    companyName: '',
                    sector: '',
                    location: '',
                    additionalNotes: ''
                  });
                  setAnalysis(null);
                }}
                className="border-border/50"
              >
                Clear All
              </Button>
              <Button
                type="submit"
                disabled={isSubmitting || submitted || !analysis}
                className={cn(
                  "btn-neon min-w-[160px]",
                  (isSubmitting || submitted || !analysis) && "opacity-70"
                )}
              >
                {isSubmitting ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Submitting...
                  </>
                ) : submitted ? (
                  <>
                    <CheckCircle2 className="w-4 h-4 mr-2" />
                    Submitted
                  </>
                ) : (
                  <>
                    <FilePlus className="w-4 h-4 mr-2" />
                    Submit Report
                  </>
                )}
              </Button>
            </div>
          </motion.form>

          {/* Analysis Panel */}
          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.2 }}
            className="space-y-4"
          >
            <div className="glass-panel p-4 sticky top-6">
              <h3 className="text-sm font-medium text-foreground flex items-center gap-2 mb-4">
                <Sparkles className="w-4 h-4 text-primary" />
                AI Report Analysis
              </h3>

              <ScrollArea className="h-[calc(100vh-220px)]">
                <AnimatePresence mode="wait">
                  {isAnalyzing ? (
                    <motion.div
                      key="loading"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      className="flex flex-col items-center justify-center py-12 text-center"
                    >
                      <div className="relative">
                        <div className="w-12 h-12 rounded-full border-2 border-primary/30 border-t-primary animate-spin" />
                        <Sparkles className="w-5 h-5 text-primary absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2" />
                      </div>
                      <p className="text-sm text-muted-foreground mt-4">Analyzing claims & relationships...</p>
                    </motion.div>
                  ) : analysis ? (
                    <motion.div
                      key="analysis"
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0 }}
                      className="space-y-4 pr-2"
                    >
                      {/* Overall Risk */}
                      <div className={cn(
                        "inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium border",
                        getRiskColor(analysis.overallRiskLevel)
                      )}>
                        <ShieldAlert className="w-4 h-4" />
                        {analysis.overallRiskLevel} Overall Risk
                      </div>

                      {/* Report Summary */}
                      <div className="p-3 rounded-lg bg-muted/30 border border-border/30">
                        <p className="text-xs text-muted-foreground mb-1">Summary</p>
                        <p className="text-sm text-foreground">{analysis.reportSummary}</p>
                      </div>

                      {/* Contradictions */}
                      {analysis.relationships.contradictions.length > 0 && (
                        <div className="p-3 rounded-lg bg-danger/5 border border-danger/20">
                          <div className="flex items-center gap-1.5 mb-2">
                            <Unlink2 className="w-3.5 h-3.5 text-danger" />
                            <p className="text-xs font-medium text-danger">Contradictions Found</p>
                          </div>
                          <div className="space-y-2">
                            {analysis.relationships.contradictions.map((rel, i) => (
                              <div key={i} className="text-xs">
                                <div className="flex items-center gap-1.5 mb-1">
                                  <span className="font-mono text-danger">
                                    Claims {rel.claimIds.map(id => getClaimIndex(id)).join(' ↔ ')}
                                  </span>
                                  {rel.severity && (
                                    <Badge variant="outline" className={cn("text-[10px] px-1.5 py-0", getRiskColor(rel.severity))}>
                                      {rel.severity}
                                    </Badge>
                                  )}
                                </div>
                                <p className="text-muted-foreground">{rel.description}</p>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Inconsistencies */}
                      {analysis.relationships.inconsistencies.length > 0 && (
                        <div className="p-3 rounded-lg bg-warning/5 border border-warning/20">
                          <div className="flex items-center gap-1.5 mb-2">
                            <AlertTriangle className="w-3.5 h-3.5 text-warning" />
                            <p className="text-xs font-medium text-warning">Inconsistencies</p>
                          </div>
                          <div className="space-y-2">
                            {analysis.relationships.inconsistencies.map((rel, i) => (
                              <div key={i} className="text-xs">
                                <span className="font-mono text-warning">
                                  Claims {rel.claimIds.map(id => getClaimIndex(id)).join(' ↔ ')}:
                                </span>
                                <p className="text-muted-foreground mt-0.5">{rel.description}</p>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Supporting */}
                      {analysis.relationships.supporting.length > 0 && (
                        <div className="p-3 rounded-lg bg-success/5 border border-success/20">
                          <div className="flex items-center gap-1.5 mb-2">
                            <Link2 className="w-3.5 h-3.5 text-success" />
                            <p className="text-xs font-medium text-success">Supporting Claims</p>
                          </div>
                          <div className="space-y-2">
                            {analysis.relationships.supporting.map((rel, i) => (
                              <div key={i} className="text-xs">
                                <span className="font-mono text-success">
                                  Claims {rel.claimIds.map(id => getClaimIndex(id)).join(' + ')}:
                                </span>
                                <p className="text-muted-foreground mt-0.5">{rel.description}</p>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Duplicates */}
                      {analysis.relationships.duplicates.length > 0 && (
                        <div className="p-3 rounded-lg bg-muted/30 border border-border/30">
                          <div className="flex items-center gap-1.5 mb-2">
                            <Copy className="w-3.5 h-3.5 text-muted-foreground" />
                            <p className="text-xs font-medium text-muted-foreground">Potential Duplicates</p>
                          </div>
                          <div className="space-y-2">
                            {analysis.relationships.duplicates.map((rel, i) => (
                              <div key={i} className="text-xs">
                                <span className="font-mono">
                                  Claims {rel.claimIds.map(id => getClaimIndex(id)).join(' ≈ ')}:
                                </span>
                                <p className="text-muted-foreground mt-0.5">{rel.description}</p>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Individual Claim Details */}
                      <div className="pt-2">
                        <p className="text-xs font-medium text-muted-foreground mb-2 flex items-center gap-1.5">
                          <GitCompare className="w-3.5 h-3.5" />
                          Individual Claim Analysis
                        </p>
                        <div className="space-y-2">
                          {analysis.claims.map((claim, i) => (
                            <div
                              key={claim.id}
                              className={cn(
                                "p-2.5 rounded-lg border text-xs",
                                claim.riskLevel === 'High' ? 'border-danger/30 bg-danger/5' :
                                claim.riskLevel === 'Medium' ? 'border-warning/30 bg-warning/5' :
                                'border-success/30 bg-success/5'
                              )}
                            >
                              <div className="flex items-center justify-between mb-1.5">
                                <span className="font-medium">Claim {getClaimIndex(claim.id)}</span>
                                <Badge className={cn("text-[10px] px-1.5 py-0", getRiskColor(claim.riskLevel))}>
                                  {claim.riskLevel}
                                </Badge>
                              </div>
                              <p className="text-muted-foreground mb-1">{claim.claimType}</p>
                              <div className="flex gap-3">
                                <span className={cn("font-mono", getScoreColor(claim.specificityScore))}>
                                  <Target className="w-3 h-3 inline mr-0.5" />
                                  {claim.specificityScore}/10
                                </span>
                                <span className={cn("font-mono", getScoreColor(claim.verifiabilityScore))}>
                                  <Eye className="w-3 h-3 inline mr-0.5" />
                                  {claim.verifiabilityScore}/10
                                </span>
                              </div>
                              {claim.redFlags.length > 0 && (
                                <div className="mt-1.5 pt-1.5 border-t border-border/30">
                                  <p className="text-danger text-[10px] font-medium">Red Flags:</p>
                                  <ul className="text-muted-foreground">
                                    {claim.redFlags.slice(0, 2).map((flag, fi) => (
                                      <li key={fi} className="truncate">• {flag}</li>
                                    ))}
                                  </ul>
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    </motion.div>
                  ) : (
                    <motion.div
                      key="empty"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      className="text-center py-12"
                    >
                      <div className="w-12 h-12 rounded-full bg-muted/50 flex items-center justify-center mx-auto mb-3">
                        <AlertCircle className="w-6 h-6 text-muted-foreground" />
                      </div>
                      <p className="text-sm text-muted-foreground">
                        Add claims and click "Analyze All Claims" to see AI insights
                      </p>
                      <p className="text-xs text-muted-foreground/60 mt-2">
                        AI will detect contradictions, supporting claims & duplicates
                      </p>
                    </motion.div>
                  )}
                </AnimatePresence>
              </ScrollArea>
            </div>
          </motion.div>
        </div>
      </div>
    </AppLayout>
  );
};

export default SubmitReport;
