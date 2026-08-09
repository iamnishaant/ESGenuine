// Upload an ESG PDF and run it through the PRODUCTION pipeline:
//   parse (Docling tables + PyMuPDF text) → LLM claim extraction → quality gate
//   → ontology/framework tagging → bge embeddings → Supabase.
//
// Until this existed the pipeline had no UI at all: POST /v1/reports/ingest and
// GET /v1/jobs/{id} had zero frontend call sites, so the dashboard could only ever
// show corpus loaded by hand from `backend/scripts/`. This closes that gap.
//
// The endpoint is auth-gated (Depends(get_current_user)), so this panel also owns a
// compact login/register bar — same Bearer token as the Integrity Audit page.
import { useCallback, useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Link } from 'react-router-dom';
import {
  UploadCloud, Loader2, CheckCircle2, AlertTriangle, FileText,
  LogOut, ArrowRight, Copy,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { useToast } from '@/hooks/use-toast';
import { cn } from '@/lib/utils';
import {
  ingestReport, getJob, isIngestDuplicate,
  login as apiLogin, register as apiRegister, logout as apiLogout, me as apiMe, getToken,
  type JobState, type IngestDuplicate,
} from '@/lib/api';
import { invalidateClaimsCache } from '@/hooks/useClaims';
import { invalidateBackendScores } from '@/hooks/useBackendScores';

const POLL_MS = 3000;

// Ordered pipeline stages. `queued` is included so the bar starts populated the
// moment the job is accepted, rather than looking stalled before parsing begins.
const STAGES: Array<{ key: JobState['status']; label: string }> = [
  { key: 'queued', label: 'Queued' },
  { key: 'parsing', label: 'Parsing PDF' },
  { key: 'extracting', label: 'Extracting claims' },
  { key: 'ingesting', label: 'Embedding + writing' },
  { key: 'done', label: 'Done' },
];

const stageIndex = (s: JobState['status'] | null) =>
  s ? STAGES.findIndex((x) => x.key === s) : -1;

export function ReportIngestPanel() {
  const { toast } = useToast();

  // ── auth ──
  const [user, setUser] = useState<{ email: string; role: string } | null>(null);
  const [authEmail, setAuthEmail] = useState('');
  const [authPw, setAuthPw] = useState('');
  const [authBusy, setAuthBusy] = useState(false);

  // ── form ──
  const [file, setFile] = useState<File | null>(null);
  const [companyName, setCompanyName] = useState('');
  const [reportYear, setReportYear] = useState<string>(String(new Date().getFullYear() - 1));
  const [useVlmTables, setUseVlmTables] = useState(false);

  // ── job ──
  const [submitting, setSubmitting] = useState(false);
  const [job, setJob] = useState<JobState | null>(null);
  const [duplicate, setDuplicate] = useState<IngestDuplicate | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current !== null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  // Never leave an interval running after the panel unmounts.
  useEffect(() => stopPolling, [stopPolling]);

  useEffect(() => {
    if (getToken()) {
      apiMe().then(setUser).catch(() => { apiLogout(); setUser(null); });
    }
  }, []);

  const doAuth = async (kind: 'login' | 'register') => {
    setAuthBusy(true);
    try {
      await (kind === 'login' ? apiLogin : apiRegister)(authEmail.trim().toLowerCase(), authPw);
      setUser(await apiMe());
      setAuthPw('');
      toast({ title: kind === 'login' ? 'Signed in' : 'Account created' });
    } catch (e) {
      toast({
        title: `${kind === 'login' ? 'Login' : 'Registration'} failed`,
        description: e instanceof Error ? e.message : String(e),
        variant: 'destructive',
      });
    } finally {
      setAuthBusy(false);
    }
  };

  const signOut = () => { apiLogout(); setUser(null); };

  // Poll until the job reaches a terminal state. On success, drop the module-level
  // caches so Portfolio/Globe/Claim Explorer pick the new report up without a reload.
  const startPolling = useCallback((jobId: string) => {
    stopPolling();
    pollRef.current = window.setInterval(async () => {
      try {
        const state = await getJob(jobId);
        setJob(state);
        if (state.status === 'done') {
          stopPolling();
          invalidateClaimsCache();
          invalidateBackendScores();
          toast({
            title: 'Ingest complete',
            description: `${state.inserted ?? 0} claims written for ${state.doc_id ?? state.report_id}.`,
          });
        } else if (state.status === 'error') {
          stopPolling();
          setError(state.error || 'Ingest failed.');
        }
      } catch (e) {
        // A transient 404/network blip shouldn't kill the poll loop; a persistent
        // one surfaces when the user reloads. Only hard-stop on explicit job error.
        console.warn('job poll failed (will retry):', e);
      }
    }, POLL_MS);
  }, [stopPolling, toast]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file || !companyName.trim()) return;

    const year = Number(reportYear);
    if (!Number.isInteger(year) || year < 1990 || year > new Date().getFullYear() + 1) {
      toast({ title: 'Check the report year', description: 'Enter a plausible 4-digit year.', variant: 'destructive' });
      return;
    }

    setSubmitting(true);
    setError(null);
    setJob(null);
    setDuplicate(null);
    try {
      const res = await ingestReport(file, companyName.trim(), year, useVlmTables);
      if (isIngestDuplicate(res)) {
        setDuplicate(res);
        toast({ title: 'Already ingested', description: res.message });
      } else {
        setJob({ job_id: res.job_id, status: 'queued', report_id: res.report_id });
        startPolling(res.job_id);
        toast({ title: 'Ingest started', description: `Job ${res.job_id} queued.` });
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
      toast({ title: 'Ingest failed', description: msg, variant: 'destructive' });
    } finally {
      setSubmitting(false);
    }
  };

  const running = !!job && job.status !== 'done' && job.status !== 'error';
  const idx = stageIndex(job?.status ?? null);
  const docId = job?.doc_id || job?.report_id || duplicate?.report_id;

  // ── auth gate ──
  if (!user) {
    return (
      <div className="glass-panel p-6 space-y-4">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-primary/10 border border-primary/20">
            <UploadCloud className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h2 className="text-lg font-medium text-foreground">Sign in to ingest a report</h2>
            <p className="text-sm text-muted-foreground">
              Writing to the corpus is authenticated. Reading stays open to everyone.
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Input
            className="h-9 w-56 text-sm" placeholder="you@example.com" type="email"
            value={authEmail} onChange={(e) => setAuthEmail(e.target.value)}
          />
          <Input
            className="h-9 w-44 text-sm" placeholder="password" type="password"
            value={authPw} onChange={(e) => setAuthPw(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && doAuth('login')}
          />
          <Button size="sm" variant="outline" disabled={authBusy} onClick={() => doAuth('login')}>
            {authBusy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : 'Login'}
          </Button>
          <Button size="sm" variant="ghost" disabled={authBusy} onClick={() => doAuth('register')}>
            Register
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="glass-panel p-6 space-y-5">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-primary/10 border border-primary/20">
            <UploadCloud className="w-5 h-5 text-primary" />
          </div>
          <div>
            <h2 className="text-lg font-medium text-foreground">Upload ESG report (PDF)</h2>
            <p className="text-sm text-muted-foreground">
              Runs the full pipeline: parse → extract → quality gate → embed → corpus.
            </p>
          </div>
        </div>
        <Button size="sm" variant="ghost" className="text-xs gap-1.5" onClick={signOut}>
          <LogOut className="w-3.5 h-3.5" /> {user.email}
        </Button>
      </div>

      <form onSubmit={submit} className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="pdf">Report PDF *</Label>
          <label
            htmlFor="pdf"
            className={cn(
              'flex items-center gap-3 p-4 rounded-lg border border-dashed cursor-pointer transition-colors',
              file ? 'border-primary/40 bg-primary/5' : 'border-border/60 bg-muted/30 hover:border-primary/30',
            )}
          >
            <FileText className="w-5 h-5 text-primary shrink-0" />
            <span className="text-sm text-foreground truncate">
              {file ? file.name : 'Choose a PDF…'}
            </span>
            {file && (
              <Badge variant="secondary" className="ml-auto text-xs shrink-0">
                {(file.size / 1_048_576).toFixed(1)} MB
              </Badge>
            )}
          </label>
          <input
            id="pdf" type="file" accept="application/pdf,.pdf" className="sr-only"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor="ingestCompany">Company name *</Label>
            <Input
              id="ingestCompany" placeholder="e.g. Tata Power"
              value={companyName} onChange={(e) => setCompanyName(e.target.value)}
              className="bg-muted/50 border-border/50 focus:border-primary"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="ingestYear">Report year *</Label>
            <Input
              id="ingestYear" type="number" inputMode="numeric"
              min={1990} max={new Date().getFullYear() + 1}
              value={reportYear} onChange={(e) => setReportYear(e.target.value)}
              className="bg-muted/50 border-border/50 focus:border-primary"
            />
          </div>
        </div>

        <div className="flex items-start gap-2">
          <Checkbox
            id="vlm" checked={useVlmTables}
            onCheckedChange={(v) => setUseVlmTables(v === true)}
            className="mt-0.5"
          />
          <Label htmlFor="vlm" className="text-xs font-normal text-muted-foreground leading-relaxed">
            Also run vision-model table extraction — recovers borderless performance tables
            pdfplumber misses, but is markedly slower and consumes LLM credits.
          </Label>
        </div>

        <Button
          type="submit" className="btn-neon w-full"
          disabled={submitting || running || !file || !companyName.trim()}
        >
          {submitting || running ? (
            <><Loader2 className="w-4 h-4 mr-2 animate-spin" />{running ? 'Ingesting…' : 'Uploading…'}</>
          ) : (
            <><UploadCloud className="w-4 h-4 mr-2" />Ingest report</>
          )}
        </Button>
      </form>

      {/* ── progress / outcome ── */}
      <AnimatePresence mode="wait">
        {job && (
          <motion.div
            key="job" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
            className="p-4 rounded-lg bg-muted/30 border border-border/40 space-y-3"
          >
            <div className="flex items-center justify-between text-xs">
              <span className="font-mono text-muted-foreground">job {job.job_id}</span>
              <Badge variant="outline" className="text-[10px]">{job.status}</Badge>
            </div>

            <div className="flex gap-1">
              {STAGES.map((s, i) => (
                <div
                  key={s.key}
                  title={s.label}
                  className={cn(
                    'h-1.5 flex-1 rounded-full transition-colors',
                    job.status === 'error' ? 'bg-danger/30'
                      : i <= idx ? 'bg-primary'
                      : 'bg-border/60',
                  )}
                />
              ))}
            </div>
            <p className="text-xs text-muted-foreground">
              {job.status === 'error'
                ? 'Failed'
                : STAGES[Math.max(idx, 0)]?.label}
              {job.pages != null && ` · ${job.pages} pages`}
              {job.sentences != null && ` · ${job.sentences} sentences`}
              {job.extracted != null && ` · ${job.extracted} claims extracted`}
              {job.inserted != null && ` · ${job.inserted} written`}
            </p>

            {job.status === 'done' && (
              <div className="flex flex-wrap items-center gap-2 pt-1">
                <CheckCircle2 className="w-4 h-4 text-success" />
                <span className="text-sm text-foreground">
                  {job.inserted ?? 0} claims added to the corpus.
                </span>
                {docId && (
                  <Button asChild size="sm" variant="outline" className="h-7 text-xs gap-1 ml-auto">
                    <Link to="/integrity-audit">Open Integrity Audit <ArrowRight className="w-3 h-3" /></Link>
                  </Button>
                )}
              </div>
            )}
          </motion.div>
        )}

        {duplicate && (
          <motion.div
            key="dup" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
            className="p-4 rounded-lg bg-warning/5 border border-warning/25 space-y-2"
          >
            <div className="flex items-center gap-2 text-warning text-sm font-medium">
              <Copy className="w-4 h-4" /> Already in the corpus
            </div>
            <p className="text-xs text-muted-foreground">
              {duplicate.message} Report <span className="font-mono">{duplicate.report_id}</span>
              {duplicate.claim_count != null && ` · ${duplicate.claim_count} claims`}.
              Content-hash dedup prevents duplicate claims from being written.
            </p>
            <Button asChild size="sm" variant="outline" className="h-7 text-xs gap-1">
              <Link to="/integrity-audit">Open Integrity Audit <ArrowRight className="w-3 h-3" /></Link>
            </Button>
          </motion.div>
        )}

        {error && (
          <motion.div
            key="err" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
            className="p-4 rounded-lg bg-danger/5 border border-danger/25"
          >
            <div className="flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 text-danger mt-0.5 shrink-0" />
              <div className="space-y-1">
                <p className="text-sm font-medium text-danger">Ingest failed</p>
                <p className="text-xs text-muted-foreground break-words">{error}</p>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export default ReportIngestPanel;
