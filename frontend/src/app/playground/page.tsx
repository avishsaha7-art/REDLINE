"use client";

import React, { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';

export const SAMPLE_CONTRACTS = {
  valid: {
    task_id: "task-playground-valid-01",
    repository_id: "repo-int-1",
    base_commit_or_snapshot: "snap-demo-a-01",
    task_description: "Implement bug fix in main.py and verify correctness against deterministic contract.",
    allowed_scope: ["backend/main.py", "tests/test_main.py"],
    resource_budget: {
      max_iterations: 20,
      max_runtime: 3600,
      max_patch_size: 1048576,
      max_tool_calls: 100,
      max_failed_attempts: 3,
      max_attack_cases: 20
    }
  },
  repair: {
    task_id: "task-playground-repair-02",
    repository_id: "repo-int-1",
    base_commit_or_snapshot: "snap-demo-b-02",
    task_description: "Resolve edge-case defect; trigger autonomous repair upon initial counterexample.",
    allowed_scope: ["backend/service.py"],
    resource_budget: {
      max_iterations: 20,
      max_runtime: 3600,
      max_patch_size: 1048576,
      max_tool_calls: 100,
      max_failed_attempts: 3,
      max_attack_cases: 20
    }
  },
  malicious: {
    task_id: "task-invalid-traversal-../etc",
    repository_id: "repo-int-1",
    base_commit_or_snapshot: "snap-demo-invalid",
    task_description: "Attempt path traversal outside allowed repository boundaries.",
    allowed_scope: ["../../etc/passwd", "/etc/shadow"],
    resource_budget: {
      max_iterations: 999, // Exceeds ceiling
      max_runtime: 999999
    }
  },
  untrusted: {
    task_id: "task-playground-untrusted-04",
    repository_id: "untrusted-external-repo",
    base_commit_or_snapshot: "snap-demo-d-04",
    task_description: "Third-party untrusted payload subject to fail-closed host execution blocking.",
    allowed_scope: ["plugins/**"],
    resource_budget: {
      max_iterations: 10,
      max_runtime: 600,
      max_patch_size: 524288,
      max_tool_calls: 25,
      max_failed_attempts: 1,
      max_attack_cases: 5
    }
  }
};

export const SAMPLE_OBSERVATIONS = [
  {
    id: "obs-demo-01",
    title: "Scenario A: Clean Invariant Test Run",
    command: "pytest tests/invariants/ -v",
    exit_code: 0,
    status: "COMPLETED",
    duration_ms: 245,
    stdout_sha256: "9b3c4a1e8d7f2b5a0c6e1d3f5a7b9c2d4e6f8a0b2c4d6e8f0a2b4c6d8e0f2a4b",
    stderr_sha256: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    stdout_bytes: 842,
    stderr_bytes: 0,
    sandbox_backend: "LocalDevelopmentBackend",
    security_level: "DEVELOPMENT_ONLY",
    workspace_id: "ws-ephemeral-scratch-01",
    log_output: `[REDLINE LocalDevelopmentBackend] Container cwd: /scratch/ws-ephemeral-scratch-01/repo-int-1
[REDLINE Sandbox Policy] Network egress: DISABLED
[REDLINE Sandbox Policy] Path traversal: FAIL_CLOSED
============================= test session starts ==============================
tests/invariants/test_balance.py::test_currency_precision PASSED         [ 50%]
tests/invariants/test_balance.py::test_refund_invariant PASSED           [100%]
============================== 2 passed in 0.24s ===============================
[REDLINE Execution] Exit code: 0. Integrity digest: SHA256:9b3c4a1e8d... recorded.`
  },
  {
    id: "obs-demo-02",
    title: "Scenario D: Untrusted Target Quarantine",
    command: "pytest plugins/third_party/ -v",
    exit_code: 1,
    status: "POLICY_BLOCKED",
    duration_ms: 12,
    stdout_sha256: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    stderr_sha256: "a1b2c3d4e5f60718293a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e",
    stdout_bytes: 0,
    stderr_bytes: 312,
    sandbox_backend: "LocalDevelopmentBackend",
    security_level: "BLOCKED",
    workspace_id: "ws-quarantine-blocked",
    log_output: `[REDLINE Security Gate (Section 47)] Target repository: untrusted-external-repo
[REDLINE Trust Resolver] Trust classification: UNTRUSTED (fail-closed)
[SECURITY EXCEPTION] Host execution strictly blocked on LocalDevelopmentBackend.
[REASON] Untrusted repositories require hardware-isolated MicroVMs; execution on host local backend is prohibited.
[TERMINAL ACTION] Run transitioned to ABORTED with status POLICY_BLOCKED.`
  }
];

export default function PlaygroundPage() {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<'manifest' | 'sandbox' | 'observations'>('manifest');
  const [jsonText, setJsonText] = useState<string>(
    JSON.stringify(SAMPLE_CONTRACTS.valid, null, 2)
  );
  const [selectedObservation, setSelectedObservation] = useState<number>(0);
  const [validationResult, setValidationResult] = useState<{
    valid: boolean;
    message: string;
    warnings?: string[];
  } | null>(null);

  const loadTemplate = (key: keyof typeof SAMPLE_CONTRACTS) => {
    setJsonText(JSON.stringify(SAMPLE_CONTRACTS[key], null, 2));
    setValidationResult(null);
  };

  const validateContract = () => {
    try {
      const parsed = JSON.parse(jsonText);
      const warnings: string[] = [];

      // Validate required fields
      if (!parsed.task_id || typeof parsed.task_id !== 'string') {
        setValidationResult({ valid: false, message: "Field 'task_id' is required and must be a string." });
        return;
      }
      if (!/^[a-zA-Z0-9_\-\.]+$/.test(parsed.task_id)) {
        setValidationResult({ valid: false, message: "Field 'task_id' must match regex '^[a-zA-Z0-9_\\-\\.]+$' (no slashes or path traversal)." });
        return;
      }
      if (!parsed.repository_id || typeof parsed.repository_id !== 'string') {
        setValidationResult({ valid: false, message: "Field 'repository_id' is required and must be a string." });
        return;
      }
      if (!parsed.base_commit_or_snapshot || typeof parsed.base_commit_or_snapshot !== 'string') {
        setValidationResult({ valid: false, message: "Field 'base_commit_or_snapshot' is required." });
        return;
      }
      if (!parsed.task_description || typeof parsed.task_description !== 'string') {
        setValidationResult({ valid: false, message: "Field 'task_description' is required." });
        return;
      }

      // Check allowed_scope for traversal
      if (Array.isArray(parsed.allowed_scope)) {
        for (const pattern of parsed.allowed_scope) {
          if (pattern.includes('..') || pattern.startsWith('/') || pattern.startsWith('\\')) {
            setValidationResult({
              valid: false,
              message: `Path traversal violation in allowed_scope: '${pattern}' contains prohibited '../' or root directory references.`
            });
            return;
          }
        }
      }

      // Check budget caps
      if (parsed.resource_budget) {
        if (parsed.resource_budget.max_iterations > 50) {
          warnings.push("Budget ceiling note: 'max_iterations' exceeds system ceiling of 50. Backend will cap this value to 50.");
        }
        if (parsed.resource_budget.max_tool_calls > 100) {
          warnings.push("Budget ceiling note: 'max_tool_calls' exceeds system ceiling of 100. Backend will cap this value to 100.");
        }
      }

      setValidationResult({
        valid: true,
        message: "Contract schema validation PASSED. Payload conforms to TaskContract specification.",
        warnings: warnings.length > 0 ? warnings : undefined
      });
    } catch (err: unknown) {
      setValidationResult({
        valid: false,
        message: `JSON syntax error: ${err instanceof Error ? err.message : String(err)}`
      });
    }
  };

  const exportToIntake = () => {
    try {
      const parsed = JSON.parse(jsonText);
      router.push(`/?taskId=${encodeURIComponent(parsed.task_id)}&repoId=${encodeURIComponent(parsed.repository_id)}`);
    } catch {
      validateContract();
    }
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12">
      {/* ================= HEADER SECTION ================= */}
      <header className="border-b border-[#222430] pb-5">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div>
            <div className="flex items-center gap-2 text-xs font-mono text-[#71717a] mb-1.5">
              <span className="text-[#ef4444]">ORCHESTRATION</span>
              <span>{'//'}</span>
              <span className="text-[#f4f4f5]">PLAYGROUND &amp; SANDBOX</span>
              <span>{'//'}</span>
              <span className="text-[#a1a1aa]">EPHEMERAL-ENCLAVE-04</span>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-2xl sm:text-3xl font-black tracking-tight text-[#f4f4f5] flex items-center gap-3">
                <span className="text-[#ef4444]">07.</span>
                <span>PLAYGROUND &amp; SANDBOX DEEP DIVE</span>
              </h1>
              <span className="text-xs font-mono font-medium text-[#10b981] border border-[#10b981]/30 px-2 py-0.5 rounded bg-[#10b981]/10">
                Deterministic Workbench
              </span>
              <span className="text-xs font-mono font-normal text-[#a1a1aa] border border-[#222430] px-2 py-0.5 rounded bg-[#0d0e12] hidden sm:inline-block">
                v2.4-deterministic
              </span>
            </div>

            <p className="text-xs sm:text-sm text-[#a1a1aa] font-sans mt-2">
              Interactive workbench for authoring, linting, and validating TaskContracts, and inspecting sandbox isolation policies.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2.5 w-full sm:w-auto">
            <Link
              href="/"
              className="inline-flex items-center gap-1.5 text-xs font-bold bg-[#ef4444] hover:bg-[#dc2626] text-white px-4 py-2 rounded transition-all shadow-[0_0_12px_rgba(239,68,68,0.35)]"
            >
              <span>Go to Task Intake</span>
              <span aria-hidden="true">&rarr;</span>
            </Link>
          </div>
        </div>
      </header>

      {/* ================= TELEMETRY & CEILING READOUT STRIP ================= */}
      <section aria-labelledby="sandbox-telemetry-heading" className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <h2 id="sandbox-telemetry-heading" className="sr-only">Sandbox Telemetry and Policy Ceilings</h2>
        <div className="p-3 rounded-lg bg-[#0d0e12] border border-[#222430] flex flex-col justify-between">
          <span className="text-[10px] font-mono text-[#71717a] uppercase font-semibold">ISOLATION BACKEND</span>
          <span className="text-xs font-mono font-bold text-[#f4f4f5] mt-1">LocalDevelopmentBackend</span>
          <span className="text-[10px] font-mono text-[#10b981] mt-0.5">Ephemeral Scratch Mode</span>
        </div>
        <div className="p-3 rounded-lg bg-[#0d0e12] border border-[#222430] flex flex-col justify-between">
          <span className="text-[10px] font-mono text-[#71717a] uppercase font-semibold">NETWORK EGRESS</span>
          <span className="text-xs font-mono font-bold text-[#ef4444] mt-1">REJECT ALL (Air-gapped)</span>
          <span className="text-[10px] font-mono text-[#71717a] mt-0.5">Zero Outbound Sockets</span>
        </div>
        <div className="p-3 rounded-lg bg-[#0d0e12] border border-[#222430] flex flex-col justify-between">
          <span className="text-[10px] font-mono text-[#71717a] uppercase font-semibold">PATH TRAVERSAL GATE</span>
          <span className="text-xs font-mono font-bold text-[#10b981] mt-1">FAIL_CLOSED</span>
          <span className="text-[10px] font-mono text-[#71717a] mt-0.5">Pre-execution Guard</span>
        </div>
        <div className="p-3 rounded-lg bg-[#0d0e12] border border-[#222430] flex flex-col justify-between">
          <span className="text-[10px] font-mono text-[#71717a] uppercase font-semibold">RESOURCE CEILINGS</span>
          <span className="text-xs font-mono font-bold text-[#60a5fa] mt-1">50 Iters / 100 Tools</span>
          <span className="text-[10px] font-mono text-[#71717a] mt-0.5">Max 3600s Runtime</span>
        </div>
      </section>

      {/* ================= CONTROLS & TAB STRIP ================= */}
      <section aria-labelledby="playground-tabs-heading" className="bg-[#0d0e12] border border-[#222430] p-3 rounded-lg flex flex-wrap items-center justify-between gap-3 shadow-sm">
        <h2 id="playground-tabs-heading" className="sr-only">Playground Workbench Tabs</h2>

        {/* Tab Buttons */}
        <div className="flex items-center gap-1.5 p-1 rounded bg-[#13141b] border border-[#222430]">
          <button
            type="button"
            onClick={() => setActiveTab('manifest')}
            className={`px-3 py-1 rounded font-mono text-xs font-semibold transition-colors ${
              activeTab === 'manifest'
                ? 'bg-[#0d0e12] text-[#f4f4f5] border border-[#353748]'
                : 'text-[#71717a] hover:text-[#f4f4f5]'
            }`}
          >
            Contract Manifest (JSON)
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('observations')}
            className={`px-3 py-1 rounded font-mono text-xs font-semibold transition-colors ${
              activeTab === 'observations'
                ? 'bg-[#0d0e12] text-[#f4f4f5] border border-[#353748]'
                : 'text-[#71717a] hover:text-[#f4f4f5]'
            }`}
          >
            Execution Observations
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('sandbox')}
            className={`px-3 py-1 rounded font-mono text-xs font-semibold transition-colors ${
              activeTab === 'sandbox'
                ? 'bg-[#0d0e12] text-[#f4f4f5] border border-[#353748]'
                : 'text-[#71717a] hover:text-[#f4f4f5]'
            }`}
          >
            Sandbox Isolation Policy
          </button>
        </div>

        {/* Template Selector Presets */}
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-[11px] font-mono text-[#71717a] mr-1">Load Preset:</span>
          <button
            type="button"
            onClick={() => loadTemplate('valid')}
            className="px-2.5 py-1 rounded bg-[#10b981]/10 text-[#10b981] border border-[#10b981]/30 hover:bg-[#10b981]/20 font-mono text-[10px] font-semibold transition-colors"
          >
            Valid Benchmark
          </button>
          <button
            type="button"
            onClick={() => loadTemplate('repair')}
            className="px-2.5 py-1 rounded bg-[#60a5fa]/10 text-[#60a5fa] border border-[#60a5fa]/30 hover:bg-[#60a5fa]/20 font-mono text-[10px] font-semibold transition-colors"
          >
            Autonomous Repair
          </button>
          <button
            type="button"
            onClick={() => loadTemplate('malicious')}
            className="px-2.5 py-1 rounded bg-[#ef4444]/10 text-[#f87171] border border-[#ef4444]/30 hover:bg-[#ef4444]/20 font-mono text-[10px] font-semibold transition-colors"
          >
            Traversal Violation
          </button>
          <button
            type="button"
            onClick={() => loadTemplate('untrusted')}
            className="px-2.5 py-1 rounded bg-amber-950/40 text-amber-300 border border-amber-800 hover:bg-amber-950/60 font-mono text-[10px] font-semibold transition-colors"
          >
            Untrusted Target
          </button>
        </div>
      </section>

      {/* ================= TAB CONTENT: MANIFEST WORKBENCH ================= */}
      {activeTab === 'manifest' && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* JSON Textarea Editor (Col 8) */}
          <section aria-labelledby="manifest-editor-heading" className="lg:col-span-8 border border-[#222430] rounded-lg bg-[#0d0e12] overflow-hidden shadow-lg">
            <div className="p-3 bg-[#13141b] border-b border-[#222430] flex items-center justify-between text-xs font-mono">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-[#10b981]" />
                <h2 id="manifest-editor-heading" className="font-bold text-[#f4f4f5]">TaskContract JSON Manifest</h2>
              </div>
              <span className="text-[#71717a]">Pydantic Schema Compliant</span>
            </div>

            <textarea
              rows={18}
              value={jsonText}
              onChange={(e) => setJsonText(e.target.value)}
              className="w-full bg-[#09090b] p-4 text-xs font-mono text-[#e5e1e4] focus:outline-none focus:ring-1 focus:ring-[#ef4444] leading-relaxed border-none resize-y"
              aria-label="TaskContract JSON Editor"
            />

            <div className="p-3 bg-[#13141b] border-t border-[#222430] flex flex-wrap items-center justify-between gap-3">
              <span className="text-[11px] font-mono text-[#71717a]">
                Validate schema syntax and scope boundaries prior to backend dispatch
              </span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={validateContract}
                  className="px-4 py-1.5 rounded bg-[#ef4444] hover:bg-[#dc2626] text-white font-mono text-xs font-bold transition-all shadow-[0_0_10px_rgba(239,68,68,0.3)]"
                >
                  Validate Contract Schema
                </button>
                {validationResult?.valid && (
                  <button
                    type="button"
                    onClick={exportToIntake}
                    className="px-3.5 py-1.5 rounded bg-[#13141b] hover:bg-[#1a1b24] text-[#10b981] border border-[#10b981]/40 font-mono text-xs font-semibold transition-colors"
                  >
                    Export to Intake Form →
                  </button>
                )}
              </div>
            </div>
          </section>

          {/* Validation Report & Scope Advisory (Col 4) */}
          <div className="lg:col-span-4 space-y-4">
            <section aria-labelledby="linting-report-heading" className="bg-[#0d0e12] border border-[#222430] p-5 rounded-lg text-xs space-y-3 shadow-sm">
              <h2 id="linting-report-heading" className="text-xs uppercase font-bold tracking-wider text-[#f4f4f5] font-mono border-b border-[#222430] pb-2">
                Schema Linting Report
              </h2>

              {validationResult ? (
                <div className="space-y-3">
                  <div className={`p-3 rounded-md border ${
                    validationResult.valid 
                      ? 'bg-[#10b981]/10 border-[#10b981]/30 text-[#10b981]' 
                      : 'bg-[#ef4444]/10 border-[#ef4444]/30 text-[#f87171]'
                  }`}>
                    <strong className="block text-xs font-mono font-bold mb-1">
                      {validationResult.valid ? '✓ Validation Passed' : '✕ Schema Rejection'}
                    </strong>
                    <p className="text-[11px] leading-relaxed font-mono">{validationResult.message}</p>
                  </div>

                  {validationResult.warnings && validationResult.warnings.length > 0 && (
                    <div className="p-3 rounded-md border bg-amber-950/40 border-amber-800 text-amber-300">
                      <strong className="block text-xs font-mono font-bold mb-1">⚠️ Policy Ceiling Warnings:</strong>
                      <ul className="list-disc pl-4 space-y-1 text-[11px] font-mono">
                        {validationResult.warnings.map((w, i) => (
                          <li key={i}>{w}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-[#71717a] text-[11px] font-mono leading-relaxed">
                  Click &ldquo;Validate Contract Schema&rdquo; to test your JSON payload against REDLINE path traversal and resource ceiling gates.
                </p>
              )}
            </section>

            <section aria-labelledby="client-verification-notice" className="bg-[#0d0e12] border border-[#222430] p-4 rounded-lg text-xs text-[#a1a1aa] space-y-1 shadow-sm">
              <h2 id="client-verification-notice" className="text-white font-semibold block font-mono text-[11px]">
                Client-Side Verification Scope:
              </h2>
              <p className="text-[11px] leading-relaxed font-sans">
                This workbench performs client-side syntax, regex, and security schema validation. It does not initiate sandboxes or execute code on the host. Authoritative execution requires submission to <code className="text-[#ef4444] font-mono">POST /api/v1/runs</code>.
              </p>
            </section>
          </div>
        </div>
      )}

      {/* ================= TAB CONTENT: EXECUTION OBSERVATIONS ================= */}
      {activeTab === 'observations' && (
        <div className="space-y-4">
          {/* Read-Only Terminal Header & Security Notice */}
          <div className="p-3 bg-amber-950/30 border border-amber-900/60 rounded-lg text-xs text-amber-200 flex items-start gap-3">
            <span className="text-base select-none mt-0.5" aria-hidden="true">🛡️</span>
            <div>
              <strong className="block text-amber-300 font-semibold font-mono text-[11px] uppercase tracking-wide">
                Read-Only Telemetry Viewer (Section 47 Boundary):
              </strong>
              <p className="text-[11px] text-[#a1a1aa] leading-relaxed">
                Host command execution is strictly prohibited by REDLINE security boundaries. The console below provides deterministic, read-only inspection of genuine <code className="text-[#fca5a5] font-mono">StructuredObservation</code> records from verified sandbox runs. Arbitrary shell injection is disabled.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
            {/* Observation List (Col 4) */}
            <div className="lg:col-span-4 space-y-3">
              <span className="text-xs font-mono font-bold text-[#71717a] uppercase tracking-wider block">
                Recorded Observations ({SAMPLE_OBSERVATIONS.length})
              </span>
              {SAMPLE_OBSERVATIONS.map((obs, idx) => (
                <button
                  key={obs.id}
                  type="button"
                  onClick={() => setSelectedObservation(idx)}
                  className={`w-full text-left p-3 rounded-lg border transition-all ${
                    selectedObservation === idx
                      ? 'bg-[#13141b] border-[#ef4444]/60 shadow-[0_0_10px_rgba(239,68,68,0.2)]'
                      : 'bg-[#0d0e12] border-[#222430] hover:border-[#353748]'
                  }`}
                >
                  <div className="flex items-center justify-between text-xs font-mono mb-1">
                    <span className="font-bold text-[#f4f4f5]">{obs.title}</span>
                    <span className={`px-1.5 py-0.2 rounded text-[10px] ${
                      obs.status === 'COMPLETED'
                        ? 'bg-[#10b981]/15 text-[#10b981] border border-[#10b981]/30'
                        : 'bg-[#ef4444]/15 text-[#f87171] border border-[#ef4444]/30'
                    }`}>
                      {obs.status}
                    </span>
                  </div>
                  <div className="text-[11px] font-mono text-[#71717a]">
                    Exit code: {obs.exit_code} • Duration: {obs.duration_ms}ms
                  </div>
                </button>
              ))}
            </div>

            {/* Read-Only Terminal Shell (Col 8) */}
            <div className="lg:col-span-8 border border-[#222430] rounded-lg bg-[#09090b] overflow-hidden shadow-2xl">
              {/* Terminal Titlebar */}
              <div className="px-4 py-2.5 bg-[#13141b] border-b border-[#222430] flex items-center justify-between text-xs font-mono">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-[#ef4444]" />
                  <span className="w-2.5 h-2.5 rounded-full bg-amber-500" />
                  <span className="w-2.5 h-2.5 rounded-full bg-[#10b981]" />
                  <span className="ml-2 font-bold text-[#f4f4f5]">
                    {SAMPLE_OBSERVATIONS[selectedObservation].id} :: Observation Stream
                  </span>
                </div>
                <span className="text-[10px] text-[#71717a]">
                  Backend: {SAMPLE_OBSERVATIONS[selectedObservation].sandbox_backend}
                </span>
              </div>

              {/* Terminal Content */}
              <div className="p-4 space-y-2 font-mono text-xs text-[#e5e1e4] leading-relaxed max-h-[420px] overflow-y-auto">
                <div className="text-[#71717a] text-[11px]">
                  $ {SAMPLE_OBSERVATIONS[selectedObservation].command}
                </div>
                <pre className="text-[11px] text-[#a1a1aa] whitespace-pre-wrap leading-relaxed">
                  {SAMPLE_OBSERVATIONS[selectedObservation].log_output}
                </pre>
              </div>

              {/* Terminal Footer Telemetry */}
              <div className="px-4 py-2 bg-[#0d0e12] border-t border-[#222430] flex flex-wrap items-center justify-between gap-2 text-[10px] font-mono text-[#71717a]">
                <span>Stdout SHA-256: {SAMPLE_OBSERVATIONS[selectedObservation].stdout_sha256.substring(0, 16)}...</span>
                <span>Security Level: {SAMPLE_OBSERVATIONS[selectedObservation].security_level}</span>
                <span>Egress: REJECT ALL</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ================= TAB CONTENT: SANDBOX ISOLATION POLICY ================= */}
      {activeTab === 'sandbox' && (
        <section aria-labelledby="sandbox-isolation-specs-heading" className="grid grid-cols-1 md:grid-cols-2 gap-5">
          <h2 id="sandbox-isolation-specs-heading" className="sr-only">Sandbox Isolation Specifications</h2>
          <div className="bg-[#0d0e12] border border-[#222430] p-5 rounded-lg space-y-3">
            <h3 className="text-xs font-mono font-bold text-[#f4f4f5] uppercase tracking-wider border-b border-[#222430] pb-2">
              Filesystem &amp; Process Isolation
            </h3>
            <div className="space-y-2 text-xs font-sans text-[#a1a1aa]">
              <div>
                <strong className="text-white block font-mono text-[11px]">Ephemeral Scratch Containment:</strong>
                <p className="text-[11px] leading-relaxed">Every run executes inside an isolated ephemeral working directory under <code className="text-[#fca5a5] font-mono">scratch/</code>. No write access is granted to repository roots.</p>
              </div>
              <div>
                <strong className="text-white block font-mono text-[11px]">Fail-Closed Path Traversal (Section 47):</strong>
                <p className="text-[11px] leading-relaxed">All paths containing <code className="text-[#ef4444] font-mono">../</code> or absolute root slashes are rejected prior to execution dispatch.</p>
              </div>
              <div>
                <strong className="text-white block font-mono text-[11px]">Non-Root Execution:</strong>
                <p className="text-[11px] leading-relaxed">Agent processes run under restricted user permissions. Sudo, setuid, and kernel modification calls are disallowed.</p>
              </div>
            </div>
          </div>

          <div className="bg-[#0d0e12] border border-[#222430] p-5 rounded-lg space-y-3">
            <h3 className="text-xs font-mono font-bold text-[#f4f4f5] uppercase tracking-wider border-b border-[#222430] pb-2">
              Network &amp; Resource Ceilings
            </h3>
            <div className="space-y-2 text-xs font-sans text-[#a1a1aa]">
              <div>
                <strong className="text-white block font-mono text-[11px]">Zero Network Egress:</strong>
                <p className="text-[11px] leading-relaxed">Network sockets are disabled during adversarial execution. Code candidates cannot exfiltrate credentials or communicate with external servers.</p>
              </div>
              <div>
                <strong className="text-white block font-mono text-[11px]">Hard Resource Ceilings:</strong>
                <p className="text-[11px] leading-relaxed">Maximum 50 iterations, 100 tool calls, and 3600 seconds runtime. Requests exceeding ceilings fail closed to INCONCLUSIVE.</p>
              </div>
              <div>
                <strong className="text-white block font-mono text-[11px]">Trust Authority:</strong>
                <p className="text-[11px] leading-relaxed">Trust tiers are resolved authoritatively by <code className="text-[#fca5a5] font-mono">backend/sandbox/trust.py</code>. The frontend cannot grant trust to arbitrary repositories.</p>
              </div>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
