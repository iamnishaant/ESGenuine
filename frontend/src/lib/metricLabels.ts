// Human-readable labels for metric keys.
//
// The backend identifies every metric by a dotted canonical key of the shape
// `{aspect_node}.{dimension}` — e.g. `social.workforce.total.count`,
// `emissions.scope1.co2e`, `social.diversity.gender.percent`. Those keys are
// precise but unreadable, and several pages were rendering them verbatim. This
// maps a key to a label an analyst actually wants to see ("Total Workforce",
// "Scope 1 Emissions (CO₂e)").
//
// Strategy: strip the trailing dimension, look the aspect node up in a curated
// table (so the common metrics read exactly right), fall back to a generic
// humanizer for the long tail, then append a dimension qualifier only where it
// adds information.

// Dimensions emitted by UnitCanonicalizer.dimension_of (+ 'unspecified').
const DIMENSIONS = new Set([
  'co2e', 'mass', 'energy', 'volume', 'area', 'count',
  'percent', 'rate', 'currency', 'unspecified',
]);

// Aspect node → label. Mirrors the backend taxonomy (ontology.py TAXONOMY).
const CURATED: Record<string, string> = {
  // Environmental
  'emissions.scope1': 'Scope 1 Emissions',
  'emissions.scope2': 'Scope 2 Emissions',
  'emissions.scope3': 'Scope 3 Emissions',
  'emissions.total': 'Total GHG Emissions',
  'energy.renewable': 'Renewable Energy',
  'energy.total': 'Total Energy Use',
  'water.consumption': 'Water Consumption',
  'water.recycled': 'Water Recycled',
  'waste.total': 'Total Waste',
  'waste.recycled': 'Waste Recycled',
  'biodiversity.conservation': 'Biodiversity & Conservation',
  // Social
  'social.diversity.gender': 'Gender Diversity',
  'social.health_safety.ltifr': 'Lost-Time Injury Rate (LTIFR)',
  'social.health_safety.fatalities': 'Workplace Fatalities',
  'social.workforce.total': 'Total Workforce',
  'social.training.hours': 'Training Hours',
  // Governance
  'governance.board.diversity': 'Board Diversity',
  'governance.ethics.incidents': 'Ethics Incidents',
  // Family-level fallbacks (when only a 2-part node survives)
  'emissions': 'Emissions',
  'energy': 'Energy',
  'water': 'Water',
  'waste': 'Waste',
  'biodiversity': 'Biodiversity',
  'social.diversity': 'Diversity',
  'social.health_safety': 'Health & Safety',
  'social.workforce': 'Workforce',
  'social.training': 'Training & Development',
  'governance.board': 'Board Governance',
  'governance.ethics': 'Ethics & Compliance',
};

// Dimension → trailing qualifier, only where it disambiguates. count/mass/energy/
// volume/area are already implied by the label, so they get no qualifier.
const DIM_QUALIFIER: Record<string, string> = {
  co2e: 'CO₂e',
  percent: '%',
  currency: 'spend',
  rate: 'rate',
};

// Token-level fixups for the generic humanizer (unknown keys).
const TOKEN_FIXUPS: Record<string, string> = {
  scope1: 'Scope 1', scope2: 'Scope 2', scope3: 'Scope 3',
  ghg: 'GHG', co2e: 'CO₂e', co2: 'CO₂', ltifr: 'LTIFR',
  esg: 'ESG', kpi: 'KPI', randd: 'R&D',
};

function titleCaseWord(w: string): string {
  if (!w) return w;
  if (TOKEN_FIXUPS[w]) return TOKEN_FIXUPS[w];
  return w.charAt(0).toUpperCase() + w.slice(1);
}

function humanize(node: string): string {
  return node
    .split('.')
    .flatMap((seg) => seg.split('_'))
    .map(titleCaseWord)
    .join(' ')
    .trim();
}

/**
 * Convert a canonical metric key (or bare aspect node) into a human-readable
 * label. Safe on null/empty/uncategorized.
 */
export function metricLabel(key: string | null | undefined): string {
  const k = (key || '').trim().toLowerCase();
  if (!k || k === 'uncategorized' || k === 'none') return 'Uncategorized';

  // Split off a trailing dimension suffix, if present.
  const parts = k.split('.');
  let dim: string | null = null;
  let node = k;
  if (parts.length > 1 && DIMENSIONS.has(parts[parts.length - 1])) {
    dim = parts[parts.length - 1];
    node = parts.slice(0, -1).join('.');
  }

  const base = CURATED[node] ?? humanize(node);
  const qualifier = dim ? DIM_QUALIFIER[dim] : undefined;
  // Don't append a qualifier the label already contains (e.g. LTIFR + "rate").
  if (qualifier && !base.toLowerCase().includes(qualifier.toLowerCase())) {
    return `${base} (${qualifier})`;
  }
  return base;
}
