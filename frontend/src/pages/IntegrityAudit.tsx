import { useState } from 'react';
import { motion } from 'framer-motion';
import { useQuery } from '@tanstack/react-query';
import {
  ShieldCheck, AlertTriangle, Scale, Send, Loader2, Satellite, FileText, Database,
  TrendingDown, TrendingUp, CheckCircle2, XCircle, HelpCircle,
} from 'lucide-react';
import { AppLayout } from '@/components/AppLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import {
  getIntegrityReport, getFactCheck, getScorecard, askAudit,
  verificationMethod, VERIFICATION_LABEL, type AskAnswer,
} from '@/lib/api';
import { metricLabel } from '@/lib/metricLabels';

const DOCS = [
  { id: 'tata_power_2024', label: 'Tata Power 2024', company: 'tata_power' },
  { id: 'shell_2022', label: 'Shell 2022', company: 'shell' },
  { id: 'shell_2023', label: 'Shell 2023', company: 'shell' },
];

const SEV_COLOR: Record<string, string> = {
  Critical: 'bg-destructive/20 text-destructive border-destructive/40',
  High: 'bg-orange-500/20 text-orange-400 border-orange-500/40',
  Medium: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/40',
  Low: 'bg-blue-500/20 text-blue-400 border-blue-500/40',
};
const VERDICT_ICON: Record<string, JSX.Element> = {
  SUPPORTED: <CheckCircle2 className="w-4 h-4 text-success" />,
  CONTRADICTED: <XCircle className="w-4 h-4 text-destructive" />,
  UNVERIFIED: <HelpCircle className="w-4 h-4 text-muted-foreground" />,
};
const METHOD_ICON = { imagery: Satellite, data_crosscheck: Database, document_review: FileText };

const gradeColor = (g?: string) =>
  g === 'A' ? 'text-success' : g === 'B' ? 'text-emerald-400'
  : g === 'C' ? 'text-yellow-400' : g === 'D' ? 'text-orange-400' : 'text-destructive';

const IntegrityAudit = () => {
  const [doc, setDoc] = useState(DOCS[0]);
  const [question, setQuestion] = useState('');
  const [chat, setChat] = useState<AskAnswer[]>([]);
  const [asking, setAsking] = useState(false);

  const report = useQuery({ queryKey: ['integrity', doc.id], queryFn: () => getIntegrityReport(doc.id) });
  const factcheck = useQuery({ queryKey: ['factcheck', doc.id], queryFn: () => getFactCheck(doc.id, 40) });
  const scorecard = useQuery({ queryKey: ['scorecard', doc.company], queryFn: () => getScorecard(doc.company) });

  const ask = async () => {
    const q = question.trim();
    if (!q) return;
    setAsking(true);
    try {
      const a = await askAudit(q, doc.id);
      setChat((c) => [a, ...c]);
      setQuestion('');
    } catch (e: any) {
      setChat((c) => [{ question: q, answer: `Error: ${e.message}`, engine: 'error', citations: [] }, ...c]);
    } finally {
      setAsking(false);
    }
  };

  return (
    <AppLayout>
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* Header + doc selector */}
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h1 className="text-2xl font-semibold flex items-center gap-2">
              <ShieldCheck className="w-6 h-6 text-primary" /> ESG Integrity Audit
            </h1>
            <p className="text-sm text-muted-foreground">Greenwashing flags · external fact-check · peer benchmark · AI audit</p>
          </div>
          <div className="flex gap-2">
            {DOCS.map((d) => (
              <Button key={d.id} variant={d.id === doc.id ? 'default' : 'outline'} size="sm" onClick={() => setDoc(d)}>
                {d.label}
              </Button>
            ))}
          </div>
        </div>

        {/* Top row: score + fact-check summary */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <Card className="glass-panel">
            <CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground">Integrity Score</CardTitle></CardHeader>
            <CardContent>
              {report.isLoading ? <Loader2 className="animate-spin" /> : report.isError ? (
                <p className="text-sm text-destructive">API offline — start the backend on :8000</p>
              ) : (
                <div>
                  <div className="flex items-end gap-3">
                    <span className="text-5xl font-bold">{report.data?.integrity_score ?? '—'}</span>
                    <span className={cn('text-3xl font-bold', gradeColor(report.data?.grade))}>{report.data?.grade}</span>
                    <Badge variant="outline" className="mb-2">{report.data?.greenwashing_risk} risk</Badge>
                  </div>
                  <p className="text-xs text-muted-foreground mt-2">{report.data?.summary}</p>
                </div>
              )}
            </CardContent>
          </Card>

          <Card className="glass-panel lg:col-span-2">
            <CardHeader className="pb-2"><CardTitle className="text-sm text-muted-foreground flex items-center gap-2"><Scale className="w-4 h-4" /> External Fact-Check</CardTitle></CardHeader>
            <CardContent>
              {factcheck.isLoading ? <Loader2 className="animate-spin" /> : factcheck.isError ? (
                <p className="text-sm text-destructive">API offline</p>
              ) : (
                <div className="flex gap-6 items-center">
                  {Object.entries(factcheck.data?.verdict_counts ?? {}).map(([k, v]) => (
                    <div key={k} className="flex items-center gap-2">
                      {VERDICT_ICON[k]}<span className="text-2xl font-bold">{v}</span>
                      <span className="text-xs text-muted-foreground">{k.toLowerCase()}</span>
                    </div>
                  ))}
                  <div className="ml-auto text-right">
                    <div className="text-xs text-muted-foreground">credibility</div>
                    <div className="text-2xl font-bold">{factcheck.data?.credibility != null ? `${Math.round(factcheck.data.credibility * 100)}%` : '—'}</div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Greenwashing flags */}
        <Card className="glass-panel">
          <CardHeader className="pb-2"><CardTitle className="text-sm flex items-center gap-2"><AlertTriangle className="w-4 h-4 text-yellow-400" /> Greenwashing Flags</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {(report.data?.flags ?? []).map((f, i) => (
              <motion.div key={i} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}
                className="border border-border/40 rounded-lg p-3">
                <div className="flex items-center gap-2 flex-wrap">
                  <Badge className={cn('border', SEV_COLOR[f.severity])}>{f.severity}</Badge>
                  <span className="font-medium text-sm">{f.title}</span>
                  <span className="text-xs text-muted-foreground">×{f.count}</span>
                </div>
                <p className="text-xs text-muted-foreground mt-1">{f.description}</p>
                {f.regulations?.[0] && <p className="text-[11px] text-primary/80 mt-1">⚖ {f.regulations[0]}</p>}
                <p className="text-[11px] text-muted-foreground mt-1">→ {f.recommendation}</p>
              </motion.div>
            ))}
            {report.data && (report.data.flags?.length ?? 0) === 0 && <p className="text-sm text-muted-foreground">No flags raised.</p>}
          </CardContent>
        </Card>

        {/* Fact-check detail with verification-method routing */}
        <Card className="glass-panel">
          <CardHeader className="pb-2"><CardTitle className="text-sm">Claim Verdicts &amp; Verification Method</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            {(factcheck.data?.results ?? []).slice(0, 12).map((r) => {
              const method = verificationMethod(r.metric_key, r.claim_value != null, r.observability_type);
              const MIcon = METHOD_ICON[method];
              return (
                <div key={r.claim_id} className="flex items-start gap-3 border-b border-border/30 pb-2">
                  {VERDICT_ICON[r.verdict]}
                  <div className="flex-1 min-w-0">
                    <p className="text-xs truncate">{r.claim_text}</p>
                    <p className="text-[11px] text-muted-foreground">{metricLabel(r.metric_key)} @{r.reference_year} — {r.reasoning}</p>
                  </div>
                  <Badge variant="outline" className="text-[10px] whitespace-nowrap flex items-center gap-1">
                    <MIcon className="w-3 h-3" /> {VERIFICATION_LABEL[method]}
                  </Badge>
                </div>
              );
            })}
            {factcheck.data && factcheck.data.results.length === 0 && <p className="text-sm text-muted-foreground">No comparable evidence found.</p>}
          </CardContent>
        </Card>

        {/* Benchmark scorecard */}
        <Card className="glass-panel">
          <CardHeader className="pb-2"><CardTitle className="text-sm">Peer Benchmark — {doc.company}</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            {(scorecard.data?.metrics ?? []).slice(0, 10).map((m) => (
              <div key={m.metric_key} className="flex items-center gap-3 text-xs">
                {m.verdict === 'leading' ? <TrendingUp className="w-4 h-4 text-success" /> : m.verdict === 'lagging' ? <TrendingDown className="w-4 h-4 text-destructive" /> : <Scale className="w-4 h-4 text-muted-foreground" />}
                <span className="flex-1 truncate" title={m.metric_key}>{metricLabel(m.metric_key)}</span>
                <span className="text-muted-foreground">{m.value}{m.unit ? ` ${m.unit}` : ''}</span>
                <div className="w-24 h-1.5 bg-muted rounded-full overflow-hidden">
                  <div className={cn('h-full', m.percentile >= 66 ? 'bg-success' : m.percentile <= 33 ? 'bg-destructive' : 'bg-yellow-400')} style={{ width: `${m.percentile}%` }} />
                </div>
                <Badge variant="outline" className="text-[10px] w-16 justify-center">{m.verdict}</Badge>
              </div>
            ))}
            {scorecard.data && scorecard.data.metrics.length === 0 && <p className="text-sm text-muted-foreground">No shared metrics with peers yet.</p>}
          </CardContent>
        </Card>

        {/* Conversational audit */}
        <Card className="glass-panel">
          <CardHeader className="pb-2"><CardTitle className="text-sm">Ask the Auditor</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <div className="flex gap-2">
              <Input placeholder="e.g. What emissions targets has the company set?" value={question}
                onChange={(e) => setQuestion(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && ask()} />
              <Button onClick={ask} disabled={asking}>{asking ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}</Button>
            </div>
            {chat.map((c, i) => (
              <div key={i} className="border border-border/40 rounded-lg p-3 space-y-1">
                <p className="text-xs font-medium text-primary">Q: {c.question}</p>
                <p className="text-sm">{c.answer}</p>
                {c.citations?.length > 0 && (
                  <div className="text-[11px] text-muted-foreground space-y-0.5 pt-1">
                    {c.citations.slice(0, 4).map((ct) => (
                      <p key={ct.n}>[{ct.n}] {ct.company} {ct.year}, p{ct.page} — {ct.text.slice(0, 90)}</p>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </AppLayout>
  );
};

export default IntegrityAudit;
