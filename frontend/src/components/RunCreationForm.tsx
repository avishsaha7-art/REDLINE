"use client";

import React, { useState } from 'react';
import { apiClient } from '../api/client';
import { TaskContract } from '../models/types';

interface Props {
  onRunCreated?: (runId: string) => void;
}

export const RunCreationForm: React.FC<Props> = ({ onRunCreated }) => {
  const [taskId, setTaskId] = useState('');
  const [repoId, setRepoId] = useState('');
  const [baseCommit, setBaseCommit] = useState('');
  const [description, setDescription] = useState('');
  const [maxIterations, setMaxIterations] = useState(20);
  const [error, setError] = useState<string | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const loadScenario = (scenario: 'A' | 'B' | 'C' | 'D') => {
    setError(null);
    if (scenario === 'A') {
      setTaskId('task-demo-verified-01');
      setRepoId('repo-int-1');
      setBaseCommit('snap-demo-a-01');
      setDescription('Implement bug fix in main.py and verify correctness against deterministic contract.');
      setMaxIterations(20);
    } else if (scenario === 'B') {
      setTaskId('task-demo-repair-02');
      setRepoId('repo-int-1');
      setBaseCommit('snap-demo-b-02');
      setDescription('Resolve edge-case defect; trigger autonomous repair upon initial counterexample.');
      setMaxIterations(20);
    } else if (scenario === 'C') {
      setTaskId('task-demo-rejected-03');
      setRepoId('repo-int-1');
      setBaseCommit('snap-demo-c-03');
      setDescription('Unfixable boundary defect; proves REJECTED candidate is never marked successful.');
      setMaxIterations(5);
    } else if (scenario === 'D') {
      setTaskId('task-demo-untrusted-04');
      setRepoId('untrusted-external-repo');
      setBaseCommit('snap-demo-d-04');
      setDescription('Attempt untrusted execution on LocalDevelopmentBackend; policy must block host execution.');
      setMaxIterations(5);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError(null);
    setRunId(null);

    const trimmedTaskId = taskId.trim();
    const trimmedRepoId = repoId.trim();
    const trimmedBaseCommit = baseCommit.trim();
    const trimmedDescription = description.trim();

    if (!trimmedTaskId || !trimmedRepoId || !trimmedBaseCommit || !trimmedDescription) {
      setError('All fields are required.');
      setIsLoading(false);
      return;
    }

    const contract: TaskContract = {
      task_id: trimmedTaskId,
      repository_id: trimmedRepoId,
      base_commit_or_snapshot: trimmedBaseCommit,
      task_description: trimmedDescription,
      allowed_scope: [],
      resource_budget: {
        max_iterations: Math.min(Math.max(1, maxIterations), 50),
        max_runtime: 3600,
        max_patch_size: 1048576,
        max_tool_calls: 100,
        max_failed_attempts: 3,
        max_attack_cases: 20,
        max_file_size: 1048576,
        max_repo_files: 1000,
        max_repo_bytes: 52428800,
        max_context_bytes: 131072
      }
    };

    try {
      const response = await apiClient.createRun(contract);
      setRunId(response.run_id);
      if (onRunCreated) {
        onRunCreated(response.run_id);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="run-creation-form border border-[#222430] p-5 rounded bg-[#0d0e12] card-laser-border text-[#f4f4f5] shadow-lg" role="region" aria-label="Task Contract Creation Form">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-4 border-b border-[#222430] pb-3 gap-2">
        <div>
          <h2 className="text-base font-bold text-[#f4f4f5] tracking-wide font-sans">Create Verification Run</h2>
          <p className="text-[11px] text-[#71717a] font-mono mt-0.5">Authoritative intake validated against TaskContract schema</p>
        </div>
        <div className="flex flex-wrap gap-1 text-xs font-mono">
          <span className="text-[#71717a] self-center mr-1 text-[11px]">Presets:</span>
          <button
            type="button"
            onClick={() => loadScenario('A')}
            className="text-[11px] bg-[#10b981]/10 hover:bg-[#10b981]/20 text-[#10b981] border border-[#10b981]/30 font-semibold rounded px-2 py-0.5 transition-colors focus-visible:ring-2 focus-visible:ring-[#10b981] focus-visible:outline-none"
            title="Scenario A: Successful Verification"
          >
            A: Verify
          </button>
          <button
            type="button"
            onClick={() => loadScenario('B')}
            className="text-[11px] bg-[#06b6d4]/10 hover:bg-[#06b6d4]/20 text-[#06b6d4] border border-[#06b6d4]/30 font-semibold rounded px-2 py-0.5 transition-colors focus-visible:ring-2 focus-visible:ring-[#06b6d4] focus-visible:outline-none"
            title="Scenario B: Autonomous Repair"
          >
            B: Repair
          </button>
          <button
            type="button"
            onClick={() => loadScenario('C')}
            className="text-[11px] bg-[#f59e0b]/10 hover:bg-[#f59e0b]/20 text-[#f59e0b] border border-[#f59e0b]/30 font-semibold rounded px-2 py-0.5 transition-colors focus-visible:ring-2 focus-visible:ring-[#f59e0b] focus-visible:outline-none"
            title="Scenario C: Failing/Rejected Candidate"
          >
            C: Reject
          </button>
          <button
            type="button"
            onClick={() => loadScenario('D')}
            className="text-[11px] bg-[#ef4444]/10 hover:bg-[#ef4444]/20 text-[#f87171] border border-[#ef4444]/30 font-semibold rounded px-2 py-0.5 transition-colors focus-visible:ring-2 focus-visible:ring-[#ef4444] focus-visible:outline-none"
            title="Scenario D: Untrusted Repo (Policy Blocked)"
          >
            D: Untrusted
          </button>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4" aria-busy={isLoading}>
        <div>
          <label htmlFor="task-id-input" className="block text-[11px] font-mono font-semibold uppercase tracking-wider text-[#71717a] mb-1">
            Task ID
          </label>
          <input 
            id="task-id-input"
            type="text" 
            required 
            placeholder="e.g. task-benchmark-42"
            value={taskId} 
            onChange={e => setTaskId(e.target.value)}
            className="mt-1 block w-full bg-[#13141b] border border-[#222430] rounded p-2.5 text-xs font-mono text-[#f4f4f5] placeholder:text-[#52525b] focus:border-[#ef4444] focus-visible:ring-1 focus-visible:ring-[#ef4444] focus-visible:outline-none transition-colors"
          />
        </div>

        <div>
          <label htmlFor="repo-id-input" className="block text-[11px] font-mono font-semibold uppercase tracking-wider text-[#71717a] mb-1">
            Repository Target ID
          </label>
          <input 
            id="repo-id-input"
            type="text" 
            required 
            placeholder="e.g. repo-payments-api"
            value={repoId} 
            onChange={e => setRepoId(e.target.value)}
            className="mt-1 block w-full bg-[#13141b] border border-[#222430] rounded p-2.5 text-xs font-mono text-[#f4f4f5] placeholder:text-[#52525b] focus:border-[#ef4444] focus-visible:ring-1 focus-visible:ring-[#ef4444] focus-visible:outline-none transition-colors"
          />
        </div>

        <div>
          <label htmlFor="base-commit-input" className="block text-[11px] font-mono font-semibold uppercase tracking-wider text-[#71717a] mb-1">
            Base Commit / Snapshot Hash
          </label>
          <input 
            id="base-commit-input"
            type="text" 
            required 
            placeholder="e.g. snap-demo-a-01 or SHA256 hex"
            value={baseCommit} 
            onChange={e => setBaseCommit(e.target.value)}
            className="mt-1 block w-full bg-[#13141b] border border-[#222430] rounded p-2.5 text-xs font-mono text-[#f4f4f5] placeholder:text-[#52525b] focus:border-[#ef4444] focus-visible:ring-1 focus-visible:ring-[#ef4444] focus-visible:outline-none transition-colors"
          />
        </div>

        <div>
          <label htmlFor="description-input" className="block text-[11px] font-mono font-semibold uppercase tracking-wider text-[#71717a] mb-1">
            Task Description &amp; Security Objectives
          </label>
          <textarea 
            id="description-input"
            required 
            rows={3}
            placeholder="Describe the desired functionality and invariants to verify..."
            value={description} 
            onChange={e => setDescription(e.target.value)}
            className="mt-1 block w-full bg-[#13141b] border border-[#222430] rounded p-2.5 text-xs text-[#f4f4f5] placeholder:text-[#52525b] focus:border-[#ef4444] focus-visible:ring-1 focus-visible:ring-[#ef4444] focus-visible:outline-none leading-relaxed transition-colors"
          />
        </div>

        <div>
          <div className="flex justify-between items-center mb-1">
            <label htmlFor="max-iterations-input" className="block text-[11px] font-mono font-semibold uppercase tracking-wider text-[#71717a]">
              Max Iterations
            </label>
            <span className="text-[11px] font-mono text-[#71717a]">System ceiling: 50</span>
          </div>
          <input 
            id="max-iterations-input"
            type="number" 
            min="1"
            max="50"
            value={maxIterations} 
            onChange={e => setMaxIterations(parseInt(e.target.value, 10) || 1)}
            className="block w-full bg-[#13141b] border border-[#222430] rounded p-2 text-xs font-mono text-[#f4f4f5] focus:border-[#ef4444] focus-visible:ring-1 focus-visible:ring-[#ef4444] focus-visible:outline-none transition-colors"
          />
        </div>

        <button 
          type="submit" 
          disabled={isLoading}
          className="w-full bg-[#ef4444] hover:bg-[#dc2626] text-white font-bold text-xs px-4 py-2.5 rounded transition-all shadow-[0_0_12px_rgba(239,68,68,0.25)] hover:shadow-[0_0_16px_rgba(239,68,68,0.4)] disabled:opacity-50 focus-visible:ring-2 focus-visible:ring-[#ef4444] focus-visible:outline-none cursor-pointer font-mono flex items-center justify-center gap-2"
        >
          {isLoading ? (
            <>
              <span className="motion-safe:animate-spin">◷</span>
              <span>Launching in Background...</span>
            </>
          ) : (
            <span>⚡ Launch Adversarial Verification Run</span>
          )}
        </button>
      </form>
      
      {error && (
        <div className="mt-4 p-3 bg-[#ef4444]/15 text-[#f87171] rounded border border-[#ef4444]/30 text-xs font-mono" role="alert">
          <strong className="block mb-0.5">Submission Error:</strong> {error}
        </div>
      )}
      
      {runId && (
        <div className="mt-4 p-3 bg-[#10b981]/15 text-[#10b981] rounded border border-[#10b981]/30 text-xs font-mono" role="status">
          <strong className="block mb-0.5">Run Initiated Successfully!</strong>
          <span>Run ID: <code className="font-mono font-bold select-all text-white bg-[#09090b] px-1.5 py-0.5 rounded border border-[#10b981]/40">{runId}</code></span>
        </div>
      )}
    </div>
  );
};
