"use client";

import React, { useState, useEffect, useMemo, useCallback } from 'react';
import Link from 'next/link';
import { apiClient } from '@/api/client';
import { RepositoryResponse } from '@/models/types';

export interface RepositoryPolicy {
  repositoryId: string;
  trustLevel: 'TRUSTED' | 'UNTRUSTED';
  sandboxPolicy: string;
  scopeEnforcement: string;
  pathTraversalGate: string;
  snapshotDigest: string;
  fixtureRole: string;
  defaultBranch: string;
}

export const REPOSITORY_POLICIES: RepositoryPolicy[] = [
  {
    repositoryId: "repo-int-1",
    trustLevel: "TRUSTED",
    sandboxPolicy: "LOCAL_SANDBOX_ISOLATED (Stage 16.1 Working Directory Hardening)",
    scopeEnforcement: "STRICT_ALLOWLIST (Files outside allowed_scope rejected)",
    pathTraversalGate: "FAIL_CLOSED (All ../ and absolute paths rejected)",
    snapshotDigest: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    fixtureRole: "Core Invariant Benchmark",
    defaultBranch: "main"
  },
  {
    repositoryId: "repo-payments-api",
    trustLevel: "TRUSTED",
    sandboxPolicy: "LOCAL_SANDBOX_ISOLATED (Sandboxed test execution)",
    scopeEnforcement: "STRICT_ALLOWLIST (ledger/** only)",
    pathTraversalGate: "FAIL_CLOSED (Path normalization verified)",
    snapshotDigest: "8f7d6e5c4b3a2910fedcba9876543210abcdef0123456789abcdef0123456789",
    fixtureRole: "Financial Ledger Benchmark",
    defaultBranch: "master"
  },
  {
    repositoryId: "repo-sample-auth-service",
    trustLevel: "TRUSTED",
    sandboxPolicy: "LOCAL_SANDBOX_ISOLATED (AST subshell execution blocking)",
    scopeEnforcement: "STRICT_ALLOWLIST (auth/**, tokens/**)",
    pathTraversalGate: "FAIL_CLOSED (Directory boundary verified)",
    snapshotDigest: "2c624232cdd221771294dfbb379ac8ab73e04e1160d5615d031f1da83ee80480",
    fixtureRole: "Token Auth & Cryptography Target",
    defaultBranch: "main"
  },
  {
    repositoryId: "untrusted-external-repo",
    trustLevel: "UNTRUSTED",
    sandboxPolicy: "POLICY_BLOCKED (Host execution strictly prohibited on LocalDevelopmentBackend)",
    scopeEnforcement: "HARD_BLOCK (No write or execute access granted)",
    pathTraversalGate: "FAIL_CLOSED (Pre-execution rejection)",
    snapshotDigest: "4a59a721c5b8d96f9a72b83c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e",
    fixtureRole: "Quarantined Host Quarantine",
    defaultBranch: "external"
  }
];

export default function RepositoriesPage() {
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [trustFilter, setTrustFilter] = useState<'ALL' | 'TRUSTED' | 'UNTRUSTED'>('ALL');
  const [copiedDigest, setCopiedDigest] = useState<string | null>(null);

  // Dynamic remote repositories state
  const [remoteTargets, setRemoteTargets] = useState<RepositoryResponse[]>([]);
  const [isLoadingTargets, setIsLoadingTargets] = useState<boolean>(false);
  const [showImportForm, setShowImportForm] = useState<boolean>(false);
  const [importUrl, setImportUrl] = useState<string>('');
  const [importCommit, setImportCommit] = useState<string>('');
  const [isImporting, setIsImporting] = useState<boolean>(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [importSuccess, setImportSuccess] = useState<RepositoryResponse | null>(null);

  const fetchRemoteTargets = useCallback(async () => {
    setIsLoadingTargets(true);
    try {
      const targets = await apiClient.listRepositories();
      // Keep only remote quarantined targets from API to combine with policies
      const remotes = targets.filter(t => t.repository_id.startsWith('repo-remote-'));
      setRemoteTargets(remotes);
    } catch {
      // Gracefully continue with static targets if offline
    } finally {
      setIsLoadingTargets(false);
    }
  }, []);

  useEffect(() => {
    fetchRemoteTargets();
  }, [fetchRemoteTargets]);

  const handleCopyDigest = (digest: string) => {
    if (typeof navigator !== 'undefined' && navigator.clipboard) {
      navigator.clipboard.writeText(digest);
      setCopiedDigest(digest);
      setTimeout(() => setCopiedDigest(null), 2000);
    }
  };

  const handleImportSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setImportError(null);
    setImportSuccess(null);

    const trimmedUrl = importUrl.trim();
    const trimmedSha = importCommit.trim();

    if (!trimmedUrl.startsWith('https://')) {
      setImportError("Repository URL must use the secure 'https://' scheme.");
      return;
    }
    if (!/^[0-9a-fA-F]{40}$|^[0-9a-fA-F]{64}$/.test(trimmedSha)) {
      setImportError('Commit SHA must be a full 40-character or 64-character hex hash.');
      return;
    }

    setIsImporting(true);
    try {
      const res = await apiClient.importRepository({
        repository_url: trimmedUrl,
        commit_sha: trimmedSha
      });
      setImportSuccess(res);
      setImportUrl('');
      setImportCommit('');
      await fetchRemoteTargets();
    } catch (err: unknown) {
      setImportError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsImporting(false);
    }
  };

  // Combine baseline static policies with live remote targets
  const combinedRepositories = useMemo(() => {
    const list: RepositoryPolicy[] = [...REPOSITORY_POLICIES];

    for (const r of remoteTargets) {
      if (!list.some(item => item.repositoryId === r.repository_id)) {
        list.push({
          repositoryId: r.repository_id,
          trustLevel: 'UNTRUSTED',
          sandboxPolicy: 'SECURE_SANDBOX_CONTAINER (Quarantined Execution)',
          scopeEnforcement: 'WORKSPACE_CONTAINED (Filesystem scratch boundary)',
          pathTraversalGate: 'FAIL_CLOSED (Quarantine boundary strictly enforced)',
          snapshotDigest: r.snapshot_hash || '4a59a721c5b8d96f9a72b83c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e',
          fixtureRole: `Remote Import: ${r.repository_url || 'Public Git Repository'}`,
          defaultBranch: r.commit_sha ? r.commit_sha.slice(0, 8) : 'pinned'
        });
      }
    }
    return list;
  }, [remoteTargets]);

  const filteredRepositories = useMemo(() => {
    return combinedRepositories.filter((repo) => {
      const matchesFilter =
        trustFilter === 'ALL' || repo.trustLevel === trustFilter;

      const query = searchQuery.trim().toLowerCase();
      const matchesSearch =
        !query ||
        repo.repositoryId.toLowerCase().includes(query) ||
        repo.fixtureRole.toLowerCase().includes(query) ||
        repo.sandboxPolicy.toLowerCase().includes(query) ||
        repo.scopeEnforcement.toLowerCase().includes(query) ||
        repo.pathTraversalGate.toLowerCase().includes(query) ||
        repo.snapshotDigest.toLowerCase().includes(query) ||
        repo.defaultBranch.toLowerCase().includes(query);

      return matchesFilter && matchesSearch;
    });
  }, [combinedRepositories, searchQuery, trustFilter]);

  const trustedCount = useMemo(() => 
    combinedRepositories.filter((r) => r.trustLevel === 'TRUSTED').length, [combinedRepositories]
  );
  const untrustedCount = useMemo(() => 
    combinedRepositories.filter((r) => r.trustLevel === 'UNTRUSTED').length, [combinedRepositories]
  );

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12">
      {/* ================= HEADER SECTION ================= */}
      <header className="border-b border-[#222430] pb-5">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div>
            <div className="flex items-center gap-2 text-xs font-mono text-[#71717a] mb-1.5">
              <span className="text-[#ef4444]">SYSTEM</span>
              <span>::</span>
              <span className="text-[#f4f4f5]">ENVIRONMENT_05</span>
              <span>/</span>
              <span>SOURCE_TREE</span>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-2xl sm:text-3xl font-black tracking-tight text-[#f4f4f5] flex items-center gap-3">
                <span className="text-[#ef4444]">05.</span>
                <span>REPOSITORIES</span>
              </h1>
              <span className="text-xs font-mono font-medium text-[#60a5fa] border border-[#60a5fa]/30 px-2 py-0.5 rounded bg-[#60a5fa]/10">
                Static Reference
              </span>
              <span className="text-xs font-mono font-normal text-[#a1a1aa] border border-[#222430] px-2 py-0.5 rounded bg-[#0d0e12] hidden sm:inline-block">
                v2.4-deterministic
              </span>
            </div>

            <p className="text-xs sm:text-sm text-[#a1a1aa] font-sans mt-2">
              Static reference of repository trust tiers, snapshot digests, and fail-closed sandbox policies.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3 w-full sm:w-auto">
            {/* Import Repository Toggle Button */}
            <button
              id="toggle-import-button"
              type="button"
              onClick={() => setShowImportForm(!showImportForm)}
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 text-xs font-mono font-bold bg-[#13141b] hover:bg-[#1f202b] text-[#f4f4f5] px-3.5 py-2 rounded border border-[#353748] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#3b82f6]"
            >
              <span>{showImportForm ? '✕ Close Import' : '📥 Import Remote Repository'}</span>
            </button>

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

      {/* ================= OPTIONAL COLLAPSIBLE REPOSITORY IMPORT DRAWER ================= */}
      {showImportForm && (
        <section aria-labelledby="repo-import-drawer-heading" className="bg-[#0d0e12] border border-[#3b82f6]/40 p-5 rounded-lg shadow-xl space-y-4">
          <div className="flex items-center justify-between border-b border-[#222430] pb-2">
            <h2 id="repo-import-drawer-heading" className="text-xs font-bold text-[#f4f4f5] uppercase font-mono tracking-wider flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-[#3b82f6]"></span>
              <span>Import Public Remote Repository (Quarantine Boundary)</span>
            </h2>
            <span className="text-[10px] font-mono text-[#a1a1aa]">SSRF Protected • Enforces UNTRUSTED</span>
          </div>

          <form onSubmit={handleImportSubmit} className="grid grid-cols-1 md:grid-cols-12 gap-3 items-end">
            <div className="md:col-span-6">
              <label htmlFor="repo-page-url-input" className="block text-[11px] font-mono text-[#a1a1aa] uppercase mb-1">
                Repository HTTPS URL
              </label>
              <input
                id="repo-page-url-input"
                type="url"
                required
                placeholder="https://github.com/org/repo.git"
                value={importUrl}
                onChange={e => setImportUrl(e.target.value)}
                disabled={isImporting}
                className="w-full bg-[#13141b] border border-[#222430] rounded p-2 text-xs font-mono text-[#f4f4f5] focus:border-[#ef4444] focus-visible:outline-none"
              />
            </div>

            <div className="md:col-span-4">
              <label htmlFor="repo-page-commit-input" className="block text-[11px] font-mono text-[#a1a1aa] uppercase mb-1">
                Pinned Commit SHA (40/64 hex)
              </label>
              <input
                id="repo-page-commit-input"
                type="text"
                required
                placeholder="Full commit hash"
                value={importCommit}
                onChange={e => setImportCommit(e.target.value)}
                disabled={isImporting}
                maxLength={64}
                className="w-full bg-[#13141b] border border-[#222430] rounded p-2 text-xs font-mono text-[#f4f4f5] focus:border-[#ef4444] focus-visible:outline-none"
              />
            </div>

            <div className="md:col-span-2">
              <button
                type="submit"
                disabled={isImporting || !importUrl.trim() || !importCommit.trim()}
                className="w-full bg-[#2563eb] hover:bg-[#1d4ed8] text-white font-mono font-bold text-xs p-2 rounded transition-colors disabled:opacity-50"
              >
                {isImporting ? 'Quarantining...' : 'Import'}
              </button>
            </div>
          </form>

          {importError && (
            <div className="p-3 bg-[#ef4444]/15 border border-[#ef4444]/30 text-[#f87171] text-xs font-mono rounded" role="alert">
              <strong>Import Failed:</strong> {importError}
            </div>
          )}

          {importSuccess && (
            <div className="p-3 bg-[#10b981]/15 border border-[#10b981]/30 text-[#10b981] text-xs font-mono rounded flex items-center justify-between" role="status">
              <div>
                <strong>✓ Registered:</strong> Target ID <code className="font-bold text-white bg-[#09090b] px-1.5 py-0.5 rounded ml-1">{importSuccess.repository_id}</code> (Trust: UNTRUSTED)
              </div>
              <Link
                href={`/?repoId=${encodeURIComponent(importSuccess.repository_id)}`}
                className="bg-[#10b981] text-black font-bold px-3 py-1 rounded text-[11px] hover:bg-[#34d399] transition-colors"
              >
                Launch Verification Run →
              </Link>
            </div>
          )}
        </section>
      )}

      {/* ================= ARCHITECTURE REFERENCE NOTICE ================= */}
      <section aria-labelledby="architecture-reference-notice">
        <h2 id="architecture-reference-notice" className="sr-only">Static Architecture Reference Notice</h2>
        <div className="bg-[#0d0e12] border border-blue-900/60 p-4 rounded-lg text-xs text-blue-200/90 flex items-start gap-3.5 shadow-sm">
          <div className="w-5 h-5 rounded-full bg-blue-500/20 text-blue-400 flex items-center justify-center shrink-0 mt-0.5 border border-blue-500/30">
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="16" x2="12" y2="12" />
              <line x1="12" y1="8" x2="12.01" y2="8" />
            </svg>
          </div>
          <div className="space-y-1">
            <strong className="block text-blue-300 font-semibold tracking-wide">
              Static Architecture Reference:
            </strong>
            <p className="text-[#a1a1aa] text-[11px] leading-relaxed">
              The repository trust tiers, digests, and sandbox boundaries below are architectural specifications and baseline profiles.
              Dynamic repository registration and remote repository management APIs are enforced authoritatively by the backend cloner and sandbox.
            </p>
          </div>
        </div>
      </section>

      {/* ================= SECURITY BOUNDARY ENFORCEMENT ================= */}
      <section aria-labelledby="security-boundary-notice">
        <h2 id="security-boundary-notice" className="sr-only">Security Boundary Enforcement Notice</h2>
        <div className="bg-[#0d0e12] border border-red-900/60 p-4 rounded-lg text-xs text-red-200/90 space-y-1.5 shadow-sm">
          <div className="flex items-center gap-2 font-bold text-[#ef4444] tracking-wide">
            <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            </svg>
            <span>Security Boundary Enforcement (Section 47):</span>
          </div>
          <p className="text-[11px] text-[#a1a1aa] leading-relaxed">
            The frontend cannot elevate repository trust or authorize sandbox execution. Trust resolution is authoritatively calculated by <code className="text-[#fca5a5] font-mono">backend/sandbox/trust.py</code>. Untrusted repositories are fail-closed and blocked from host execution without isolated backend virtualization.
          </p>
        </div>
      </section>

      {/* ================= COMMAND SEARCH & FILTER CONTROLS ================= */}
      <section aria-labelledby="repo-filter-controls">
        <h2 id="repo-filter-controls" className="sr-only">Repository Filter and Search Controls</h2>
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
          {/* Monospace Command Search */}
          <div className="relative flex-1 max-w-lg">
            <label htmlFor="repo-search" className="sr-only">Search repositories</label>
            <span className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none font-mono text-[#ef4444] font-bold text-xs">
              &gt;
            </span>
            <input
              id="repo-search"
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search repositories by ID, role, policy, or digest..."
              className="w-full pl-7 pr-8 py-2 rounded bg-[#0d0e12] border border-[#222430] text-[#f4f4f5] placeholder:text-[#71717a] font-mono text-xs focus:border-[#ef4444] focus:outline-none transition-colors"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery('')}
                className="absolute inset-y-0 right-0 pr-2.5 flex items-center text-[#71717a] hover:text-[#f4f4f5]"
                aria-label="Clear repository search"
              >
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            )}
          </div>

          {/* Filter Tabs */}
          <div className="flex items-center gap-1.5 p-1 rounded bg-[#0d0e12] border border-[#222430] self-start sm:self-auto">
            <button
              onClick={() => setTrustFilter('ALL')}
              className={`px-3 py-1 rounded font-mono text-[11px] font-semibold transition-all ${
                trustFilter === 'ALL'
                  ? 'bg-[#13141b] text-[#f4f4f5] border border-[#353748] shadow-sm'
                  : 'text-[#a1a1aa] hover:text-[#f4f4f5]'
              }`}
            >
              All ({combinedRepositories.length})
            </button>
            <button
              onClick={() => setTrustFilter('TRUSTED')}
              className={`px-3 py-1 rounded font-mono text-[11px] font-semibold transition-all ${
                trustFilter === 'TRUSTED'
                  ? 'bg-[#10b981]/15 text-[#10b981] border border-[#10b981]/40 shadow-sm'
                  : 'text-[#a1a1aa] hover:text-[#10b981]'
              }`}
            >
              Trusted ({trustedCount})
            </button>
            <button
              onClick={() => setTrustFilter('UNTRUSTED')}
              className={`px-3 py-1 rounded font-mono text-[11px] font-semibold transition-all ${
                trustFilter === 'UNTRUSTED'
                  ? 'bg-[#ef4444]/15 text-[#f87171] border border-[#ef4444]/40 shadow-sm'
                  : 'text-[#a1a1aa] hover:text-[#f87171]'
              }`}
            >
              Untrusted ({untrustedCount})
            </button>
          </div>
        </div>
      </section>

      {/* ================= REPOSITORY INVENTORY TABLE ================= */}
      <section aria-labelledby="registered-repositories-heading">
        <div className="border border-[#222430] rounded-lg bg-[#0d0e12] shadow-xl overflow-hidden">
          <div className="p-4 border-b border-[#222430] bg-[#13141b]/60 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <svg className="w-4 h-4 text-[#ef4444]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
              <h2 id="registered-repositories-heading" className="text-xs font-bold text-[#f4f4f5] uppercase tracking-wider font-mono">
                Registered Target Repositories &amp; Policies ({filteredRepositories.length})
              </h2>
            </div>
            <div className="flex items-center gap-3">
              {isLoadingTargets && (
                <span className="text-[10px] font-mono text-[#a1a1aa]">Syncing dynamic targets...</span>
              )}
              <span className="text-[10px] font-mono text-[#71717a] hidden sm:inline-block">
                Authoritative Gate: backend/sandbox/trust.py
              </span>
            </div>
          </div>

          {filteredRepositories.length === 0 ? (
            <div className="p-10 text-center space-y-3">
              <p className="text-xs font-mono text-[#a1a1aa]">
                No repository policies match &ldquo;{searchQuery}&rdquo; under {trustFilter.toLowerCase()} filter.
              </p>
              <button
                onClick={() => {
                  setSearchQuery('');
                  setTrustFilter('ALL');
                }}
                className="text-xs font-mono text-[#ef4444] hover:underline"
              >
                Reset Search &amp; Filters
              </button>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-[#222430] bg-[#09090b] font-semibold text-[#a1a1aa] uppercase tracking-wider font-mono text-[10px]">
                    <th scope="col" className="p-3.5">Repository &amp; Role</th>
                    <th scope="col" className="p-3.5">Trust Tier</th>
                    <th scope="col" className="p-3.5">Sandbox Policy</th>
                    <th scope="col" className="p-3.5">Scope Gate</th>
                    <th scope="col" className="p-3.5">Path Traversal Gate</th>
                    <th scope="col" className="p-3.5">Snapshot Digest</th>
                    <th scope="col" className="p-3.5 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#222430]">
                  {filteredRepositories.map((repo) => {
                    const isTrusted = repo.trustLevel === 'TRUSTED';
                    const isCopied = copiedDigest === repo.snapshotDigest;

                    return (
                      <tr
                        key={repo.repositoryId}
                        className="hover:bg-[#13141b]/80 transition-colors group"
                      >
                        {/* Repository ID & Role */}
                        <td className="p-3.5 align-top">
                          <div className="space-y-1">
                            <div className="flex items-center gap-2">
                              <span className="font-mono font-bold text-[#ef4444] text-xs">
                                {repo.repositoryId}
                              </span>
                              <span className="inline-flex items-center gap-1 px-1.5 py-0.2 rounded bg-[#13141b] border border-[#222430] font-mono text-[10px] text-[#71717a]">
                                <svg className="w-2.5 h-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                  <path strokeLinecap="round" strokeLinejoin="round" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                                </svg>
                                {repo.defaultBranch}
                              </span>
                            </div>
                            <p className="text-[11px] text-[#a1a1aa] font-sans">
                              {repo.fixtureRole}
                            </p>
                          </div>
                        </td>

                        {/* Trust Tier */}
                        <td className="p-3.5 align-top">
                          <span
                            className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[10px] font-mono font-bold border ${
                              isTrusted
                                ? 'bg-[#10b981]/10 text-[#10b981] border-[#10b981]/30'
                                : 'bg-[#ef4444]/10 text-[#f87171] border-[#ef4444]/30'
                            }`}
                          >
                            <span className={`w-1.5 h-1.5 rounded-full ${isTrusted ? 'bg-[#10b981]' : 'bg-[#ef4444]'}`} />
                            {repo.trustLevel}
                          </span>
                        </td>

                        {/* Sandbox Policy */}
                        <td className="p-3.5 align-top">
                          <span className="font-mono text-[11px] text-[#e5e1e4] leading-relaxed block max-w-xs">
                            {repo.sandboxPolicy}
                          </span>
                        </td>

                        {/* Scope Enforcement */}
                        <td className="p-3.5 align-top">
                          <span className="font-mono text-[11px] text-[#a1a1aa] leading-relaxed block max-w-xs">
                            {repo.scopeEnforcement}
                          </span>
                        </td>

                        {/* Path Traversal Gate */}
                        <td className="p-3.5 align-top">
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-[#13141b] border border-[#222430] font-mono text-[10px] text-[#fca5a5]">
                            <svg className="w-3 h-3 text-[#ef4444]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                              <path strokeLinecap="round" strokeLinejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                            </svg>
                            {repo.pathTraversalGate}
                          </span>
                        </td>

                        {/* Snapshot Digest */}
                        <td className="p-3.5 align-top font-mono text-[11px]">
                          <div className="flex items-center gap-1.5">
                            <span 
                              className="text-[#71717a] truncate max-w-[100px]" 
                              title={repo.snapshotDigest}
                            >
                              {repo.snapshotDigest.substring(0, 16)}&hellip;
                            </span>
                            <button
                              onClick={() => handleCopyDigest(repo.snapshotDigest)}
                              className="text-[#71717a] hover:text-[#f4f4f5] p-1 rounded hover:bg-[#13141b] transition-colors"
                              title={isCopied ? "Copied full SHA-256 hash!" : "Copy SHA-256 hash"}
                              aria-label={`Copy digest for ${repo.repositoryId}`}
                            >
                              {isCopied ? (
                                <span className="text-[10px] text-[#10b981] font-mono font-bold">✓</span>
                              ) : (
                                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                  <path strokeLinecap="round" strokeLinejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                                </svg>
                              )}
                            </button>
                          </div>
                        </td>

                        {/* Action: Dispatch Task */}
                        <td className="p-3.5 align-top text-right">
                          <Link
                            href={`/?repoId=${encodeURIComponent(repo.repositoryId)}`}
                            className="inline-flex items-center gap-1 text-[11px] font-mono font-bold text-[#ef4444] hover:text-[#f87171] hover:underline"
                          >
                            <span>Verify</span>
                            <span aria-hidden="true">&rarr;</span>
                          </Link>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
