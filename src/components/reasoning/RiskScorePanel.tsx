import React from 'react';
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { PieChart, Pie, Cell, ResponsiveContainer } from 'recharts';

interface RiskData {
  greenwashing_risk: number;
  status: string;
  vague_claims: number;
  narrative_claims: number;
  missing_metrics: number;
  contradictions: number;
  high_severity: number;
}

const RiskScorePanel: React.FC<{ data: RiskData | null }> = ({ data }) => {
  if (!data) return <Card className="h-full animate-pulse glass-panel" /> ;

  const score = Math.round(data.greenwashing_risk * 100);
  
  // Gauge Data Setup
  const chartData = [
    { name: 'Score', value: score },
    { name: 'Remainder', value: 100 - score }
  ];

  let color = '#22c55e'; // Green
  if (score > 60) color = '#ef4444'; // Red
  else if (score > 30) color = '#f59e0b'; // Amber

  return (
    <Card className="h-full glass-panel flex flex-col md:flex-row items-center overflow-hidden border-border/30">
        
       {/* Left side: The Gauge */}
       <div className="w-full md:w-1/3 h-48 relative flex items-center justify-center p-4 bg-background/30 border-r border-border/30">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={chartData}
                cx="50%"
                cy="75%"
                startAngle={180}
                endAngle={0}
                innerRadius={60}
                outerRadius={80}
                paddingAngle={0}
                dataKey="value"
                stroke="none"
              >
                <Cell key="cell-0" fill={color} />
                <Cell key="cell-1" fill="#e2e8f0" />
              </Pie>
            </PieChart>
          </ResponsiveContainer>
          
          <div className="absolute flex flex-col items-center justify-center mt-8">
             <span className="text-4xl font-bold text-foreground tracking-tighter">{score}%</span>
             <span className="text-xs uppercase font-semibold text-muted-foreground tracking-wider mt-1">{data.status}</span>
          </div>
       </div>

       {/* Right side: The Breakdown */}
       <div className="w-full md:w-2/3 p-6">
           <CardTitle className="text-lg text-foreground mb-1">Company ESG Credibility Score</CardTitle>
           <p className="text-sm text-muted-foreground mb-4 pb-4 border-b border-border/30">
              Calculated dynamically via Ontology Mapping, Semantic Searching, and Natural Language Inference reasoning over all extracted claims.
           </p>

           <div className="grid grid-cols-2 gap-4">
              
              <div className="flex items-center gap-3">
                 <div className="w-10 h-10 rounded-full flex items-center justify-center text-danger bg-danger/10 text-lg font-bold border border-danger/20 shadow-sm">
                    {data.contradictions}
                 </div>
                 <div>
                    <div className="text-sm font-semibold text-foreground/90">Contradictions</div>
                    <div className="text-xs text-muted-foreground">{data.high_severity} critical/high</div>
                 </div>
              </div>

              <div className="flex items-center gap-3">
                 <div className="w-10 h-10 rounded-full flex items-center justify-center text-warning bg-warning/10 text-lg font-bold border border-warning/20 shadow-sm">
                    {data.vague_claims}
                 </div>
                 <div>
                    <div className="text-sm font-semibold text-foreground/90">Vague Claims</div>
                    <div className="text-xs text-muted-foreground">Missing strict thresholds</div>
                 </div>
              </div>

              <div className="flex items-center gap-3">
                 <div className="w-10 h-10 rounded-full flex items-center justify-center text-primary bg-primary/10 text-lg font-bold border border-primary/20 shadow-sm">
                    {data.narrative_claims}
                 </div>
                 <div>
                    <div className="text-sm font-semibold text-foreground/90">Narrative Only</div>
                    <div className="text-xs text-muted-foreground">Unmeasurable commitments</div>
                 </div>
              </div>

              <div className="flex items-center gap-3">
                 <div className="w-10 h-10 rounded-full flex items-center justify-center text-primary bg-primary/10 text-lg font-bold border border-primary/20 shadow-sm">
                    {data.missing_metrics}
                 </div>
                 <div>
                    <div className="text-sm font-semibold text-foreground/90">Missing Metrics</div>
                    <div className="text-xs text-muted-foreground">No numeric backing</div>
                 </div>
              </div>

           </div>
       </div>

    </Card>
  );
};

export default RiskScorePanel;
