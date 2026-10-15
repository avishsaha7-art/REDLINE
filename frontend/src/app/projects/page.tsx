"use client";

import React, { useEffect, useState, useMemo, useRef } from 'react';
import Link from 'next/link';
import { apiClient } from '@/api/client';
import { RunHistoryItem } from '@/models/types';
import { animateEntrance } from '@/lib/anime';

export interface ProjectWorkspace {
  id: string;
  name: string;
  description: string;
  trustTier: 'TRUSTED' | 'UNTRUSTED';
  defaultBranch: string;
  allowedScope: string[];
  baseSnapshot: string;
  stack: string;
  role: string;
}

export const REGISTERED_PROJECTS: ProjectWorkspace[] = [
  {
    id: "repo-int-1",
    name: "Core Integration Workspace",
    description: "Authoritative internal benchmark target containing deterministic invariant test suites and patch verification.",
    trustTier: "TRUSTED",
    defaultBranch: "main",
    allowedScope: ["backend/**", "src/**"],
    baseSnapshot: "snap-demo-a-01",
    stack: "Python / FastAPI",
    role: "Core Benchmark"
  },
  {
    id: "repo-payments-api",
    name: "Payments Service Benchmark",
    description: "Synthetic financial ledger repository with strict decimal precision, ledger balancing, and refund invariants.",
    trustTier: "TRUSTED",
    defaultBranch: "master",
    allowedScope: ["ledger/**", "tests/invariants/**"],
    baseSnapshot: "snap-ledger-01",
    stack: "Python / Ledger",
    role: "Financial Ledger"
  },
  {
    id: "repo-sample-auth-service",
    name: "Auth & Identity Target",
    description: "Authentication and session token service target enforcing cryptographic token invariants and subshell blocking.",
    trustTier: "TRUSTED",
    defaultBranch: "main",
    allowedScope: ["auth/**", "tokens/**"],
    baseSnapshot: "snap-auth-02",
    stack: "Python / Cryptography",
    role: "Identity Security"
  },
  {
    id: "untrusted-external-repo",
    name: "External Host Sandbox Target",
    description: "Third-party untrusted repository subject to fail-closed host execution blocking on local backend environments.",
    trustTier: "UNTRUSTED",
    defaultBranch: "external",
    allowedScope: ["plugins/**"],
    baseSnapshot: "snap-demo-d-04",
    stack: "Untrusted / Arbitrary",
    role: "Adversarial Quarantine"
  }
];

export default function ProjectsPage() {
  const [history, setHistory] = useState<RunHistoryItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Search & Filter State
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [tierFilter, setTierFilter] = useState<'ALL' | 'TRUSTED' | 'UNTRUSTED'>('ALL');

  // Animation Ref
  const gridContainerRef = useRef<HTMLDivElement>(null);
  const hasAnimatedRef = useRef<boolean>(false);
  const fetchRuns = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await apiClient.getRunHistory();
      setHistory(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    let ignore = false;
    apiClient.getRunHistory()
      .then((data) => {
        if (!ignore) {
          setHistory(data);
          setError(null);
          setIsLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!ignore) {
          setError(err instanceof Error ? err.message : String(err));
          setIsLoading(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, []);

  useEffect(() => {
    if (!hasAnimatedRef.current && gridContainerRef.current) {
      const cards = gridContainerRef.current.querySelectorAll('.project-bento-card');
      if (cards.length > 0) {
        animateEntrance(cards as unknown as HTMLElement[]);
        hasAnimatedRef.current = true;
      }
    }
  }, [isLoading]);

  // Filtered projects
  const filteredProjects = useMemo(() => {
    return REGISTERED_PROJECTS.filter((proj) => {
      const matchesTier = 
        tierFilter === 'ALL' || proj.trustTier === tierFilter;
      
      const query = searchQuery.trim().toLowerCase();
      const matchesSearch = 
        !query ||
        proj.id.toLowerCase().includes(query) ||
        proj.name.toLowerCase().includes(query) ||
        proj.description.toLowerCase().includes(query) ||
        proj.stack.toLowerCase().includes(query) ||
        proj.allowedScope.some(s => s.toLowerCase().includes(query));

      return matchesTier && matchesSearch;
    });
  }, [searchQuery, tierFilter]);

  const trustedCount = useMemo(() => 
    REGISTERED_PROJECTS.filter(p => p.trustTier === 'TRUSTED').length, []
  );
  const untrustedCount = useMemo(() => 
    REGISTERED_PROJECTS.filter(p => p.trustTier === 'UNTRUSTED').length, []
  );

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12">
      {/* ================= HEADER SECTION ================= */}
      <header className="border-b border-[#222430] pb-5">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div>
            <div className="flex items-center gap-2 text-xs font-mono text-[#71717a] mb-1.5">
              <span className="text-[#ef4444]">WORKSPACE</span>
              <span>/</span>
              <span>TARGET_DIRECTORIES</span>
              <span>/</span>
              <span className="text-[#f4f4f5]">PROJECTS</span>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <span className="px-2 py-0.5 rounded bg-[#13141b] text-[#ef4444] border border-[#ef4444]/30 font-mono text-xs font-bold">
                03
              </span>
              <h1 className="text-2xl sm:text-3xl font-black tracking-tight text-[#f4f4f5] flex items-center gap-3">
                PROJECTS
              </h1>
              <span className="text-xs font-mono font-medium text-amber-400 border border-amber-900/60 px-2 py-0.5 rounded bg-amber-950/40">
                Demo Fixtures
              </span>
              <span className="text-xs font-mono font-medium text-[#10b981] border border-[#10b981]/30 px-2 py-0.5 rounded bg-[#10b981]/10 hidden sm:inline-block">
                Reference Workspaces
              </span>
            </div>

            <p className="text-xs sm:text-sm text-[#a1a1aa] font-sans mt-2">
              Static demo target codebase repositories for invariant verification scenarios.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3 w-full sm:w-auto">
            {/* Quick Authoritative Telemetry Readouts */}
            <div className="hidden lg:flex items-center gap-3 font-mono text-xs text-[#a1a1aa]">
              <div className="flex items-center gap-2 px-3 py-1.5 rounded bg-[#0d0e12] border border-[#222430]">
                <span className="w-2 h-2 rounded-full bg-[#10b981]"></span>
                <span>Fixtures: <strong className="text-[#f4f4f5]">{REGISTERED_PROJECTS.length}</strong></span>
              </div>
              <div className="flex items-center gap-2 px-3 py-1.5 rounded bg-[#0d0e12] border border-[#222430]">
                <span className="w-2 h-2 rounded-full bg-[#ef4444]"></span>
                <span>
                  Authoritative Runs: <strong className="text-[#f4f4f5]">{isLoading ? '...' : history.length}</strong>
                </span>
              </div>
            </div>

            <Link
              href="/"
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 text-xs font-bold bg-[#ef4444] hover:bg-[#dc2626] active:bg-[#b91c1c] text-white px-4 py-2 rounded transition-all duration-150 shadow-[0_0_12px_rgba(239,68,68,0.35)] hover:shadow-[0_0_16px_rgba(239,68,68,0.5)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
              </svg>
              <span>+ New Task Contract</span>
            </Link>
          </div>
        </div>
      </header>

      {/* ================= ARCHITECTURE & SAFETY DISCLOSURE ================= */}
      <section aria-labelledby="projects-safety-notice">
        <h2 id="projects-safety-notice" className="sr-only">Static Target Workspaces Disclosure</h2>
        <div className="bg-[#0d0e12] border border-amber-900/60 rounded-lg p-4 text-xs text-amber-200/90 flex items-start gap-3.5 shadow-sm">
          <div className="w-5 h-5 rounded-full bg-amber-500/20 text-amber-400 flex items-center justify-center shrink-0 mt-0.5 border border-amber-500/30">
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <div className="space-y-1">
            <strong className="text-amber-300 font-semibold block tracking-wide">
              Static Demo Target Workspaces:
            </strong>
            <p className="text-[#a1a1aa] text-[11px] leading-relaxed">
              The target workspaces and policies displayed below are static demonstration fixtures used to populate Task Contracts.
              Dynamic multi-tenant project CRUD and remote repository synchronization APIs are not implemented in this stage.
              Repository execution permissions are authoritatively governed by <code className="text-[#fca5a5] font-mono">backend/sandbox/trust.py</code>.
            </p>
          </div>
        </div>
      </section>

      {/* ================= ERROR BANNER (IF RUN SYNC FAILS) ================= */}
      {error && (
        <div 
          role="alert" 
          className="bg-[#ef4444]/10 border border-[#ef4444]/30 rounded-lg p-3 text-xs text-[#f87171] flex items-center justify-between gap-3"
        >
          <div className="flex items-center gap-2">
            <svg className="w-4 h-4 shrink-0 text-[#ef4444]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <span>Live run history sync failed: {error}. Target fixture specifications remain active.</span>
          </div>
          <button 
            onClick={fetchRuns}
            className="px-2.5 py-1 rounded bg-[#ef4444]/20 hover:bg-[#ef4444]/30 text-white font-mono text-[10px] uppercase font-semibold transition-colors"
          >
            Retry Sync
          </button>
        </div>
      )}

      {/* ================= FILTER & SEARCH CONTROLS ================= */}
      <section aria-labelledby="projects-filter-controls">
        <h2 id="projects-filter-controls" className="sr-only">Project Filter and Search Controls</h2>
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
          {/* Search Input */}
          <div className="relative flex-1 max-w-md">
            <label htmlFor="project-search" className="sr-only">Search projects</label>
            <span className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-[#71717a]">
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <circle cx="11" cy="11" r="8" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-4.35-4.35" />
              </svg>
            </span>
            <input
              id="project-search"
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search projects by ID, name, stack, or scope..."
              className="w-full pl-9 pr-8 py-1.5 rounded bg-[#0d0e12] border border-[#222430] text-[#f4f4f5] placeholder:text-[#71717a] font-mono text-xs focus:border-[#ef4444] focus:outline-none transition-colors"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery('')}
                className="absolute inset-y-0 right-0 pr-2.5 flex items-center text-[#71717a] hover:text-[#f4f4f5]"
                aria-label="Clear search query"
              >
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            )}
          </div>

          {/* Filter Pills */}
          <div className="flex items-center gap-1.5 p-1 rounded bg-[#0d0e12] border border-[#222430] self-start sm:self-auto">
            <button
              onClick={() => setTierFilter('ALL')}
              className={`px-3 py-1 rounded font-mono text-[11px] font-semibold transition-all ${
                tierFilter === 'ALL'
                  ? 'bg-[#13141b] text-[#f4f4f5] border border-[#353748] shadow-sm'
                  : 'text-[#a1a1aa] hover:text-[#f4f4f5]'
              }`}
            >
              All ({REGISTERED_PROJECTS.length})
            </button>
            <button
              onClick={() => setTierFilter('TRUSTED')}
              className={`px-3 py-1 rounded font-mono text-[11px] font-semibold transition-all ${
                tierFilter === 'TRUSTED'
                  ? 'bg-[#10b981]/15 text-[#10b981] border border-[#10b981]/40 shadow-sm'
                  : 'text-[#a1a1aa] hover:text-[#10b981]'
              }`}
            >
              Trusted ({trustedCount})
            </button>
            <button
              onClick={() => setTierFilter('UNTRUSTED')}
              className={`px-3 py-1 rounded font-mono text-[11px] font-semibold transition-all ${
                tierFilter === 'UNTRUSTED'
                  ? 'bg-[#ef4444]/15 text-[#f87171] border border-[#ef4444]/40 shadow-sm'
                  : 'text-[#a1a1aa] hover:text-[#f87171]'
              }`}
            >
              Untrusted ({untrustedCount})
            </button>
          </div>
        </div>
      </section>

      {/* ================= BENTO GRID SECTION ================= */}
      <section aria-labelledby="registered-projects-heading">
        <h2 id="registered-projects-heading" className="sr-only">Target Project Workspaces</h2>

        {filteredProjects.length === 0 ? (
          <div className="bg-[#0d0e12] border border-[#222430] rounded-lg p-10 text-center space-y-3">
            <div className="w-10 h-10 rounded-full bg-[#13141b] border border-[#222430] text-[#71717a] flex items-center justify-center mx-auto">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
              </svg>
            </div>
            <p className="text-xs font-mono text-[#a1a1aa]">
              No project workspaces match &ldquo;{searchQuery}&rdquo; under {tierFilter.toLowerCase()} filter.
            </p>
            <button
              onClick={() => {
                setSearchQuery('');
                setTierFilter('ALL');
              }}
              className="text-xs font-mono text-[#ef4444] hover:underline"
            >
              Reset Search & Filters
            </button>
          </div>
        ) : (
          <div 
            ref={gridContainerRef}
            className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-2 xl:grid-cols-2 gap-5"
          >
            {filteredProjects.map((project) => {
              // Count authoritative runs for this project
              const projectRuns = history.filter(
                (h) => h.task_id.toLowerCase().includes(project.id.toLowerCase()) ||
                       h.task_id.toLowerCase().includes(project.id.replace('repo-', '').toLowerCase())
              );

              const isTrusted = project.trustTier === 'TRUSTED';

              return (
                <article
                  key={project.id}
                  className="project-bento-card group card-laser-border relative flex flex-col justify-between p-5 rounded-lg bg-[#0d0e12] border border-[#222430] overflow-hidden transition-all duration-200"
                >
                  {/* Subtle Laser Top Accent Line on hover */}
                  <div className="absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r from-transparent via-[#ef4444]/60 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-200" />

                  <div className="space-y-4">
                    {/* Card Header */}
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="w-9 h-9 rounded bg-[#13141b] border border-[#222430] flex items-center justify-center text-[#a1a1aa] group-hover:text-[#ef4444] group-hover:border-[#ef4444]/40 transition-colors shrink-0">
                          {isTrusted ? (
                            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                              <path strokeLinecap="round" strokeLinejoin="round" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                            </svg>
                          ) : (
                            <svg className="w-4 h-4 text-[#f87171]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                            </svg>
                          )}
                        </div>
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-xs font-bold text-[#ef4444] truncate">
                              {project.id}
                            </span>
                            <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-[#13141b] border border-[#222430] text-[#71717a]">
                              {project.role}
                            </span>
                          </div>
                          <h3 className="text-base font-bold text-[#f4f4f5] group-hover:text-white transition-colors truncate mt-0.5">
                            {project.name}
                          </h3>
                        </div>
                      </div>

                      {/* Trust Tier Badge */}
                      <span
                        className={`inline-flex items-center gap-1.5 text-[10px] font-mono font-bold px-2.5 py-1 rounded border shrink-0 ${
                          isTrusted
                            ? 'bg-[#10b981]/10 text-[#10b981] border-[#10b981]/30'
                            : 'bg-[#ef4444]/10 text-[#f87171] border-[#ef4444]/30'
                        }`}
                      >
                        <span className={`w-1.5 h-1.5 rounded-full ${isTrusted ? 'bg-[#10b981]' : 'bg-[#ef4444]'}`} />
                        {project.trustTier}
                      </span>
                    </div>

                    {/* Description */}
                    <p className="text-xs text-[#a1a1aa] leading-relaxed line-clamp-2">
                      {project.description}
                    </p>

                    {/* Technical Metadata Row */}
                    <div className="flex flex-wrap items-center gap-1.5 font-mono text-[11px]">
                      <span className="px-2 py-0.5 rounded bg-[#13141b] border border-[#222430] text-[#f4f4f5] flex items-center gap-1.5">
                        <span className="w-1.5 h-1.5 rounded-full bg-[#06b6d4]"></span>
                        {project.stack}
                      </span>
                      <span className="px-2 py-0.5 rounded bg-[#13141b] border border-[#222430] text-[#a1a1aa] flex items-center gap-1">
                        <svg className="w-3 h-3 text-[#71717a]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                        </svg>
                        {project.defaultBranch}
                      </span>
                      <span className="px-2 py-0.5 rounded bg-[#13141b] border border-[#222430] text-[#71717a]">
                        {project.baseSnapshot}
                      </span>
                    </div>

                    {/* Allowed Scope Specs */}
                    <div className="pt-2.5 border-t border-[#222430]/70 space-y-1.5 font-mono text-[11px]">
                      <div className="flex items-center justify-between">
                        <span className="text-[#71717a]">Allowed Scope:</span>
                        <div className="flex flex-wrap gap-1 max-w-[220px] justify-end">
                          {project.allowedScope.map((scope) => (
                            <span 
                              key={scope} 
                              className="px-1.5 py-0.2 rounded bg-[#13141b] border border-[#222430] text-[#a1a1aa] text-[10px]"
                            >
                              {scope}
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Card Footer */}
                  <div className="pt-4 mt-4 border-t border-[#222430] flex items-center justify-between text-xs">
                    <span className="text-[#71717a] font-mono text-[11px] flex items-center gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-[#8b5cf6]"></span>
                      {isLoading ? (
                        <span className="text-[#71717a]">Syncing runs...</span>
                      ) : (
                        <span>{projectRuns.length} recorded runs</span>
                      )}
                    </span>

                    <Link
                      href={`/?repoId=${encodeURIComponent(project.id)}`}
                      className="inline-flex items-center gap-1 font-semibold text-xs text-[#ef4444] hover:text-[#f87171] group-hover:translate-x-0.5 transition-all duration-150 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[#ef4444]"
                    >
                      <span>Verify Code</span>
                      <span aria-hidden="true">&rarr;</span>
                    </Link>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
