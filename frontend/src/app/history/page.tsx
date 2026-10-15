"use client";

import React, { useEffect, useState, useCallback, useMemo } from 'react';
import Link from 'next/link';
import { apiClient } from '@/api/client';
import { RunHistoryItem } from '@/models/types';

export default function SessionHistoryPage() {
  const [history, setHistory] = useState<RunHistoryItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [verdictFilter, setVerdictFilter] = useState<string>('ALL');
  const [copiedRunId, setCopiedRunId] = useState<string | null>(null);

  const fetchHistory = useCallback(async () => {
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
  }, []);

  useEffect(() => {
    let ignore = false;
    apiClient.getRunHistory().then((data) => {
      if (!ignore) {
        setHistory(data);
        setIsLoading(false);
      }
    }).catch((err: unknown) => {
      if (!ignore) {
        setError(err instanceof Error ? err.message : String(err));
        setIsLoading(false);
      }
    });
    return () => {
      ignore = true;
    };
  }, []);

  const copyRunId = (id: string) => {
    if (typeof navigator !== 'undefined' && navigator.clipboard) {
      navigator.clipboard.writeText(id).catch(() => {});
      setCopiedRunId(id);
      setTimeout(() => setCopiedRunId(null), 2000);
    }
  };

  // Metric counts derived strictly from genuine records
  const totalCount = history.length;
  const verifiedCount = history.filter((r) => r.verdict === 'VERIFIED').length;
  const rejectedCount = history.filter((r) => r.verdict === 'REJECTED').length;
  const inconclusiveCount = history.filter((r) => r.verdict === 'INCONCLUSIVE').length;
  const pendingCount = history.filter((r) => !r.verdict).length;

  const filteredHistory = useMemo(() => {
    return history.filter((item) => {
      const matchesSearch = 
        item.run_id.toLowerCase().includes(searchTerm.toLowerCase()) ||
        item.task_id.toLowerCase().includes(searchTerm.toLowerCase()) ||
        String(item.final_state).toLowerCase().includes(searchTerm.toLowerCase());

      if (!matchesSearch) return false;

      if (verdictFilter === 'ALL') return true;
      if (verdictFilter === 'VERIFIED') return item.verdict === 'VERIFIED';
      if (verdictFilter === 'REJECTED') return item.verdict === 'REJECTED';
      if (verdictFilter === 'INCONCLUSIVE') return item.verdict === 'INCONCLUSIVE';
      if (verdictFilter === 'PENDING') return !item.verdict;

      return true;
    });
  }, [history, searchTerm, verdictFilter]);

  return (
    <div className="space-y-6">
      {/* Monospace Subheader */}
      <header className="border-b border-[#222430] pb-5">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div>
            <div className="flex items-center gap-2 font-mono text-[11px] text-slate-500 mb-1">
              <span>AUDIT</span>
              <span>//</span>
              <span className="text-slate-400">RUN_REPOSITORIES</span>
              <span>//</span>
              <span className="text-[#ef4444] font-semibold">VERIFICATION_LEDGER</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-black tracking-tight text-white flex items-center gap-3">
              <span>09. Verification History &amp; Audit Ledger</span>
              <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-[#13141b] border border-[#222430] text-slate-400">
                Immutable Records
              </span>
            </h1>
            <p className="text-xs text-slate-400 font-mono mt-1">
              Searchable chronological record of all executed verification pipelines and deterministic findings.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <Link
              href="/"
              className="text-xs font-mono font-bold bg-[#ef4444] hover:bg-[#dc2626] text-white px-3 py-2 rounded-md transition-colors shadow-sm"
            >
              + Launch Verification
            </Link>
            <button
              type="button"
              onClick={fetchHistory}
              disabled={isLoading}
              className="text-xs text-slate-300 hover:text-white bg-[#13141b] hover:bg-[#1a1b24] border border-[#222430] px-3 py-2 rounded-md transition-colors disabled:opacity-50 font-mono"
            >
              {isLoading ? 'Refreshing...' : '↻ Refresh Ledger'}
            </button>
          </div>
        </div>
      </header>

      {/* Top Telemetry Ribbon (Truthful, non-fabricated metrics from SQLite) */}
      <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4" aria-label="Ledger Telemetry">
        <div className="p-4 rounded-lg bg-[#0d0e12] border border-[#222430]">
          <div className="flex justify-between items-start mb-1">
            <span className="font-mono text-[10px] text-slate-500 uppercase tracking-wider">Total Pipeline Runs</span>
            <span className="text-slate-400 text-xs">📊</span>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-black text-white">{totalCount}</span>
            <span className="text-xs font-mono text-slate-400">records in database</span>
          </div>
          <div className="mt-2 text-[10px] font-mono text-slate-500 flex items-center justify-between">
            <span>Authoritative SQLite table</span>
            <span className="text-slate-400">GET /api/v1/runs</span>
          </div>
        </div>

        <div className="p-4 rounded-lg bg-[#0d0e12] border border-[#222430]">
          <div className="flex justify-between items-start mb-1">
            <span className="font-mono text-[10px] text-slate-500 uppercase tracking-wider">Verified Sound</span>
            <span className="text-emerald-400 text-xs">✓</span>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-black text-emerald-400">{verifiedCount}</span>
            <span className="text-xs font-mono text-slate-400">runs passed</span>
          </div>
          <div className="mt-2 text-[10px] font-mono text-slate-500 flex items-center justify-between">
            <span>Deterministic Oracle Proof</span>
            <span className="text-emerald-400 font-semibold">
              {totalCount > 0 ? `${((verifiedCount / totalCount) * 100).toFixed(0)}%` : '0%'}
            </span>
          </div>
        </div>

        <div className="p-4 rounded-lg bg-[#0d0e12] border border-[#222430]">
          <div className="flex justify-between items-start mb-1">
            <span className="font-mono text-[10px] text-slate-500 uppercase tracking-wider">Rejected Unsound</span>
            <span className="text-rose-400 text-xs">✕</span>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-black text-rose-400">{rejectedCount}</span>
            <span className="text-xs font-mono text-slate-400">counterexamples found</span>
          </div>
          <div className="mt-2 text-[10px] font-mono text-slate-500 flex items-center justify-between">
            <span>Neutralized vulnerabilities</span>
            <span className="text-rose-400 font-semibold">Blocked</span>
          </div>
        </div>

        <div className="p-4 rounded-lg bg-[#0d0e12] border border-[#222430]">
          <div className="flex justify-between items-start mb-1">
            <span className="font-mono text-[10px] text-slate-500 uppercase tracking-wider">Inconclusive / Active</span>
            <span className="text-amber-400 text-xs">⚠</span>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-black text-amber-400">{inconclusiveCount + pendingCount}</span>
            <span className="text-xs font-mono text-slate-400">need review / in-flight</span>
          </div>
          <div className="mt-2 text-[10px] font-mono text-slate-500 flex items-center justify-between">
            <span>{pendingCount} in flight</span>
            <span className="text-amber-400">{inconclusiveCount} inconclusive</span>
          </div>
        </div>
      </section>

      {/* Filter and Search Bar */}
      <div className="bg-[#0d0e12] border border-[#222430] p-4 rounded-lg flex flex-col md:flex-row gap-4 items-stretch md:items-center justify-between text-xs">
        <div className="flex-1 max-w-md relative">
          <input
            type="text"
            placeholder="Search by Run ID, Task ID, or State..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full bg-[#13141b] border border-[#222430] p-2.5 rounded-md font-mono text-xs text-slate-100 placeholder:text-slate-600 focus-visible:ring-2 focus-visible:ring-[#ef4444] focus-visible:outline-none"
            aria-label="Filter runs by query"
          />
          {searchTerm && (
            <button
              type="button"
              onClick={() => setSearchTerm('')}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-white font-mono text-xs"
              aria-label="Clear search"
            >
              ✕
            </button>
          )}
        </div>

        {/* Verdict Filter Tabs */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 md:pb-0" role="tablist" aria-label="Verdict filters">
          <button
            type="button"
            onClick={() => setVerdictFilter('ALL')}
            className={`px-3 py-1.5 rounded text-xs font-mono transition-colors ${
              verdictFilter === 'ALL'
                ? 'bg-[#ef4444] text-white font-bold'
                : 'bg-[#13141b] text-slate-400 hover:text-white border border-[#222430]'
            }`}
          >
            All ({totalCount})
          </button>
          <button
            type="button"
            onClick={() => setVerdictFilter('VERIFIED')}
            className={`px-3 py-1.5 rounded text-xs font-mono transition-colors ${
              verdictFilter === 'VERIFIED'
                ? 'bg-emerald-600 text-white font-bold'
                : 'bg-[#13141b] text-slate-400 hover:text-white border border-[#222430]'
            }`}
          >
            Verified ({verifiedCount})
          </button>
          <button
            type="button"
            onClick={() => setVerdictFilter('REJECTED')}
            className={`px-3 py-1.5 rounded text-xs font-mono transition-colors ${
              verdictFilter === 'REJECTED'
                ? 'bg-rose-600 text-white font-bold'
                : 'bg-[#13141b] text-slate-400 hover:text-white border border-[#222430]'
            }`}
          >
            Rejected ({rejectedCount})
          </button>
          <button
            type="button"
            onClick={() => setVerdictFilter('INCONCLUSIVE')}
            className={`px-3 py-1.5 rounded text-xs font-mono transition-colors ${
              verdictFilter === 'INCONCLUSIVE'
                ? 'bg-amber-600 text-white font-bold'
                : 'bg-[#13141b] text-slate-400 hover:text-white border border-[#222430]'
            }`}
          >
            Inconclusive ({inconclusiveCount})
          </button>
          <button
            type="button"
            onClick={() => setVerdictFilter('PENDING')}
            className={`px-3 py-1.5 rounded text-xs font-mono transition-colors ${
              verdictFilter === 'PENDING'
                ? 'bg-blue-600 text-white font-bold'
                : 'bg-[#13141b] text-slate-400 hover:text-white border border-[#222430]'
            }`}
          >
            In-Flight ({pendingCount})
          </button>
        </div>
      </div>

      {error && (
        <div className="p-4 bg-rose-950/30 text-rose-300 border border-rose-800 rounded-lg text-xs font-mono flex items-center justify-between" role="alert">
          <div>
            <strong className="block mb-1 text-rose-400">Error Loading Session History:</strong>
            <span>{error}</span>
          </div>
          <button
            type="button"
            onClick={fetchHistory}
            className="px-3 py-1 bg-rose-900/60 hover:bg-rose-800 text-white rounded text-xs font-mono"
          >
            Retry Fetch
          </button>
        </div>
      )}

      {/* High-Density Ledger Table */}
      <div className="border border-[#222430] rounded-lg bg-[#0d0e12] shadow-lg overflow-hidden">
        {isLoading && history.length === 0 ? (
          <div className="py-16 text-center text-xs font-mono text-slate-500" role="status">
            <span className="inline-block motion-safe:animate-spin mr-2">◷</span>
            Fetching session history from backend...
          </div>
        ) : filteredHistory.length === 0 ? (
          <div className="py-16 text-center text-xs font-mono text-slate-500 bg-[#090a0f]">
            <p className="font-semibold text-slate-400">No matching runs found.</p>
            <p className="mt-1 text-[11px] text-slate-600">
              {history.length === 0 ? "Submit a task contract to record your first run." : "Try adjusting your search query or verdict filter."}
            </p>
            {(searchTerm || verdictFilter !== 'ALL') && (
              <button
                type="button"
                onClick={() => { setSearchTerm(''); setVerdictFilter('ALL'); }}
                className="mt-3 px-3 py-1.5 rounded bg-[#13141b] hover:bg-[#1a1b24] border border-[#222430] text-slate-300 text-xs font-mono transition-colors"
              >
                Reset Filters
              </button>
            )}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse font-mono">
              <thead>
                <tr className="border-b border-[#222430] bg-[#101117] font-semibold text-slate-400 uppercase tracking-wider text-[10px]">
                  <th scope="col" className="p-3 pl-4">Run ID</th>
                  <th scope="col" className="p-3">Target Task</th>
                  <th scope="col" className="p-3">Lifecycle State</th>
                  <th scope="col" className="p-3">Deterministic Verdict</th>
                  <th scope="col" className="p-3">Created</th>
                  <th scope="col" className="p-3">Completed</th>
                  <th scope="col" className="p-3 pr-4 text-right">Audit Destinations</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#1b1c26] text-slate-300">
                {filteredHistory.map((run) => (
                  <tr
                    key={run.run_id}
                    className="hover:bg-[#13141b] transition-colors"
                  >
                    <td className="p-3 pl-4 font-bold text-[#ef4444]">
                      <div className="flex items-center gap-2">
                        <Link
                          href={`/results?runId=${encodeURIComponent(run.run_id)}`}
                          className="hover:underline select-all"
                        >
                          {run.run_id}
                        </Link>
                        <button
                          type="button"
                          onClick={() => copyRunId(run.run_id)}
                          className="text-slate-600 hover:text-white text-[10px]"
                          title="Copy Run ID"
                        >
                          {copiedRunId === run.run_id ? '✓' : '⧉'}
                        </button>
                      </div>
                    </td>
                    <td className="p-3 text-slate-300 truncate max-w-[170px]" title={run.task_id}>
                      {run.task_id}
                    </td>
                    <td className="p-3">
                      <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-bold border ${
                        run.final_state === 'VERIFIED' ? 'bg-emerald-950/40 text-emerald-300 border-emerald-800/60' :
                        run.final_state === 'ABORTED' ? 'bg-rose-950/40 text-rose-300 border-rose-800/60' :
                        'bg-blue-950/40 text-blue-300 border-blue-800/60'
                      }`}>
                        {run.final_state}
                      </span>
                    </td>
                    <td className="p-3 font-bold">
                      {run.verdict ? (
                        <span className={`inline-block px-2 py-0.5 rounded text-[10px] border ${
                          run.verdict === 'VERIFIED' ? 'bg-emerald-950/60 text-emerald-300 border-emerald-700/70' :
                          run.verdict === 'REJECTED' ? 'bg-rose-950/60 text-rose-300 border-rose-700/70' :
                          'bg-amber-950/60 text-amber-300 border-amber-700/70'
                        }`}>
                          {run.verdict === 'VERIFIED' ? '✓ ' : run.verdict === 'REJECTED' ? '✕ ' : '⚠ '}
                          {run.verdict}
                        </span>
                      ) : (
                        <span className="text-slate-600 font-normal">— PENDING</span>
                      )}
                    </td>
                    <td className="p-3 text-slate-400 text-[11px] whitespace-nowrap">
                      {run.created_at ? new Date(run.created_at).toLocaleString() : 'N/A'}
                    </td>
                    <td className="p-3 text-slate-500 text-[11px] whitespace-nowrap">
                      {run.completed_at ? new Date(run.completed_at).toLocaleTimeString() : '—'}
                    </td>
                    <td className="p-3 pr-4 text-right whitespace-nowrap">
                      <div className="flex items-center justify-end gap-1.5">
                        <Link
                          href={`/sessions?runId=${encodeURIComponent(run.run_id)}`}
                          className="text-[11px] bg-[#1a1b24] hover:bg-[#222430] text-slate-300 hover:text-white px-2 py-1 rounded border border-[#222430] transition-colors"
                          title="View in Mission Control"
                        >
                          🛰️ Sessions
                        </Link>
                        <Link
                          href={`/results?runId=${encodeURIComponent(run.run_id)}`}
                          className="text-[11px] bg-[#1a1b24] hover:bg-[#222430] text-slate-300 hover:text-white px-2 py-1 rounded border border-[#222430] transition-colors"
                          title="View Verdict"
                        >
                          ⚖️ Results
                        </Link>
                        <Link
                          href={`/evidence?runId=${encodeURIComponent(run.run_id)}`}
                          className="text-[11px] bg-[#1a1b24] hover:bg-[#222430] text-slate-300 hover:text-white px-2 py-1 rounded border border-[#222430] transition-colors"
                          title="Audit Cryptographic Evidence"
                        >
                          🛡️ Evidence
                        </Link>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
