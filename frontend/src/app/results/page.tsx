"use client";

import React, { useState, useEffect, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { apiClient } from '@/api/client';
import { RunStatus, RunHistoryItem } from '@/models/types';
import { VerdictDisplay } from '@/components/VerdictDisplay';
import { JudgeExplanationView } from '@/components/JudgeExplanationView';
import { DiffViewer } from '@/components/DiffViewer';

function ResultsContent() {
  const searchParams = useSearchParams();
  const initialRunId = searchParams.get('runId') || '';

  const [selectedRunId, setSelectedRunId] = useState<string>(initialRunId);
  const [inputRunId, setInputRunId] = useState<string>(initialRunId);
  const [status, setStatus] = useState<RunStatus | null>(null);
  const [history, setHistory] = useState<RunHistoryItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(Boolean(initialRunId));
  const [error, setError] = useState<string | null>(null);

  // Load history for quick selection
  useEffect(() => {
    let ignore = false;
    apiClient.getRunHistory().then((data) => {
      if (!ignore) {
        setHistory(data);
        if (!initialRunId && data.length > 0) {
          const latest = data[data.length - 1].run_id;
          setIsLoading(true);
          setSelectedRunId(latest);
          setInputRunId(latest);
        }
      }
    }).catch(() => {});
    return () => {
      ignore = true;
    };
  }, [initialRunId]);

  useEffect(() => {
    if (!selectedRunId.trim()) return;
    let ignore = false;
    setIsLoading(true);

    apiClient.getRunStatus(selectedRunId.trim()).then((data) => {
      if (!ignore) {
        setStatus(data);
        setError(null);
        setIsLoading(false);
      }
    }).catch((err: unknown) => {
      if (!ignore) {
        setError(err instanceof Error ? err.message : String(err));
        setStatus(null);
        setIsLoading(false);
      }
    });

    return () => {
      ignore = true;
    };
  }, [selectedRunId]);

  const handleSelectRun = (id: string) => {
    setIsLoading(true);
    setSelectedRunId(id);
    setInputRunId(id);
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (inputRunId.trim()) {
      handleSelectRun(inputRunId.trim());
    }
  };

  const verdict = status?.evidence_receipt?.verdict || status?.evidence_receipt?.deterministic_verdict || null;
  const receipt = status?.evidence_receipt;
  const judge = status?.judge_explanation;

  return (
    <div className="space-y-6">
      {/* Monospace Subheader */}
      <header className="border-b border-[#222430] pb-5">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div>
            <div className="flex items-center gap-2 font-mono text-[11px] text-slate-500 mb-1">
              <span>ORCHESTRATION</span>
              <span>//</span>
              <span className="text-slate-400">RUN_ANALYSIS</span>
              <span>//</span>
              <span className="text-[#ef4444] font-semibold">VERDICT_RESULTS</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-black tracking-tight text-white flex items-center gap-3">
              <span>07. Run Verification Results</span>
              <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-[#13141b] border border-[#222430] text-slate-400">
                v2.4-deterministic
              </span>
            </h1>
            <p className="text-xs text-slate-400 font-mono mt-1">
              Authoritative deterministic verification outcomes, operational execution status, and candidate patch audit.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <Link
              href="/"
              className="text-xs font-mono font-bold bg-[#ef4444] hover:bg-[#dc2626] text-white px-3 py-2 rounded-md transition-colors shadow-sm"
            >
              + New Task Contract
            </Link>
          </div>
        </div>
      </header>

      {/* Selector & Quick Switcher Bar */}
      <div className="bg-[#0d0e12] border border-[#222430] p-4 rounded-lg flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4">
        <form onSubmit={handleSearchSubmit} className="flex gap-2 flex-1 max-w-md">
          <input
            type="text"
            placeholder="Enter Run ID (e.g. run-1234)"
            value={inputRunId}
            onChange={(e) => setInputRunId(e.target.value)}
            className="bg-[#13141b] border border-[#222430] p-2 rounded-md flex-1 text-xs font-mono text-slate-100 placeholder:text-slate-600 focus-visible:ring-2 focus-visible:ring-[#ef4444] focus-visible:outline-none"
            aria-label="Search Run ID for Results"
          />
          <button
            type="submit"
            disabled={isLoading || !inputRunId.trim()}
            className="bg-[#1a1b24] hover:bg-[#222430] text-slate-200 border border-[#222430] px-4 py-2 rounded-md text-xs font-semibold font-mono transition-colors disabled:opacity-50"
          >
            {isLoading ? 'Loading...' : 'Inspect'}
          </button>
        </form>

        {history.length > 0 && (
          <div className="flex items-center gap-2 text-xs">
            <span className="text-slate-500 font-mono">Select Run:</span>
            <select
              value={selectedRunId}
              onChange={(e) => handleSelectRun(e.target.value)}
              className="bg-[#13141b] border border-[#222430] text-slate-300 text-xs font-mono rounded-md p-2 focus-visible:ring-2 focus-visible:ring-[#ef4444] focus-visible:outline-none max-w-xs truncate"
              aria-label="Select past run for results"
            >
              {history.map((h) => (
                <option key={h.run_id} value={h.run_id}>
                  {h.run_id} — {h.task_id} ({h.verdict || h.final_state})
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      {isLoading && (
        <div className="p-12 text-center text-xs font-mono text-slate-400 bg-[#0d0e12] border border-[#222430] rounded-lg" role="status">
          <span className="inline-block motion-safe:animate-spin mr-2">◷</span>
          Retrieving authoritative run status and verification verdict...
        </div>
      )}

      {error && !isLoading && (
        <div className="p-4 bg-rose-950/30 text-rose-300 border border-rose-800 rounded-lg text-xs font-mono" role="alert">
          <strong className="block mb-1 text-rose-400">Inspection Error:</strong>
          <span>{error}</span>
          <p className="mt-2 text-[11px] text-slate-400">
            Please verify the Run ID. You can choose any completed or historical run from the dropdown above.
          </p>
        </div>
      )}

      {status && !isLoading && (
        <div className="space-y-6">
          {/* Authoritative Deterministic Verdict Banner */}
          <VerdictDisplay
            verdict={verdict}
            error={status.operational_error}
            lifecycleState={status.state}
          />

          {/* Technical Summary Meta Grid */}
          <div className="bg-[#0d0e12] border border-[#222430] p-5 rounded-lg grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs font-mono">
            <div className="bg-[#13141b] p-3 rounded border border-[#222430]">
              <span className="text-slate-500 block text-[10px] uppercase">Run Identifier</span>
              <span className="font-bold text-[#ef4444] select-all truncate block">{status.run_id}</span>
            </div>
            <div className="bg-[#13141b] p-3 rounded border border-[#222430]">
              <span className="text-slate-500 block text-[10px] uppercase">Target Task</span>
              <span className="font-bold text-slate-200 truncate block">{status.task_id}</span>
            </div>
            <div className="bg-[#13141b] p-3 rounded border border-[#222430]">
              <span className="text-slate-500 block text-[10px] uppercase">Lifecycle State</span>
              <span className="font-bold text-slate-200">{status.state}</span>
            </div>
            <div className="bg-[#13141b] p-3 rounded border border-[#222430]">
              <span className="text-slate-500 block text-[10px] uppercase">Iterations Used</span>
              <span className="font-bold text-slate-200">
                {status.iteration} / {status.resource_status?.iterations_limit ?? 20}
              </span>
            </div>
          </div>

          {/* Verification Scope & Evidence Quick Highlights (if receipt attached) */}
          {receipt && (
            <div className="bg-[#0d0e12] border border-[#222430] p-5 rounded-lg space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#222430] pb-3">
                <div>
                  <h2 className="font-mono text-xs font-bold text-white uppercase tracking-wider">
                    Authoritative Verification Scope &amp; Proof Summary
                  </h2>
                  <span className="text-slate-500 text-[11px] font-mono">
                    Compiled by EvidenceBuilder upon verification conclusion
                  </span>
                </div>
                <Link
                  href={`/evidence?runId=${encodeURIComponent(status.run_id)}`}
                  className="text-xs font-mono text-[#ef4444] hover:text-[#ff6b6b] flex items-center gap-1 font-semibold"
                >
                  <span>Audit Full Cryptographic Bundle →</span>
                </Link>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs font-mono">
                <div className="p-3 bg-[#13141b] rounded border border-[#222430]">
                  <span className="text-[10px] text-slate-500 block uppercase">Tests Executed</span>
                  <span className="text-base font-bold text-white">{receipt.test_summary?.executed ?? 0}</span>
                </div>
                <div className="p-3 bg-[#13141b] rounded border border-[#222430]">
                  <span className="text-[10px] text-slate-500 block uppercase">Tests Passed</span>
                  <span className="text-base font-bold text-emerald-400">{receipt.test_summary?.passed ?? 0}</span>
                </div>
                <div className="p-3 bg-[#13141b] rounded border border-[#222430]">
                  <span className="text-[10px] text-slate-500 block uppercase">Tests Failed</span>
                  <span className="text-base font-bold text-rose-400">{receipt.test_summary?.failed ?? 0}</span>
                </div>
                <div className="p-3 bg-[#13141b] rounded border border-[#222430]">
                  <span className="text-[10px] text-slate-500 block uppercase">Counterexamples</span>
                  <span className={`text-base font-bold ${receipt.counterexamples?.length ? 'text-rose-400' : 'text-emerald-400'}`}>
                    {receipt.counterexamples?.length ?? 0}
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Subordinate Judge Explanation */}
          {judge && (
            <JudgeExplanationView explanation={judge} />
          )}

          {/* Diff Viewer for candidate patch */}
          <DiffViewer runId={status.run_id} />

          {/* Multi-Destination Action Navigation Bar */}
          <div className="bg-[#0d0e12] border border-[#222430] p-4 rounded-lg flex flex-wrap items-center justify-between gap-4 text-xs font-mono">
            <div className="text-slate-400">
              Explore execution milestones in Mission Control or examine cryptographic receipts:
            </div>
            <div className="flex items-center gap-2">
              <Link
                href={`/sessions?runId=${encodeURIComponent(status.run_id)}`}
                className="bg-[#1a1b24] hover:bg-[#222430] text-slate-200 px-3 py-1.5 rounded border border-[#222430] transition-colors"
              >
                🛰️ Mission Control
              </Link>
              <Link
                href={`/evidence?runId=${encodeURIComponent(status.run_id)}`}
                className="bg-[#ef4444] hover:bg-[#dc2626] text-white font-bold px-3 py-1.5 rounded transition-colors shadow-sm"
              >
                🛡️ Audit Evidence Receipts →
              </Link>
            </div>
          </div>
        </div>
      )}

      {!selectedRunId && !isLoading && (
        <div className="p-12 text-center text-xs text-slate-500 bg-[#0d0e12] rounded-lg border border-dashed border-[#222430]">
          <p className="font-semibold text-slate-400">No Run Selected</p>
          <p className="mt-1">Enter a Run ID above or select from history to review verification verdicts.</p>
        </div>
      )}
    </div>
  );
}

export default function ResultsPage() {
  return (
    <Suspense fallback={
      <div className="p-12 text-center text-xs font-mono text-slate-500 bg-[#0d0e12] border border-[#222430] rounded-lg">
        Loading Run Results...
      </div>
    }>
      <ResultsContent />
    </Suspense>
  );
}
