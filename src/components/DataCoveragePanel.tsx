import { motion } from 'framer-motion';
import { Cloud, CalendarX, Maximize2, Layers, Activity, HelpCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

interface DataCoverageMetric {
  label: string;
  value: string | number;
  unit?: string;
  level: 'good' | 'warning' | 'poor';
  icon: React.ElementType;
  tooltip: string;
}

const metrics: DataCoverageMetric[] = [
  {
    label: 'Cloud Coverage',
    value: 12,
    unit: '%',
    level: 'good',
    icon: Cloud,
    tooltip: 'Percentage of observation area obscured by cloud cover',
  },
  {
    label: 'Temporal Gaps',
    value: 2,
    unit: 'months missing',
    level: 'warning',
    icon: CalendarX,
    tooltip: 'Number of months with insufficient satellite observations',
  },
  {
    label: 'Spatial Resolution',
    value: 10,
    unit: 'm/pixel',
    level: 'good',
    icon: Maximize2,
    tooltip: 'Ground sampling distance of primary observation data',
  },
  {
    label: 'Modality Used',
    value: 'Optical + SAR Fused',
    level: 'good',
    icon: Layers,
    tooltip: 'Satellite sensor types combined for analysis',
  },
  {
    label: 'Confidence Level',
    value: 'Medium',
    level: 'warning',
    icon: Activity,
    tooltip: 'Overall confidence in data sufficiency for verification',
  },
];

const levelColors = {
  good: 'text-success',
  warning: 'text-warning',
  poor: 'text-danger',
};

const levelBgColors = {
  good: 'bg-success',
  warning: 'bg-warning',
  poor: 'bg-danger',
};

export const DataCoveragePanel = () => {
  return (
    <motion.div
      className="glass-panel p-4 space-y-4"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.35 }}
    >
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-foreground flex items-center gap-2">
          <Activity className="w-4 h-4 text-primary" />
          Data Coverage & Uncertainty
        </h3>
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <button className="text-muted-foreground hover:text-foreground transition-colors">
                <HelpCircle className="w-4 h-4" />
              </button>
            </TooltipTrigger>
            <TooltipContent side="left" className="max-w-[240px]">
              <p className="text-xs">
                Metrics describing data availability and quality. Higher coverage and resolution improve verification confidence.
              </p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>

      <div className="space-y-3">
        {metrics.map((metric, index) => (
          <TooltipProvider key={metric.label}>
            <Tooltip>
              <TooltipTrigger asChild>
                <motion.div
                  className="flex items-center justify-between text-sm cursor-help group"
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.4 + index * 0.05 }}
                >
                  <span className="text-muted-foreground flex items-center gap-1.5 group-hover:text-foreground transition-colors">
                    <metric.icon className="w-3.5 h-3.5" />
                    {metric.label}
                  </span>
                  <div className="flex items-center gap-2">
                    <span className={cn("font-mono text-xs", levelColors[metric.level])}>
                      {metric.value}{metric.unit ? ` ${metric.unit}` : ''}
                    </span>
                    <div className={cn(
                      "w-2 h-2 rounded-full animate-pulse",
                      levelBgColors[metric.level]
                    )} />
                  </div>
                </motion.div>
              </TooltipTrigger>
              <TooltipContent side="left">
                <p className="text-xs max-w-[200px]">{metric.tooltip}</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        ))}
      </div>

      {/* Progress bars for key metrics */}
      <div className="space-y-2 pt-3 border-t border-border/30">
        <div className="space-y-1.5">
          <div className="flex justify-between text-xs">
            <span className="text-muted-foreground">Data Completeness</span>
            <span className="text-warning font-mono">78%</span>
          </div>
          <div className="h-1.5 rounded-full bg-muted overflow-hidden">
            <motion.div
              className="h-full rounded-full bg-warning"
              initial={{ width: 0 }}
              animate={{ width: '78%' }}
              transition={{ duration: 0.8, delay: 0.5 }}
            />
          </div>
        </div>
        <div className="space-y-1.5">
          <div className="flex justify-between text-xs">
            <span className="text-muted-foreground">Observation Quality</span>
            <span className="text-success font-mono">89%</span>
          </div>
          <div className="h-1.5 rounded-full bg-muted overflow-hidden">
            <motion.div
              className="h-full rounded-full bg-success"
              initial={{ width: 0 }}
              animate={{ width: '89%' }}
              transition={{ duration: 0.8, delay: 0.6 }}
            />
          </div>
        </div>
      </div>

      {/* Footer note */}
      <p className="text-[10px] text-muted-foreground/70 italic pt-2 border-t border-border/30">
        Absence of observable change is treated as uncertainty, not negative evidence.
      </p>
    </motion.div>
  );
};
