import { motion } from 'framer-motion';
import { Shield, Radio, Settings, Bell, User } from 'lucide-react';

export const Header = () => {
  return (
    <motion.header 
      className="h-16 border-b border-border/50 glass-panel flex items-center justify-between px-6"
      initial={{ opacity: 0, y: -20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
    >
      {/* Logo */}
      <div className="flex items-center gap-3">
        <div className="relative">
          <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-primary to-primary/60 flex items-center justify-center glow-primary">
            <Shield className="w-5 h-5 text-primary-foreground" />
          </div>
          <motion.div 
            className="absolute -top-1 -right-1 w-3 h-3 rounded-full bg-success"
            animate={{ scale: [1, 1.2, 1] }}
            transition={{ duration: 2, repeat: Infinity }}
          />
        </div>
        <div>
          <h1 className="font-semibold text-foreground tracking-tight">
            PHAROS<span className="text-primary">-INTEGRITY</span>
          </h1>
          <p className="text-[10px] text-muted-foreground uppercase tracking-widest">
            ESG Verification Platform
          </p>
        </div>
      </div>

      {/* Status indicator */}
      <div className="flex items-center gap-6">
        <div className="flex items-center gap-2">
          <motion.div 
            className="w-2 h-2 rounded-full bg-success"
            animate={{ opacity: [0.5, 1, 0.5] }}
            transition={{ duration: 2, repeat: Infinity }}
          />
          <span className="text-xs text-muted-foreground">Live Analysis</span>
        </div>
        
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-muted/50 border border-border/50">
          <Radio className="w-3.5 h-3.5 text-primary animate-pulse" />
          <span className="text-xs font-mono text-foreground">3 Active Scans</span>
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2">
        <motion.button 
          className="w-9 h-9 rounded-lg bg-muted/50 flex items-center justify-center hover:bg-muted transition-colors"
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
        >
          <Bell className="w-4 h-4 text-muted-foreground" />
        </motion.button>
        <motion.button 
          className="w-9 h-9 rounded-lg bg-muted/50 flex items-center justify-center hover:bg-muted transition-colors"
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}
        >
          <Settings className="w-4 h-4 text-muted-foreground" />
        </motion.button>
        <div className="w-px h-6 bg-border mx-2" />
        <motion.button 
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-muted/50 hover:bg-muted transition-colors"
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
        >
          <div className="w-7 h-7 rounded-full bg-gradient-to-br from-primary/80 to-primary flex items-center justify-center">
            <User className="w-4 h-4 text-primary-foreground" />
          </div>
          <span className="text-sm text-foreground">Auditor</span>
        </motion.button>
      </div>
    </motion.header>
  );
};
