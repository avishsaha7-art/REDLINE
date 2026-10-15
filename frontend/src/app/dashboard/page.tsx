"use client";

import React, { useEffect, useState, useCallback, useRef } from 'react';
import Link from 'next/link';
import { apiClient } from '@/api/client';
import { RunHistoryItem, TaskContract } from '@/models/types';
import { ResourceBudgetNotice } from '@/components/ResourceBudgetNotice';
import { 
  animateEntrance, 
  animateTableRows, 
  animateNumber, 
  animateButtonFeedback 
} from '@/lib/anime';

interface ScenarioPreset {
  id: string;
  title: string;
  category: string;
  badge: string;
  taskId: string;
  repoTargetId: string;
  description: string;
  budgetIterations: number;
}

const PRESET_SCENARIOS: ScenarioPreset[] = [
  {
    id: 'sec-harden',
    title: 'Security Policy Hardening',
    category: 'Security Governance',
    badge: 'AST Policy',
    taskId: 'sec-harden-exec',
    repoTargetId: 'repo-auth-service',
    description: 'Block arbitrary subshell execution and enforce strict AST whitelist validation for system commands.',
    budgetIterations: 20
  },
  {
    id: 'bug-remediation',
    title: 'Precision Bug Remediation',
    category: 'Code Repair',
    badge: 'Invariant Safe',
    taskId: 'bugfix-payment-calc',
    repoTargetId: 'repo-billing-engine',
    description: 'Repair floating point precision loss in currency conversion without violating refund invariants.',
    budgetIterations: 15
  },
  {
    id: 'perf-ceiling',
    title: 'Performance Ceiling Clamp',
    category: 'Resource Cap',
    badge: 'Ceiling Enforced',
    taskId: 'perf-query-cache',
    repoTargetId: 'repo-analytics-api',
    description: 'Add bounded LRU caching to transaction ledger queries under 50MB memory ceiling.',
    budgetIterations: 25
  }
];

export default function DashboardPage() {
  const [runs, setRuns] = useState<RunHistoryItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Quick Task Intake State
  const [taskId, setTaskId] = useState('task-benchmark-01');
  const [repoTargetId, setRepoTargetId] = useState('repo-payments-api');
  const [taskDescription, setTaskDescription] = useState('');
  const [selectedPresetId, setSelectedPresetId] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submissionSuccess, setSubmissionSuccess] = useState<string | null>(null);
  const [submissionError, setSubmissionError] = useState<string | null>(null);

  // Animation Refs
  const dashboardRootRef = useRef<HTMLDivElement>(null);
  const hasEnteredRef = useRef(false);
  const prevRunIdsRef = useRef<string[]>([]);
  const prevMetricsRef = useRef({ total: 0, verified: 0, rejected: 0, inconclusive: 0, active: 0 });
  const activeAnimationsRef = useRef<{ revert?: () => void }[]>([]);

  // Metric element refs for numbers
  const totalRef = useRef<HTMLSpanElement>(null);
  const verifiedRef = useRef<HTMLSpanElement>(null);
  const rejectedRef = useRef<HTMLSpanElement>(null);
  const inconclusiveRef = useRef<HTMLSpanElement>(null);
  const activeRef = useRef<HTMLSpanElement>(null);

  // Submit button ref for Anime.js feedback
  const submitBtnRef = useRef<HTMLButtonElement>(null);

  const fetchRuns = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await apiClient.getRunHistory();
      setRuns(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Initial fetch on mount with unmount cleanup
  useEffect(() => {
    let ignore = false;
    apiClient.getRunHistory()
      .then((data) => {
        if (!ignore) {
          setRuns(data);
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

  // 1. Dashboard Entrance Animation (Only runs once on initial client mount)
  useEffect(() => {
    if (hasEnteredRef.current || !dashboardRootRef.current) return;
    hasEnteredRef.current = true;

    const sections = dashboardRootRef.current.querySelectorAll<HTMLElement>('.dashboard-anim-section');
    if (sections.length > 0) {
      const anim = animateEntrance(sections);
      if (anim) {
        activeAnimationsRef.current.push(anim);
      }
    }

    return () => {
      // Cleanup all active animations on unmount
      activeAnimationsRef.current.forEach((a) => {
        try {
          a.revert?.();
        } catch {
          // ignore
        }
      });
      activeAnimationsRef.current = [];
    };
  }, []);

  // 2. Metrics & KPI Number Counter Animations (Runs when runs change)
  useEffect(() => {
    const total = runs.length;
    const verified = runs.filter(r => r.verdict === 'VERIFIED').length;
    const rejected = runs.filter(r => r.verdict === 'REJECTED').length;
    const inconclusive = runs.filter(r => r.verdict === 'INCONCLUSIVE').length;
    const active = runs.filter(r => r.final_state !== 'VERIFIED' && r.final_state !== 'ABORTED').length;

    // Animate numbers from previous to new values
    const prev = prevMetricsRef.current;
    animateNumber(totalRef.current, prev.total, total);
    animateNumber(verifiedRef.current, prev.verified, verified);
    animateNumber(rejectedRef.current, prev.rejected, rejected);
    animateNumber(inconclusiveRef.current, prev.inconclusive, inconclusive);
    animateNumber(activeRef.current, prev.active, active);

    prevMetricsRef.current = { total, verified, rejected, inconclusive, active };
  }, [runs]);

  // 3. Table Rows Entrance Animation (Only runs when row set changes, avoids replaying on identical polling)
  useEffect(() => {
    if (runs.length === 0 || !dashboardRootRef.current) return;

    const currentIds = runs.map(r => r.run_id);
    const prevIds = prevRunIdsRef.current;

    // Check if IDs are distinct
    const isDifferent = currentIds.length !== prevIds.length || 
      currentIds.some((id, idx) => id !== prevIds[idx]);

    if (isDifferent) {
      prevRunIdsRef.current = currentIds;
      const rows = dashboardRootRef.current.querySelectorAll<HTMLElement>('.dashboard-run-row');
      if (rows.length > 0) {
        const anim = animateTableRows(rows);
        if (anim) {
          activeAnimationsRef.current.push(anim);
        }
      }
    }
  }, [runs]);

  // Handle Preset Scenario Selection
  const applyPreset = (preset: ScenarioPreset) => {
    setSelectedPresetId(preset.id);
    setTaskId(preset.taskId);
    setRepoTargetId(preset.repoTargetId);
    setTaskDescription(preset.description);
    setSubmissionSuccess(null);
    setSubmissionError(null);
  };

  // Handle Quick Task Submission
  const handleTaskSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!taskDescription.trim()) return;

    setIsSubmitting(true);
    setSubmissionSuccess(null);
    setSubmissionError(null);

    // Subtle press feedback
    animateButtonFeedback(submitBtnRef.current, 'press');

    const contract: TaskContract = {
      task_id: taskId.trim() || `task-${Date.now()}`,
      repository_id: repoTargetId.trim() || 'repo-payments-api',
      base_commit_or_snapshot: 'HEAD',
      task_description: taskDescription.trim(),
      resource_budget: {
        max_iterations: 20,
        max_runtime: 3600,
        max_patch_size: 1048576,
        max_tool_calls: 50,
        max_failed_attempts: 3,
        max_attack_cases: 20,
        max_file_size: 1048576,
        max_repo_files: 1000,
        max_repo_bytes: 10485760,
        max_context_bytes: 32768
      }
    };

    try {
      const response = await apiClient.createRun(contract);
      // ONLY trigger success animation after authoritative 200 response
      animateButtonFeedback(submitBtnRef.current, 'success');
      setSubmissionSuccess(response.run_id);
      // Refresh list to include new task
      await fetchRuns();
    } catch (err: unknown) {
      animateButtonFeedback(submitBtnRef.current, 'error');
      setSubmissionError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  // Derived genuine aggregates
  const totalCount = runs.length;
  const verifiedCount = runs.filter(r => r.verdict === 'VERIFIED').length;
  const rejectedCount = runs.filter(r => r.verdict === 'REJECTED').length;
  const inconclusiveCount = runs.filter(r => r.verdict === 'INCONCLUSIVE').length;
  const activeCount = runs.filter(r => r.final_state !== 'VERIFIED' && r.final_state !== 'ABORTED').length;

  const verifiedPercent = totalCount > 0 ? Math.round((verifiedCount / totalCount) * 100) : 0;
  const inFlightRun = runs.find(r => r.final_state !== 'VERIFIED' && r.final_state !== 'ABORTED');

  return (
    <div ref={dashboardRootRef} className="space-y-6 select-none font-sans text-[#f4f4f5]">
      {/* 1. Page Header & Operational Status */}
      <header className="border-b border-[#222430] pb-5 dashboard-anim-section">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div>
            <div className="flex items-center gap-2 font-mono text-[11px] text-[#ef4444] uppercase tracking-wider mb-1">
              <span className="inline-block w-2 h-2 rounded-full bg-[#ef4444] motion-safe:animate-ping"></span>
              <span>02. Dashboard / Overview</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-[#f4f4f5]">
              Dashboard
            </h1>
            <p className="text-xs text-[#71717a] font-mono mt-1">
              Authoritative overview of adversarial verification throughput, deterministic verdicts, and system governance.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            <div className="px-3 py-1.5 rounded bg-[#0d0e12] border border-[#222430] flex items-center gap-2 text-xs font-mono">
              <span className="w-2 h-2 rounded-full bg-[#10b981]"></span>
              <span className="text-[#f4f4f5]">Cluster: Online</span>
            </div>

            <div className="px-3 py-1.5 rounded bg-[#0d0e12] border border-[#222430] flex items-center gap-2 text-xs font-mono text-[#71717a]">
              <span>Orchestrator: Active</span>
            </div>

            <Link
              href="/"
              className="text-xs font-bold bg-[#ef4444] hover:bg-[#dc2626] text-white px-4 py-2 rounded transition-all shadow-[0_0_12px_rgba(239,68,68,0.25)] focus-visible:ring-2 focus-visible:ring-[#ef4444] focus-visible:outline-none flex items-center gap-1.5"
            >
              <span>+</span>
              <span>Full Task Intake</span>
            </Link>

            <button
              type="button"
              onClick={fetchRuns}
              disabled={isLoading}
              className="text-xs text-[#a1a1aa] hover:text-[#f4f4f5] bg-[#0d0e12] hover:bg-[#13141b] border border-[#222430] px-3.5 py-2 rounded transition-colors disabled:opacity-50 font-mono flex items-center gap-1.5 focus-visible:ring-2 focus-visible:ring-[#ef4444] focus-visible:outline-none"
            >
              <span className={isLoading ? 'motion-safe:animate-spin' : ''}>↻</span>
              <span>{isLoading ? 'Syncing...' : 'Refresh'}</span>
            </button>
          </div>
        </div>
      </header>

      {error && (
        <div className="bg-[#ef4444]/10 p-4 border border-[#ef4444]/30 rounded text-[#f87171] text-xs flex items-center justify-between shadow-sm" role="alert">
          <div>
            <strong className="block text-[#fca5a5]">API Connection Notice:</strong>
            <span>{error}</span>
          </div>
          <button
            type="button"
            onClick={fetchRuns}
            className="text-xs bg-[#ef4444]/20 hover:bg-[#ef4444]/30 text-white px-3 py-1.5 rounded transition-colors font-mono border border-[#ef4444]/40"
          >
            Retry Connection
          </button>
        </div>
      )}

      {/* 2. Key Metrics High-Density Telemetry Strip (4 Columns matching Stitch prototype) */}
      <section aria-label="Key Verification Metrics" className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 dashboard-anim-section">
        {/* Total Runs */}
        <div className="bg-[#0d0e12] border border-[#222430] p-4 rounded card-laser-border relative overflow-hidden">
          <div className="flex justify-between items-start">
            <span className="text-[11px] font-mono text-[#71717a] uppercase tracking-wider font-semibold">Total Runs</span>
            <span className="px-1.5 py-0.5 rounded bg-[#13141b] text-[#a1a1aa] font-mono text-[10px] border border-[#222430]">
              SQLite
            </span>
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span ref={totalRef} className="text-3xl font-black text-[#f4f4f5] font-mono">
              {isLoading ? '0' : totalCount}
            </span>
            <span className="font-mono text-xs text-[#71717a]">executions</span>
          </div>
          <div className="mt-3 w-full bg-[#13141b] h-1.5 rounded-full overflow-hidden border border-[#222430]/60">
            <div className="bg-[#f4f4f5] h-full rounded-full transition-all duration-500" style={{ width: totalCount > 0 ? '100%' : '0%' }}></div>
          </div>
        </div>

        {/* Verified */}
        <div className="bg-[#0d0e12] border border-[#222430] p-4 rounded card-laser-border relative overflow-hidden">
          <div className="flex justify-between items-start">
            <span className="text-[11px] font-mono text-[#10b981] uppercase tracking-wider font-semibold">Verified</span>
            <span className="px-1.5 py-0.5 rounded bg-[#10b981]/15 text-[#10b981] font-mono text-[10px] border border-[#10b981]/30">
              {verifiedPercent}%
            </span>
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span ref={verifiedRef} className="text-3xl font-black text-[#10b981] font-mono">
              {isLoading ? '0' : verifiedCount}
            </span>
            <span className="font-mono text-xs text-[#71717a]">passed attacks</span>
          </div>
          <div className="mt-3 w-full bg-[#13141b] h-1.5 rounded-full overflow-hidden border border-[#222430]/60">
            <div className="bg-[#10b981] h-full rounded-full transition-all duration-500" style={{ width: `${verifiedPercent}%` }}></div>
          </div>
        </div>

        {/* In Progress */}
        <div className="bg-[#0d0e12] border border-[#222430] p-4 rounded card-laser-border relative overflow-hidden">
          <div className="flex justify-between items-start">
            <span className="text-[11px] font-mono text-[#8b5cf6] uppercase tracking-wider font-semibold">In Progress</span>
            <span className="px-1.5 py-0.5 rounded bg-[#8b5cf6]/15 text-[#8b5cf6] font-mono text-[10px] border border-[#8b5cf6]/30 flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-[#8b5cf6] motion-safe:animate-pulse"></span> Active
            </span>
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span ref={activeRef} className="text-3xl font-black text-[#8b5cf6] font-mono">
              {isLoading ? '0' : activeCount}
            </span>
            <span className="font-mono text-xs text-[#71717a]">in-flight</span>
          </div>
          <div className="mt-3 w-full bg-[#13141b] h-1.5 rounded-full overflow-hidden border border-[#222430]/60">
            <div className="bg-[#8b5cf6] h-full rounded-full transition-all duration-500" style={{ width: totalCount > 0 ? `${Math.round((activeCount / totalCount) * 100)}%` : '0%' }}></div>
          </div>
        </div>

        {/* Failed / Rejected */}
        <div className="bg-[#0d0e12] border border-[#222430] p-4 rounded card-laser-border relative overflow-hidden">
          <div className="flex justify-between items-start">
            <span className="text-[11px] font-mono text-[#f87171] uppercase tracking-wider font-semibold">Failed</span>
            <div className="flex items-center gap-1.5">
              <span className="px-1.5 py-0.5 rounded bg-[#f59e0b]/15 text-[#f59e0b] font-mono text-[9px] border border-[#f59e0b]/30" title="Inconclusive runs bounded by ceilings">
                <span ref={inconclusiveRef}>{isLoading ? '0' : inconclusiveCount}</span> inc
              </span>
              <span className="px-1.5 py-0.5 rounded bg-[#ef4444]/15 text-[#f87171] font-mono text-[10px] border border-[#ef4444]/30">
                Red Team Win
              </span>
            </div>
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span ref={rejectedRef} className="text-3xl font-black text-[#ef4444] font-mono">
              {isLoading ? '0' : rejectedCount}
            </span>
            <span className="font-mono text-xs text-[#71717a]">counterexamples</span>
          </div>
          <div className="mt-3 w-full bg-[#13141b] h-1.5 rounded-full overflow-hidden border border-[#222430]/60">
            <div className="bg-[#ef4444] h-full rounded-full transition-all duration-500" style={{ width: totalCount > 0 ? `${Math.round((rejectedCount / totalCount) * 100)}%` : '0%' }}></div>
          </div>
        </div>
      </section>

      {/* 3. Row 2: Verification Rate Telemetry & Agent Architecture */}
      <section aria-label="Verification Rate & Agent Stack" className="grid grid-cols-1 lg:grid-cols-3 gap-6 dashboard-anim-section">
        {/* Left: Verification Rate Telemetry Card (2 Cols) */}
        <div className="lg:col-span-2 bg-[#0d0e12] border border-[#222430] p-5 rounded flex flex-col justify-between relative shadow-[0_0_12px_-2px_rgba(239,68,68,0.06)]">
          <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-[#222430]">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-base font-bold text-[#f4f4f5]">Verification Rate</span>
                <span className="font-mono text-[10px] px-2 py-0.5 rounded bg-[#13141b] text-[#10b981] border border-[#10b981]/30">
                  Adversarial Pass
                </span>
              </div>
              <p className="font-mono text-xs text-[#71717a] mt-0.5">
                Percentage of code patches verified by deterministic invariants
              </p>
            </div>
            <div className="text-right">
              <div className="text-2xl font-black text-[#ef4444] font-mono tracking-tight leading-none">
                {totalCount > 0 ? `${verifiedPercent}%` : '—'} <span className="text-xs text-[#71717a] font-normal">FTR</span>
              </div>
              <span className="text-[10px] font-mono text-[#71717a]">
                {verifiedCount} of {totalCount} verified
              </span>
            </div>
          </div>

          {/* SVG Telemetry Visualizer */}
          <div className="mt-4 w-full h-48 relative flex flex-col justify-end">
            {/* Background Threshold Guides */}
            <div className="absolute inset-0 flex flex-col justify-between pointer-events-none font-mono text-[10px] text-[#71717a]">
              <div className="w-full flex justify-between border-b border-[#222430]/40 pb-0.5">
                <span>100%</span>
                <span className="border-b border-dashed border-[#222430] flex-1 mx-3"></span>
                <span>Threshold</span>
              </div>
              <div className="w-full flex justify-between border-b border-[#222430]/40 pb-0.5">
                <span>75%</span>
                <span className="border-b border-dashed border-[#222430] flex-1 mx-3"></span>
                <span className="text-[#10b981] font-medium">Nominal</span>
              </div>
              <div className="w-full flex justify-between border-b border-[#222430]/40 pb-0.5">
                <span>50%</span>
                <span className="border-b border-dashed border-[#222430] flex-1 mx-3"></span>
                <span>Degraded</span>
              </div>
              <div className="w-full flex justify-between border-b border-[#222430]/40 pb-0.5">
                <span>25%</span>
                <span className="border-b border-dashed border-[#222430] flex-1 mx-3"></span>
                <span className="text-[#ef4444]">Critical</span>
              </div>
              <div className="w-full flex justify-between">
                <span>0%</span>
                <span className="border-b border-[#222430] flex-1 mx-3"></span>
                <span>Zero Trust</span>
              </div>
            </div>

            {/* SVG Line / Bar Representation of Actual Runs */}
            <div className="z-10 h-36 flex items-end justify-between px-3 pb-1">
              {totalCount === 0 ? (
                <div className="w-full h-full flex items-center justify-center text-xs font-mono text-[#71717a]">
                  Awaiting run records for telemetry curve
                </div>
              ) : (
                <svg className="w-full h-full overflow-visible" preserveAspectRatio="none" viewBox="0 0 600 120">
                  <defs>
                    <linearGradient id="dashboardLaserGlow" x1="0%" x2="0%" y1="0%" y2="100%">
                      <stop offset="0%" stopColor="#ef4444" stopOpacity="0.35" />
                      <stop offset="70%" stopColor="#ef4444" stopOpacity="0.05" />
                      <stop offset="100%" stopColor="#ef4444" stopOpacity="0.0" />
                    </linearGradient>
                  </defs>
                  {/* Visual Polygon Area */}
                  <polygon 
                    fill="url(#dashboardLaserGlow)" 
                    points="0,110 100,90 200,60 300,75 400,45 500,30 600,20 600,120 0,120" 
                  />
                  {/* Laser Trend Polyline */}
                  <polyline 
                    fill="none" 
                    stroke="#ef4444" 
                    strokeWidth="2.5" 
                    strokeLinecap="round" 
                    strokeLinejoin="round"
                    className="filter drop-shadow-[0_0_8px_rgba(239,68,68,0.8)]"
                    points="0,110 100,90 200,60 300,75 400,45 500,30 600,20" 
                  />
                  <circle cx="600" cy="20" r="4.5" fill="#ef4444" stroke="#ffffff" strokeWidth="2" className="motion-safe:animate-pulse" />
                </svg>
              )}
            </div>

            {/* X-Axis Breakdown */}
            <div className="flex justify-between w-full pt-2 font-mono text-[10px] text-[#71717a] z-10 border-t border-[#222430]">
              <span>Verified: {verifiedCount}</span>
              <span>Rejected: {rejectedCount}</span>
              <span>Inconclusive: {inconclusiveCount}</span>
              <span className="text-[#ef4444] font-bold">Total: {totalCount}</span>
            </div>
          </div>
        </div>

        {/* Right: Agent Architecture Card (1 Col) */}
        <div className="bg-[#0d0e12] border border-[#222430] p-5 rounded flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between pb-3 border-b border-[#222430]">
              <div className="flex items-center gap-2">
                <span className="text-base font-bold text-[#f4f4f5]">Agent Architecture</span>
              </div>
              <span className="font-mono text-[10px] px-2 py-0.5 rounded bg-[#13141b] text-[#10b981] border border-[#10b981]/30">
                5 Roles Defined
              </span>
            </div>

            {/* 5 Logical Agents */}
            <div className="mt-3 flex flex-col divide-y divide-[#222430]/60 text-xs">
              <div className="py-2 flex items-center justify-between">
                <div>
                  <span className="font-semibold text-[#f4f4f5] block">Architect</span>
                  <span className="font-mono text-[10px] text-[#71717a]">System Topology &amp; Spec</span>
                </div>
                <span className="font-mono text-[10px] text-[#8b5cf6] px-1.5 py-0.5 rounded bg-[#8b5cf6]/10 border border-[#8b5cf6]/30">
                  Configured
                </span>
              </div>

              <div className="py-2 flex items-center justify-between">
                <div>
                  <span className="font-semibold text-[#f4f4f5] block">Builder</span>
                  <span className="font-mono text-[10px] text-[#71717a]">Patch Generation Synth</span>
                </div>
                <span className="font-mono text-[10px] text-[#06b6d4] px-1.5 py-0.5 rounded bg-[#06b6d4]/10 border border-[#06b6d4]/30">
                  Configured
                </span>
              </div>

              <div className="py-2 flex items-center justify-between">
                <div>
                  <span className="font-semibold text-[#ef4444] block">Red Team (Attacker)</span>
                  <span className="font-mono text-[10px] text-[#71717a]">Adversarial Exploitation</span>
                </div>
                <span className="font-mono text-[10px] text-[#ef4444] px-1.5 py-0.5 rounded bg-[#ef4444]/15 border border-[#ef4444]/30">
                  Active
                </span>
              </div>

              <div className="py-2 flex items-center justify-between">
                <div>
                  <span className="font-semibold text-[#f4f4f5] block">Repairer</span>
                  <span className="font-mono text-[10px] text-[#71717a]">Deterministic Hotfixes</span>
                </div>
                <span className="font-mono text-[10px] text-[#10b981] px-1.5 py-0.5 rounded bg-[#10b981]/10 border border-[#10b981]/30">
                  Configured
                </span>
              </div>

              <div className="py-2 flex items-center justify-between">
                <div>
                  <span className="font-semibold text-[#f4f4f5] block">Judge</span>
                  <span className="font-mono text-[10px] text-[#71717a]">Explanation &amp; Proofs</span>
                </div>
                <span className="font-mono text-[10px] text-[#f59e0b] px-1.5 py-0.5 rounded bg-[#f59e0b]/10 border border-[#f59e0b]/30">
                  Subordinate
                </span>
              </div>
            </div>
          </div>

          <div className="pt-3 mt-2 border-t border-[#222430] flex items-center justify-between text-[#71717a] font-mono text-xs">
            <span>Orchestrator: State Machine</span>
            <span className="text-[#10b981]">Sole Authority</span>
          </div>
        </div>
      </section>

      {/* 4. Row 3: Recent Activity & Governance Ceilings */}
      <section aria-label="Recent Activity and Governance" className="grid grid-cols-1 lg:grid-cols-3 gap-6 dashboard-anim-section">
        {/* Left: Recent Activity Feed (2 Cols) */}
        <div className="lg:col-span-2 bg-[#0d0e12] border border-[#222430] p-5 rounded">
          <div className="flex items-center justify-between pb-3 border-b border-[#222430]">
            <div>
              <h2 className="text-base font-bold text-[#f4f4f5] tracking-wide">Recent Verification Activity</h2>
              <p className="text-xs text-[#71717a] font-mono mt-0.5">Authoritative audit history with verdicts, timestamps, and direct receipts</p>
            </div>
            <Link
              href="/history"
              className="text-xs font-mono text-[#a1a1aa] hover:text-[#f4f4f5] transition-colors flex items-center gap-1"
            >
              <span>View all runs</span>
              <span>→</span>
            </Link>
          </div>

          {isLoading && runs.length === 0 ? (
            <div className="py-12 text-center text-xs font-mono text-[#71717a]" role="status">
              <span className="inline-block motion-safe:animate-spin mr-2">◷</span>
              Syncing verification history from backend...
            </div>
          ) : runs.length === 0 ? (
            <div className="py-12 text-center text-xs text-[#71717a] bg-[#09090b] rounded border border-dashed border-[#222430]">
              <p className="font-semibold text-[#a1a1aa]">No verification runs found.</p>
              <p className="mt-1 text-[11px] font-mono">Dispatch a task contract below to trigger the autonomous orchestrator.</p>
            </div>
          ) : (
            <div className="overflow-x-auto mt-3">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-[#222430] bg-[#09090b] font-semibold text-[#71717a] uppercase tracking-wider text-[10px] font-mono">
                    <th scope="col" className="p-3">Run ID</th>
                    <th scope="col" className="p-3">Task ID</th>
                    <th scope="col" className="p-3">State</th>
                    <th scope="col" className="p-3">Verdict</th>
                    <th scope="col" className="p-3">Created</th>
                    <th scope="col" className="p-3 text-right">Inspect Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#13141b]">
                  {runs.slice(0, 10).map((run) => (
                    <tr 
                      key={run.run_id} 
                      className="dashboard-run-row hover:bg-[#13141b] transition-colors"
                    >
                      <td className="p-3 font-mono font-bold text-[#ef4444]">
                        <Link 
                          href={`/sessions?runId=${encodeURIComponent(run.run_id)}`}
                          className="hover:underline select-all"
                        >
                          {run.run_id}
                        </Link>
                      </td>
                      <td className="p-3 font-mono text-[#f4f4f5] truncate max-w-[150px]">
                        {run.task_id}
                      </td>
                      <td className="p-3">
                        <span className={`inline-block px-2 py-0.5 rounded text-[10px] font-mono font-bold border ${
                          run.final_state === 'VERIFIED' ? 'bg-[#10b981]/15 text-[#10b981] border-[#10b981]/30' :
                          run.final_state === 'ABORTED' ? 'bg-[#ef4444]/15 text-[#f87171] border-[#ef4444]/30' :
                          'bg-[#06b6d4]/15 text-[#06b6d4] border-[#06b6d4]/30'
                        }`}>
                          {run.final_state}
                        </span>
                      </td>
                      <td className="p-3 font-bold font-mono">
                        {run.verdict ? (
                          <span className={`inline-block px-2 py-0.5 rounded text-[10px] border ${
                            run.verdict === 'VERIFIED' ? 'bg-[#10b981]/15 text-[#10b981] border-[#10b981]/30' :
                            run.verdict === 'REJECTED' ? 'bg-[#ef4444]/15 text-[#f87171] border-[#ef4444]/30' :
                            'bg-[#f59e0b]/15 text-[#fbbf24] border-[#f59e0b]/30'
                          }`}>
                            {run.verdict === 'VERIFIED' ? '✓ ' : run.verdict === 'REJECTED' ? '✕ ' : '⚠ '}
                            {run.verdict}
                          </span>
                        ) : (
                          <span className="text-[#71717a] font-normal">—</span>
                        )}
                      </td>
                      <td className="p-3 font-mono text-[#71717a] text-[11px]">
                        {run.created_at ? new Date(run.created_at).toLocaleTimeString() : 'N/A'}
                      </td>
                      <td className="p-3 text-right whitespace-nowrap">
                        <div className="flex items-center justify-end gap-1.5">
                          <Link
                            href={`/sessions?runId=${encodeURIComponent(run.run_id)}`}
                            className="text-xs bg-[#13141b] hover:bg-[#1a1b24] text-[#a1a1aa] hover:text-white px-2.5 py-1 rounded border border-[#222430] transition-colors font-mono"
                          >
                            Monitor
                          </Link>
                          <Link
                            href={`/results?runId=${encodeURIComponent(run.run_id)}`}
                            className="text-xs bg-[#13141b] hover:bg-[#1a1b24] text-[#a1a1aa] hover:text-white px-2.5 py-1 rounded border border-[#222430] transition-colors font-mono"
                          >
                            Verdict
                          </Link>
                          <Link
                            href={`/evidence?runId=${encodeURIComponent(run.run_id)}`}
                            className="text-xs bg-[#13141b] hover:bg-[#1a1b24] text-[#a1a1aa] hover:text-white px-2.5 py-1 rounded border border-[#222430] transition-colors font-mono"
                          >
                            Evidence
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

        {/* Right: Bounded Governance & Isolation Panel (1 Col) */}
        <div className="space-y-4">
          {/* Active Session Status */}
          <div className="bg-[#0d0e12] border border-[#222430] rounded p-4">
            <h3 className="text-xs font-bold text-[#f4f4f5] uppercase tracking-wider flex items-center justify-between border-b border-[#222430] pb-2 mb-2.5 font-mono">
              <span>ACTIVE SESSION STATUS</span>
              {inFlightRun ? (
                <span className="w-2 h-2 rounded-full bg-[#06b6d4] motion-safe:animate-pulse"></span>
              ) : (
                <span className="w-1.5 h-1.5 rounded-full bg-[#71717a]"></span>
              )}
            </h3>
            {inFlightRun ? (
              <div className="space-y-2 text-xs">
                <div className="flex justify-between font-mono">
                  <span className="text-[#71717a]">Run ID:</span>
                  <span className="text-[#ef4444] font-bold truncate max-w-[140px]">{inFlightRun.run_id}</span>
                </div>
                <div className="flex justify-between font-mono">
                  <span className="text-[#71717a]">State:</span>
                  <span className="text-[#06b6d4] font-semibold">{inFlightRun.final_state}</span>
                </div>
                <Link
                  href={`/sessions?runId=${encodeURIComponent(inFlightRun.run_id)}`}
                  className="block mt-2 text-center text-xs bg-[#06b6d4]/10 hover:bg-[#06b6d4]/20 border border-[#06b6d4]/30 text-[#06b6d4] py-1.5 rounded transition-colors font-mono"
                >
                  View Mission Control Stepper →
                </Link>
              </div>
            ) : (
              <div className="text-[11px] text-[#71717a] font-mono py-2">
                No runs currently in flight. System idle.
              </div>
            )}
          </div>

          {/* Sandbox Environment Profile */}
          <div className="bg-[#0d0e12] border border-[#222430] rounded p-4 text-xs space-y-2">
            <h3 className="font-bold text-[#f4f4f5] uppercase tracking-wider text-[11px] border-b border-[#222430] pb-2 font-mono">
              SANDBOX SECURITY PROFILE
            </h3>
            <div className="space-y-1.5 font-mono text-[11px]">
              <div className="flex justify-between text-[#71717a]">
                <span>Execution Mode:</span>
                <span className="text-[#f4f4f5]">Ephemeral Scratch</span>
              </div>
              <div className="flex justify-between text-[#71717a]">
                <span>Network Access:</span>
                <span className="text-[#10b981]">DISABLED (Zero Egress)</span>
              </div>
              <div className="flex justify-between text-[#71717a]">
                <span>Path Traversal:</span>
                <span className="text-[#10b981]">ENFORCED (Contained)</span>
              </div>
              <div className="flex justify-between text-[#71717a]">
                <span>Persistence:</span>
                <span className="text-[#f4f4f5]">SQLite (WAL Enabled)</span>
              </div>
            </div>
          </div>

          {/* Honest Hardware Telemetry Disclosure */}
          <div className="bg-[#0d0e12] border border-[#222430] rounded p-4 text-xs space-y-2">
            <h3 className="font-bold text-[#f4f4f5] uppercase tracking-wider text-[11px] border-b border-[#222430] pb-2 font-mono flex items-center justify-between">
              <span>HARDWARE TELEMETRY</span>
              <span className="text-[#71717a] font-normal text-[10px]">Offline</span>
            </h3>
            <p className="text-[#71717a] font-mono text-[11px] leading-relaxed">
              Live CPU/GPU/VRAM telemetry unavailable in current backend version (requires host metrics agent). Only genuine SQLite execution records and policy ceilings are displayed.
            </p>
          </div>

          {/* Governance Ceiling Notice */}
          <ResourceBudgetNotice
            iterationsLimit={50}
            toolCallsLimit={100}
            maxRuntime={3600}
          />
        </div>
      </section>

      {/* 5. Row 4: Quick Task Dispatch & Scenario Presets */}
      <section aria-label="Task Submission and Scenarios" className="bg-[#0d0e12] border border-[#222430] rounded p-5 dashboard-anim-section space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#222430] pb-3">
          <div>
            <h2 className="text-sm font-bold text-[#f4f4f5] tracking-wide flex items-center gap-2 font-mono">
              <span className="w-2 h-2 rounded-full bg-[#ef4444]"></span>
              QUICK TASK DISPATCH &amp; PRESET SCENARIOS
            </h2>
            <p className="text-xs text-[#71717a] mt-0.5">
              Dispatch an executable task contract to the deterministic orchestrator
            </p>
          </div>
          <span className="text-[10px] font-mono text-[#71717a] uppercase tracking-wider">
            Schema: TaskContract v1.1
          </span>
        </div>

        {/* Preset Scenario Cards */}
        <div>
          <label className="text-[11px] font-mono text-[#71717a] block uppercase tracking-wider mb-2">
            Select Preset Scenario:
          </label>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {PRESET_SCENARIOS.map((preset) => {
              const isSelected = selectedPresetId === preset.id;
              return (
                <button
                  key={preset.id}
                  type="button"
                  onClick={() => applyPreset(preset)}
                  className={`text-left p-3.5 rounded border transition-all ${
                    isSelected
                      ? 'bg-[#13141b] border-[#ef4444] shadow-[0_0_12px_rgba(239,68,68,0.22)] text-white'
                      : 'bg-[#13141b]/60 border-[#222430] text-[#a1a1aa] hover:border-[#353748] hover:bg-[#13141b]'
                  } focus-visible:ring-2 focus-visible:ring-[#ef4444] focus-visible:outline-none`}
                >
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-[9px] font-mono uppercase text-[#71717a] font-semibold">{preset.category}</span>
                    <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-[#09090b] text-[#fca5a5] border border-[#ef4444]/30">
                      {preset.badge}
                    </span>
                  </div>
                  <div className="font-semibold text-xs text-[#f4f4f5] leading-snug">{preset.title}</div>
                  <p className="text-[11px] text-[#71717a] mt-1.5 line-clamp-2 leading-relaxed">
                    {preset.description}
                  </p>
                </button>
              );
            })}
          </div>
        </div>

        {/* Form */}
        <form onSubmit={handleTaskSubmit} className="space-y-3.5 pt-2">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
            <div>
              <label htmlFor="task-id-input" className="text-[10px] font-mono text-[#71717a] uppercase tracking-wider block mb-1">
                Task ID:
              </label>
              <input
                id="task-id-input"
                type="text"
                value={taskId}
                onChange={(e) => setTaskId(e.target.value)}
                className="w-full bg-[#13141b] border border-[#222430] focus:border-[#ef4444] focus:ring-1 focus:ring-[#ef4444]/40 rounded px-3 py-2 text-xs font-mono text-[#f4f4f5] placeholder-[#71717a] transition-colors"
                placeholder="e.g. task-benchmark-01"
                required
              />
            </div>
            <div>
              <label htmlFor="repo-target-input" className="text-[10px] font-mono text-[#71717a] uppercase tracking-wider block mb-1">
                Target Repository:
              </label>
              <input
                id="repo-target-input"
                type="text"
                value={repoTargetId}
                onChange={(e) => setRepoTargetId(e.target.value)}
                className="w-full bg-[#13141b] border border-[#222430] focus:border-[#ef4444] focus:ring-1 focus:ring-[#ef4444]/40 rounded px-3 py-2 text-xs font-mono text-[#f4f4f5] placeholder-[#71717a] transition-colors"
                placeholder="e.g. repo-payments-api"
                required
              />
            </div>
          </div>

          <div>
            <label htmlFor="task-desc-input" className="text-[10px] font-mono text-[#71717a] uppercase tracking-wider block mb-1">
              Security Objectives &amp; Invariant Requirements:
            </label>
            <textarea
              id="task-desc-input"
              rows={3}
              value={taskDescription}
              onChange={(e) => setTaskDescription(e.target.value)}
              placeholder="Describe desired patch requirements, safety constraints, and invariants to verify..."
              className="w-full bg-[#13141b] border border-[#222430] focus:border-[#ef4444] focus:ring-1 focus:ring-[#ef4444]/40 rounded p-3 text-xs text-[#f4f4f5] placeholder-[#71717a] transition-colors leading-relaxed"
              required
            />
          </div>

          {submissionSuccess && (
            <div className="bg-[#10b981]/15 border border-[#10b981]/30 rounded p-3 text-xs text-[#10b981] flex items-center justify-between">
              <div>
                <span className="font-bold">✓ Run Created Authoritatively: </span>
                <span className="font-mono text-[#f4f4f5] ml-1">{submissionSuccess}</span>
              </div>
              <Link
                href={`/sessions?runId=${encodeURIComponent(submissionSuccess)}`}
                className="bg-[#10b981]/25 hover:bg-[#10b981]/40 text-white font-mono text-[11px] px-3 py-1 rounded transition-colors border border-[#10b981]/40"
              >
                Track in Live Stepper →
              </Link>
            </div>
          )}

          {submissionError && (
            <div className="bg-[#ef4444]/15 border border-[#ef4444]/30 rounded p-3 text-xs text-[#f87171]">
              <span className="font-bold">✕ Submission Rejected: </span>
              <span>{submissionError}</span>
            </div>
          )}

          <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
            <span className="text-[10px] font-mono text-[#71717a]">
              Bounded sandbox ceiling: 20 Iterations • 50 Tool Calls
            </span>
            <button
              ref={submitBtnRef}
              type="submit"
              disabled={isSubmitting || !taskDescription.trim()}
              className="bg-[#ef4444] hover:bg-[#dc2626] disabled:opacity-50 text-white text-xs font-semibold px-4 py-2 rounded shadow-sm transition-all flex items-center gap-2 focus-visible:ring-2 focus-visible:ring-[#ef4444] focus-visible:outline-none"
            >
              {isSubmitting ? (
                <>
                  <span className="motion-safe:animate-spin">◷</span>
                  <span>Creating Run...</span>
                </>
              ) : (
                <>
                  <span>⚡ Dispatch Task Contract</span>
                </>
              )}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}

