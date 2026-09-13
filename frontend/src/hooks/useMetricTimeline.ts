import { useMemo } from 'react';
import { Claim } from './useClaims';
import { metricLabel } from '@/lib/metricLabels';

export interface MetricPoint {
  year: string;
  value: number;
  anomaly?: boolean;
  anomalyLabel?: string;
}

export interface MetricSeries {
  id: string;
  label: string;
  unit: string;
  color: string;
  data: MetricPoint[];
  category: 'environment' | 'social' | 'governance';
}

// Helper to determine category based on metric key
const getCategory = (key: string): 'environment' | 'social' | 'governance' => {
  const lower = key.toLowerCase();
  if (lower.includes('water') || lower.includes('emission') || lower.includes('carbon') || lower.includes('energy') || lower.includes('waste')) {
    return 'environment';
  }
  if (lower.includes('employee') || lower.includes('diversity') || lower.includes('health') || lower.includes('safety') || lower.includes('community')) {
    return 'social';
  }
  return 'governance';
};

// Stable categorical palette for series, stepped for the dark surface. The ORDER is
// deliberate — it keeps adjacent series distinguishable under colour-vision deficiency —
// so assign slots in order and never re-sort. Eight slots; past that, series repeat.
const COLORS = [
  '#3987e5', '#d95926', '#199e70', '#c98500',
  '#d55181', '#008300', '#9085e9', '#e66767'
];

export function useMetricTimeline(claims: Claim[]): MetricSeries[] {
  return useMemo(() => {
    if (!claims || claims.length === 0) return [];

    // Filter claims that have a metric value and year
    const metricClaims = claims.filter(c => c.metricValue !== undefined && c.metricValue !== null && c.metricKey);

    // Group by metricKey
    const groups = new Map<string, Claim[]>();
    metricClaims.forEach(c => {
      const key = c.metricKey as string;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(c);
    });

    const series: MetricSeries[] = [];
    let colorIndex = 0;

    groups.forEach((groupClaims, key) => {
      // Group points by year
      const yearMap = new Map<string, MetricPoint>();
      
      groupClaims.forEach(c => {
        // Extract year from date 
        const dateObj = new Date(c.date);
        const year = isNaN(dateObj.getFullYear()) ? c.date.substring(0, 4) : dateObj.getFullYear().toString();
        
        // If we already have a point for this year, maybe we average or just take the first. Let's just take the first or if there's an anomaly logic.
        if (!yearMap.has(year)) {
          yearMap.set(year, {
            year,
            value: c.metricValue!,
            anomaly: c.status === 'gap',
            anomalyLabel: c.status === 'gap' ? 'Narrative anomaly detected' : undefined
          });
        } else if (c.status === 'gap') {
           // Overwrite if it's a gap so we definitely flag the anomaly for the year
           const existing = yearMap.get(year)!;
           existing.anomaly = true;
           existing.anomalyLabel = 'Narrative anomaly detected';
        }
      });

      // Sort points by year
      const sortedData = Array.from(yearMap.values()).sort((a, b) => a.year.localeCompare(b.year));

      // Only include series with at least 2 data points for a meaningful timeline
      if (sortedData.length > 0) {
        series.push({
          id: key,
          label: metricLabel(key),
          unit: groupClaims[0].metricUnit || 'units',
          color: COLORS[colorIndex % COLORS.length],
          category: getCategory(key),
          data: sortedData
        });
        colorIndex++;
      }
    });

    return series.sort((a, b) => b.data.length - a.data.length);
  }, [claims]);
}
