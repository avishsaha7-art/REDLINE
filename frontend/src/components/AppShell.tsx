"use client";

import React, { Suspense, useState, useEffect } from 'react';
import { NavigationSidebar } from './NavigationSidebar';
import { apiClient } from '@/api/client';

interface AppShellProps {
  children: React.ReactNode;
}

export const AppShell: React.FC<AppShellProps> = ({ children }) => {
  const [apiStatus, setApiStatus] = useState<'checking' | 'reachable' | 'unreachable'>('checking');
  const [latencyMs, setLatencyMs] = useState<number | null>(null);

  useEffect(() => {
    let isMounted = true;
    const probeGateway = async () => {
      const start = performance.now();
      try {
        await apiClient.getRunHistory();
        if (isMounted) {
          setLatencyMs(Math.round(performance.now() - start));
          setApiStatus('reachable');
        }
      } catch {
        if (isMounted) {
          setApiStatus('unreachable');
        }
      }
    };

    probeGateway();
    const interval = setInterval(probeGateway, 30000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  return (
    <div className="min-h-screen bg-[#09090b] text-[#f4f4f5] flex flex-col lg:flex-row font-sans selection:bg-[#ef4444]/20 selection:text-[#fca5a5]">
      {/* Accessible Skip Link */}
      <a 
        href="#main-content" 
        className="sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 focus:px-4 focus:py-2 focus:bg-[#ef4444] focus:text-white focus:font-bold focus:rounded focus:shadow-[0_0_20px_rgba(239,68,68,0.5)] focus:outline-none focus:ring-2 focus:ring-white"
      >
        Skip to main content
      </a>

      {/* Persistent Navigation Sidebar */}
      <Suspense fallback={<aside className="w-64 bg-[#0d0e12] border-r border-[#222430] hidden lg:block" />}>
        <NavigationSidebar />
      </Suspense>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top Operational Status Header */}
        <header 
          className="border-b border-[#222430] bg-[#0d0e12]/95 backdrop-blur-md px-4 sm:px-6 py-2.5 flex flex-wrap justify-between items-center gap-2.5 lg:sticky top-0 z-30" 
          role="banner"
        >
          <div className="flex flex-wrap items-center gap-2 sm:gap-3">
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-mono uppercase tracking-wider text-[#71717a] font-semibold">
                GATEWAY:
              </span>
              {apiStatus === 'checking' && (
                <span className="inline-flex items-center gap-1.5 text-[11px] font-mono text-[#a1a1aa] bg-[#13141b] px-2 py-0.5 rounded border border-[#222430]">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#71717a] animate-pulse"></span>
                  PROBING...
                </span>
              )}
              {apiStatus === 'reachable' && (
                <span 
                  className="inline-flex items-center gap-1.5 text-[11px] font-mono text-[#10b981] bg-[#10b981]/10 px-2 py-0.5 rounded border border-[#10b981]/30 shadow-[0_0_8px_rgba(16,185,129,0.15)]"
                  title="FastAPI gateway responded to GET /api/v1/runs probe (verifies route reachability only)"
                >
                  <span className="w-1.5 h-1.5 rounded-full bg-[#10b981] motion-safe:animate-pulse"></span>
                  API REACHABLE {latencyMs !== null ? `(${latencyMs}ms)` : ''}
                </span>
              )}
              {apiStatus === 'unreachable' && (
                <span 
                  className="inline-flex items-center gap-1.5 text-[11px] font-mono text-[#f87171] bg-[#ef4444]/10 px-2 py-0.5 rounded border border-[#ef4444]/30"
                  title="Gateway unreachable at configured endpoint"
                >
                  <span className="w-1.5 h-1.5 rounded-full bg-[#ef4444]"></span>
                  API UNREACHABLE
                </span>
              )}
            </div>

            <span 
              className="hidden md:inline-flex items-center gap-1.5 text-[11px] font-mono text-[#e5e1e4] bg-[#13141b] px-2 py-0.5 rounded border border-[#222430]"
              title="Deterministic execution environment"
            >
              <span className="w-1.5 h-1.5 rounded-full bg-[#06b6d4]"></span>
              SANDBOX POLICY: HARDENED
            </span>

            <span 
              className="hidden lg:inline-flex items-center gap-1.5 text-[11px] font-mono text-[#71717a] bg-[#13141b] px-2 py-0.5 rounded border border-[#222430]"
              title="Configured model specification (Static reference, no active GPU metrics)"
            >
              MODEL: Llama-3.1-70B (Nebius Spec)
            </span>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-[10px] font-mono font-bold text-[#fca5a5] bg-[#ef4444]/15 px-2.5 py-0.5 rounded border border-[#ef4444]/30 shadow-sm tracking-tight">
              FRONTEND IS PRESENTATION ONLY • BACKEND IS SOURCE OF TRUTH
            </span>
          </div>
        </header>

        {/* Dynamic Route Content */}
        <main id="main-content" className="flex-1 p-4 sm:p-6 lg:p-8 max-w-7xl w-full mx-auto" tabIndex={-1}>
          {children}
        </main>
      </div>
    </div>
  );
};

