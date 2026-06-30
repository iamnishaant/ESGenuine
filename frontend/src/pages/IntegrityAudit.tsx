import { useState, useMemo, useEffect } from 'react';
import { motion } from 'framer-motion';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ShieldCheck, AlertTriangle, Scale, Send, Loader2, Satellite, FileText, Database,
  TrendingDown, TrendingUp, CheckCircle2, XCircle, HelpCircle, Lightbulb, Sparkles,
  UserCheck, Check, X, Undo2, ArrowRight,
} from 'lucide-react';
import { AppLayout } from '@/components/AppLayout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import {
  getIntegrityReport, getFactCheck, getScorecard, askAudit, getSuggestedQuestions,
  getReviewQueue, postReview, getPortfolioIntegrity,
  login as apiLogin, register as apiRegister, logout as apiLogout, me as apiMe, getToken,
  verificationMethod, VERIFICATION_LABEL, type AskAnswer, type ReviewItem,
} from '@/lib/api';
import { metricLabel } from '@/lib/metricLabels';

type Doc = { id: string; label: string; company: string };

// Flag types a reviewer can act on, grouped for a small visual cue in the queue.
const REVIEW_SEV: Record<string, string> = {
  CONTRADICTION: 'Critical', DISCLOSURE_GAP: 'High', VAGUE: 'High',
  UNSUBSTANTIATED_TARGET: 'High', NON_GROUNDABLE: 'High',
  MISSING_BASELINE: 'Medium', SELECTIVE_SCOPE: 'Medium', ASPIRATIONAL_HEAVY: 'Medium',
};

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

// 0–1 fraction → "84%" (or em-dash when null/undefined).
const pct = (v?: number | null) => (v != null ? `${Math.round(v * 100)}%` : '—');

const METHOD_PROFILE: Array<{ key: 'imagery' | 'data_crosscheck' | 'document_review'; label: string; cls: string }> = [
  { key: 'imagery', label: 'Imagery', cls: 'text-success' },
  { key: 'data_crosscheck', label: 'Data cross-check', cls: 'text-primary' },
  { key: 'document_review', label: 'Document review', cls: 'text-muted-foreground' },
];

const IntegrityAudit = () => {
  const qc = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [question, setQuestion] = useState('');
  const [chat, setChat] = useState<AskAnswer[]>([]);
  const [asking, setAsking] = useState(false);
  const [notes, setNotes] = useState<Record<string, string>>({});

  // ── auth (writes are gated) ──────────────────────────────────────────────
  const [user, setUser] = useState<{ email: string; role: string } | null>(null);
  const [authEmail, setAuthEmail] = useState('');
  const [authPw, setAuthPw] = useState('');
  const [authErr, setAuthErr] = useState('');
  const [authBusy, setAuthBusy] = useState(false);

  useEffect(() => {
    if (getToken()) apiMe().then(setUser).catch(() => { apiLogout(); setUser(null); });
  }, []);

  const doAuth = async (kind: 'login' | 'register') => {
    setAuthBusy(true); setAuthErr('');
    try {
      const s = await (kind === 'login' ? apiLogin : apiRegister)(authEmail.trim().toLowerCase(), authPw);
      setUser({ email: s.email, role: s.role });
      setAuthEmail(''); setAuthPw('');
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '';
      setAuthErr(msg.includes('401') ? 'Invalid email or password'
        : msg.includes('409') ? 'Email already registered'
        : msg.includes('400') ? 'Password must be at least 8 characters'
        : 'Auth failed — is the backend running?');
    } finally { setAuthBusy(false); }
  };
  const doLogout = () => { apiLogout(); setUser(null); };

  // Doc list is derived from the portfolio so EVERY ingested company is reviewable
  // (was a hardcoded 3 — Microsoft/Infosys never appeared).
  const portfolio = useQuery({ queryKey: ['portfolio'], queryFn: getPortfolioIntegrity });
  const docs: Doc[] = useMemo(
    () => (portfolio.data?.companies ?? [])
      .filter((c) => c.doc_id)
      .map((c) => ({ id: c.doc_id as string, company: c.company_id,
                     label: `${c.company_name} ${c.report_year ?? ''}`.trim() })),
    [portfolio.data],
  );
  const doc = docs.find((d) => d.id === selectedId) ?? docs[0];
  const docId = doc?.id;

  const report = useQuery({ queryKey: ['integrity', docId], queryFn: () => getIntegrityReport(docId!), enabled: !!docId });
  const factcheck = useQuery({ queryKey: ['factcheck', docId], queryFn: () => getFactCheck(docId!, 40), enabled: !!docId });
  const scorecard = useQuery({ queryKey: ['scorecard', doc?.company], queryFn: () => getScorecard(doc!.company), enabled: !!doc });
  const suggestions = useQuery({ queryKey: ['suggested', docId], queryFn: () => getSuggestedQuestions(docId!), enabled: !!docId });
  const reviewQueue = useQuery({ queryKey: ['reviewQueue', docId], queryFn: () => getReviewQueue(docId!), enabled: !!docId });

  // Saving a verdict refreshes the score (adjusted), the queue, and the portfolio grade.
  const reviewMut = useMutation({
    mutationFn: (v: { item: ReviewItem; verdict: 'dismissed' | 'confirmed' }) =>
      postReview(docId!, {
        subject_id: v.item.subject_id, flag_type: v.item.flag_type, verdict: v.verdict,
        note: notes[v.item.subject_id + v.item.flag_type] || undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['integrity', docId] });
      qc.invalidateQueries({ queryKey: ['reviewQueue', docId] });
      qc.invalidateQueries({ queryKey: ['portfolio'] });
    },
    onError: (e: unknown) => {
      // Token expired/invalid → drop it so the auth bar reappears.
      if (e instanceof Error && e.message.includes('401')) { apiLogout(); setUser(null); }
    },
  });

  const ask = async (preset?: string) => {
    const q = (preset ?? question).trim();
    if (!q || asking || !docId) return;
    setAsking(true);
    try {
      const a = await askAudit(q, docId);
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
          <div className="flex gap-2 flex-wrap">
            {portfolio.isLoading && <Loader2 className="animate-spin w-4 h-4" />}
            {docs.map((d) => (
              <Button key={d.id} variant={d.id === doc?.id ? 'default' : 'outline'} size="sm" onClick={() => setSelectedId(d.id)}>
                {d.label}
              </Button>
            ))}
          </div>
        </div>

        {/* Auth bar — writes (review verdicts, ingest) require sign-in */}
        <div className="flex items-center gap-2 text-xs flex-wrap glass-panel rounded-lg px-3 py-2">
          {user ? (
            <>
              <UserCheck className="w-3.5 h-3.5 text-success" />
              <span className="text-muted-foreground">signed in as <span className="text-foreground">{user.email}</span> ({user.role})</span>
              <Button size="sm" variant="ghost" className="h-7 text-xs ml-auto" onClick={doLogout}>Sign out</Button>
            </>
          ) : (
            <>
              <span className="text-muted-foreground">Sign in to review flags / ingest reports:</span>
              <Input className="h-7 w-48 text-xs" placeholder="email" value={authEmail}
                onChange={(e) => setAuthEmail(e.target.value)} />
              <Input className="h-7 w-40 text-xs" type="password" placeholder="password (8+ chars)" value={authPw}
                onChange={(e) => setAuthPw(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && doAuth('login')} />
              <Button size="sm" variant="outline" className="h-7 text-xs" disabled={authBusy} onClick={() => doAuth('login')}>Login</Button>
              <Button size="sm" variant="ghost" className="h-7 text-xs" disabled={authBusy} onClick={() => doAuth('register')}>Register</Button>
              {authErr && <span className="text-destructive">{authErr}</span>}
            </>
          )}
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
                    {(report.data?.reviews_applied ?? 0) > 0 && report.data?.integrity_score_raw != null && (
                      <span className="text-2xl font-semibold text-muted-foreground/70 line-through mb-1">
                        {report.data.integrity_score_raw}
                      </span>
                    )}
                    {(report.data?.reviews_applied ?? 0) > 0 && (
                      <ArrowRight className="w-5 h-5 text-muted-foreground mb-3" />
                    )}
                    <span className="text-5xl font-bold">{report.data?.integrity_score ?? '—'}</span>
                    <span className={cn('text-3xl font-bold', gradeColor(report.data?.grade))}>{report.data?.grade}</span>
                    <Badge variant="outline" className="mb-2">{report.data?.greenwashing_risk} risk</Badge>
                  </div>
                  {(report.data?.reviews_applied ?? 0) > 0 && (
                    <p className="text-[11px] text-primary mt-1 flex items-center gap-1">
                      <UserCheck className="w-3 h-3" /> {report.data?.reviews_applied} reviewer override
                      {(report.data?.reviews_applied ?? 0) === 1 ? '' : 's'} applied
                      {report.data?.grade_raw && report.data.grade_raw !== report.data.grade
                        ? ` · grade ${report.data.grade_raw} → ${report.data.grade}` : ''}
                    </p>
                  )}
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
                <>
                <div className="flex gap-6 items-center flex-wrap">
                  {Object.entries(factcheck.data?.verdict_counts ?? {}).map(([k, v]) => (
                    <div key={k} className="flex items-center gap-2">
                      {VERDICT_ICON[k]}<span className="text-2xl font-bold">{v}</span>
                      <span className="text-xs text-muted-foreground">{k.toLowerCase()}</span>
                    </div>
                  ))}
                  <div className="ml-auto flex gap-6 text-right">
                    <div title="SUPPORTED ÷ checked (materiality-weighted variant shown below)">
                      <div className="text-xs text-muted-foreground">credibility</div>
                      <div className="text-2xl font-bold">{pct(factcheck.data?.credibility)}</div>
                      {factcheck.data?.weighted_credibility != null && (
                        <div className="text-[10px] text-muted-foreground">{pct(factcheck.data.weighted_credibility)} weighted</div>
                      )}
                    </div>
                    <div title="checked ÷ checkable — how much of the verifiable surface we had evidence for">
                      <div className="text-xs text-muted-foreground">coverage</div>
                      <div className="text-2xl font-bold">{pct(factcheck.data?.coverage)}</div>
                      {factcheck.data?.checkable != null && (
                        <div className="text-[10px] text-muted-foreground">{factcheck.data.checked}/{factcheck.data.checkable} checkable</div>
                      )}
                    </div>
                  </div>
                </div>
                {(factcheck.data?.llm_assisted ?? 0) > 0 && (
                  <p className="text-[11px] text-muted-foreground mt-2 flex items-center gap-1">
                    <Sparkles className="w-3 h-3" /> {factcheck.data?.llm_assisted} verdict(s) used the guarded LLM fallback (numeric checks stay authoritative)
                  </p>
                )}
                {factcheck.data?.corpus_quality?.illustrative_only && (
                  <p className="text-[11px] text-yellow-400 mt-2 flex items-center gap-1">
                    <AlertTriangle className="w-3 h-3" /> Reference corpus is illustrative (no verified figures) — treat credibility as a demo signal, not production ground truth.
                  </p>
                )}
                </>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Score breakdown + verification profile */}
        {report.data?.status === 'ok' && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <Card className="glass-panel lg:col-span-2">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Scale className="w-4 h-4 text-primary" /> Score Breakdown
                  <span className="text-xs font-normal text-muted-foreground">— where the 100 points went</span>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {(report.data.penalty_breakdown ?? []).length === 0 ? (
                  <p className="text-sm text-muted-foreground">No penalties — full 100/100.</p>
                ) : (
                  <>
                    {(report.data.penalty_breakdown ?? []).map((p, i) => (
                      <div key={i} className="flex items-center gap-3 text-xs">
                        <Badge className={cn('border w-16 justify-center text-[10px]', SEV_COLOR[p.severity])}>{p.severity}</Badge>
                        <span className="flex-1 truncate" title={`${p.type} ×${p.count} · ${Math.round((p.prevalence ?? 0) * 100)}% of claims`}>{p.title}</span>
                        <div className="w-28 h-1.5 bg-muted rounded-full overflow-hidden">
                          <div className="h-full bg-destructive/70" style={{ width: `${Math.min(100, p.points_deducted * 2)}%` }} />
                        </div>
                        <span className="text-destructive font-medium w-12 text-right">−{p.points_deducted}</span>
                      </div>
                    ))}
                    <p className="text-[11px] text-muted-foreground pt-1">
                      Count-weighted: each penalty = severity × prevalence (share of claims that triggered the flag), so pervasive issues cost more than rare ones.
                      {report.data.computed_at && ` · computed ${report.data.computed_at.replace('T', ' ').replace('+00:00', 'Z')}`}
                      {report.data.report_version && ` · v${report.data.report_version}`}
                    </p>
                  </>
                )}
              </CardContent>
            </Card>

            <Card className="glass-panel">
              <CardHeader className="pb-2"><CardTitle className="text-sm">Verification Profile</CardTitle></CardHeader>
              <CardContent className="space-y-2">
                <p className="text-[11px] text-muted-foreground -mt-1">How this report's claims can be checked.</p>
                {METHOD_PROFILE.map(({ key, label, cls }) => {
                  const vp = report.data?.statistics?.verification_profile;
                  const count = vp?.[key] ?? 0;
                  const total = vp ? vp.imagery + vp.data_crosscheck + vp.document_review : 0;
                  return (
                    <div key={key} className="flex items-center gap-3 text-xs">
                      <span className={cn('flex-1', cls)}>{label}</span>
                      <div className="w-20 h-1.5 bg-muted rounded-full overflow-hidden">
                        <div className="h-full bg-primary/60" style={{ width: total ? `${(count / total) * 100}%` : '0%' }} />
                      </div>
                      <span className="text-muted-foreground w-8 text-right">{count}</span>
                    </div>
                  );
                })}
              </CardContent>
            </Card>
          </div>
        )}

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

        {/* Human-in-the-loop flag review */}
        <Card className="glass-panel">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2">
              <UserCheck className="w-4 h-4 text-primary" /> Human Review
              {reviewQueue.data && (
                <span className="text-xs font-normal text-muted-foreground">
                  — {reviewQueue.data.reviewed}/{reviewQueue.data.total} reviewed · dismiss a false positive to raise the score
                </span>
              )}
              {!user && <span className="text-xs font-normal text-yellow-400">· sign in above to record verdicts</span>}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {reviewQueue.isLoading ? <Loader2 className="animate-spin" /> :
              reviewQueue.isError ? <p className="text-sm text-destructive">Review queue unavailable — start the backend / run the claim_reviews migration.</p> :
              (reviewQueue.data?.items?.length ?? 0) === 0 ? <p className="text-sm text-muted-foreground">No flagged items to review.</p> : (
              (reviewQueue.data?.items ?? []).slice(0, 40).map((it) => {
                const key = it.subject_id + it.flag_type;
                const sev = REVIEW_SEV[it.flag_type] ?? 'Low';
                return (
                  <div key={key} className={cn('border rounded-lg p-3 space-y-2',
                    it.verdict === 'dismissed' ? 'border-success/40 bg-success/5'
                      : it.verdict === 'confirmed' ? 'border-border/40 opacity-70' : 'border-border/40')}>
                    <div className="flex items-center gap-2 flex-wrap">
                      <Badge className={cn('border text-[10px]', SEV_COLOR[sev])}>{it.flag_type}</Badge>
                      <span className="text-sm font-medium">{it.title}</span>
                      {it.page_number != null && <span className="text-[11px] text-muted-foreground">p{it.page_number}</span>}
                      {it.verdict && (
                        <Badge variant="outline" className={cn('text-[10px] ml-auto',
                          it.verdict === 'dismissed' ? 'text-success border-success/40' : 'text-muted-foreground')}>
                          {it.verdict === 'dismissed' ? 'dismissed (false positive)' : 'confirmed valid'}
                        </Badge>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground">{it.reason}</p>
                    {it.source_sentence && <p className="text-[11px] text-muted-foreground/80 italic">"{it.source_sentence}"</p>}
                    <div className="flex items-center gap-2">
                      <Input className="h-7 text-xs" placeholder="note (optional)"
                        value={notes[key] ?? ''} onChange={(e) => setNotes((n) => ({ ...n, [key]: e.target.value }))} />
                      {it.verdict ? (
                        <Button size="sm" variant="ghost" className="h-7 text-xs gap-1"
                          disabled={reviewMut.isPending || !user}
                          onClick={() => reviewMut.mutate({ item: it, verdict: it.verdict === 'dismissed' ? 'confirmed' : 'dismissed' })}>
                          <Undo2 className="w-3 h-3" /> change
                        </Button>
                      ) : (
                        <>
                          <Button size="sm" variant="outline" className="h-7 text-xs gap-1 text-success border-success/40"
                            disabled={reviewMut.isPending || !user}
                            onClick={() => reviewMut.mutate({ item: it, verdict: 'dismissed' })}>
                            <Check className="w-3 h-3" /> Dismiss
                          </Button>
                          <Button size="sm" variant="outline" className="h-7 text-xs gap-1"
                            disabled={reviewMut.isPending || !user}
                            onClick={() => reviewMut.mutate({ item: it, verdict: 'confirmed' })}>
                            <X className="w-3 h-3" /> Valid
                          </Button>
                        </>
                      )}
                    </div>
                  </div>
                );
              })
            )}
            {(reviewQueue.data?.items?.length ?? 0) > 40 && (
              <p className="text-[11px] text-muted-foreground">Showing first 40 of {reviewQueue.data?.total}.</p>
            )}
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
          <CardHeader className="pb-2"><CardTitle className="text-sm">Peer Benchmark — {doc?.company}</CardTitle></CardHeader>
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
              <Button onClick={() => ask()} disabled={asking}>{asking ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}</Button>
            </div>
            {(suggestions.data?.questions?.length ?? 0) > 0 && (
              <div className="flex flex-wrap gap-2">
                <span className="text-[11px] text-muted-foreground flex items-center gap-1"><Lightbulb className="w-3 h-3" /> Suggested:</span>
                {suggestions.data?.questions.map((q, i) => (
                  <button key={i} onClick={() => ask(q)} disabled={asking}
                    className="text-[11px] px-2 py-1 rounded-full border border-border/50 text-muted-foreground hover:text-foreground hover:border-primary/50 transition-colors disabled:opacity-50">
                    {q}
                  </button>
                ))}
              </div>
            )}
            {chat.map((c, i) => (
              <div key={i} className="border border-border/40 rounded-lg p-3 space-y-1">
                <p className="text-xs font-medium text-primary">Q: {c.question}</p>
                {c.low_relevance && (
                  <p className="text-[11px] text-yellow-400 flex items-center gap-1">
                    <AlertTriangle className="w-3 h-3" /> Low relevance — the corpus has no strong match for this question; answer may be off-topic.
                  </p>
                )}
                <p className="text-sm">{c.answer}</p>
                {(c.unsupported_citations?.length ?? 0) > 0 && (
                  <p className="text-[11px] text-destructive">⚠ Cited evidence {c.unsupported_citations?.join(', ')} not found in retrieved claims.</p>
                )}
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
