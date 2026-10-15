"use client";

import React, { useState, useEffect, useCallback, useRef } from 'react';
import Link from 'next/link';
import { RunCreationForm } from '@/components/RunCreationForm';
import { OrchestrationVisualizer } from '@/components/OrchestrationVisualizer';
import { EvidenceReceiptView } from '@/components/EvidenceReceiptView';
import { VerdictDisplay } from '@/components/VerdictDisplay';
import { JudgeExplanationView } from '@/components/JudgeExplanationView';
import { RunHistory } from '@/components/RunHistory';
import { apiClient, ApiError } from '@/api/client';
import { RunStatus } from '@/models/types';

export const POLLING_INTERVAL_MS = 1500;
export const MAX_POLLING_DURATION_MS = 300000; // 5 minutes
export const MAX_CONSECUTIVE_POLLING_FAILURES = 5;

export interface PollingEvaluation {
  shouldStop: boolean;
  stopReason?: 'TERMINAL_STATE' | 'NOT_FOUND_404' | 'MAX_FAILURES' | 'TIMEOUT';
  alertMessage?: string;
  nextConsecutiveFailures: number;
}

export function evaluatePollingSuccess(
  latestStatus: RunStatus,
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  _currentFailures: number
): PollingEvaluation {
  const isTerminal = 
    latestStatus.status !== 'active' ||
    latestStatus.state === 'VERIFIED' ||
    latestStatus.state === 'ABORTED';

  if (isTerminal) {
    return {
      shouldStop: true,
      stopReason: 'TERMINAL_STATE',
      alertMessage: undefined,
      nextConsecutiveFailures: 0,
    };
  }

  return {
    shouldStop: false,
    alertMessage: undefined,
    nextConsecutiveFailures: 0,
  };
}

export function evaluatePollingError(
  err: unknown,
  runId: string,
  currentFailures: number,
  maxFailures: number = MAX_CONSECUTIVE_POLLING_FAILURES
): PollingEvaluation {
  const is404 = 
    (err instanceof ApiError && err.status === 404) ||
    (typeof err === 'object' && err !== null && 'status' in err && (err as { status: unknown }).status === 404) ||
    (err instanceof Error && (err.message.includes('404') || err.message.includes('Not Found')));

  if (is404) {
    return {
      shouldStop: true,
      stopReason: 'NOT_FOUND_404',
      alertMessage: `Operational alert: Run '${runId}' not found (HTTP 404). Polling stopped.`,
      nextConsecutiveFailures: currentFailures + 1,
    };
  }

  const nextFailures = currentFailures + 1;
  if (nextFailures >= maxFailures) {
    return {
      shouldStop: true,
      stopReason: 'MAX_FAILURES',
      alertMessage: `Operational connection alert: Polling stopped after ${nextFailures} consecutive failures. Verify network or server connectivity.`,
      nextConsecutiveFailures: nextFailures,
    };
  }

  return {
    shouldStop: false,
    alertMessage: undefined,
    nextConsecutiveFailures: nextFailures,
  };
}

export function isRequestCurrent(requestRunId: string, activeRunId: string): boolean {
  return Boolean(requestRunId) && requestRunId.trim() === activeRunId.trim();
}

export default function Home() {
  const [runId, setRunId] = useState<string>('');
  const [status, setStatus] = useState<RunStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isFetching, setIsFetching] = useState<boolean>(false);
  const [connectionAlert, setConnectionAlert] = useState<string | null>(null);

  // Finding 1: Robust request identity ref and abort controller
  const selectedRunIdRef = useRef<string>('');
  const abortControllerRef = useRef<AbortController | null>(null);

  // Finding 2: Polling state refs
  const activePollingStartTimeRef = useRef<number | null>(null);
  const consecutiveFailuresRef = useRef<number>(0);
  const isPollingInFlightRef = useRef<boolean>(false);

  const fetchStatusForId = useCallback(async (targetId: string) => {
    const trimmed = targetId.trim();
    if (!trimmed) return;

    // Track active request identity
    selectedRunIdRef.current = trimmed;
    setConnectionAlert(null);

    // Cancel in-flight request if any
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setIsFetching(true);
    try {
      const data = await apiClient.getRunStatus(trimmed, controller.signal);
      // Finding 1: Stale response guard
      if (selectedRunIdRef.current === trimmed) {
        setStatus(data);
        setError(null);
        consecutiveFailuresRef.current = 0;
      }
    } catch (err: unknown) {
      // Ignore if request was aborted or is obsolete
      if (controller.signal.aborted || selectedRunIdRef.current !== trimmed) {
        return;
      }
      const message = err instanceof Error ? err.message : String(err);
      setError(message);
      setStatus(null);
    } finally {
      if (selectedRunIdRef.current === trimmed) {
        setIsFetching(false);
      }
    }
  }, []);

  const handleManualFetch = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = runId.trim();
    if (!trimmed) return;
    selectedRunIdRef.current = trimmed;
    activePollingStartTimeRef.current = Date.now();
    consecutiveFailuresRef.current = 0;
    fetchStatusForId(trimmed);
  };

  const handleRunCreated = (newRunId: string) => {
    const trimmed = newRunId.trim();
    setRunId(trimmed);
    selectedRunIdRef.current = trimmed;
    activePollingStartTimeRef.current = Date.now();
    consecutiveFailuresRef.current = 0;
    fetchStatusForId(trimmed);
  };

  const handleSelectRun = (selectedId: string) => {
    const trimmed = selectedId.trim();
    setRunId(trimmed);
    selectedRunIdRef.current = trimmed;
    activePollingStartTimeRef.current = Date.now();
    consecutiveFailuresRef.current = 0;
    fetchStatusForId(trimmed);
  };

  // Active run polling effect with bounded 300s timeout & consecutive failure handling
  useEffect(() => {
    const currentRunId = runId.trim();
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
      // Check bounded timeout (300 seconds)
      const elapsedMs = Date.now() - (activePollingStartTimeRef.current || Date.now());
      if (elapsedMs > MAX_POLLING_DURATION_MS) {
        clearInterval(intervalId);
        if (!isCleanedUp && selectedRunIdRef.current === currentRunId) {
          setConnectionAlert("Operational alert: Polling upper limit (5 minutes) reached. Polling stopped.");
        }
        return;
      }

      // Finding 2: Prevent overlapping polling requests if previous request is still in flight
      if (isPollingInFlightRef.current) {
        return;
      }

      // Guard: verify selected run identity before issuing poll request
      if (selectedRunIdRef.current !== currentRunId || isCleanedUp) {
        clearInterval(intervalId);
        return;
      }

      isPollingInFlightRef.current = true;

      try {
        const latest = await apiClient.getRunStatus(currentRunId);

        // Finding 1: verify response belongs to active run
        if (isCleanedUp || selectedRunIdRef.current !== currentRunId) {
          return;
        }

        const evalResult = evaluatePollingSuccess(latest, consecutiveFailuresRef.current);
        consecutiveFailuresRef.current = evalResult.nextConsecutiveFailures;
        setStatus(latest);

        if (evalResult.shouldStop) {
          clearInterval(intervalId);
        }
      } catch (err: unknown) {
        if (isCleanedUp || selectedRunIdRef.current !== currentRunId) {
          return;
        }

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
  }, [runId, status]);

  // Global unmount cleanup
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  return (
    <div className="space-y-6">
      <header className="border-b border-[#222430] pb-5" role="banner">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-3">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Link 
                href="/dashboard"
                className="text-xs font-mono text-[#a1a1aa] hover:text-[#f4f4f5] px-2.5 py-1 rounded bg-[#0d0e12] border border-[#222430] hover:bg-[#13141b] transition-colors flex items-center gap-1.5 focus-visible:ring-2 focus-visible:ring-[#ef4444] focus-visible:outline-none"
              >
                <span>←</span>
                <span>Dashboard Overview</span>
              </Link>
            </div>
            <h1 className="text-2xl sm:text-3xl font-black tracking-tight text-[#f4f4f5] flex items-center gap-3">
              <span className="text-[#ef4444]">REDLINE</span>
              <span className="text-xs font-mono font-normal text-[#a1a1aa] border border-[#222430] px-2 py-0.5 rounded bg-[#0d0e12]">
                New Task Intake
              </span>
            </h1>
            <p className="text-xs text-[#71717a] font-mono mt-1">
              Autonomous Software-Engineering Verification System — AI-generated code is guilty until proven safe.
            </p>
          </div>
          <div className="text-left md:text-right">
            <span className="text-[11px] font-mono text-[#f87171] font-bold border border-[#ef4444]/40 inline-block px-3 py-1 bg-[#ef4444]/10 rounded">
              FRONTEND IS NON-AUTHORITATIVE • BACKEND IS SOURCE OF TRUTH
            </span>
          </div>
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* Left Column (5 cols): Intake & History */}
        <section className="lg:col-span-5 space-y-6" aria-label="Run Creation and Selector Controls">
          <RunCreationForm onRunCreated={handleRunCreated} />
          
          <div className="border border-[#222430] p-5 rounded bg-[#0d0e12] card-laser-border shadow-lg text-[#f4f4f5]" role="search" aria-label="Run Inspection Search">
            <h2 className="text-sm font-bold text-[#f4f4f5] mb-2 uppercase tracking-wide font-mono">Inspect Run by ID</h2>
            <p className="text-xs text-[#71717a] mb-3 font-mono">Load live orchestration state and evidence for an existing run.</p>
            <form onSubmit={handleManualFetch} className="flex gap-2">
              <input 
                id="manual-run-id-input"
                type="text" 
                placeholder="Enter Run ID (e.g. run-1234)" 
                value={runId}
                onChange={e => setRunId(e.target.value)}
                className="bg-[#13141b] border border-[#222430] p-2.5 rounded flex-grow font-mono text-xs text-[#f4f4f5] placeholder:text-[#52525b] focus:border-[#ef4444] focus-visible:ring-1 focus-visible:ring-[#ef4444] focus-visible:outline-none transition-colors"
                aria-label="Run Identifier"
              />
              <button 
                type="submit"
                disabled={isFetching || !runId.trim()}
                className="bg-[#ef4444] hover:bg-[#dc2626] text-white text-xs font-semibold px-4 py-2 rounded transition-colors disabled:opacity-50 focus-visible:ring-2 focus-visible:ring-[#ef4444] focus-visible:outline-none cursor-pointer font-mono"
              >
                {isFetching ? 'Fetching...' : 'Inspect'}
              </button>
            </form>
            
            {error && (
              <div className="mt-3 p-3 bg-[#ef4444]/15 text-[#f87171] rounded border border-[#ef4444]/30 text-xs font-mono" role="alert">
                <strong className="block mb-0.5">Inspection Error:</strong> {error}
              </div>
            )}
          </div>

          <RunHistory onSelectRun={handleSelectRun} selectedRunId={runId} />
        </section>

        {/* Right Column (7 cols): Execution, Verdict & Evidence */}
        <section className="lg:col-span-7 space-y-6" aria-label="Verification and Evidence Results">
          {connectionAlert && (
            <div 
              className="p-4 bg-[#f59e0b]/15 text-[#fbbf24] border border-[#f59e0b]/30 rounded text-xs shadow-md font-mono" 
              role="alert"
              aria-live="assertive"
            >
              <div className="flex items-center gap-2 font-bold mb-1">
                <span aria-hidden="true">⚠️</span>
                <span>Operational Alert:</span>
              </div>
              <p>{connectionAlert}</p>
            </div>
          )}

          {runId && (
            <div className="bg-[#0d0e12] border border-[#222430] p-3 rounded flex flex-wrap items-center justify-between gap-3 text-xs font-mono">
              <div className="flex items-center gap-2">
                <span className="text-[#71717a]">Inspecting:</span>
                <span className="font-mono font-bold text-[#ef4444] select-all">{runId}</span>
              </div>
              <div className="flex items-center gap-2">
                <Link 
                  href={`/sessions?runId=${encodeURIComponent(runId)}`}
                  className="text-[#a1a1aa] hover:text-[#f4f4f5] bg-[#13141b] hover:bg-[#1a1b24] px-2.5 py-1 rounded border border-[#222430] transition-colors"
                >
                  🛰️ Mission Control
                </Link>
                <Link 
                  href={`/results?runId=${encodeURIComponent(runId)}`}
                  className="text-[#a1a1aa] hover:text-[#f4f4f5] bg-[#13141b] hover:bg-[#1a1b24] px-2.5 py-1 rounded border border-[#222430] transition-colors"
                >
                  📊 Results
                </Link>
                <Link 
                  href={`/evidence?runId=${encodeURIComponent(runId)}`}
                  className="text-[#a1a1aa] hover:text-[#f4f4f5] bg-[#13141b] hover:bg-[#1a1b24] px-2.5 py-1 rounded border border-[#222430] transition-colors"
                >
                  🛡️ Evidence &amp; Diff
                </Link>
              </div>
            </div>
          )}

          <OrchestrationVisualizer status={status} />
          
          {status && (
            <>
              <VerdictDisplay 
                verdict={status.evidence_receipt?.verdict || status.evidence_receipt?.deterministic_verdict || null} 
                error={status.operational_error} 
                lifecycleState={status.state}
              />
              <JudgeExplanationView explanation={status.judge_explanation || null} />
              <EvidenceReceiptView receipt={status.evidence_receipt || null} />
            </>
          )}
        </section>
      </div>
    </div>
  );
}
