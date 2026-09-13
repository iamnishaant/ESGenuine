import { useState } from 'react';
import { motion } from 'framer-motion';
import { AnimatedBackground } from '../components/AnimatedBackground';
import { Header } from '../components/Header';
import { DocumentViewer } from '../components/DocumentViewer';
import { Globe } from '../components/Globe';
import { ClaimIntelligence } from '../components/ClaimIntelligence';
import { CompanyPanel } from '../components/CompanyPanel';
import { DashboardCards } from '../components/DashboardCards';
import { AppSidebar } from '../components/AppSidebar';
import { RegulatoryDisclaimer } from '../components/RegulatoryDisclaimer';

const Index = () => {
  const [selectedClaim, setSelectedClaim] = useState<string | null>(null);
  const [selectedCompany, setSelectedCompany] = useState<string | null>(null);

  const handleClaimSelect = (id: string) => {
    setSelectedClaim(prev => prev === id ? null : id);
  };

  // Clicking a company HQ marker on the globe surfaces that company's claims.
  const handleCompanySelect = (name: string) => {
    setSelectedClaim(null);
    setSelectedCompany(prev => prev === name ? null : name);
  };

  return (
    <div className="min-h-screen w-full overflow-hidden relative flex">
      {/* Animated background */}
      <AnimatedBackground />
      
      
      {/* Sidebar Navigation */}
      <AppSidebar />
      
      {/* Main layout */}
      <div className="relative z-10 flex-1 flex flex-col h-screen">
        {/* Header */}
        <Header />
        
        {/* Dashboard stats */}
        <motion.div 
          className="px-6 py-4"
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
        >
          <DashboardCards />
        </motion.div>
        
        {/* Main content area */}
        <div className="flex-1 px-6 pb-4 flex gap-4 min-h-0 overflow-hidden">
          {/* Left panel - Document Viewer */}
          <motion.div 
            className="w-[360px] flex-shrink-0 h-full"
            initial={{ opacity: 0, x: -30 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.3 }}
          >
            <DocumentViewer 
              selectedClaim={selectedClaim} 
              onClaimSelect={handleClaimSelect} 
            />
          </motion.div>
          
          {/* Center panel - 3D Globe */}
          <motion.div 
            className="flex-1 flex flex-col gap-4"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.4 }}
          >
            <div className="flex-1 glass-panel relative overflow-hidden">
              {/* Globe container */}
              <div className="absolute inset-0">
                <Globe
                  selectedCompany={selectedCompany}
                  onCompanySelect={handleCompanySelect}
                />
              </div>

              {/* Overlay info */}
              <div className="absolute top-4 left-4 flex items-center gap-2 text-xs text-muted-foreground">
                <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground" />
                <span>Use “Jump to company” (top right) • or drag / scroll / click a pin</span>
              </div>

              {/* Legend */}
              <div className="absolute bottom-4 left-4 glass-panel p-3 space-y-2">
                <span className="text-xs text-muted-foreground font-medium">Company Risk</span>
                <div className="flex items-center gap-4">
                  <div className="flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-success" />
                    <span className="text-xs text-muted-foreground">Low</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-warning" />
                    <span className="text-xs text-muted-foreground">Moderate</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-danger" />
                    <span className="text-xs text-muted-foreground">High</span>
                  </div>
                </div>
              </div>
            </div>
          </motion.div>
          
          {/* Right panel - Claim Intelligence / Company claims */}
          <motion.div
            className="w-[380px] flex-shrink-0 h-full"
            initial={{ opacity: 0, x: 30 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.5 }}
          >
            {selectedClaim ? (
              <ClaimIntelligence
                selectedClaim={selectedClaim}
                onBack={selectedCompany ? () => setSelectedClaim(null) : undefined}
              />
            ) : selectedCompany ? (
              <CompanyPanel
                companyName={selectedCompany}
                onClaimSelect={setSelectedClaim}
                onClose={() => setSelectedCompany(null)}
              />
            ) : (
              <ClaimIntelligence selectedClaim={null} />
            )}
          </motion.div>
        </div>
        
        {/* Regulatory Disclaimer Footer */}
        <RegulatoryDisclaimer />
      </div>
    </div>
  );
};

export default Index;
