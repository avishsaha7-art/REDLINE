"use client";

import React, { useState, useEffect } from 'react';
import { apiClient } from '../api/client';
import { TaskContract, RepositoryResponse } from '../models/types';

interface Props {
  onRunCreated?: (runId: string) => void;
  initialRepoId?: string;
}

export const RunCreationForm: React.FC<Props> = ({ onRunCreated, initialRepoId }) => {
  const [intakeMode, setIntakeMode] = useState<'remote' | 'presets'>('remote');

  // Remote intake states
  const [repoUrl, setRepoUrl] = useState('');
  const [commitSha, setCommitSha] = useState('');
  const [isImporting, setIsImporting] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const [importedRepo, setImportedRepo] = useState<RepositoryResponse | null>(null);

  // Common TaskContract states
  const [taskId, setTaskId] = useState('');
  const [repoId, setRepoId] = useState(initialRepoId || '');
  const [baseCommit, setBaseCommit] = useState('');
  const [description, setDescription] = useState('');
  const [maxIterations, setMaxIterations] = useState(20);
  const [error, setError] = useState<string | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (initialRepoId) {
      setRepoId(initialRepoId);
    }
  }, [initialRepoId]);

  const handleImportRepository = async (e: React.FormEvent) => {
    e.preventDefault();
    setImportError(null);
    const trimmedUrl = repoUrl.trim();
    const trimmedSha = commitSha.trim();

    if (!trimmedUrl) {
      setImportError('Git repository URL is required.');
      return;
    }
    if (!trimmedUrl.startsWith('https://')) {
      setImportError("Repository URL must use the secure 'https://' scheme.");
      return;
    }
    if (!trimmedSha) {
      setImportError('Full 40-character or 64-character commit SHA is required.');
      return;
    }
    if (!/^[0-9a-fA-F]{40}$|^[0-9a-fA-F]{64}$/.test(trimmedSha)) {
      setImportError('Commit SHA must be a valid 40-hex or 64-hex commit hash. Branch names or tags are not permitted for quarantined remote imports.');
      return;
    }

    setIsImporting(true);
    try {
      const response = await apiClient.importRepository({
        repository_url: trimmedUrl,
        commit_sha: trimmedSha,
      });

      setImportedRepo(response);
      setRepoId(response.repository_id);
      setBaseCommit(response.commit_sha || trimmedSha);
      if (!taskId.trim()) {
        const shortId = response.repository_id.replace('repo-remote-', '').slice(0, 8);
        setTaskId(`task-verify-${shortId}`);
      }
      if (!description.trim()) {
        setDescription(`Verify remote repository ${trimmedUrl} at commit ${trimmedSha.slice(0, 10)} against adversarial invariants.`);
      }
      setError(null);
    } catch (err: unknown) {
      setImportError(err instanceof Error ? err.message : String(err));
      setImportedRepo(null);
    } finally {
      setIsImporting(false);
    }
  };

  const loadScenario = (scenario: 'A' | 'B' | 'C' | 'D') => {
    setIntakeMode('presets');
    setError(null);
    setImportError(null);
    setImportedRepo(null);
    setRepoUrl('');
    setCommitSha('');

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
      setError('All TaskContract fields (Task ID, Target ID, Base Commit, and Description) are required.');
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

    // Include remote metadata if intake was initiated with remote URL
    if (repoUrl.trim()) {
      contract.repository_url = repoUrl.trim();
      contract.commit_sha = commitSha.trim() || trimmedBaseCommit;
      // Authoritatively classified as UNTRUSTED
      contract.repository_trust = 'UNTRUSTED';
    } else if (trimmedRepoId.startsWith('repo-remote-')) {
      contract.repository_trust = 'UNTRUSTED';
    }

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

        {/* Presets and Mode Switcher */}
        <div className="flex flex-wrap items-center gap-1.5 text-xs font-mono">
          <div className="flex items-center gap-1 bg-[#13141b] p-0.5 rounded border border-[#222430] mr-1">
            <button
              id="remote-intake-tab"
              type="button"
              onClick={() => {
                setIntakeMode('remote');
                setError(null);
              }}
              className={`text-[10px] px-2 py-0.5 rounded font-semibold transition-colors ${
                intakeMode === 'remote'
                  ? 'bg-[#ef4444] text-white shadow-sm'
                  : 'text-[#a1a1aa] hover:text-[#f4f4f5]'
              }`}
            >
              🌐 Remote Git
            </button>
            <button
              id="presets-tab"
              type="button"
              onClick={() => {
                setIntakeMode('presets');
                setError(null);
              }}
              className={`text-[10px] px-2 py-0.5 rounded font-semibold transition-colors ${
                intakeMode === 'presets'
                  ? 'bg-[#ef4444] text-white shadow-sm'
                  : 'text-[#a1a1aa] hover:text-[#f4f4f5]'
              }`}
            >
              📋 Presets
            </button>
          </div>

          <div className="flex flex-wrap gap-1">
            <button
              type="button"
              onClick={() => loadScenario('A')}
              className="text-[10px] bg-[#10b981]/10 hover:bg-[#10b981]/20 text-[#10b981] border border-[#10b981]/30 font-semibold rounded px-1.5 py-0.5 transition-colors focus-visible:ring-2 focus-visible:ring-[#10b981] focus-visible:outline-none"
              title="Scenario A: Successful Verification"
            >
              A: Verify
            </button>
            <button
              type="button"
              onClick={() => loadScenario('B')}
              className="text-[10px] bg-[#06b6d4]/10 hover:bg-[#06b6d4]/20 text-[#06b6d4] border border-[#06b6d4]/30 font-semibold rounded px-1.5 py-0.5 transition-colors focus-visible:ring-2 focus-visible:ring-[#06b6d4] focus-visible:outline-none"
              title="Scenario B: Autonomous Repair"
            >
              B: Repair
            </button>
            <button
              type="button"
              onClick={() => loadScenario('C')}
              className="text-[10px] bg-[#f59e0b]/10 hover:bg-[#f59e0b]/20 text-[#f59e0b] border border-[#f59e0b]/30 font-semibold rounded px-1.5 py-0.5 transition-colors focus-visible:ring-2 focus-visible:ring-[#f59e0b] focus-visible:outline-none"
              title="Scenario C: Failing/Rejected Candidate"
            >
              C: Reject
            </button>
            <button
              type="button"
              onClick={() => loadScenario('D')}
              className="text-[10px] bg-[#ef4444]/10 hover:bg-[#ef4444]/20 text-[#f87171] border border-[#ef4444]/30 font-semibold rounded px-1.5 py-0.5 transition-colors focus-visible:ring-2 focus-visible:ring-[#ef4444] focus-visible:outline-none"
              title="Scenario D: Untrusted Repo (Policy Blocked)"
            >
              D: Untrusted
            </button>
          </div>
        </div>
      </div>

      {/* ================= STEP 1: REMOTE REPOSITORY IMPORT (IF REMOTE MODE) ================= */}
      {intakeMode === 'remote' && (
        <section aria-labelledby="remote-import-heading" className="mb-5 p-3.5 rounded bg-[#13141b]/70 border border-[#222430]">
          <div className="flex items-center justify-between pb-2 mb-3 border-b border-[#222430]">
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-[#3b82f6]"></span>
              <h3 id="remote-import-heading" className="text-xs font-bold text-[#f4f4f5] uppercase font-mono tracking-wider">
                Step 1: Public Git Repository Intake
              </h3>
            </div>
            <span className="text-[10px] font-mono text-[#a1a1aa] bg-[#09090b] px-2 py-0.5 rounded border border-[#222430]">
              Quarantine Isolation Active
            </span>
          </div>

          <div className="space-y-3">
            <div>
              <label htmlFor="repo-url-input" className="block text-[11px] font-mono font-semibold uppercase tracking-wider text-[#a1a1aa] mb-1">
                Public Git Repository HTTPS URL
              </label>
              <input
                id="repo-url-input"
                type="url"
                required={intakeMode === 'remote'}
                placeholder="https://github.com/org/repo.git"
                value={repoUrl}
                onChange={e => setRepoUrl(e.target.value)}
                disabled={isImporting}
                className="block w-full bg-[#0d0e12] border border-[#222430] rounded p-2 text-xs font-mono text-[#f4f4f5] placeholder:text-[#52525b] focus:border-[#ef4444] focus-visible:ring-1 focus-visible:ring-[#ef4444] focus-visible:outline-none transition-colors"
              />
              <span className="text-[10px] text-[#71717a] font-mono mt-0.5 block">
                Public HTTPS only. Localhost, private RFC 1918 subnets, and metadata IPs are rejected by SSRF gate.
              </span>
            </div>

            <div>
              <label htmlFor="commit-sha-input" className="block text-[11px] font-mono font-semibold uppercase tracking-wider text-[#a1a1aa] mb-1">
                Pinned Git Commit SHA
              </label>
              <input
                id="commit-sha-input"
                type="text"
                required={intakeMode === 'remote'}
                placeholder="e.g. 7fd1a60b01f91b314f59955a4e4d4e80d8edf11d (40 or 64 hex characters)"
                value={commitSha}
                onChange={e => setCommitSha(e.target.value)}
                disabled={isImporting}
                maxLength={64}
                className="block w-full bg-[#0d0e12] border border-[#222430] rounded p-2 text-xs font-mono text-[#f4f4f5] placeholder:text-[#52525b] focus:border-[#ef4444] focus-visible:ring-1 focus-visible:ring-[#ef4444] focus-visible:outline-none transition-colors"
              />
              <span className="text-[10px] text-[#71717a] font-mono mt-0.5 block">
                Must be an immutable exact commit SHA. Dynamic branches and tags are strictly prohibited.
              </span>
            </div>

            <div className="flex items-center gap-3 pt-1">
              <button
                id="import-repo-button"
                type="button"
                onClick={handleImportRepository}
                disabled={isImporting || !repoUrl.trim() || !commitSha.trim()}
                className="bg-[#2563eb] hover:bg-[#1d4ed8] text-white font-bold text-xs px-3.5 py-1.5 rounded transition-all shadow-sm disabled:opacity-50 focus-visible:ring-2 focus-visible:ring-[#2563eb] focus-visible:outline-none cursor-pointer font-mono flex items-center gap-2"
              >
                {isImporting ? (
                  <>
                    <span className="motion-safe:animate-spin">◷</span>
                    <span>Validating &amp; Quarantining...</span>
                  </>
                ) : (
                  <span>📥 Validate &amp; Quarantine Repository</span>
                )}
              </button>

              <span className="text-[10px] font-mono text-[#71717a]">
                Clones in isolated sandbox with zero script execution.
              </span>
            </div>

            {importError && (
              <div className="p-3 bg-[#ef4444]/15 text-[#f87171] rounded border border-[#ef4444]/30 text-xs font-mono" role="alert">
                <strong className="block mb-0.5">Import Gate Rejected:</strong>
                <span>{importError}</span>
              </div>
            )}

            {importedRepo && (
              <div className="p-3 bg-[#10b981]/10 border border-[#10b981]/30 rounded text-xs font-mono space-y-1.5" role="status">
                <div className="flex items-center justify-between text-[#10b981] font-bold">
                  <div className="flex items-center gap-1.5">
                    <span>✓ Repository Quarantined &amp; Registered</span>
                  </div>
                  <span className="px-2 py-0.5 rounded bg-[#ef4444]/15 text-[#f87171] border border-[#ef4444]/30 text-[10px]">
                    Trust: {importedRepo.trust}
                  </span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1 text-[11px] text-[#d4d4d8]">
                  <div>
                    <span className="text-[#71717a] block text-[10px] uppercase">Internal Target ID:</span>
                    <code className="text-[#60a5fa] font-bold select-all">{importedRepo.repository_id}</code>
                  </div>
                  <div>
                    <span className="text-[#71717a] block text-[10px] uppercase">Verified Commit SHA:</span>
                    <code className="text-[#a1a1aa] select-all truncate block" title={importedRepo.commit_sha || ''}>
                      {importedRepo.commit_sha ? importedRepo.commit_sha.slice(0, 16) + '...' : 'Verified'}
                    </code>
                  </div>
                  {importedRepo.snapshot_hash && (
                    <div className="sm:col-span-2">
                      <span className="text-[#71717a] block text-[10px] uppercase">Source Snapshot Digest (SHA-256):</span>
                      <code className="text-[#a1a1aa] select-all text-[10px] truncate block" title={importedRepo.snapshot_hash}>
                        {importedRepo.snapshot_hash}
                      </code>
                    </div>
                  )}
                  <div className="sm:col-span-2 flex items-center justify-between text-[10px] text-[#71717a] pt-1 border-t border-[#10b981]/20">
                    <span>Files: {importedRepo.file_count} • Size: {(importedRepo.total_bytes / 1024).toFixed(1)} KB</span>
                    <span className="text-[#fca5a5]">Enforces SecureSandbox execution (Host blocked)</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        </section>
      )}

      {/* ================= STEP 2: TASK CONTRACT SPECIFICATION ================= */}
      <form onSubmit={handleSubmit} className="space-y-4" aria-busy={isLoading}>
        {intakeMode === 'remote' && (
          <div className="flex items-center gap-1.5 pb-1 border-b border-[#222430]">
            <span className="w-2 h-2 rounded-full bg-[#ef4444]"></span>
            <h3 className="text-xs font-bold text-[#f4f4f5] uppercase font-mono tracking-wider">
              Step 2: Task Contract &amp; Invariants
            </h3>
          </div>
        )}

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
          <div className="flex justify-between items-center mb-1">
            <label htmlFor="repo-id-input" className="block text-[11px] font-mono font-semibold uppercase tracking-wider text-[#71717a]">
              Repository Target ID
            </label>
            {repoId.startsWith('repo-remote-') && (
              <span className="text-[10px] font-mono text-[#f87171]">Quarantined Target (UNTRUSTED)</span>
            )}
          </div>
          <input 
            id="repo-id-input"
            type="text" 
            required 
            placeholder="e.g. repo-payments-api or repo-remote-..."
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
            placeholder="e.g. snap-demo-a-01 or verified commit SHA"
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
          id="launch-run-button"
          type="submit" 
          disabled={isLoading || isImporting}
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
