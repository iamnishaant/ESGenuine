import { Link } from 'react-router-dom';
import {
  Search, MapPin, Calendar, AlertTriangle, CheckCircle2, Clock, ArrowUpDown, ChevronDown, FileText, ShieldAlert,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { Claim } from '@/hooks/useClaims';
import { claimTypeLabel, qualityFlagLabel } from '@/lib/claimFacets';

export const statusConfig = {
  verified: { label: 'Verified', icon: CheckCircle2, class: 'text-success bg-success/10 border-success/20' },
  review: { label: 'Under Review', icon: Clock, class: 'text-warning bg-warning/10 border-warning/20' },
  gap: { label: 'Integrity Gap', icon: AlertTriangle, class: 'text-danger bg-danger/10 border-danger/20' },
} as const;

const confidenceLevel = (score: number) =>
  score >= 80 ? { label: 'High', class: 'text-success bg-success/10 border-success/20' }
    : score >= 50 ? { label: 'Medium', class: 'text-warning bg-warning/10 border-warning/20' }
    : { label: 'Low', class: 'text-danger bg-danger/10 border-danger/20' };

interface ClaimTableProps {
  claims: Claim[];
  sortField: keyof Claim;
  sortDirection: 'asc' | 'desc';
  onSort: (field: keyof Claim) => void;
  emptyMessage: string;
  /** Rendered under the empty message - e.g. a "clear filters" button. */
  emptyAction?: React.ReactNode;
}

export function ClaimTable({ claims, sortField, sortDirection, onSort, emptyMessage, emptyAction }: ClaimTableProps) {
  const SortHeader = ({ field, children }: { field: keyof Claim; children: React.ReactNode }) => (
    <th
      className="px-6 py-4 cursor-pointer hover:text-primary transition-colors select-none"
      onClick={() => onSort(field)}
      aria-sort={sortField === field ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'}
    >
      <div className="flex items-center gap-1">
        {children}
        <ArrowUpDown className={cn('w-3 h-3', sortField === field && 'text-primary')} />
      </div>
    </th>
  );

  return (
    <div className="flex-1 glass-panel border border-border/30 rounded-xl overflow-hidden shadow-2xl flex flex-col min-h-0">
      <div className="overflow-auto">
        <table className="w-full text-left text-sm whitespace-nowrap">
          <thead className="text-xs uppercase bg-secondary/30 text-muted-foreground border-b border-border/30 sticky top-0 backdrop-blur-md z-10">
            <tr>
              <SortHeader field="id">Claim ID</SortHeader>
              <SortHeader field="claim">Extracted Claim</SortHeader>
              <SortHeader field="verifiabilityClass">Type</SortHeader>
              <SortHeader field="status">Verification</SortHeader>
              <SortHeader field="confidence">Confidence</SortHeader>
              <SortHeader field="date">Date</SortHeader>
              <th className="px-6 py-4 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/20">
            {claims.map((claim) => {
              const StatusIcon = statusConfig[claim.status].icon;
              const level = confidenceLevel(claim.confidence);
              return (
                <tr key={claim.id} className="hover:bg-white/[0.02] transition-colors group">
                  <td className="px-6 py-4 font-mono text-xs text-muted-foreground">{claim.id}</td>
                  <td className="px-6 py-4">
                    <div className="font-medium text-foreground tracking-wide max-w-md truncate">{claim.claim}</div>
                    <div className="text-xs text-muted-foreground flex items-center gap-2 mt-1">
                      <span className="flex items-center gap-1"><MapPin className="w-3 h-3" /> {claim.location}</span>
                      <span>•</span>
                      {/* Company alone is AMBIGUOUS: the corpus holds two Shell
                          reports (2022, 2023) and two Infosys reports (2023, 2025),
                          so "Shell" does not say which document a claim came from.
                          Always pair the company with its source report. */}
                      <span className="text-foreground/80">{claim.company}</span>
                      {claim.reportYear && (
                        <>
                          <span>•</span>
                          <span
                            className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded border border-border/50 bg-muted/30 font-mono text-[10px]"
                            title={claim.docId ? `Source report: ${claim.docId}` : undefined}
                          >
                            <FileText className="w-2.5 h-2.5" />
                            {claim.reportYear} report
                          </span>
                        </>
                      )}
                      {claim.page != null && (
                        <>
                          <span>•</span>
                          <span className="font-mono text-[10px]">p{claim.page}</span>
                        </>
                      )}
                      {claim.qualityFlags.length > 0 && (
                        <span
                          className="inline-flex items-center gap-1 text-warning"
                          title={claim.qualityFlags.map(qualityFlagLabel).join(' · ')}
                        >
                          <ShieldAlert className="w-3 h-3" />
                          {claim.qualityFlags.length}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <span className="text-xs text-muted-foreground">{claimTypeLabel(claim.verifiabilityClass)}</span>
                  </td>
                  <td className="px-6 py-4">
                    <span className={cn('inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border', statusConfig[claim.status].class)}>
                      <StatusIcon className="w-3.5 h-3.5" />
                      {statusConfig[claim.status].label}
                    </span>
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-3">
                      <div className="flex-1 w-16 h-1.5 bg-background rounded-full overflow-hidden border border-border/50">
                        <div
                          className={cn('h-full rounded-full transition-all duration-1000', claim.confidence >= 80 ? 'bg-success glow-success' : claim.confidence >= 50 ? 'bg-warning glow-warning' : 'bg-danger glow-danger')}
                          style={{ width: `${claim.confidence}%` }}
                        />
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-mono w-7">{claim.confidence}%</span>
                        <span className={cn('text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded border', level.class)}>
                          {level.label}
                        </span>
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-1.5 text-muted-foreground">
                      <Calendar className="w-3.5 h-3.5" />
                      {/* An undated claim shows its report year, never a fabricated day. */}
                      {claim.dateKnown ? claim.date : claim.reportYear ? `${claim.reportYear} (report)` : '—'}
                    </div>
                  </td>
                  <td className="px-6 py-4 text-right">
                    <Link
                      to={`/claims/${claim.id}`}
                      aria-label={`Open claim ${claim.id}`}
                      className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-primary/10 text-primary hover:bg-primary hover:text-primary-foreground hover:shadow-[0_0_15px_rgba(6,182,212,0.4)] transition-all"
                    >
                      <ChevronDown className="w-4 h-4 -rotate-90" />
                    </Link>
                  </td>
                </tr>
              );
            })}
            {claims.length === 0 && (
              <tr>
                <td colSpan={7} className="px-6 py-12 text-center text-muted-foreground">
                  <div className="flex flex-col items-center justify-center gap-3 opacity-70">
                    <Search className="w-8 h-8" />
                    <p className="text-sm">{emptyMessage}</p>
                    {emptyAction}
                  </div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
