import { motion } from 'framer-motion';
import { useLocation, Link } from 'react-router-dom';
import { 
  Globe, 
  Search, 
  Satellite, 
  ClipboardList, 
  Building2, 
  ShieldCheck,
  Settings,
  ChevronLeft,
  ChevronRight,
  FilePlus
} from 'lucide-react';
import { useState } from 'react';
import { cn } from '@/lib/utils';

const navItems = [
  { 
    path: '/', 
    label: 'Live Dashboard', 
    icon: Globe,
    description: 'Real-time integrity monitoring'
  },
  { 
    path: '/claims', 
    label: 'Claim Explorer', 
    icon: Search,
    description: 'Filter and analyze claims'
  },
  { 
    path: '/evidence', 
    label: 'Evidence Analysis', 
    icon: Satellite,
    description: 'Satellite & sensor data'
  },
  { 
    path: '/audit-trail', 
    label: 'Audit Trail', 
    icon: ClipboardList,
    description: 'Decision logs & exports'
  },
  { 
    path: '/portfolio', 
    label: 'Portfolio Overview', 
    icon: Building2,
    description: 'Company-level summary'
  },
  { 
    path: '/transparency', 
    label: 'System Transparency', 
    icon: ShieldCheck,
    description: 'Model limitations & calibration'
  },
  { 
    path: '/submit-report', 
    label: 'Submit Report', 
    icon: FilePlus,
    description: 'Add new ESG claims'
  },
  { 
    path: '/settings',
    label: 'Settings', 
    icon: Settings,
    description: 'Configure your experience'
  },
];

export const AppSidebar = () => {
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);

  return (
    <motion.aside
      className={cn(
        "relative z-20 h-screen glass-panel border-r border-border/30 flex flex-col transition-all duration-300",
        collapsed ? "w-16" : "w-64"
      )}
      initial={{ x: -100, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      transition={{ duration: 0.5 }}
    >
      {/* Logo */}
      <div className={cn(
        "h-16 border-b border-border/30 flex items-center px-4 gap-3",
        collapsed && "justify-center"
      )}>
        <div className="relative flex-shrink-0">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary to-primary/60 flex items-center justify-center glow-primary">
            <Globe className="w-4 h-4 text-primary-foreground" />
          </div>
          <motion.div 
            className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-success"
            animate={{ scale: [1, 1.2, 1] }}
            transition={{ duration: 2, repeat: Infinity }}
          />
        </div>
        {!collapsed && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.1 }}
          >
            <span className="font-semibold text-sm text-foreground tracking-tight">
              PHAROS<span className="text-primary">-INTEGRITY</span>
            </span>
          </motion.div>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-4 px-2 space-y-1 overflow-y-auto">
        {navItems.map((item) => {
          const isActive = location.pathname === item.path;
          const Icon = item.icon;
          
          return (
            <Link
              key={item.path}
              to={item.path}
            >
              <motion.div
                className={cn(
                  "relative flex items-center gap-3 px-3 py-2.5 rounded-lg transition-all duration-200 group",
                  isActive 
                    ? "bg-primary/15 text-primary" 
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/50",
                  collapsed && "justify-center px-2"
                )}
                whileHover={{ x: collapsed ? 0 : 4 }}
                whileTap={{ scale: 0.98 }}
              >
                {/* Active indicator */}
                {isActive && (
                  <motion.div
                    className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-6 rounded-full bg-primary glow-primary"
                    layoutId="activeIndicator"
                  />
                )}
                
                <Icon className={cn(
                  "w-5 h-5 flex-shrink-0 transition-colors",
                  isActive && "text-primary"
                )} />
                
                {!collapsed && (
                  <div className="flex-1 min-w-0">
                    <span className={cn(
                      "text-sm font-medium block truncate",
                      isActive && "text-primary"
                    )}>
                      {item.label}
                    </span>
                    <span className="text-[10px] text-muted-foreground/70 truncate block">
                      {item.description}
                    </span>
                  </div>
                )}

                {/* Tooltip for collapsed state */}
                {collapsed && (
                  <div className="absolute left-full ml-2 px-2 py-1 rounded bg-popover border border-border text-xs text-foreground opacity-0 group-hover:opacity-100 pointer-events-none whitespace-nowrap z-50 transition-opacity">
                    {item.label}
                  </div>
                )}
              </motion.div>
            </Link>
          );
        })}
      </nav>

      {/* Collapse button */}
      <div className="p-2 border-t border-border/30">
        <motion.button
          onClick={() => setCollapsed(!collapsed)}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
        >
          {collapsed ? (
            <ChevronRight className="w-4 h-4" />
          ) : (
            <>
              <ChevronLeft className="w-4 h-4" />
              <span className="text-xs">Collapse</span>
            </>
          )}
        </motion.button>
      </div>
    </motion.aside>
  );
};
