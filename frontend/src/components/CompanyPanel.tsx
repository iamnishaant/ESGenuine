import { motion, AnimatePresence } from 'framer-motion';
import { Building2, MapPin, X, ChevronRight, CheckCircle, HelpCircle, AlertCircle } from 'lucide-react';
import { useMemo } from 'react';
import { useClaims, Claim } from '@/hooks/useClaims';
import { useBackendScores } from '@/hooks/useBackendScores';
import { resolveHeadquarters } from '@/lib/companyHeadquarters';

interface CompanyPanelProps {
  companyName: string;
  onClaimSelect: (id: string) => void;
  onClose: () => void;
}

const StatusIcon = ({ status }: { status: Claim['status'] }) => {
  switch (status) {
    case 'verified': return <CheckCircle className="w-4 h-4 text-success" />;
    case 'review': return <HelpCircle className="w-4 h-4 text-warning" />;
    case 'gap': return <AlertCircle className="w-4 h-4 text-danger" />;
  }
};

const scoreColor = (score: number | null) =>
  score == null ? 'text-muted-foreground'
    : score >= 70 ? 'text-success' : score >= 40 ? 'text-warning' : 'text-danger';

const riskColor = (risk: 'low' | 'medium' | 'high') =>
  risk === 'low' ? 'bg-success/20 text-success'
    : risk === 'medium' ? 'bg-warning/20 text-warning'
    : 'bg-danger/20 text-danger';

// The right-hand panel shown when a company's HQ marker is clicked on the globe.
// Lists every claim ESGenuine extracted from that company's report(s).
export const CompanyPanel = ({ companyName, onClaimSelect, onClose }: CompanyPanelProps) => {
  const { claims, companies } = useClaims();
  // Integrity score comes exclusively from the backend audit (single source of
  // truth); "—" when the backend is unreachable — never a homegrown number.
  const { forCompany } = useBackendScores();

  const company = useMemo(
    () => companies.find((c) => c.name === companyName),
    [companies, companyName],
  );
  const companyClaims = useMemo(
    () => claims.filter((c) => c.company === companyName),
    [claims, companyName],
  );
  const hq = resolveHeadquarters(companyName);

  const counts = company?.claims ?? { verified: 0, review: 0, gap: 0 };
  const backend = forCompany(companyName) ?? forCompany(company?.id);
  const integrity = backend?.integrity_score != null ? Math.round(backend.integrity_score) : null;
  const risk = (backend?.greenwashing_risk === 'Low' ? 'low'
    : backend?.greenwashing_risk === 'High' ? 'high'
    : backend?.greenwashing_risk ? 'medium'
    : company?.riskLevel ?? 'medium') as 'low' | 'medium' | 'high';

  return (
    <motion.div
      className="h-full flex flex-col glass-panel"
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.4 }}
    >
      {/* Header */}
      <div className="p-4 border-b border-border/50">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-lg bg-primary/20 flex items-center justify-center flex-shrink-0">
            <Building2 className="w-5 h-5 text-primary" />
          </div>
          <div className="flex-1 min-w-0">
            <h2 className="font-semibold text-foreground truncate">{companyName}</h2>
            <p className="text-xs text-muted-foreground flex items-center gap-1">
              <MapPin className="w-3 h-3" />
              {hq ? `${hq.city}, ${hq.country}` : 'Headquarters unknown'}
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/40 transition-colors"
            aria-label="Close company view"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Summary row */}
        <div className="flex items-center gap-3 mt-3">
          <div className="flex items-baseline gap-1">
            <span className={`font-mono text-xl font-bold ${scoreColor(integrity)}`}>{integrity ?? '—'}</span>
            <span className="text-[10px] text-muted-foreground">integrity</span>
          </div>
          <span className={`text-[10px] px-1.5 py-0.5 rounded uppercase font-medium ${riskColor(risk)}`}>
            {risk} risk
          </span>
          <span className="ml-auto text-xs text-muted-foreground">{companyClaims.length} claims</span>
        </div>

        {/* Status breakdown */}
        <div className="flex items-center gap-4 mt-3 text-xs">
          <span className="flex items-center gap-1 text-success"><CheckCircle className="w-3.5 h-3.5" />{counts.verified} verified</span>
          <span className="flex items-center gap-1 text-warning"><HelpCircle className="w-3.5 h-3.5" />{counts.review} review</span>
          <span className="flex items-center gap-1 text-danger"><AlertCircle className="w-3.5 h-3.5" />{counts.gap} gaps</span>
        </div>
      </div>

      {/* Claims list */}
      <div className="flex-1 overflow-y-auto p-4 space-y-2">
        <AnimatePresence mode="wait">
          {companyClaims.length === 0 ? (
            <div className="text-sm text-center text-muted-foreground py-8">
              No claims found for this company.
            </div>
          ) : (
            <motion.div
              key={companyName}
              className="space-y-2"
              initial="hidden"
              animate="visible"
              variants={{ hidden: {}, visible: { transition: { staggerChildren: 0.04 } } }}
            >
              {companyClaims.map((claim) => (
                <motion.button
                  key={claim.id}
                  onClick={() => onClaimSelect(claim.id)}
                  className="w-full text-left p-3 rounded-lg hover:bg-muted/30 transition-all group"
                  variants={{ hidden: { opacity: 0, y: 8 }, visible: { opacity: 1, y: 0 } }}
                  whileHover={{ scale: 1.01 }}
                  whileTap={{ scale: 0.99 }}
                >
                  <div className="flex items-start gap-3">
                    <div className="mt-0.5"><StatusIcon status={claim.status} /></div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm leading-relaxed text-foreground/90 line-clamp-3">{claim.claim}</p>
                      <div className="flex items-center gap-3 mt-1.5 text-xs text-muted-foreground">
                        {claim.location !== 'Unspecified' && (
                          <span className="flex items-center gap-1"><MapPin className="w-3 h-3" />{claim.location}</span>
                        )}
                        {claim.page && <span>p.{claim.page}</span>}
                        {claim.reportYear && <span>{claim.reportYear}</span>}
                      </div>
                    </div>
                    <ChevronRight className="w-4 h-4 text-muted-foreground group-hover:text-primary transition-colors flex-shrink-0" />
                  </div>
                </motion.button>
              ))}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  );
};
