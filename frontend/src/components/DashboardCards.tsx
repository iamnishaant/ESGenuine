import { motion } from 'framer-motion';
import { AlertTriangle, CheckCircle, HelpCircle, FileSearch } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useClaims } from '@/hooks/useClaims';

interface StatCardProps {
  title: string;
  value: number;
  suffix?: string;
  icon: React.ReactNode;
  color: string;
  delay?: number;
}

const AnimatedCounter = ({ value, duration = 2000 }: { value: number; duration?: number }) => {
  const [count, setCount] = useState(0);

  useEffect(() => {
    let startTime: number;
    let animationFrameId: number;
    
    // Safety check - if value is 0, set immediately
    if (value === 0) {
       setCount(0);
       return;
    }

    const step = (timestamp: number) => {
      if (!startTime) startTime = timestamp;
      const progress = Math.min((timestamp - startTime) / duration, 1);
      setCount(Math.floor(progress * value));
      if (progress < 1) {
        animationFrameId = requestAnimationFrame(step);
      }
    };
    animationFrameId = requestAnimationFrame(step);
    
    return () => cancelAnimationFrame(animationFrameId);
  }, [value, duration]);

  return <span>{count}</span>;
};

const StatCard = ({ title, value, suffix = '', icon, color, delay = 0 }: StatCardProps) => {
  return (
    <motion.div
      className="glass-panel p-4 card-lift relative overflow-hidden"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay }}
    >
      <div className="flex items-start justify-between z-10 relative">
        <div className="space-y-2">
          <span className="text-xs text-muted-foreground uppercase tracking-wider">{title}</span>
          <div className="counter-value flex items-baseline gap-1">
            <AnimatedCounter value={value} />
            {suffix && <span className="text-lg">{suffix}</span>}
          </div>
        </div>
        <div 
          className="w-10 h-10 rounded-lg flex items-center justify-center"
          style={{ backgroundColor: `${color}20` }}
        >
          <div style={{ color }}>{icon}</div>
        </div>
      </div>
      
    </motion.div>
  );
};

export const DashboardCards = () => {
  const { claims } = useClaims();

  const verifiedCount = claims.filter(c => c.status === 'verified').length;
  const reviewCount = claims.filter(c => c.status === 'review').length;
  const gapCount = claims.filter(c => c.status === 'gap').length;

  const stats = [
    { 
      title: 'Claims Analyzed', 
      value: claims.length, 
      icon: <FileSearch className="w-5 h-5" />, 
      color: 'hsl(187, 94%, 50%)' 
    },
    { 
      title: 'Verified', 
      value: verifiedCount, 
      icon: <CheckCircle className="w-5 h-5" />, 
      color: 'hsl(142, 76%, 50%)' 
    },
    { 
      title: 'Under Review', 
      value: reviewCount, 
      icon: <HelpCircle className="w-5 h-5" />, 
      color: 'hsl(38, 92%, 50%)' 
    },
    { 
      title: 'Integrity Gaps', 
      value: gapCount, 
      icon: <AlertTriangle className="w-5 h-5" />, 
      color: 'hsl(0, 84%, 60%)' 
    },
  ];

  return (
    <motion.div 
      className="grid grid-cols-4 gap-4"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3 }}
    >
      {stats.map((stat, i) => (
        <StatCard key={stat.title} {...stat} delay={i * 0.1} />
      ))}
    </motion.div>
  );
};
