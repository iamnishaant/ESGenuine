import { motion, AnimatePresence } from 'framer-motion';
import { FileText, ChevronRight, AlertCircle, CheckCircle, HelpCircle, Upload, Loader2, BookOpen, MapPin, Zap, Target, Hash } from 'lucide-react';
import { useState, useCallback } from 'react';
import { useClaims } from '@/hooks/useClaims';
import { API_BASE } from '@/lib/api';

// ── Types ──

interface Claim {
  id: string;
  text: string;
  status: 'verified' | 'review' | 'gap';
  location?: string;
}

export interface ExtractedClaim {
  aspect: string;
  action: string;
  metric?: { value: string; unit: string; direction: string | null };
  location?: { raw_text: string; specificity: string };
  time?: { start_date: string; end_date: string };
  provenance: { page_number: number; source_sentence: string; section_label: string; bbox: any };
  groundability_score: number;
  observability_type: string;
}

interface ClaimCandidate {
  candidate_id: string;
  sentence_id: string;
  text: string;
  score: number;
  features: {
    has_number: boolean;
    has_unit: boolean;
    has_action_verb: boolean;
    has_esg_keyword: boolean;
    in_esg_section: boolean;
  };
  page_number: number;
  section_id: string | null;
  section_title: string | null;
  bbox: { x0: number; y0: number; x1: number; y1: number } | null;
}

interface PipelineSentence {
  sentence_id: string;
  text: string;
  block_id: string;
  page_number: number;
  section_id: string | null;
  section_title: string | null;
  bbox: { x0: number; y0: number; x1: number; y1: number };
  sentence_index: number;
}

interface UploadResult {
  document_id: string;
  filename: string;
  status: string;
  raw_blocks: number;
  classified_blocks: number;
  sections: number;
  sentences: number;
  table_rows: number;
  claim_candidates: number;
  semantic_chunks: number;
  provenance_records: number;
  sections_detected: string[];
}

interface DocumentViewerProps {
  selectedClaim: string | null;
  onClaimSelect: (id: string) => void;
}

// ── API Config ──
// API_BASE comes from lib/api (VITE_API_BASE, scheme-tolerant, localhost fallback).
// It must NOT be redeclared here: this component renders on the landing page, so a
// hardcoded localhost broke every deployed build (and was blocked as mixed content
// on an HTTPS origin) even though render.yaml injects VITE_API_BASE correctly.

// ── Removed mock claims ──

// ── Sub-Components ──

const StatusIcon = ({ status }: { status: Claim['status'] }) => {
  switch (status) {
    case 'verified': return <CheckCircle className="w-4 h-4 text-success" />;
    case 'review': return <HelpCircle className="w-4 h-4 text-warning" />;
    case 'gap': return <AlertCircle className="w-4 h-4 text-danger" />;
  }
};

const StatusBadge = ({ status }: { status: Claim['status'] }) => {
  const baseClasses = "text-xs font-medium";
  switch (status) {
    case 'verified': return <span className={`status-verified pulse-success ${baseClasses}`}><CheckCircle className="w-3 h-3" /> Verified</span>;
    case 'review': return <span className={`status-review pulse-warning ${baseClasses}`}><HelpCircle className="w-3 h-3" /> Review</span>;
    case 'gap': return <span className={`status-gap pulse-danger ${baseClasses}`}><AlertCircle className="w-3 h-3" /> Gap</span>;
  }
};

const CandidateScoreBadge = ({ score }: { score: number }) => {
  const color = score >= 0.8 ? 'text-success' : score >= 0.6 ? 'text-warning' : 'text-muted-foreground';
  const bg = score >= 0.8 ? 'bg-success/10' : score >= 0.6 ? 'bg-warning/10' : 'bg-muted/30';
  return (
    <span className={`text-[10px] px-1.5 py-0.5 rounded font-mono font-semibold ${color} ${bg}`}>
      <Target className="w-2.5 h-2.5 inline mr-0.5" />
      {(score * 100).toFixed(0)}%
    </span>
  );
};

const FeatureChips = ({ features }: { features: ClaimCandidate['features'] }) => (
  <div className="flex flex-wrap gap-1 mt-1.5">
    {features.has_number && <span className="text-[9px] px-1 py-0.5 rounded bg-primary/10 text-primary"><Hash className="w-2.5 h-2.5 inline" /> Number</span>}
    {features.has_unit && <span className="text-[9px] px-1 py-0.5 rounded bg-primary/10 text-primary">📏 Unit</span>}
    {features.has_action_verb && <span className="text-[9px] px-1 py-0.5 rounded bg-primary/10 text-primary"><Zap className="w-2.5 h-2.5 inline" /> Action</span>}
    {features.has_esg_keyword && <span className="text-[9px] px-1 py-0.5 rounded bg-success/10 text-success">🌱 ESG</span>}
    {features.in_esg_section && <span className="text-[9px] px-1 py-0.5 rounded bg-warning/10 text-warning">📄 Section</span>}
  </div>
);

const ProvenanceBadge = ({ page, blockId }: { page: number; blockId: string }) => (
  <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground font-mono">
    p.{page} / {blockId}
  </span>
);

// ── Main Component ──

export const DocumentViewer = ({ selectedClaim, onClaimSelect }: DocumentViewerProps) => {
  const { claims: globalClaims } = useClaims();
  const [isUploading, setIsUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null);
  const [candidates, setCandidates] = useState<ClaimCandidate[]>([]);
  const [extractedClaims, setExtractedClaims] = useState<ExtractedClaim[]>([]);
  const [allSentences, setAllSentences] = useState<PipelineSentence[]>([]);
  const [isDragOver, setIsDragOver] = useState(false);
  const [selectedCandidate, setSelectedCandidate] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<'claims' | 'candidates' | 'all'>('claims');
  const [availableDocs, setAvailableDocs] = useState<Record<string, any>>({});

  const isLiveMode = candidates.length > 0 || allSentences.length > 0 || extractedClaims.length > 0;

  // ── Handlers ──

  const loadDocument = useCallback(async (docId: string) => {
    try {
      // Fetch full doc data
      const candRes = await fetch(`${API_BASE}/v1/documents/${docId}/candidates`);
      if (candRes.ok) {
        const candData = await candRes.json();
        setCandidates(candData.candidates || []);
      }

      const sentRes = await fetch(`${API_BASE}/v1/documents/${docId}/sentences`);
      if (sentRes.ok) {
        const sentData = await sentRes.json();
        setAllSentences(sentData.sentences || []);
      }

      const claimRes = await fetch(`${API_BASE}/v1/claims/${docId}`);
      if (claimRes.ok) {
        const claimData = await claimRes.json();
        setExtractedClaims(claimData.claims || []);
      }

      setUploadResult({
        document_id: docId,
        filename: availableDocs[docId]?.filename || `Document ${docId}`,
        status: 'ready',
        raw_blocks: 0, classified_blocks: 0, sections: 0, sentences: 0, 
        table_rows: 0, claim_candidates: 0, semantic_chunks: 0, provenance_records: 0,
        sections_detected: []
      });
    } catch (err) {
      console.error('Error loading document:', err);
    }
  }, [availableDocs]);

  const fetchDocs = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/v1/documents`);
      if (res.ok) {
        const data = await res.json();
        setAvailableDocs(data.documents || {});
      }
    } catch (err) {
      console.error('Fetch docs error:', err);
    }
  }, []);

  useState(() => {
    fetchDocs();
  });

  const handleUpload = useCallback(async (file: File) => {
    if (!file.name.toLowerCase().endsWith('.pdf')) return;
    setIsUploading(true);

    try {
      const formData = new FormData();
      formData.append('file', file);

      // Step 1: Upload and run full 8-step pipeline
      const uploadRes = await fetch(`${API_BASE}/v1/upload`, { method: 'POST', body: formData });
      if (!uploadRes.ok) throw new Error('Upload failed');
      const result: UploadResult = await uploadRes.json();
      setUploadResult(result);

      // Step 2: Fetch claim candidates (Step 6 output)
      const candRes = await fetch(`${API_BASE}/v1/documents/${result.document_id}/candidates`);
      if (candRes.ok) {
        const candData = await candRes.json();
        setCandidates(candData.candidates || []);
      }

      // Step 3: Fetch all sentences (for "all sentences" view)
      const sentRes = await fetch(`${API_BASE}/v1/documents/${result.document_id}/sentences`);
      if (sentRes.ok) {
        const sentData = await sentRes.json();
        setAllSentences(sentData.sentences || []);
      }

      // Step 4: Try to fetch extracted LLM claims (Week 3 output)
      const claimRes = await fetch(`${API_BASE}/v1/claims/${result.document_id}`);
      if (claimRes.ok) {
         const claimData = await claimRes.json();
         setExtractedClaims(claimData.claims || []);
      }
    } catch (err) {
      console.error('Upload error:', err);
    } finally {
      setIsUploading(false);
    }
  }, []);

  // ── Drag & Drop ──

  const handleDragOver = useCallback((e: React.DragEvent) => { e.preventDefault(); setIsDragOver(true); }, []);
  const handleDragLeave = useCallback(() => { setIsDragOver(false); }, []);
  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault(); setIsDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleUpload(file);
  }, [handleUpload]);
  const handleFileInput = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleUpload(file);
  }, [handleUpload]);

  // ── Group candidates/sentences by section ──
  const groupedCandidates = candidates.reduce<Record<string, ClaimCandidate[]>>((acc, c) => {
    const section = c.section_title || 'Unknown';
    if (!acc[section]) acc[section] = [];
    acc[section].push(c);
    return acc;
  }, {});

  const groupedSentences = allSentences.reduce<Record<string, PipelineSentence[]>>((acc, s) => {
    const section = s.section_title || 'Unknown';
    if (!acc[section]) acc[section] = [];
    acc[section].push(s);
    return acc;
  }, {});

  return (
    <motion.div className="h-full flex flex-col glass-panel" initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.5 }}>
      {/* Header */}
      <div className="p-4 border-b border-border/50">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-primary/20 flex items-center justify-center">
            <FileText className="w-5 h-5 text-primary" />
          </div>
          <div className="flex-1">
            <h2 className="font-semibold text-foreground">
              {uploadResult ? uploadResult.filename : 'ESG Report Viewer'}
            </h2>
            <p className="text-xs text-muted-foreground">
              {uploadResult
                ? `${uploadResult.claim_candidates} candidates · ${uploadResult.sentences} sentences · ${uploadResult.sections} sections`
                : 'Upload a PDF or explore demo claims'}
            </p>
          </div>
        </div>

        {/* View Toggle (only in live mode) */}
        {isLiveMode && (
          <div className="flex gap-1 mt-3 p-0.5 rounded-lg bg-muted/30">
            <button
              className={`flex-1 text-xs py-1.5 rounded-md transition-all ${viewMode === 'claims' ? 'bg-primary/15 text-primary font-medium' : 'text-muted-foreground hover:text-foreground'}`}
              onClick={() => setViewMode('claims')}
            >
              <CheckCircle className="w-3 h-3 inline mr-1" />
              Extracted Claims ({extractedClaims.length})
            </button>
            <button
              className={`flex-1 text-xs py-1.5 rounded-md transition-all ${viewMode === 'candidates' ? 'bg-primary/15 text-primary font-medium' : 'text-muted-foreground hover:text-foreground'}`}
              onClick={() => setViewMode('candidates')}
            >
              <Target className="w-3 h-3 inline mr-1" />
              Candidates ({candidates.length})
            </button>
            <button
              className={`flex-1 text-xs py-1.5 rounded-md transition-all ${viewMode === 'all' ? 'bg-primary/15 text-primary font-medium' : 'text-muted-foreground hover:text-foreground'}`}
              onClick={() => setViewMode('all')}
            >
              <BookOpen className="w-3 h-3 inline mr-1" />
              All ({allSentences.length})
            </button>
          </div>
        )}
      </div>

      {/* Upload Zone */}
      {!isLiveMode && !isUploading && (
        <div className="flex-1 flex flex-col items-center justify-center p-6">
          <div
            className={`w-full max-w-sm p-8 border-2 border-dashed rounded-xl transition-all duration-200 cursor-pointer flex flex-col items-center gap-3 text-center ${isDragOver ? 'border-primary bg-primary/5' : 'border-border/50 hover:border-primary/50 hover:bg-muted/20'}`}
            onDragOver={handleDragOver} onDragLeave={handleDragLeave} onDrop={handleDrop}
            onClick={() => document.getElementById('pdf-upload-input')?.click()}
          >
            <Upload className="w-8 h-8 text-muted-foreground" />
            <div>
              <p className="text-sm text-foreground font-medium">Drop ESG PDF here</p>
              <p className="text-xs text-muted-foreground">Runs full 8-step parsing pipeline</p>
            </div>
          </div>
          <input id="pdf-upload-input" type="file" accept=".pdf" className="hidden" onChange={handleFileInput} />
          
          {/* Recent Docs */}
          {Object.keys(availableDocs).length > 0 && (
            <div className="mt-8 w-full max-w-xs space-y-2">
              <p className="text-[10px] text-muted-foreground uppercase font-bold tracking-widest text-center mb-3">Discovered Reports</p>
              {Object.entries(availableDocs).map(([id, info]: [string, any]) => (
                <button
                  key={id}
                  onClick={(e) => { e.stopPropagation(); loadDocument(id); }}
                  className="w-full text-left p-3 rounded-lg border border-border/40 bg-muted/10 hover:bg-primary/5 hover:border-primary/30 transition-all flex items-center gap-3 group"
                >
                  <FileText className="w-4 h-4 text-primary/60 group-hover:text-primary transition-colors" />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium truncate">{info.filename}</p>
                    <p className="text-[9px] text-muted-foreground font-mono">{id}</p>
                  </div>
                  <ChevronRight className="w-3 h-3 text-muted-foreground/40 group-hover:text-primary transition-colors" />
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Loading State */}
      {isUploading && (
        <div className="flex-1 flex flex-col items-center justify-center gap-3">
          <Loader2 className="w-8 h-8 text-primary animate-spin" />
          <p className="text-sm text-muted-foreground">Running 8-step parsing pipeline...</p>
          <div className="text-[10px] text-muted-foreground/60 space-y-0.5 text-center">
            <p>① Extract → ② Classify → ③ Sections → ④ Segment</p>
            <p>⑤ Tables → ⑥ Candidates → ⑦ Chunks → ⑧ Provenance</p>
          </div>
        </div>
      )}

      {/* Document content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        <AnimatePresence mode="wait">
          {isLiveMode && viewMode === 'claims' ? (
            /* ═══ EXTRACTED CLAIMS VIEW ═══ */
            <motion.div key="claims" className="space-y-4" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
              {extractedClaims.length === 0 ? (
                 <div className="text-sm text-center text-muted-foreground py-8">
                   No extracted claims found yet. Extraction might be still running.
                 </div>
              ) : (
                extractedClaims.map((claim, idx) => (
                  <motion.div
                    key={idx}
                    className="p-4 rounded-lg bg-card border border-border/50 shadow-sm space-y-3"
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: idx * 0.05 }}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2">
                           <span className="text-[10px] font-bold tracking-wider uppercase px-2 py-0.5 rounded bg-primary/10 text-primary">
                             {claim.aspect}
                           </span>
                           <span className="text-xs text-muted-foreground uppercase">{claim.action}</span>
                        </div>
                        <p className="text-sm font-medium text-foreground italic border-l-2 border-primary/30 pl-3">
                          "{claim.provenance.source_sentence}"
                        </p>
                      </div>
                      <CandidateScoreBadge score={claim.groundability_score} />
                    </div>

                    <div className="grid grid-cols-2 gap-2 mt-3 pt-3 border-t border-border/50">
                      {claim.metric && (
                        <div className="flex items-center gap-2 text-xs">
                          <Target className="w-3.5 h-3.5 text-blue-500" />
                          <span className="font-semibold">{claim.metric.value}</span> 
                          <span className="text-muted-foreground">{claim.metric.unit}</span>
                        </div>
                      )}
                      {claim.location && (
                        <div className="flex items-center gap-2 text-xs">
                          <MapPin className="w-3.5 h-3.5 text-emerald-500" />
                          <span className="font-medium">{claim.location.raw_text}</span>
                        </div>
                      )}
                      {claim.time && (
                        <div className="flex items-center gap-2 text-xs">
                          <CheckCircle className="w-3.5 h-3.5 text-amber-500" />
                          <span className="font-medium">{claim.time.start_date} → {claim.time.end_date}</span>
                        </div>
                      )}
                    </div>
                    
                    <div className="text-[10px] text-muted-foreground/50 tracking-wide pt-1">
                       Extracted from: Page {claim.provenance.page_number} · {claim.provenance.section_label}
                    </div>
                  </motion.div>
                ))
              )}
            </motion.div>
          ) : isLiveMode && viewMode === 'candidates' ? (
            /* ═══ CANDIDATES VIEW ═══ */
            <motion.div key="candidates" className="space-y-6" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
              {Object.entries(groupedCandidates).map(([section, sectionCandidates]) => (
                <div key={section} className="space-y-2">
                  <div className="flex items-center gap-2 sticky top-0 bg-background/80 backdrop-blur-sm z-10 py-1">
                    <BookOpen className="w-3.5 h-3.5 text-primary" />
                    <span className="text-xs font-semibold text-primary uppercase tracking-wider">{section}</span>
                    <span className="text-[10px] text-muted-foreground">({sectionCandidates.length})</span>
                  </div>

                  {sectionCandidates.map((cand) => (
                    <motion.div
                      key={cand.candidate_id}
                      className={`relative p-3 rounded-lg cursor-pointer transition-all duration-300 ${selectedCandidate === cand.candidate_id ? 'glass-panel-highlight' : 'hover:bg-muted/30'}`}
                      onClick={() => { setSelectedCandidate(cand.candidate_id); onClaimSelect(cand.candidate_id); }}
                      whileHover={{ scale: 1.005 }} whileTap={{ scale: 0.995 }}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <p className={`text-sm leading-relaxed flex-1 ${selectedCandidate === cand.candidate_id ? 'claim-highlight' : 'text-foreground/80'}`}>
                          {cand.text}
                        </p>
                        <CandidateScoreBadge score={cand.score} />
                      </div>
                      <FeatureChips features={cand.features} />
                      <div className="flex items-center gap-2 mt-2">
                        <ProvenanceBadge page={cand.page_number} blockId={cand.sentence_id} />
                      </div>
                      {selectedCandidate === cand.candidate_id && (
                        <motion.div className="absolute inset-0 rounded-lg pointer-events-none" initial={{ opacity: 0 }} animate={{ opacity: 1 }}
                          style={{ background: 'hsl(var(--primary) / 0.05)' }}
                        />
                      )}
                    </motion.div>
                  ))}
                </div>
              ))}
            </motion.div>
          ) : isLiveMode && viewMode === 'all' ? (
            /* ═══ ALL SENTENCES VIEW ═══ */
            <motion.div key="all" className="space-y-6" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
              {Object.entries(groupedSentences).map(([section, sectionSents]) => (
                <div key={section} className="space-y-1">
                  <div className="flex items-center gap-2 sticky top-0 bg-background/80 backdrop-blur-sm z-10 py-1">
                    <BookOpen className="w-3.5 h-3.5 text-muted-foreground" />
                    <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">{section}</span>
                  </div>
                  {sectionSents.map((sent) => {
                    const isCandidate = candidates.some(c => c.sentence_id === sent.sentence_id);
                    return (
                      <div key={sent.sentence_id}
                        className={`p-2 rounded text-xs leading-relaxed ${isCandidate ? 'bg-primary/5 border-l-2 border-primary text-foreground' : 'text-muted-foreground/70'}`}
                      >
                        {sent.text}
                        <span className="text-[9px] text-muted-foreground/50 ml-2 font-mono">p.{sent.page_number}</span>
                      </div>
                    );
                  })}
                </div>
              ))}
            </motion.div>
          ) : !isUploading ? (
            /* ═══ LIVE GLOBAL CLAIMS ═══ */
            <motion.div key="demo" className="space-y-3" initial="hidden" animate="visible"
              variants={{ hidden: {}, visible: { transition: { staggerChildren: 0.1 } } }}
            >
              <motion.div className="flex flex-col gap-2" variants={{ hidden: { opacity: 0, y: 10 }, visible: { opacity: 1, y: 0 } }}>
                <p className="text-sm text-foreground font-semibold">Live Database Claims</p>
                <p className="text-sm text-muted-foreground leading-relaxed">
                  These claims are actively synced from your global pipeline. Upload an ESG PDF to run the local extraction engine.
                </p>
              </motion.div>
              {globalClaims.map((claim) => (
                <motion.div key={claim.id}
                  className={`relative p-3 rounded-lg cursor-pointer transition-all duration-300 ${selectedClaim === claim.id ? 'glass-panel-highlight' : 'hover:bg-muted/30'}`}
                  onClick={() => onClaimSelect(claim.id)}
                  variants={{ hidden: { opacity: 0, y: 10 }, visible: { opacity: 1, y: 0 } }}
                  whileHover={{ scale: 1.01 }} whileTap={{ scale: 0.99 }}
                >
                  <div className="flex items-start gap-3">
                    <div className="mt-0.5"><StatusIcon status={claim.status as any} /></div>
                    <div className="flex-1 min-w-0">
                      <p className={`text-sm leading-relaxed ${selectedClaim === claim.id ? 'claim-highlight' : ''}`}>{claim.claim}</p>
                      <div className="flex items-center justify-between mt-2">
                        <span className="text-xs text-muted-foreground flex items-center gap-1"><MapPin className="w-3 h-3" />{claim.location}</span>
                        <StatusBadge status={claim.status as any} />
                      </div>
                    </div>
                    <ChevronRight className={`w-4 h-4 text-muted-foreground transition-transform ${selectedClaim === claim.id ? 'rotate-90 text-primary' : ''}`} />
                  </div>
                </motion.div>
              ))}
            </motion.div>
          ) : null}
        </AnimatePresence>
      </div>
    </motion.div>
  );
};

export type { Claim };
