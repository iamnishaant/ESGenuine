import { ReactNode } from 'react';
import { motion } from 'framer-motion';
import { CursorGlow } from './CursorGlow';
import { AnimatedBackground } from './AnimatedBackground';
import { AppSidebar } from './AppSidebar';

interface AppLayoutProps {
  children: ReactNode;
}

export const AppLayout = ({ children }: AppLayoutProps) => {
  return (
    <div className="min-h-screen w-full overflow-hidden relative flex">
      <AnimatedBackground />
      <CursorGlow />
      
      {/* Sidebar Navigation */}
      <AppSidebar />
      
      {/* Main content */}
      <div className="relative z-10 flex-1 flex flex-col h-screen overflow-hidden">
        {children}
      </div>
    </div>
  );
};
