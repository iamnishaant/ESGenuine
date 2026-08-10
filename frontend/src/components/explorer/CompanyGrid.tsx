import { useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { Search, ChevronLeft, ChevronRight, Building2, MapPin, FileText, ArrowRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { CompanyGroup, ReportGroup } from '@/lib/claimFacets';
import { resolveHeadquarters } from '@/lib/companyHeadquarters';
import { useBackendScores } from '@/hooks/useBackendScores';

/** 3 x 3. The page size IS the grid, so a page never renders a ragged half-row. */
const PAGE_SIZE = 9;

const scoreColor = (score: number | null) =>
  score == null ? 'text-muted-foreground'
    : score >= 70 ? 'text-success'
    : score >= 40 ? 'text-warning'
    : 'text-danger';

/** Proportional verified / review / gap bar - the company's shape at a glance. */
function StatusBar({ group }: { group: { total: number; verified: number; review: number; gap: number } }) {
  const pct = (n: number) => (group.total ? (n / group.total) * 100 : 0);
  return (
    <div className="flex h-1.5 w-full overflow-hidden rounded-full bg-background/60 border border-border/40">
      <div className="bg-success" style={{ width: `${pct(group.verified)}%` }} />
      <div className="bg-warning" style={{ width: `${pct(group.review)}%` }} />
      <div className="bg-danger" style={{ width: `${pct(group.gap)}%` }} />
    </div>
  );
}

function ReportCell({ report, onOpen }: { report: ReportGroup; onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      title={`${report.docId} — ${report.total} claims`}
      className="group/cell rounded-lg border border-border/50 bg-background/40 px-2 py-2 text-left transition-all hover:border-primary/60 hover:bg-primary/10 focus:outline-none focus-visible:ring-1 focus-visible:ring-primary"
    >
      <div className="flex items-baseline justify-between gap-1">
        <span className="font-mono text-sm font-semibold text-foreground group-hover/cell:text-primary transition-colors">
          {report.year ?? '—'}
        </span>
        <span className="text-[10px] text-muted-foreground">{report.total}</span>
      </div>
      <StatusBar group={report} />
    </button>
  );
}

interface CompanyGridProps {
  groups: CompanyGroup[];
  search: string;
  onSearchChange: (v: string) => void;
  /** docId === null means "every claim this company has, across all reports". */
  onOpenReport: (companyName: string, docId: string | null) => void;
  loading: boolean;
}

export function CompanyGrid({ groups, search, onSearchChange, onOpenReport, loading }: CompanyGridProps) {
  const [page, setPage] = useState(0);
  const { forCompany } = useBackendScores();

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return groups;
    return groups.filter((g) => {
      const hq = resolveHeadquarters(g.name);
      const haystack = `${g.name} ${hq ? `${hq.city} ${hq.country}` : ''} ${g.reports.map((r) => r.docId).join(' ')}`;
      return haystack.toLowerCase().includes(q);
    });
  }, [groups, search]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  // A search that shrinks the list can strand you on a page that no longer
  // exists, which reads as "no companies" on a non-empty result set.
  useEffect(() => { if (page > pageCount - 1) setPage(0); }, [page, pageCount]);

  const start = page * PAGE_SIZE;
  const visible = filtered.slice(start, start + PAGE_SIZE);

  return (
    <div className="flex flex-col h-full">
      {/* Search + pager */}
      <div className="flex flex-col md:flex-row gap-3 mb-5">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground w-4 h-4" />
          <input
            type="text"
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search companies, headquarters, or report IDs..."
            className="w-full bg-background/50 border border-border/50 text-foreground text-sm rounded-lg pl-10 pr-4 py-2.5 focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary transition-all glass-panel"
          />
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground font-mono whitespace-nowrap px-1">
            {filtered.length === 0 ? '0' : `${start + 1}–${Math.min(start + PAGE_SIZE, filtered.length)}`} of {filtered.length}
          </span>
          <button
            type="button"
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            aria-label="Previous page"
            className="p-2 rounded-lg glass-panel border border-border/50 text-foreground disabled:opacity-30 disabled:cursor-not-allowed hover:bg-white/[0.06] transition-colors"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <span className="text-xs text-muted-foreground font-mono whitespace-nowrap">
            {page + 1}/{pageCount}
          </span>
          <button
            type="button"
            onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
            disabled={page >= pageCount - 1}
            aria-label="Next page"
            className="p-2 rounded-lg glass-panel border border-border/50 text-foreground disabled:opacity-30 disabled:cursor-not-allowed hover:bg-white/[0.06] transition-colors"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* The 3 x 3 grid */}
      {visible.length === 0 ? (
        <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground opacity-70">
          <Building2 className="w-8 h-8 mb-3" />
          <p className="text-sm">
            {loading ? 'Loading companies…'
              : search.trim() ? `No company matches “${search.trim()}”.`
              : 'No companies in the corpus yet. Ingest a report to populate this view.'}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 auto-rows-fr">
          {visible.map((group, i) => {
            const hq = resolveHeadquarters(group.name);
            const backend = forCompany(group.name);
            const integrity = backend?.integrity_score != null ? Math.round(backend.integrity_score) : null;

            return (
              <motion.div
                key={group.name}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.03, duration: 0.25 }}
                className="glass-panel border border-border/40 rounded-xl p-4 flex flex-col gap-3 hover:border-primary/40 transition-colors"
              >
                {/* Identity */}
                <div className="flex items-start gap-3">
                  <div className="w-9 h-9 rounded-lg bg-primary/15 flex items-center justify-center flex-shrink-0">
                    <Building2 className="w-4 h-4 text-primary" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <h3 className="font-semibold text-foreground truncate">{group.name}</h3>
                    <p className="text-[11px] text-muted-foreground flex items-center gap-1 truncate">
                      <MapPin className="w-3 h-3 flex-shrink-0" />
                      {hq ? `${hq.city}, ${hq.country}` : 'Headquarters unknown'}
                    </p>
                  </div>
                  {/* Integrity score is backend-only; "—" when it is unreachable. */}
                  <div className="text-right flex-shrink-0">
                    <div className={cn('font-mono text-lg font-bold leading-none', scoreColor(integrity))}>
                      {integrity ?? '—'}
                    </div>
                    <div className="text-[9px] uppercase tracking-wider text-muted-foreground">integrity</div>
                  </div>
                </div>

                {/* Portfolio shape */}
                <div className="space-y-1.5">
                  <StatusBar group={group} />
                  <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
                    <span className="text-success">{group.verified} verified</span>
                    <span className="text-warning">{group.review} review</span>
                    <span className="text-danger">{group.gap} gaps</span>
                  </div>
                </div>

                {/* Year cells - the drill-down the whole page is built around */}
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1.5 flex items-center gap-1">
                    <FileText className="w-3 h-3" />
                    {group.reports.length} report{group.reports.length === 1 ? '' : 's'}
                  </div>
                  <div className="grid grid-cols-3 gap-1.5">
                    {group.reports.map((report) => (
                      <ReportCell
                        key={report.docId}
                        report={report}
                        onOpen={() => onOpenReport(group.name, report.docId)}
                      />
                    ))}
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => onOpenReport(group.name, null)}
                  className="mt-auto flex items-center justify-between text-xs text-muted-foreground hover:text-primary transition-colors pt-1 group/all"
                >
                  <span>All {group.total} claims</span>
                  <ArrowRight className="w-3.5 h-3.5 group-hover/all:translate-x-0.5 transition-transform" />
                </button>
              </motion.div>
            );
          })}
        </div>
      )}
    </div>
  );
}
