"use client";

import React, { useState, useEffect, useRef, Suspense, useMemo } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { apiClient } from '@/api/client';
import { RunStatus, RunHistoryItem, RunState } from '@/models/types';
import { ResourceBudgetNotice } from '@/components/ResourceBudgetNotice';
import { VerdictDisplay } from '@/components/VerdictDisplay';
import { LIFECYCLE_STAGES } from '@/components/OrchestrationVisualizer';
import { 
  evaluatePollingSuccess, 
  evaluatePollingError, 
  isRequestCurrent,
  POLLING_INTERVAL_MS,
  MAX_POLLING_DURATION_MS
} from '@/app/page';

function SessionsContent() {
  const searchParams = useSearchParams();
  const initialRunId = searchParams.get('runId') || '';

  const [selectedRunId, setSelectedRunId] = useState<string>(initialRunId);
  const [inputRunId, setInputRunId] = useState<string>(initialRunId);
  const [status, setStatus] = useState<RunStatus | null>(null);
  const [history, setHistory] = useState<RunHistoryItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [connectionAlert, setConnectionAlert] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'timeline' | 'diff' | 'policy'>('timeline');

  const selectedRunIdRef = useRef<string>(initialRunId);
  const abortControllerRef = useRef<AbortController | null>(null);
  const activePollingStartTimeRef = useRef<number | null>(null);
  const consecutiveFailuresRef = useRef<number>(0);
  const isPollingInFlightRef = useRef<boolean>(false);

  // Fetch available runs for the selector dropdown
  useEffect(() => {
    let isMounted = true;
    apiClient.getRunHistory().then((data) => {
      if (!isMounted) return;
      setHistory(data);
      // Auto-select latest run if no run specified in URL
      if (!initialRunId && data.length > 0) {
        const latest = data[data.length - 1].run_id;
        setSelectedRunId(latest);
        setInputRunId(latest);
      }
    }).catch(() => {});

    return () => {
      isMounted = false;
    };
  }, [initialRunId]);

  // Fetch run status when selectedRunId changes
  useEffect(() => {
    if (!selectedRunId) {
      setStatus(null);
      return;
    }
    const target = selectedRunId.trim();
    if (!target) return;

    selectedRunIdRef.current = target;
    activePollingStartTimeRef.current = Date.now();
    consecutiveFailuresRef.current = 0;
    setIsLoading(true);
    setError(null);
    setConnectionAlert(null);

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    apiClient.getRunStatus(target, controller.signal).then((data) => {
      if (isRequestCurrent(target, selectedRunIdRef.current)) {
        setStatus(data);
        setError(null);
        setIsLoading(false);
      }
    }).catch((err: unknown) => {
      if (!controller.signal.aborted && isRequestCurrent(target, selectedRunIdRef.current)) {
        const errorMsg = err instanceof Error ? err.message : String(err);
        setError(errorMsg);
        setStatus(null);
        setIsLoading(false);
      }
    });

    return () => {
      controller.abort();
    };
  }, [selectedRunId]);

  // Polling effect for active runs
  useEffect(() => {
    const currentRunId = selectedRunId.trim();
    if (!currentRunId || !status || status.status !== 'active' || selectedRunIdRef.current !== currentRunId) {
      activePollingStartTimeRef.current = null;
      isPollingInFlightRef.current = false;
      return;
    }

    if (!activePollingStartTimeRef.current) {
      activePollingStartTimeRef.current = Date.now();
    }

    let isCleanedUp = false;

    const intervalId = setInterval(async () => {
      const elapsedMs = Date.now() - (activePollingStartTimeRef.current || Date.now());
      if (elapsedMs > MAX_POLLING_DURATION_MS) {
        clearInterval(intervalId);
        if (!isCleanedUp && isRequestCurrent(currentRunId, selectedRunIdRef.current)) {
          setConnectionAlert("Operational alert: Polling upper limit (5 minutes) reached. Polling stopped.");
        }
        return;
      }

      if (isPollingInFlightRef.current) return;
      if (!isRequestCurrent(currentRunId, selectedRunIdRef.current) || isCleanedUp) {
        clearInterval(intervalId);
        return;
      }

      isPollingInFlightRef.current = true;

      try {
        const latest = await apiClient.getRunStatus(currentRunId);
        if (isCleanedUp || !isRequestCurrent(currentRunId, selectedRunIdRef.current)) return;

        const evalResult = evaluatePollingSuccess(latest, consecutiveFailuresRef.current);
        consecutiveFailuresRef.current = evalResult.nextConsecutiveFailures;
        setStatus(latest);

        if (evalResult.shouldStop) {
          clearInterval(intervalId);
        }
      } catch (err: unknown) {
        if (isCleanedUp || !isRequestCurrent(currentRunId, selectedRunIdRef.current)) return;

        const evalResult = evaluatePollingError(err, currentRunId, consecutiveFailuresRef.current);
        consecutiveFailuresRef.current = evalResult.nextConsecutiveFailures;

        if (evalResult.shouldStop) {
          clearInterval(intervalId);
          if (evalResult.alertMessage) {
            setConnectionAlert(evalResult.alertMessage);
          }
        }
      } finally {
        isPollingInFlightRef.current = false;
      }
    }, POLLING_INTERVAL_MS);

    return () => {
      isCleanedUp = true;
      clearInterval(intervalId);
      isPollingInFlightRef.current = false;
    };
  }, [selectedRunId, status]);

  const handleSelectRun = (id: string) => {
    setSelectedRunId(id);
    setInputRunId(id);
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (inputRunId.trim()) {
      handleSelectRun(inputRunId.trim());
    }
  };

  // Derive execution event timeline from genuine persisted data
  const timelineEvents = useMemo(() => {
    if (!status) return [];
    const events: { label: string; text: string; time: string; type: 'info' | 'success' | 'warn' | 'error' | 'active' }[] = [];

    // Run Initialization
    events.push({
      label: 'INIT',
      text: `Task submitted with contract ID: ${status.task_id}. Initialized state machine in INIT.`,
      time: status.started_at ? new Date(status.started_at).toLocaleTimeString() : '00:00:00',
      type: 'info'
    });

    // Resource budget status
    events.push({
      label: 'BUDGET',
      text: `Resource ceiling configured: Max ${status.resource_status.iterations_limit} iterations, ${status.resource_status.tool_calls_limit || 100} tool calls. Current iteration: ${status.iteration}.`,
      time: status.started_at ? new Date(status.started_at).toLocaleTimeString() : '00:00:00',
      type: 'info'
    });

    // Patch Candidate
    if (status.patch_candidate) {
      events.push({
        label: 'BUILD',
        text: `Patch candidate synthesized (${status.patch_candidate.patch_id}). Files changed: ${status.patch_candidate.changed_files.join(', ') || 'none'}.`,
        time: status.updated_at ? new Date(status.updated_at).toLocaleTimeString() : '00:00:00',
        type: 'success'
      });
    }

    // Lineage iterations
    if (status.patch_lineage && status.patch_lineage.length > 0) {
      events.push({
        label: 'LINEAGE',
        text: `Patch lineage preserved across ${status.patch_lineage.length} iteration(s): [${status.patch_lineage.map(p => p.substring(0, 8)).join(' → ')}].`,
        time: status.updated_at ? new Date(status.updated_at).toLocaleTimeString() : '00:00:00',
        type: 'info'
      });
    }

    // Evidence Receipt
    if (status.evidence_receipt) {
      const receipt = status.evidence_receipt;
      events.push({
        label: 'VERIFY',
        text: `Deterministic invariant evaluation completed: ${receipt.invariant_summary.length} invariants checked, ${receipt.oracle_results.length} oracle checks executed.`,
        time: status.updated_at ? new Date(status.updated_at).toLocaleTimeString() : '00:00:00',
        type: receipt.verdict === 'VERIFIED' ? 'success' : receipt.verdict === 'REJECTED' ? 'error' : 'warn'
      });

      if (receipt.counterexamples && receipt.counterexamples.length > 0) {
        events.push({
          label: 'COUNTEREXAMPLE',
          text: `Adversarial Red Team counterexample discovered: ${receipt.counterexamples[0].failure_reason || 'Invariant violation observed'}.`,
          time: status.updated_at ? new Date(status.updated_at).toLocaleTimeString() : '00:00:00',
          type: 'error'
        });
      }

      events.push({
        label: 'RECEIPT',
        text: `Evidence Receipt generated with Merkle digest: ${receipt.receipt_hash ? receipt.receipt_hash.substring(0, 24) + '...' : 'Unsigned'}. Verdict: ${receipt.verdict}.`,
        time: receipt.timestamp ? new Date(receipt.timestamp).toLocaleTimeString() : '00:00:00',
        type: receipt.verdict === 'VERIFIED' ? 'success' : 'warn'
      });
    }

    // Judge Explanation
    if (status.judge_explanation) {
      events.push({
        label: 'JUDGE',
        text: `Subordinate Judge rationale: "${status.judge_explanation.summary}" (Note: Non-authoritative).`,
        time: status.updated_at ? new Date(status.updated_at).toLocaleTimeString() : '00:00:00',
        type: 'info'
      });
    }

    // Operational Result / Error
    if (status.operational_error || status.operational_result) {
      events.push({
        label: 'OP_ERROR',
        text: `Operational Result: ${status.operational_result || 'FAILURE'}. Error: ${status.operational_error || 'Execution halted'}`,
        time: status.updated_at ? new Date(status.updated_at).toLocaleTimeString() : '00:00:00',
        type: 'error'
      });
    }

    // Current State
    events.push({
      label: 'STATE',
      text: `Lifecycle state: ${status.state} (${status.status.toUpperCase()}). Last heartbeat recorded.`,
      time: status.updated_at ? new Date(status.updated_at).toLocaleTimeString() : '00:00:00',
      type: status.status === 'active' ? 'active' : status.state === 'VERIFIED' ? 'success' : 'warn'
    });

    return events;
  }, [status]);

  // Compute lifecycle stages indices
  const currentStateIndex = status ? LIFECYCLE_STAGES.indexOf(status.state) : -1;
  const isAborted = status?.state === 'ABORTED';
  const isVerified = status?.state === 'VERIFIED';
  const isActive = status?.status === 'active';

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12">
      {/* ================= HEADER SECTION ================= */}
      <header className="border-b border-[#222430] pb-5">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div>
            <div className="flex items-center gap-2 text-xs font-mono text-[#71717a] mb-1.5">
              <span className="text-[#ef4444]">04. SESSION DETAIL</span>
              <span>/</span>
              <span className="text-[#f4f4f5]">MISSION CONTROL</span>
              <span>/</span>
              <span className="text-[#a1a1aa]">{status ? status.run_id : 'AWAITING SELECTION'}</span>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-2xl sm:text-3xl font-black tracking-tight text-[#f4f4f5] flex items-center gap-3">
                <span className="text-[#ef4444]">MISSION CONTROL</span>
              </h1>
              <span className="text-xs font-mono font-medium text-[#60a5fa] border border-[#60a5fa]/30 px-2 py-0.5 rounded bg-[#60a5fa]/10">
                Live Orchestration
              </span>
              {isActive && (
                <span className="inline-flex items-center gap-1.5 text-xs font-mono font-semibold px-2.5 py-0.5 rounded bg-[#ef4444]/15 border border-[#ef4444]/40 text-[#f87171]">
                  <span className="w-2 h-2 rounded-full bg-[#ef4444] animate-ping" />
                  In Progress (Polling 1500ms)
                </span>
              )}
              {isVerified && (
                <span className="inline-flex items-center gap-1.5 text-xs font-mono font-semibold px-2.5 py-0.5 rounded bg-[#10b981]/15 border border-[#10b981]/40 text-[#10b981]">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#10b981]" />
                  Verified Deterministic
                </span>
              )}
              {isAborted && (
                <span className="inline-flex items-center gap-1.5 text-xs font-mono font-semibold px-2.5 py-0.5 rounded bg-[#ef4444]/15 border border-[#ef4444]/40 text-[#f87171]">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#ef4444]" />
                  Aborted / Rejected
                </span>
              )}
            </div>

            <p className="text-xs sm:text-sm text-[#a1a1aa] font-sans mt-2">
              Authoritative live progression tracking across the frozen state machine lifecycle stages.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2.5 w-full sm:w-auto">
            {status && (
              <>
                <Link
                  href={`/results?runId=${encodeURIComponent(status.run_id)}`}
                  className="px-3 py-1.5 rounded bg-[#13141b] hover:bg-[#1a1b24] text-[#f4f4f5] border border-[#222430] hover:border-[#353748] font-mono text-xs transition-colors"
                >
                  Inspect Results →
                </Link>
                <Link
                  href={`/evidence?runId=${encodeURIComponent(status.run_id)}`}
                  className="px-3 py-1.5 rounded bg-[#13141b] hover:bg-[#1a1b24] text-[#f4f4f5] border border-[#222430] hover:border-[#353748] font-mono text-xs transition-colors"
                >
                  Audit Evidence →
                </Link>
              </>
            )}
            <Link
              href="/"
              className="inline-flex items-center gap-1.5 text-xs font-bold bg-[#ef4444] hover:bg-[#dc2626] text-white px-3.5 py-1.5 rounded transition-all shadow-[0_0_12px_rgba(239,68,68,0.35)]"
            >
              + Launch Run
            </Link>
          </div>
        </div>
      </header>

      {/* ================= RUN SELECTOR BAR ================= */}
      <section aria-labelledby="session-selector-heading" className="bg-[#0d0e12] border border-[#222430] p-4 rounded-lg flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4 shadow-sm">
        <h2 id="session-selector-heading" className="sr-only">Session and Run Selector</h2>

        {/* Manual Run ID Search */}
        <form onSubmit={handleSearchSubmit} className="flex gap-2 flex-1 max-w-md">
          <label htmlFor="mission-control-run-id" className="sr-only">Run ID</label>
          <div className="relative flex-1">
            <span className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none font-mono text-[#ef4444] text-xs font-bold">
              &gt;
            </span>
            <input
              id="mission-control-run-id"
              type="text"
              placeholder="Enter Run ID (e.g. run-1234)"
              value={inputRunId}
              onChange={(e) => setInputRunId(e.target.value)}
              className="w-full bg-[#13141b] border border-[#222430] pl-7 pr-3 py-1.5 rounded text-xs font-mono text-[#f4f4f5] placeholder:text-[#71717a] focus:border-[#ef4444] focus:outline-none transition-colors"
            />
          </div>
          <button
            type="submit"
            disabled={isLoading || !inputRunId.trim()}
            className="bg-[#13141b] hover:bg-[#1a1b24] text-[#f4f4f5] border border-[#222430] hover:border-[#353748] px-4 py-1.5 rounded text-xs font-mono font-semibold transition-colors disabled:opacity-50"
          >
            {isLoading ? 'Loading...' : 'Load'}
          </button>
        </form>

        {/* Quick Dropdown Selector */}
        {history.length > 0 && (
          <div className="flex items-center gap-2 text-xs">
            <label htmlFor="quick-run-select" className="text-[#71717a] font-mono shrink-0">Quick Pick:</label>
            <select
              id="quick-run-select"
              value={selectedRunId}
              onChange={(e) => handleSelectRun(e.target.value)}
              className="bg-[#13141b] border border-[#222430] text-[#f4f4f5] text-xs font-mono rounded p-1.5 focus:border-[#ef4444] focus:outline-none"
            >
              {history.map((h) => (
                <option key={h.run_id} value={h.run_id}>
                  {h.run_id} — {h.task_id} ({h.verdict || h.final_state})
                </option>
              ))}
            </select>
          </div>
        )}
      </section>

      {/* ================= OPERATIONAL ALERTS ================= */}
      {connectionAlert && (
        <div 
          role="alert" 
          className="p-4 bg-amber-950/40 text-amber-200 border-2 border-amber-600/80 rounded-lg text-xs space-y-1 shadow-md"
        >
          <div className="flex items-center gap-2 font-bold text-amber-300">
            <span aria-hidden="true">⚠️</span>
            <span>Connection Alert:</span>
          </div>
          <p className="font-mono text-[11px] leading-relaxed">{connectionAlert}</p>
        </div>
      )}

      {error && (
        <div 
          role="alert" 
          className="p-4 bg-[#ef4444]/15 text-[#f87171] border border-[#ef4444]/40 rounded-lg text-xs space-y-1 shadow-md"
        >
          <div className="flex items-center gap-2 font-bold text-[#fca5a5]">
            <span aria-hidden="true">✕</span>
            <span>Operational Error:</span>
          </div>
          <p className="font-mono text-[11px] leading-relaxed">{error}</p>
        </div>
      )}

      {/* ================= LIFECYCLE STEPPER PIPELINE ================= */}
      <section aria-labelledby="pipeline-stepper-heading" className="bg-[#0d0e12] border border-[#222430] rounded-lg p-5 shadow-lg">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-[#222430] gap-2 mb-4">
          <div>
            <h2 id="pipeline-stepper-heading" className="text-xs uppercase font-bold tracking-wider text-[#f4f4f5] font-mono">
              State Machine Progression Pipeline
            </h2>
            <p className="text-[11px] text-[#71717a] font-sans">
              Authoritative transitions governed strictly by <code className="text-[#fca5a5] font-mono">backend/orchestrator/orchestrator.py</code>
            </p>
          </div>
          {status && (
            <span className="text-xs font-mono text-[#a1a1aa] bg-[#13141b] px-2.5 py-1 rounded border border-[#222430]">
              Current State: <strong className="text-[#f4f4f5]">{status.state}</strong> • Iteration: <strong className="text-[#f4f4f5]">{status.iteration}</strong>
            </span>
          )}
        </div>

        {/* Stepper Scroll Container */}
        <div className="overflow-x-auto pb-2">
          <div className="flex items-center justify-between min-w-[760px] relative px-4 py-2">
            {/* Connecting Track Line */}
            <div className="absolute left-8 right-8 top-1/2 -translate-y-2 h-[2px] bg-[#1a1b24] z-0" />

            {LIFECYCLE_STAGES.map((stage, idx) => {
              const isCurrent = status?.state === stage;
              const isPast = !isAborted && currentStateIndex >= 0 && idx < currentStateIndex;
              const isStageAborted = isAborted && isCurrent;

              return (
                <div key={stage} className="relative z-10 flex flex-col items-center group">
                  {/* Circle Indicator */}
                  <div 
                    className={`w-7 h-7 rounded-full flex items-center justify-center font-mono text-xs font-bold transition-all duration-150 mb-1.5 ${
                      isStageAborted
                        ? 'bg-[#ef4444] text-white ring-4 ring-[#ef4444]/20'
                        : isCurrent
                        ? 'bg-[#ef4444] text-white ring-4 ring-[#ef4444]/30 motion-safe:animate-pulse shadow-[0_0_12px_rgba(239,68,68,0.5)]'
                        : isPast
                        ? 'bg-[#10b981] text-white border border-[#10b981]'
                        : 'bg-[#13141b] text-[#71717a] border border-[#222430]'
                    }`}
                    title={`Stage ${stage}: ${isCurrent ? 'Current Active State' : isPast ? 'Completed' : 'Pending'}`}
                  >
                    {isStageAborted ? '✕' : isPast ? '✓' : isCurrent ? '●' : idx + 1}
                  </div>

                  {/* Stage Label */}
                  <span className={`font-mono text-[10px] font-semibold tracking-wide ${
                    isCurrent ? 'text-[#ef4444]' : isPast ? 'text-[#10b981]' : 'text-[#71717a]'
                  }`}>
                    {stage}
                  </span>

                  {/* Non-color accessibility marker */}
                  <span className="text-[9px] font-mono text-[#71717a] opacity-80">
                    {isStageAborted ? '[Aborted]' : isCurrent ? '[Active]' : isPast ? '[Done]' : '[Pending]'}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* ================= MAIN MONITORING SPLIT GRID ================= */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Column: Timeline, Diff, Verdict (8 Cols) */}
        <div className="lg:col-span-8 space-y-6">
          {/* Tabs Control */}
          <div className="bg-[#0d0e12] border border-[#222430] rounded-lg overflow-hidden shadow-sm">
            <div className="flex items-center justify-between px-4 py-2.5 bg-[#13141b] border-b border-[#222430]">
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => setActiveTab('timeline')}
                  className={`px-3 py-1 rounded font-mono text-xs font-semibold transition-colors ${
                    activeTab === 'timeline'
                      ? 'bg-[#0d0e12] text-[#f4f4f5] border border-[#222430]'
                      : 'text-[#71717a] hover:text-[#f4f4f5]'
                  }`}
                >
                  Execution Timeline
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab('diff')}
                  className={`px-3 py-1 rounded font-mono text-xs font-semibold transition-colors flex items-center gap-1.5 ${
                    activeTab === 'diff'
                      ? 'bg-[#0d0e12] text-[#f4f4f5] border border-[#222430]'
                      : 'text-[#71717a] hover:text-[#f4f4f5]'
                  }`}
                >
                  <span>Patch Diff</span>
                  {status?.patch_candidate && (
                    <span className="w-1.5 h-1.5 rounded-full bg-[#10b981]" />
                  )}
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab('policy')}
                  className={`px-3 py-1 rounded font-mono text-xs font-semibold transition-colors ${
                    activeTab === 'policy'
                      ? 'bg-[#0d0e12] text-[#f4f4f5] border border-[#222430]'
                      : 'text-[#71717a] hover:text-[#f4f4f5]'
                  }`}
                >
                  Policy Ceilings
                </button>
              </div>

              <span className="text-[10px] font-mono text-[#71717a] hidden sm:inline-block">
                HTTP Snapshot Refreshed
              </span>
            </div>

            {/* Tab 1: Execution Event Timeline */}
            {activeTab === 'timeline' && (
              <div className="p-4 space-y-4">
                <div className="flex items-center justify-between text-xs font-mono text-[#71717a] border-b border-[#222430] pb-2">
                  <span>Authoritative Event Sequence</span>
                  <span>Source: SQLite / Runs API</span>
                </div>

                {timelineEvents.length === 0 ? (
                  <div className="p-8 text-center text-xs font-mono text-[#71717a]">
                    No run selected. Select a run ID from the quick-pick dropdown or submit an intake contract.
                  </div>
                ) : (
                  <div className="space-y-3 font-mono text-xs">
                    {timelineEvents.map((evt, idx) => (
                      <div 
                        key={idx} 
                        className="flex items-start gap-3 p-2.5 rounded bg-[#13141b]/50 border border-[#222430]/60 hover:border-[#353748] transition-colors"
                      >
                        <span className="text-[10px] text-[#71717a] shrink-0 mt-0.5">
                          {evt.time}
                        </span>
                        <span className={`px-1.5 py-0.2 rounded text-[10px] font-bold shrink-0 ${
                          evt.type === 'success' ? 'bg-[#10b981]/15 text-[#10b981] border border-[#10b981]/30' :
                          evt.type === 'error' ? 'bg-[#ef4444]/15 text-[#f87171] border border-[#ef4444]/30' :
                          evt.type === 'warn' ? 'bg-amber-950/40 text-amber-300 border border-amber-800' :
                          evt.type === 'active' ? 'bg-[#ef4444]/20 text-[#fca5a5] border border-[#ef4444]/50' :
                          'bg-[#13141b] text-[#a1a1aa] border border-[#222430]'
                        }`}>
                          {evt.label}
                        </span>
                        <span className="text-[#e5e1e4] text-[11px] leading-relaxed break-words flex-1">
                          {evt.text}
                        </span>
                      </div>
                    ))}
                  </div>
                )}

                {/* Honest Telemetry Disclosure */}
                <div className="pt-2 border-t border-[#222430] text-[10px] font-mono text-[#71717a] flex items-center justify-between">
                  <span>Polling Interval: 1500ms</span>
                  <span>Live streaming simulated output: Disabled (Zero-Fabrication Guard)</span>
                </div>
              </div>
            )}

            {/* Tab 2: Patch Diff Preview */}
            {activeTab === 'diff' && (
              <div className="p-4 space-y-4">
                {status?.patch_candidate?.diff ? (
                  <div className="space-y-3">
                    <div className="flex flex-wrap items-center justify-between gap-2 pb-2 border-b border-[#222430] text-xs font-mono">
                      <div className="flex items-center gap-2">
                        <span className="text-[#ef4444] font-bold">{status.patch_candidate.patch_id}</span>
                        <span className="text-[#71717a]">•</span>
                        <span className="text-[#a1a1aa]">Files: {status.patch_candidate.changed_files.join(', ')}</span>
                      </div>
                      {status.patch_candidate.diff_sha256 && (
                        <span className="text-[10px] text-[#71717a] truncate max-w-xs" title={status.patch_candidate.diff_sha256}>
                          SHA-256: {status.patch_candidate.diff_sha256.substring(0, 16)}...
                        </span>
                      )}
                    </div>

                    {/* Diff Viewer Area */}
                    <pre className="p-4 rounded bg-[#09090b] border border-[#222430] overflow-x-auto text-[11px] font-mono leading-relaxed text-[#e5e1e4] max-h-96">
                      {status.patch_candidate.diff.split('\n').map((line, lIdx) => {
                        const isAdd = line.startsWith('+');
                        const isDel = line.startsWith('-');
                        const isHeader = line.startsWith('@@') || line.startsWith('diff ');

                        return (
                          <div 
                            key={lIdx}
                            className={
                              isAdd ? 'text-[#10b981] bg-[#10b981]/10' :
                              isDel ? 'text-[#f87171] bg-[#ef4444]/10' :
                              isHeader ? 'text-[#60a5fa] font-bold' :
                              'text-[#a1a1aa]'
                            }
                          >
                            {line}
                          </div>
                        );
                      })}
                    </pre>

                    {/* Untrusted Code Audit Advisory */}
                    <div className="p-3 bg-amber-950/20 border border-amber-900/40 rounded text-[11px] text-amber-300 font-sans">
                      <strong>Code Audit Advisory:</strong> AI-generated patch candidates are untrusted code. Never apply or execute patches on host workstations without verified invariant receipts.
                    </div>
                  </div>
                ) : (
                  <div className="p-10 text-center space-y-2 text-xs font-mono text-[#71717a]">
                    <p>No patch candidate diff generated for run {status?.run_id || '(none)'}.</p>
                    <p className="text-[11px]">Diffs are synthesized during the BUILD stage and refined in REPAIR.</p>
                  </div>
                )}
              </div>
            )}

            {/* Tab 3: Policy Ceilings */}
            {activeTab === 'policy' && (
              <div className="p-4">
                <ResourceBudgetNotice
                  iterationsUsed={status?.iteration || 0}
                  iterationsLimit={status?.resource_status?.iterations_limit || 20}
                  toolCallsUsed={status?.resource_status?.tool_calls_used || 0}
                  toolCallsLimit={status?.resource_status?.tool_calls_limit || 100}
                />
              </div>
            )}
          </div>

          {/* Authoritative Verdict Display */}
          <section aria-labelledby="verdict-card-heading">
            <h2 id="verdict-card-heading" className="sr-only">Authoritative Verification Verdict</h2>
            <VerdictDisplay
              verdict={status?.evidence_receipt?.verdict || (isVerified ? 'VERIFIED' : isAborted ? 'REJECTED' : null)}
              error={status?.operational_error || null}
              lifecycleState={status?.state || null}
            />
          </section>
        </div>

        {/* Right Column: Diagnostics, Sandbox Security, Budget (4 Cols) */}
        <div className="lg:col-span-4 space-y-6">
          {/* Mission Control Diagnostics */}
          <section aria-labelledby="diagnostics-heading" className="bg-[#0d0e12] border border-[#222430] p-5 rounded-lg space-y-3 shadow-sm text-xs">
            <h2 id="diagnostics-heading" className="text-xs uppercase font-bold tracking-wider text-[#f4f4f5] font-mono border-b border-[#222430] pb-2">
              Mission Control Diagnostics
            </h2>
            <div className="space-y-2.5 text-[#a1a1aa] text-[11px] font-sans">
              <div>
                <span className="text-[#71717a] font-mono block text-[10px] uppercase">Active Polling State:</span>
                <span className="font-mono text-[#f4f4f5]">
                  {isActive ? 'POLLING ACTIVE (1500ms INTERVAL)' : 'IDLE / TERMINATED'}
                </span>
              </div>
              <div>
                <span className="text-[#71717a] font-mono block text-[10px] uppercase">Lifecycle Authority:</span>
                <span className="font-mono text-[#f4f4f5]">backend/orchestrator/orchestrator.py</span>
              </div>
              <div>
                <span className="text-[#71717a] font-mono block text-[10px] uppercase">Stale Request Protection:</span>
                <span className="text-[#10b981] font-mono font-semibold">ENFORCED (useRef Identity Guard)</span>
              </div>
              <div>
                <span className="text-[#71717a] font-mono block text-[10px] uppercase">Consecutive Failure Ceiling:</span>
                <span className="font-mono text-[#f4f4f5]">5 Failures Fail-Closed</span>
              </div>
            </div>
          </section>

          {/* Sandbox Security Profile */}
          <section aria-labelledby="sandbox-profile-heading" className="bg-[#0d0e12] border border-[#222430] p-5 rounded-lg space-y-3 shadow-sm text-xs">
            <h2 id="sandbox-profile-heading" className="text-xs uppercase font-bold tracking-wider text-[#f4f4f5] font-mono border-b border-[#222430] pb-2">
              Sandbox Security Profile
            </h2>
            <div className="space-y-2 text-[11px] font-mono text-[#a1a1aa]">
              <div className="flex items-center justify-between">
                <span className="text-[#71717a]">Backend:</span>
                <span className="text-[#f4f4f5]">LocalDevelopmentBackend</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[#71717a]">Network Egress:</span>
                <span className="text-[#ef4444] font-bold">DISABLED (Zero Sockets)</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[#71717a]">Filesystem:</span>
                <span className="text-[#10b981]">Ephemeral Scratch</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[#71717a]">Path Traversal:</span>
                <span className="text-[#10b981]">FAIL_CLOSED Enforced</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[#71717a]">Trust Authority:</span>
                <span className="text-[#f4f4f5]">backend/sandbox/trust.py</span>
              </div>
            </div>
          </section>

          {/* Quick Cross-Navigation Links */}
          <div className="bg-[#0d0e12] border border-[#222430] p-4 rounded-lg space-y-2 text-xs">
            <span className="text-[10px] font-mono uppercase text-[#71717a] tracking-wider block font-semibold">
              Inspect Execution Artifacts
            </span>
            <div className="flex flex-col gap-2">
              <Link
                href={`/evidence${status ? `?runId=${encodeURIComponent(status.run_id)}` : ''}`}
                className="p-2 rounded bg-[#13141b] hover:bg-[#1a1b24] text-[#f4f4f5] border border-[#222430] flex items-center justify-between font-mono text-[11px] transition-colors"
              >
                <span>Evidence &amp; Diffs</span>
                <span>&rarr;</span>
              </Link>
              <Link
                href={`/results${status ? `?runId=${encodeURIComponent(status.run_id)}` : ''}`}
                className="p-2 rounded bg-[#13141b] hover:bg-[#1a1b24] text-[#f4f4f5] border border-[#222430] flex items-center justify-between font-mono text-[11px] transition-colors"
              >
                <span>Run Results &amp; Verdicts</span>
                <span>&rarr;</span>
              </Link>
              <Link
                href={`/playground`}
                className="p-2 rounded bg-[#13141b] hover:bg-[#1a1b24] text-[#f4f4f5] border border-[#222430] flex items-center justify-between font-mono text-[11px] transition-colors"
              >
                <span>Sandbox Playground</span>
                <span>&rarr;</span>
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function SessionsPage() {
  return (
    <Suspense fallback={
      <div className="p-12 text-center text-xs font-mono text-[#71717a]">
        Loading Mission Control...
      </div>
    }>
      <SessionsContent />
    </Suspense>
  );
}
