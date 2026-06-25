import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Index from "./pages/Index";
import ClaimExplorer from "./pages/ClaimExplorer";
import EvidenceAnalysis from "./pages/EvidenceAnalysis";
import AuditTrail from "./pages/AuditTrail";
import PortfolioOverview from "./pages/PortfolioOverview";
import SystemTransparency from "./pages/SystemTransparency";
import Settings from "./pages/Settings";
import SubmitReport from "./pages/SubmitReport";
import NotFound from "./pages/NotFound";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Index />} />
          <Route path="/claims" element={<ClaimExplorer />} />
          <Route path="/claims/:claimId" element={<EvidenceAnalysis />} />
          <Route path="/evidence" element={<EvidenceAnalysis />} />
          <Route path="/evidence/:claimId" element={<EvidenceAnalysis />} />
          <Route path="/audit-trail" element={<AuditTrail />} />
          <Route path="/audit-trail/:claimId" element={<AuditTrail />} />
          <Route path="/portfolio" element={<PortfolioOverview />} />
          <Route path="/transparency" element={<SystemTransparency />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/submit-report" element={<SubmitReport />} />
          {/* ADD ALL CUSTOM ROUTES ABOVE THE CATCH-ALL "*" ROUTE */}
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
