import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Search, 
  ChevronDown, 
  MapPin, 
  Calendar,
  AlertTriangle,
  CheckCircle2,
  Clock,
  ArrowUpDown,
  LayoutDashboard,
  ListFilter
} from 'lucide-react';
import { AppLayout } from '@/components/AppLayout';
import { cn } from '@/lib/utils';
import { Link } from 'react-router-dom';
import { supabase } from '@/lib/supabase';
import { Claim, Conflict, mapDbToClaim } from '@/hooks/useClaims';
import { metricLabel } from '@/lib/metricLabels';

import ClaimGraph from '@/components/reasoning/ClaimGraph';
import ContradictionExplorer from '@/components/reasoning/ContradictionExplorer';
import RiskScorePanel from '@/components/reasoning/RiskScorePanel';
import MetricTimeline from '@/components/reasoning/MetricTimeline';

// -----------------------------
// TYPES & MAPPING
// -----------------------------
// Claim, Conflict, and mapDbToClaim are shared from '@/hooks/useClaims'
// (single source of truth — see import above).

const statusConfig = {
  verified: { label: 'Verified', icon: CheckCircle2, class: 'text-success bg-success/10 border-success/20' },
  review: { label: 'Under Review', icon: Clock, class: 'text-warning bg-warning/10 border-warning/20' },
  gap: { label: 'Integrity Gap', icon: AlertTriangle, class: 'text-danger bg-danger/10 border-danger/20' },
};

const ClaimExplorer = () => {
  const [claims, setClaims] = useState<Claim[]>([]);
  const [conflicts, setConflicts] = useState<Conflict[]>([]);
  const [loading, setLoading] = useState(true);
  const [viewMode, setViewMode] = useState<'list' | 'dashboard'>('list');
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [sortField, setSortField] = useState<keyof Claim>('date');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc');
  const [activeNode, setActiveNode] = useState<any>(null);
  const [highlightedClaims, setHighlightedClaims] = useState<string[]>([]);

  // 1. Fetch Data
  useEffect(() => {
    async function fetchData() {
      setLoading(true);
      try {
        const { data: claimsData, error: claimsError } = await supabase
          .from('claims')
          .select('*')
          .order('groundability_score', { ascending: false });

        if (claimsError) throw claimsError;
        
        const { data: conflictsData } = await supabase
          .from('contradictions')
          .select('*');

        if (claimsData) {
          const mappedClaims = claimsData.map(mapDbToClaim);
          setClaims(mappedClaims);
          
          if (conflictsData) {
            setConflicts(conflictsData.map(c => {
              const claimA = mappedClaims.find(cl => cl.id === c.claim_a_id);
              const claimB = mappedClaims.find(cl => cl.id === c.claim_b_id);
              return {
                ...c,
                claim_a_text: claimA?.claim || "Referenced Claim A",
                claim_b_text: claimB?.claim || "Referenced Claim B",
                claim_a_page: (claimA as any)?.page || 0,
                claim_b_doc: (claimB as any)?.company || "Target"
              };
            }));
          }
        }
      } catch (err) {
        console.error('Error fetching data:', err);
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

  // 2. Computed Risk Metrics
  const riskData = {
    greenwashing_risk: claims.length > 0 ? (claims.filter(c => c.status === 'gap').length / claims.length) * 0.8 + (claims.filter(c => c.status === 'review').length / claims.length) * 0.2 : 0,
    status: claims.filter(c => c.status === 'gap').length > (claims.length * 0.1) ? "High Risk" : "Moderate Risk",
    vague_claims: claims.filter(c => c.status === 'review').length,
    narrative_claims: claims.filter(c => c.verifiabilityClass === 'Narrative').length,
    missing_metrics: claims.filter(c => c.confidence < 30).length,
    contradictions: conflicts.length,
    high_severity: conflicts.filter(c => c.severity === 'Critical' || c.severity === 'High').length
  };

  // 3. Graph Data
  const graphData = {
    nodes: claims.slice(0, 20).map(c => ({
      id: c.id,
      label: c.claim.substring(0, 35) + '...',
      group: c.status === 'verified' ? 1 : c.status === 'review' ? 2 : 3,
      val: 15 + (c.confidence / 10),
      details: {
        page: c.page,
        metric: c.metricKey ? metricLabel(c.metricKey) : undefined,
        value: c.metricValue,
        year: c.dateKnown ? c.date.substring(0, 4) : c.reportYear ? String(c.reportYear) : undefined,
        text: c.claim,
      },
    })),
    links: conflicts.map(c => ({
      source: c.claim_a_id,
      target: c.claim_b_id,
      type: 'contradiction',
      severity: c.severity
    }))
  };

  // Clear specific highlights if the user begins searching manually
  useEffect(() => {
    if (searchQuery || statusFilter !== 'all') {
      setHighlightedClaims([]);
    }
  }, [searchQuery, statusFilter]);

  const handleConflictClick = (conflict: any) => {
    setViewMode('list');
    setSearchQuery('');
    setStatusFilter('all');
    setHighlightedClaims([conflict.claim_a_id, conflict.claim_b_id]);
  };

  const getConfidenceLevel = (score: number) => {
    if (score >= 80) return { label: 'High', class: 'text-success bg-success/10 border-success/20' };
    if (score >= 50) return { label: 'Medium', class: 'text-warning bg-warning/10 border-warning/20' };
    return { label: 'Low', class: 'text-danger bg-danger/10 border-danger/20' };
  };

  const filteredClaims = claims
    .filter(claim => {
      if (highlightedClaims.length > 0) {
        return highlightedClaims.includes(claim.id);
      }
      const matchesSearch = claim.company.toLowerCase().includes(searchQuery.toLowerCase()) ||
                           claim.claim.toLowerCase().includes(searchQuery.toLowerCase()) ||
                           claim.location.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesStatus = statusFilter === 'all' || claim.status === statusFilter;
      return matchesSearch && matchesStatus;
    })
    .sort((a, b) => {
      const aVal = a[sortField];
      const bVal = b[sortField];
      const direction = sortDirection === 'asc' ? 1 : -1;
      return aVal > bVal ? direction : -direction;
    });

  const handleSort = (field: keyof Claim) => {
    if (sortField === field) {
      setSortDirection(prev => prev === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('desc');
    }
  };
  return (
    <AppLayout>
      {/* Header */}
      <motion.header 
        className="h-[72px] border-b border-border/30 glass-panel flex items-center justify-between px-6 shrink-0"
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <div>
          <h1 className="text-xl font-bold text-foreground text-glow-primary tracking-tight">Claim Directory</h1>
          <p className="text-xs text-muted-foreground mt-0.5">Filter, search, and analyze ESG claims across your portfolio</p>
        </div>
        
        {/* Toggle Switch */}
        <div className="flex bg-background/50 border border-border/50 rounded-lg p-1 backdrop-blur-md">
          <button
            onClick={() => setViewMode('list')}
            className={cn(
              "flex items-center gap-2 px-4 py-1.5 rounded-md text-sm font-medium transition-all duration-200",
              viewMode === 'list' ? "bg-primary/20 text-primary shadow-[0_0_15px_rgba(6,182,212,0.3)]" : "text-muted-foreground hover:text-foreground hover:bg-white/5"
            )}
          >
            <ListFilter className="w-4 h-4" /> List View
          </button>
          <button
            onClick={() => setViewMode('dashboard')}
            className={cn(
              "flex items-center gap-2 px-4 py-1.5 rounded-md text-sm font-medium transition-all duration-200",
              viewMode === 'dashboard' ? "bg-primary/20 text-primary shadow-[0_0_15px_rgba(6,182,212,0.3)]" : "text-muted-foreground hover:text-foreground hover:bg-white/5"
            )}
          >
            <LayoutDashboard className="w-4 h-4" /> Risk Dashboard
          </button>
        </div>
      </motion.header>

      {/* Main Content Area */}
      <div className="flex-1 overflow-auto bg-transparent relative">
        <AnimatePresence mode="wait">
          
          {/* ========================================================= */}
          {/* LIST VIEW (The Original Layout) */}
          {/* ========================================================= */}
          {viewMode === 'list' && (
            <motion.div 
              key="list"
              className="p-6 h-full flex flex-col"
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 20 }}
              transition={{ duration: 0.2 }}
            >
              {/* Controls */}
              <div className="flex flex-col md:flex-row gap-4 mb-6">
                <div className="relative flex-1">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground w-4 h-4" />
                  <input 
                    type="text" 
                    placeholder="Search claims, companies, or locations..." 
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="w-full bg-background/50 border border-border/50 text-foreground text-sm rounded-lg pl-10 pr-4 py-2.5 focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary transition-all glass-panel"
                  />
                </div>
                <div className="flex gap-3">
                  <select 
                    value={statusFilter}
                    onChange={(e) => setStatusFilter(e.target.value)}
                    className="bg-background/50 border border-border/50 text-foreground text-sm rounded-lg px-4 py-2.5 focus:outline-none focus:ring-1 focus:ring-primary appearance-none glass-panel"
                  >
                    <option value="all">All Statuses</option>
                    <option value="verified">Verified</option>
                    <option value="review">Under Review</option>
                    <option value="gap">Integrity Gap</option>
                  </select>
                </div>
              </div>

              {/* Active Filters / Highlights Indicator */}
              {highlightedClaims.length > 0 && (
                 <div className="mb-4 flex items-center gap-3 bg-primary/10 border border-primary/20 text-primary px-4 py-2 rounded-lg text-sm">
                    <AlertTriangle className="w-4 h-4" />
                    Viewing {highlightedClaims.length} Claims from specific Contradiction.
                    <button onClick={() => setHighlightedClaims([])} className="ml-auto underline font-medium hover:text-primary/80">Clear View</button>
                 </div>
              )}

              {/* Table */}
              <div className="flex-1 glass-panel border border-border/30 rounded-xl overflow-hidden shadow-2xl flex flex-col">
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm whitespace-nowrap">
                    <thead className="text-xs uppercase bg-secondary/30 text-muted-foreground border-b border-border/30 sticky top-0 backdrop-blur-md z-10">
                      <tr>
                        <th className="px-6 py-4 cursor-pointer hover:text-primary transition-colors" onClick={() => handleSort('id')}>
                          <div className="flex items-center gap-1">Claim ID <ArrowUpDown className="w-3 h-3" /></div>
                        </th>
                        <th className="px-6 py-4 cursor-pointer hover:text-primary transition-colors" onClick={() => handleSort('claim')}>
                          <div className="flex items-center gap-1">Extracted Claim <ArrowUpDown className="w-3 h-3" /></div>
                        </th>
                        <th className="px-6 py-4 cursor-pointer hover:text-primary transition-colors" onClick={() => handleSort('status')}>
                          <div className="flex items-center gap-1">Verification <ArrowUpDown className="w-3 h-3" /></div>
                        </th>
                        <th className="px-6 py-4 cursor-pointer hover:text-primary transition-colors" onClick={() => handleSort('confidence')}>
                          <div className="flex items-center gap-1">Confidence <ArrowUpDown className="w-3 h-3" /></div>
                        </th>
                        <th className="px-6 py-4 cursor-pointer hover:text-primary transition-colors" onClick={() => handleSort('date')}>
                          <div className="flex items-center gap-1">Date <ArrowUpDown className="w-3 h-3" /></div>
                        </th>
                        <th className="px-6 py-4 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/20">
                      {filteredClaims.map((claim) => {
                        const StatusIcon = statusConfig[claim.status].icon;
                        return (
                          <tr key={claim.id} className="hover:bg-white/[0.02] transition-colors group">
                            <td className="px-6 py-4 font-mono text-xs text-muted-foreground">{claim.id}</td>
                            <td className="px-6 py-4">
                              <div className="font-medium text-foreground tracking-wide max-w-md truncate">{claim.claim}</div>
                              <div className="text-xs text-muted-foreground flex items-center gap-2 mt-1">
                                <span className="flex items-center gap-1"><MapPin className="w-3 h-3" /> {claim.location}</span>
                                <span>•</span>
                                <span>{claim.company}</span>
                              </div>
                            </td>
                            <td className="px-6 py-4">
                              <span className={cn("inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border", statusConfig[claim.status].class)}>
                                <StatusIcon className="w-3.5 h-3.5" />
                                {statusConfig[claim.status].label}
                              </span>
                            </td>
                            <td className="px-6 py-4">
                              <div className="flex items-center gap-3">
                                
                                <div className="flex-1 w-16 h-1.5 bg-background rounded-full overflow-hidden border border-border/50">
                                  <div 
                                    className={cn("h-full rounded-full transition-all duration-1000", claim.confidence >= 80 ? "bg-success glow-success" : claim.confidence >= 50 ? "bg-warning glow-warning" : "bg-danger glow-danger")}
                                    style={{ width: `${claim.confidence}%` }}
                                  />
                                </div>
                                <div className="flex items-center gap-2">
                                  <span className="text-xs font-mono w-7">{claim.confidence}%</span>
                                  <span className={cn("text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded border", getConfidenceLevel(claim.confidence).class)}>
                                    {getConfidenceLevel(claim.confidence).label}
                                  </span>
                                </div>
                              </div>
                            </td>
                            <td className="px-6 py-4">
                              <div className="flex items-center gap-1.5 text-muted-foreground">
                                <Calendar className="w-3.5 h-3.5" />
                                {claim.date}
                              </div>
                            </td>
                            <td className="px-6 py-4 text-right">
                              <Link to={`/claims/${claim.id}`} className="inline-flex items-center justify-center w-8 h-8 rounded-full bg-primary/10 text-primary hover:bg-primary hover:text-primary-foreground hover:shadow-[0_0_15px_rgba(6,182,212,0.4)] transition-all">
                                <ChevronDown className="w-4 h-4 -rotate-90" />
                              </Link>
                            </td>
                          </tr>
                        );
                      })}
                      {filteredClaims.length === 0 && (
                        <tr>
                          <td colSpan={6} className="px-6 py-12 text-center text-muted-foreground">
                            <div className="flex flex-col items-center justify-center opacity-70">
                              <Search className="w-8 h-8 mb-3" />
                              <p className="text-sm">No claims found matching your filters.</p>
                            </div>
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </motion.div>
          )}

          {/* ========================================================= */}
          {/* DASHBOARD VIEW (The New Reasoning Engine Layout) */}
          {/* ========================================================= */}
          {viewMode === 'dashboard' && (
            <motion.div 
              key="dashboard"
              className="p-6 space-y-6 max-w-[1600px] mx-auto h-full overflow-y-auto"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.2 }}
            >
              {/* Top Panel: Risk Score */}
              <div className="h-48">
                 <RiskScorePanel data={riskData} />
              </div>

              {/* Bottom Split: List vs Graph */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 h-[400px]">
                 
                 {/* Left List: Contradiction Explorer */}
                 <div className="col-span-1 h-full flex flex-col">
                    <h2 className="text-sm font-semibold text-foreground/90 mb-3 uppercase tracking-wider flex items-center justify-between">
                       Active Contradictions
                       <span className="bg-danger/10 text-danger border border-danger/20 px-2 py-0.5 rounded text-[10px] animate-pulse">Live</span>
                    </h2>
                    <div className="flex-1 border border-border/50 rounded-xl shadow-sm overflow-hidden p-2 glass-panel">
                       <ContradictionExplorer 
                         conflicts={conflicts} 
                         onHover={(c) => console.log('Hovered conflict', c)} 
                         onClick={handleConflictClick}
                       />
                    </div>
                 </div>

                 {/* Right Area: The Interactive Graph */}
                 <div className="col-span-2 h-full flex flex-col">
                    <h2 className="text-sm font-semibold text-foreground/90 mb-3 uppercase tracking-wider">Semantic Claim Graph</h2>
                    <div className="flex-1 border border-border/50 rounded-xl shadow-[0_0_30px_rgba(0,0,0,0.5)] relative glass-panel overflow-hidden">
                       <ClaimGraph 
                          data={graphData} 
                          onNodeClick={(n) => setActiveNode(n)}
                       />
                    </div>
                 </div>

              </div>

              {/* Bottom Row: ESG Metric Timeline */}
              <div className="h-[380px] w-full pb-6">
                 <MetricTimeline title="Historical ESG Metric Trends" />
              </div>
            </motion.div>
          )}

        </AnimatePresence>
      </div>
    </AppLayout>
  );
};

export default ClaimExplorer;
