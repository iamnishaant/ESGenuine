import { Search, SlidersHorizontal, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  ClaimFacets,
  EMPTY_FACETS,
  FacetOption,
  activeFacetCount,
  buildFacetOptions,
} from '@/lib/claimFacets';
import { Claim } from '@/hooks/useClaims';

const selectClass =
  'bg-background/50 border border-border/50 text-foreground text-xs rounded-lg px-3 py-2 ' +
  'focus:outline-none focus:ring-1 focus:ring-primary appearance-none glass-panel max-w-[190px] truncate';

function FacetSelect({
  label, value, options, allLabel, onChange, disabled,
}: {
  label: string;
  value: string;
  options: FacetOption[];
  allLabel: string;
  onChange: (v: string) => void;
  disabled?: boolean;
}) {
  // A facet with nothing to choose between is noise - hide it rather than render
  // a dropdown whose only entry is "All".
  if (options.length === 0) return null;
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</span>
      <select
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        className={cn(selectClass, value !== 'all' && 'border-primary/60 text-primary', disabled && 'opacity-40')}
      >
        <option value="all">{allLabel}</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label} ({o.count})
          </option>
        ))}
      </select>
    </label>
  );
}

interface ClaimFiltersProps {
  facets: ClaimFacets;
  onChange: (next: ClaimFacets) => void;
  /** Claims in scope BEFORE facets are applied - the option counts come from these. */
  scope: Claim[];
  resultCount: number;
}

export function ClaimFilters({ facets, onChange, scope, resultCount }: ClaimFiltersProps) {
  const options = buildFacetOptions(scope, facets.sector);
  const active = activeFacetCount(facets);
  const set = (patch: Partial<ClaimFacets>) => onChange({ ...facets, ...patch });

  return (
    <div className="glass-panel border border-border/40 rounded-xl p-4 mb-5 space-y-3">
      <div className="flex flex-col md:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground w-4 h-4" />
          <input
            type="text"
            value={facets.search}
            onChange={(e) => set({ search: e.target.value })}
            placeholder="Search claim text, company, location, or claim ID..."
            className="w-full bg-background/50 border border-border/50 text-foreground text-sm rounded-lg pl-10 pr-4 py-2.5 focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary transition-all"
          />
        </div>
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          <SlidersHorizontal className="w-4 h-4" />
          <span className="font-mono whitespace-nowrap">
            {resultCount.toLocaleString()} claim{resultCount === 1 ? '' : 's'}
          </span>
          {active > 0 && (
            <button
              type="button"
              onClick={() => onChange({ ...EMPTY_FACETS })}
              className="flex items-center gap-1 px-2 py-1 rounded border border-border/50 hover:border-danger/50 hover:text-danger transition-colors whitespace-nowrap"
            >
              <X className="w-3 h-3" /> Clear {active} filter{active === 1 ? '' : 's'}
            </button>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-3">
        <FacetSelect
          label="Verification"
          value={facets.status}
          allLabel="All statuses"
          onChange={(v) => set({ status: v })}
          options={[
            { value: 'verified', label: 'Verified', count: scope.filter((c) => c.status === 'verified').length },
            { value: 'review', label: 'Under review', count: scope.filter((c) => c.status === 'review').length },
            { value: 'gap', label: 'Integrity gap', count: scope.filter((c) => c.status === 'gap').length },
          ].filter((o) => o.count > 0)}
        />
        <FacetSelect
          label="Claim type"
          value={facets.claimType}
          allLabel="All claim types"
          options={options.claimType}
          onChange={(v) => set({ claimType: v })}
        />
        <FacetSelect
          label="Verifiable by"
          value={facets.observability}
          allLabel="Any method"
          options={options.observability}
          onChange={(v) => set({ observability: v })}
        />
        <FacetSelect
          label="Category"
          value={facets.sector}
          allLabel="All categories"
          options={options.sector}
          // Changing category invalidates the metric choice below it.
          onChange={(v) => set({ sector: v, metric: 'all' })}
        />
        <FacetSelect
          label="Metric"
          value={facets.metric}
          allLabel={facets.sector === 'all' ? 'All metrics' : 'All in category'}
          options={options.metric}
          onChange={(v) => set({ metric: v })}
        />
        <FacetSelect
          label="Framework"
          value={facets.framework}
          allLabel="Any framework"
          options={options.framework}
          onChange={(v) => set({ framework: v })}
        />
        <FacetSelect
          label="Quality flag"
          value={facets.qualityFlag}
          allLabel="Any quality"
          options={[
            { value: 'none', label: 'No flags', count: scope.filter((c) => c.qualityFlags.length === 0).length },
            ...options.qualityFlag,
          ].filter((o) => o.count > 0)}
          onChange={(v) => set({ qualityFlag: v })}
        />
        <label className="flex flex-col gap-1">
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
            Min confidence{facets.minConfidence > 0 && <span className="text-primary"> {facets.minConfidence}%</span>}
          </span>
          <input
            type="range"
            min={0}
            max={100}
            step={5}
            value={facets.minConfidence}
            onChange={(e) => set({ minConfidence: Number(e.target.value) })}
            className="w-32 accent-primary h-[34px]"
          />
        </label>
      </div>
    </div>
  );
}
