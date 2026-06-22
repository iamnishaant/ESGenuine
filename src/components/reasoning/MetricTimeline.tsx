import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, Area, AreaChart
} from 'recharts';
import { cn } from '@/lib/utils';
import { TrendingDown, TrendingUp, AlertTriangle, Minus, Loader2 } from 'lucide-react';
import { useClaims } from '@/hooks/useClaims';
import { useMetricTimeline, MetricPoint, MetricSeries } from '@/hooks/useMetricTimeline';

interface MetricTimelineProps {
  title?: string;
}

// ─────────────────────────────────────────────
// Custom Tooltip
// ─────────────────────────────────────────────
const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;

  const point = payload[0]?.payload as MetricPoint;
  const meta = payload[0];

  return (
    <div className="glass-panel border border-border/50 rounded-xl px-4 py-3 shadow-2xl min-w-[180px]">
      <p className="text-xs text-muted-foreground mb-1">FY{label}</p>
      <p className="text-base font-bold text-foreground">
        {meta.value?.toLocaleString()}{' '}
        <span className="text-xs font-normal text-muted-foreground">{meta.name}</span>
      </p>
      {point?.anomaly && (
        <div className="mt-2 flex items-start gap-1.5 text-warning bg-warning/10 border border-warning/20 rounded-lg px-2 py-1.5">
          <AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" />
          <p className="text-[10px] leading-tight">{point.anomalyLabel}</p>
        </div>
      )}
    </div>
  );
};

// ─────────────────────────────────────────────
// Trend indicator helper
// ─────────────────────────────────────────────
const getTrend = (data: MetricPoint[]) => {
  if (data.length < 2) return null;
  const first = data[0].value;
  const last = data[data.length - 1].value;
  if (first === 0) return null; // Avoid division by zero
  const pct = ((last - first) / first * 100).toFixed(1);
  return { pct: parseFloat(pct), isDown: last < first };
};

// ─────────────────────────────────────────────
// Main Component
// ─────────────────────────────────────────────
const MetricTimeline = ({ title = "ESG Metric Trends" }: MetricTimelineProps) => {
  const { claims, loading } = useClaims();
  const metrics = useMetricTimeline(claims);

  const [activeSeries, setActiveSeries] = useState<string>('');
  const [activeCategory, setActiveCategory] = useState<string>('all');

  const categories = [
    { id: 'all', label: 'All' },
    { id: 'environment', label: 'Environment' },
    { id: 'social', label: 'Social' },
    { id: 'governance', label: 'Governance' },
  ];

  const filteredMetrics = activeCategory === 'all'
    ? metrics
    : metrics.filter(m => m.category === activeCategory);

  const current = filteredMetrics.find(m => m.id === activeSeries) || filteredMetrics[0];

  // Set the first metric as active by default if none is selected
  useEffect(() => {
    if (metrics.length > 0 && !activeSeries) {
      setActiveSeries(metrics[0].id);
    }
  }, [metrics, activeSeries]);

  if (loading) {
     return (
      <motion.div
        className="glass-panel border border-border/30 rounded-2xl overflow-hidden h-[380px] flex items-center justify-center"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
      >
        <Loader2 className="w-8 h-8 text-primary animate-spin" />
      </motion.div>
     );
  }

  if (!metrics || metrics.length === 0) {
     return (
      <motion.div
        className="glass-panel border border-border/30 rounded-2xl overflow-hidden h-[380px] flex flex-col items-center justify-center text-muted-foreground"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
      >
        <AlertTriangle className="w-8 h-8 mb-4 opacity-50" />
        <p>No quantitative metric timelines found in database.</p>
        <p className="text-xs max-w-sm text-center mt-2">Metrics require numerical extractions mapped across multiple report years.</p>
      </motion.div>
     );
  }

  const anomalyYears = current?.data.filter(d => d.anomaly).map(d => d.year) || [];
  const trend = current ? getTrend(current.data) : null;

  return (
    <motion.div
      className="glass-panel border border-border/30 rounded-2xl overflow-hidden h-full flex flex-col"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-5 pt-5 pb-3 border-b border-border/20">
        <div>
          <h3 className="text-sm font-bold text-foreground tracking-wide">{title}</h3>
          <p className="text-xs text-muted-foreground mt-0.5">Cross-report ESG metric history with anomaly detection</p>
        </div>

        {/* Category filter */}
        <div className="flex gap-1 bg-background/50 rounded-lg p-0.5 border border-border/30">
          {categories.map(cat => (
            <button
              key={cat.id}
              onClick={() => {
                setActiveCategory(cat.id);
                const first = (cat.id === 'all' ? metrics : metrics.filter(m => m.category === cat.id))[0];
                if (first) setActiveSeries(first.id);
              }}
              className={cn(
                "text-[10px] font-medium px-2.5 py-1 rounded-md transition-all",
                activeCategory === cat.id
                  ? "bg-primary/20 text-primary"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              {cat.label}
            </button>
          ))}
        </div>
      </div>

      {/* Series selector + trend badge */}
      <div className="flex items-center gap-3 px-5 py-2.5 flex-wrap border-b border-border/10">
        {filteredMetrics.map(m => (
          <button
            key={m.id}
            onClick={() => setActiveSeries(m.id)}
            className={cn(
              "flex items-center gap-1.5 text-xs px-3 py-1 rounded-full border transition-all",
              activeSeries === m.id
                ? "border-transparent text-foreground font-semibold shadow-md"
                : "border-border/30 text-muted-foreground hover:text-foreground"
            )}
            style={activeSeries === m.id ? { background: m.color + '25', borderColor: m.color + '60', color: m.color } : {}}
          >
            <span className="w-2 h-2 rounded-full" style={{ background: m.color }} />
            {m.label}
          </button>
        ))}

        {trend && (
          <div className={cn(
            "ml-auto flex items-center gap-1.5 text-xs font-semibold px-3 py-1 rounded-full border",
            trend.isDown
              ? "text-success bg-success/10 border-success/20"
              : "text-danger bg-danger/10 border-danger/20"
          )}>
            {trend.isDown ? <TrendingDown className="w-3.5 h-3.5" /> : <TrendingUp className="w-3.5 h-3.5" />}
            {Math.abs(trend.pct)}% since {current?.data[0].year}
          </div>
        )}
      </div>

      {/* Chart */}
      <div className="flex-1 p-4 min-h-0">
        {current && (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={current.data} margin={{ top: 6, right: 12, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id={`grad-${current.id}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={current.color} stopOpacity={0.25} />
                  <stop offset="95%" stopColor={current.color} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
              <XAxis
                dataKey="year"
                tick={{ fill: '#64748b', fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                tickFormatter={y => `FY${y}`}
              />
              <YAxis
                tick={{ fill: '#64748b', fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                tickFormatter={v => v >= 1000 ? `${(v/1000).toFixed(0)}k` : String(v)}
                width={42}
              />
              <Tooltip content={<CustomTooltip />} />

              {/* Anomaly reference lines */}
              {anomalyYears.map(yr => (
                <ReferenceLine
                  key={yr}
                  x={yr}
                  stroke="#f59e0b"
                  strokeDasharray="4 4"
                  strokeWidth={1.5}
                  label={{ value: '⚠', position: 'top', fill: '#f59e0b', fontSize: 12 }}
                />
              ))}

              <Area
                type="monotone"
                dataKey="value"
                name={current.unit}
                stroke={current.color}
                strokeWidth={2.5}
                fill={`url(#grad-${current.id})`}
                dot={(props: any) => {
                  const { cx, cy, payload } = props;
                  const isAnomaly = payload.anomaly;
                  return (
                    <circle
                      key={`dot-${payload.year}`}
                      cx={cx}
                      cy={cy}
                      r={isAnomaly ? 6 : 4}
                      fill={isAnomaly ? '#f59e0b' : current.color}
                      stroke={isAnomaly ? '#f59e0b40' : current.color + '40'}
                      strokeWidth={isAnomaly ? 4 : 3}
                    />
                  );
                }}
                activeDot={{ r: 7, strokeWidth: 0 }}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Anomaly legend */}
      {anomalyYears.length > 0 && (
        <div className="px-5 pb-3 flex items-center gap-2 text-[10px] text-warning/80">
          <AlertTriangle className="w-3 h-3 text-warning" />
          <span>{anomalyYears.length} narrative anomaly detected — hover the yellow data point for details</span>
        </div>
      )}
    </motion.div>
  );
};

export default MetricTimeline;
