// Company headquarters registry.
//
// The 3D globe locates the HEADQUARTERS of each company whose report has been
// ingested, then surfaces that company's claims on click. Claim `location_text`
// is the place mentioned *inside* a claim ("we planted trees in Brazil") — NOT
// the company's HQ — so HQ must come from a curated registry of real, verifiable
// coordinates. We never fabricate a location: an unknown company resolves to
// `null` and is simply not plotted.
//
// Entries cover the current ESG corpus (Shell, BP, Microsoft, Infosys, Tata
// Power) plus a set of well-known issuers so newly ingested reports light up
// without code changes. Extend `HQ_REGISTRY` to add more.

export interface Headquarters {
  city: string;
  country: string;
  lat: number;
  lng: number;
}

interface HQEntry extends Headquarters {
  /** Canonical key (for dedup / debugging). */
  key: string;
  /** Normalized name variants this HQ should match. */
  aliases: string[];
}

// Real HQ coordinates. Where two issuers share a city (Shell & BP in London) we
// use each company's actual building so their markers don't perfectly overlap.
const HQ_REGISTRY: HQEntry[] = [
  // ── Current corpus ──────────────────────────────────────────────────────
  { key: 'shell', city: 'London', country: 'United Kingdom', lat: 51.5045, lng: -0.1140,
    aliases: ['shell', 'royal dutch shell', 'shell plc'] },
  { key: 'bp', city: 'London', country: 'United Kingdom', lat: 51.5072, lng: -0.1357,
    aliases: ['bp', 'british petroleum', 'bp plc'] },
  { key: 'microsoft', city: 'Redmond, WA', country: 'United States', lat: 47.6740, lng: -122.1215,
    aliases: ['microsoft', 'microsoft corporation', 'msft'] },
  { key: 'infosys', city: 'Bengaluru', country: 'India', lat: 12.8452, lng: 77.6602,
    aliases: ['infosys', 'infosys bpm', 'infosys technologies'] },
  { key: 'tata_power', city: 'Mumbai', country: 'India', lat: 18.9298, lng: 72.8350,
    aliases: ['tata power', 'the tata power', 'tata power company', 'business responsibility',
      'business responsibility and sustainability'] },

  // ── Common issuers (so future uploads plot without code changes) ─────────
  { key: 'apple', city: 'Cupertino, CA', country: 'United States', lat: 37.3349, lng: -122.0090,
    aliases: ['apple', 'apple inc'] },
  { key: 'alphabet', city: 'Mountain View, CA', country: 'United States', lat: 37.4220, lng: -122.0841,
    aliases: ['google', 'alphabet', 'alphabet inc'] },
  { key: 'amazon', city: 'Seattle, WA', country: 'United States', lat: 47.6062, lng: -122.3321,
    aliases: ['amazon', 'amazon com'] },
  { key: 'tesla', city: 'Austin, TX', country: 'United States', lat: 30.2240, lng: -97.6186,
    aliases: ['tesla', 'tesla motors'] },
  { key: 'exxonmobil', city: 'Spring, TX', country: 'United States', lat: 30.0938, lng: -95.4196,
    aliases: ['exxon', 'exxonmobil', 'exxon mobil'] },
  { key: 'chevron', city: 'San Ramon, CA', country: 'United States', lat: 37.7799, lng: -121.9780,
    aliases: ['chevron'] },
  { key: 'totalenergies', city: 'Courbevoie', country: 'France', lat: 48.8920, lng: 2.2400,
    aliases: ['total', 'totalenergies', 'total energies'] },
  { key: 'nestle', city: 'Vevey', country: 'Switzerland', lat: 46.4628, lng: 6.8419,
    aliases: ['nestle', 'nestlé'] },
  { key: 'unilever', city: 'London', country: 'United Kingdom', lat: 51.5113, lng: -0.1180,
    aliases: ['unilever'] },
  { key: 'toyota', city: 'Toyota City', country: 'Japan', lat: 35.0820, lng: 137.1560,
    aliases: ['toyota', 'toyota motor'] },
  { key: 'samsung', city: 'Suwon', country: 'South Korea', lat: 37.2580, lng: 127.0480,
    aliases: ['samsung', 'samsung electronics'] },
  { key: 'reliance', city: 'Mumbai', country: 'India', lat: 19.0570, lng: 72.8290,
    aliases: ['reliance', 'reliance industries'] },
  { key: 'tcs', city: 'Mumbai', country: 'India', lat: 18.9270, lng: 72.8330,
    aliases: ['tcs', 'tata consultancy', 'tata consultancy services'] },
  { key: 'adani', city: 'Ahmedabad', country: 'India', lat: 23.0510, lng: 72.5170,
    aliases: ['adani', 'adani green', 'adani enterprises'] },
];

const SUFFIXES = /\b(plc|inc|ltd|limited|corp|corporation|company|co|the|group|holdings|sa|ag|nv|spa)\b/g;

/** Lowercase, strip punctuation + corporate suffixes, collapse whitespace. */
function normalize(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9 ]+/g, ' ')
    .replace(SUFFIXES, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

// Pre-normalize aliases once.
const NORMALIZED = HQ_REGISTRY.map((e) => ({
  entry: e,
  aliases: e.aliases.map(normalize).filter(Boolean),
}));

/**
 * Resolve a company display name to its HQ coordinates, or `null` if unknown.
 * Matching is alias-aware: exact, whole-word (short aliases like "bp"), and
 * multi-word substring ("tata power" inside a longer name).
 */
export function resolveHeadquarters(companyName: string | null | undefined): Headquarters | null {
  if (!companyName) return null;
  const input = normalize(companyName);
  if (!input) return null;
  const words = new Set(input.split(' '));

  for (const { entry, aliases } of NORMALIZED) {
    for (const alias of aliases) {
      if (input === alias) return entry;
      if (alias.includes(' ')) {
        if (input.includes(alias)) return entry;
      } else if (words.has(alias)) {
        return entry;
      }
    }
  }
  return null;
}
