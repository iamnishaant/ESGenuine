import { motion } from 'framer-motion';
import { Shield, Settings, User, LogIn } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useEffect, useState } from 'react';
import { useBackendScores } from '@/hooks/useBackendScores';
import { getToken, me } from '@/lib/api';

// Connection state mirrors the SAME probe the scores use, so the light and the
// "—" placeholders on the pages below can never disagree. It used to be a
// hardcoded green dot with the word "Connected" next to it: it said Connected
// while the backend was down and every score on screen read "—".
const STATUS = {
  loading: { dot: 'bg-warning', label: 'Connecting…', title: 'Checking the audit backend' },
  up: { dot: 'bg-success', label: 'Connected', title: 'Audit backend reachable' },
  down: { dot: 'bg-danger', label: 'Backend offline', title: 'Audit backend unreachable — integrity scores unavailable' },
} as const;

export const Header = () => {
  const { availability } = useBackendScores();
  const status = STATUS[availability];

  // Who is actually signed in, rather than a decorative "Auditor" chip.
  const [email, setEmail] = useState<string | null>(null);
  useEffect(() => {
    if (!getToken()) { setEmail(null); return; }
    let cancelled = false;
    me()
      .then((u) => { if (!cancelled) setEmail(u.email); })
      .catch(() => { if (!cancelled) setEmail(null); });   // expired/invalid token
    return () => { cancelled = true; };
  }, []);

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
            className={`absolute -top-1 -right-1 w-3 h-3 rounded-full ${status.dot}`}
            animate={{ scale: [1, 1.2, 1] }}
            transition={{ duration: 2, repeat: Infinity }}
          />
        </div>
        <div>
          <h1 className="font-semibold text-foreground tracking-tight">
            ESG<span className="text-primary">enuine</span>
          </h1>
          <p className="text-[10px] text-muted-foreground uppercase tracking-widest">
            ESG Verification Platform
          </p>
        </div>
      </div>

      {/* Status indicator */}
      <div className="flex items-center gap-6">
        <div className="flex items-center gap-2" title={status.title}>
          <motion.div
            className={`w-2 h-2 rounded-full ${status.dot}`}
            animate={{ opacity: [0.5, 1, 0.5] }}
            transition={{ duration: 2, repeat: Infinity }}
          />
          <span className="text-xs text-muted-foreground">{status.label}</span>
        </div>
      </div>

      {/* Actions. The old notification bell had no handler and no notification
          system behind it, so it is gone rather than faked. */}
      <div className="flex items-center gap-2">
        <Link
          to="/settings"
          title="Settings"
          className="w-9 h-9 rounded-lg bg-muted/50 flex items-center justify-center hover:bg-muted transition-colors"
        >
          <Settings className="w-4 h-4 text-muted-foreground" />
        </Link>
        <div className="w-px h-6 bg-border mx-2" />
        <Link
          to="/integrity-audit"
          title={email ? `Signed in as ${email}` : 'Sign in on the Integrity Audit page'}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-muted/50 hover:bg-muted transition-colors max-w-[220px]"
        >
          <div className="w-7 h-7 rounded-full bg-gradient-to-br from-primary/80 to-primary flex items-center justify-center flex-shrink-0">
            {email ? <User className="w-4 h-4 text-primary-foreground" /> : <LogIn className="w-4 h-4 text-primary-foreground" />}
          </div>
          <span className="text-sm text-foreground truncate">{email ?? 'Sign in'}</span>
        </Link>
      </div>
    </motion.header>
  );
};
