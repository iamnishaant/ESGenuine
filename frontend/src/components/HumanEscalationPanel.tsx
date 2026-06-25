import { motion } from 'framer-motion';
import { UserCheck, FileText, Flag, HelpCircle, FileQuestion } from 'lucide-react';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { toast } from 'sonner';

interface HumanEscalationPanelProps {
  claimId: string;
  status: 'verified' | 'review' | 'gap';
}

export const HumanEscalationPanel = ({ claimId, status }: HumanEscalationPanelProps) => {
  // Only show for gap and review claims
  if (status === 'verified') return null;

  const handleAction = (action: string) => {
    toast.success(`Noted: ${action}`, {
      description: `Claim ${claimId.slice(0, 8)} — recorded for this review session.`,
    });
  };

  const actions = [
    {
      label: 'Request Source Review',
      icon: FileText,
      description: 'Re-check the original report passage',
    },
    {
      label: 'Request Manual Audit',
      icon: UserCheck,
      description: 'Assign to a human reviewer',
    },
    {
      label: 'Flag for Regulatory Review',
      icon: Flag,
      description: 'Escalate to compliance team',
    },
    {
      label: 'Mark as Inconclusive',
      icon: FileQuestion,
      description: 'Insufficient evidence to determine',
    },
  ];

  return (
    <motion.div
      className="glass-panel p-4 space-y-4"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.4 }}
    >
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-foreground flex items-center gap-2">
          <UserCheck className="w-4 h-4 text-warning" />
          Analyst Review Actions
        </h3>
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <button className="text-muted-foreground hover:text-foreground transition-colors">
                <HelpCircle className="w-4 h-4" />
              </button>
            </TooltipTrigger>
            <TooltipContent side="left" className="max-w-[220px]">
              <p className="text-xs">
                Final determination requires qualified human review. These actions are session-only for now.
              </p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>

      <div className="grid grid-cols-2 gap-2">
        {actions.map((action) => (
          <motion.button
            key={action.label}
            onClick={() => handleAction(action.label)}
            className="flex flex-col items-start gap-1.5 p-3 rounded-lg bg-muted/30 border border-border/50 hover:border-primary/50 hover:bg-muted/50 transition-all text-left group"
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
          >
            <action.icon className="w-4 h-4 text-muted-foreground group-hover:text-primary transition-colors" />
            <span className="text-xs font-medium text-foreground">{action.label}</span>
            <span className="text-[10px] text-muted-foreground leading-tight">{action.description}</span>
          </motion.button>
        ))}
      </div>

      <p className="text-[10px] text-muted-foreground/70 italic text-center pt-2 border-t border-border/30">
        Analyst actions are session-only and are not yet persisted to a workflow backend.
      </p>
    </motion.div>
  );
};
