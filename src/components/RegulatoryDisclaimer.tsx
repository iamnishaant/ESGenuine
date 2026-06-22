import { motion } from 'framer-motion';
import { Shield } from 'lucide-react';

export const RegulatoryDisclaimer = () => {
  return (
    <motion.footer 
      className="px-6 py-3 border-t border-border/30 glass-panel"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ delay: 0.5 }}
    >
      <div className="flex items-start gap-2.5 max-w-5xl mx-auto">
        <Shield className="w-4 h-4 text-muted-foreground flex-shrink-0 mt-0.5" />
        <p className="text-[11px] text-muted-foreground/80 leading-relaxed">
          <span className="text-muted-foreground font-medium">Epistemic Disclaimer:</span>{' '}
          This system evaluates internal consistency, verifiability, and alignment with publicly available evidence. 
          It does not determine legal, factual, or regulatory truth. All outputs are decision-support signals subject to human validation.
        </p>
      </div>
    </motion.footer>
  );
};
