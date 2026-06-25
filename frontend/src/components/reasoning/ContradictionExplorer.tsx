import React from 'react';
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Conflict } from '@/hooks/useClaims';

interface ExplorerProps {
  conflicts: Conflict[];
  onHover?: (c: Conflict) => void;
  onClick?: (c: Conflict) => void;
}

const ContradictionExplorer: React.FC<ExplorerProps> = ({ conflicts, onHover, onClick }) => {

  const getSeverityColor = (sev: string) => {
    switch(sev) {
      case 'Critical': return 'destructive';
      case 'High': return 'default';
      case 'Medium': return 'secondary';
      default: return 'outline';
    }
  };

  const getSeverityStyle = (sev: string) => {
    switch(sev) {
      case 'Critical': return 'bg-danger/5 border-danger/20';
      case 'High': return 'bg-warning/5 border-warning/20';
      case 'Medium': return 'bg-primary/5 border-primary/20';
      default: return 'bg-card border-border';
    }
  };

  if(!conflicts || conflicts.length === 0) {
    return (
      <Card className="h-full flex flex-col pt-8 items-center text-center text-muted-foreground shadow-sm border-dashed border-border/50 glass-panel">
        <div className="text-4xl mb-2 flex items-center justify-center opacity-80">🛡️</div>
        <p className="font-medium text-foreground">No Contradictions Detected</p>
        <p className="text-sm">The reasoning engine found zero conflicting claims.</p>
      </Card>
    );
  }

  return (
    <div className="flex flex-col gap-3 overflow-y-auto h-full pr-2">
      {conflicts.map((c, i) => (
        <Card 
          key={i} 
          className={`cursor-pointer transition-all hover:shadow-md border ${getSeverityStyle(c.severity)} relative glass-panel card-lift`}
          onMouseEnter={() => onHover && onHover(c)}
          onClick={() => onClick && onClick(c)}
        >
          {c.severity === 'Critical' && (
            <div className="absolute -top-2 -right-2 bg-red-500 text-white rounded-full p-1 animate-pulse shadow-sm">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>
            </div>
          )}

          <CardHeader className="p-3 pb-1 flex flex-row items-center justify-between space-y-0">
              <div className="flex gap-2 items-center">
                 <Badge variant={getSeverityColor(c.severity)}>
                   {c.severity}
                 </Badge>
                 <span className="text-xs font-medium text-muted-foreground">
                    Type: <span className="text-foreground/90">{c.conflict_type}</span>
                 </span>
             </div>
             <div className="text-xs text-muted-foreground/80 font-mono">
                Conf: {(c.confidence * 100).toFixed(0)}%
             </div>
          </CardHeader>
          <CardContent className="p-3 pt-2">
            
            <div className="bg-background/40 rounded p-2 text-sm text-foreground/80 mb-2 border border-border/30">
               <span className="font-semibold text-foreground block border-b border-border/30 pb-1 mb-1">Claim A (Page {c.claim_a_page})</span>
               "{c.claim_a_text}"
            </div>

            <div className="bg-danger/10 rounded p-2 text-sm text-foreground/80 mb-2 border border-danger/20">
               <span className="font-semibold text-foreground block border-b border-danger/20 pb-1 mb-1">
                 Claim B {c.claim_b_doc ? `(Report ${c.claim_b_doc})` : ''}
                </span>
               "{c.claim_b_text}"
            </div>

            <div className="text-xs font-mono bg-muted/50 text-success rounded p-2 mt-2 border border-success/20">
               &gt; Reasoning: {c.reasoning}
            </div>

          </CardContent>
        </Card>
      ))}
    </div>
  );
};

export default ContradictionExplorer;
