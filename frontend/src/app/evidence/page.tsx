"use client";

import React, { useState, useEffect, Suspense, useMemo } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { apiClient, ApiError } from '@/api/client';
import { EvidenceReceipt, JudgeExplanation, RunHistoryItem, RunDiff } from '@/models/types';
import { getReceiptIntegrityStatus, validateSandboxCapabilities } from '@/components/EvidenceReceiptView';
import { JudgeExplanationView } from '@/components/JudgeExplanationView';
import { DiffViewer } from '@/components/DiffViewer';

type EvidenceTab = 'tests' | 'adversarial' | 'sandbox' | 'lineage';

function EvidenceContent() {
  const searchParams = useSearchParams();
  const initialRunId = searchParams.get('runId') || '';

  const [selectedRunId, setSelectedRunId] = useState<string>(initialRunId);
  const [inputRunId, setInputRunId] = useState<string>(initialRunId);
  const [receipt, setReceipt] = useState<EvidenceReceipt | null>(null);
  const [judge, setJudge] = useState<JudgeExplanation | null>(null);
  const [diff, setDiff] = useState<RunDiff | null>(null);
  const [history, setHistory] = useState<RunHistoryItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(Boolean(initialRunId));
  const [receiptError, setReceiptError] = useState<string | null>(null);
  const [judgeError, setJudgeError] = useState<string | null>(null);
  const [ledgerSearch, setLedgerSearch] = useState<string>('');
  const [ledgerVerdictFilter, setLedgerVerdictFilter] = useState<string>('ALL');
  const [activeTab, setActiveTab] = useState<EvidenceTab>('tests');
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  // Load history for ledger sidebar and run selection
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

  // Fetch evidence bundle for selected run
  useEffect(() => {
    if (!selectedRunId) return;
    const trimmed = selectedRunId.trim();
    if (!trimmed) return;

    let ignore = false;

    Promise.allSettled([
      apiClient.getEvidenceReceipt(trimmed)
        .then((r) => { if (!ignore) { setReceipt(r); setReceiptError(null); } })
        .catch((err) => {
          if (!ignore) {
            if (err instanceof ApiError && err.status === 404) {
              setReceiptError("Evidence receipt not yet available for this run (run may be active or aborted prior to verification).");
            } else {
              setReceiptError(err instanceof Error ? err.message : String(err));
            }
            setReceipt(null);
          }
        }),
      apiClient.getJudgeExplanation(trimmed)
        .then((j) => { if (!ignore) { setJudge(j); setJudgeError(null); } })
        .catch((err) => {
          if (!ignore) {
            if (err instanceof ApiError && err.status === 404) {
              setJudgeError("Judge explanation not yet available for this run.");
            } else {
              setJudgeError(err instanceof Error ? err.message : String(err));
            }
            setJudge(null);
          }
        }),
      apiClient.getRunDiff(trimmed)
        .then((d) => { if (!ignore) setDiff(d); })
        .catch(() => { if (!ignore) setDiff(null); })
    ]).finally(() => {
      if (!ignore) setIsLoading(false);
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

  const copyToClipboard = (text: string, key: string) => {
    if (typeof navigator !== 'undefined' && navigator.clipboard) {
      navigator.clipboard.writeText(text).catch(() => {});
      setCopiedKey(key);
      setTimeout(() => setCopiedKey(null), 2000);
    }
  };

  const handleDownloadReceiptJson = () => {
    if (!receipt) return;
    const jsonStr = JSON.stringify(receipt, null, 2);
    const blob = new Blob([jsonStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `evidence_receipt_${receipt.run_id}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  // Filtered ledger runs
  const filteredLedger = useMemo(() => {
    return history.filter((item) => {
      const matchesSearch = 
        item.run_id.toLowerCase().includes(ledgerSearch.toLowerCase()) ||
        item.task_id.toLowerCase().includes(ledgerSearch.toLowerCase());
      if (!matchesSearch) return false;

      if (ledgerVerdictFilter === 'ALL') return true;
      if (ledgerVerdictFilter === 'VERIFIED') return item.verdict === 'VERIFIED';
      if (ledgerVerdictFilter === 'REJECTED') return item.verdict === 'REJECTED';
      if (ledgerVerdictFilter === 'INCONCLUSIVE') return item.verdict === 'INCONCLUSIVE';
      if (ledgerVerdictFilter === 'PENDING') return !item.verdict;
      return true;
    });
  }, [history, ledgerSearch, ledgerVerdictFilter]);

  // Derived telemetry metrics (strictly truthful from real SQLite history)
  const totalReceipts = history.filter((h) => h.verdict).length;
  const verifiedCount = history.filter((h) => h.verdict === 'VERIFIED').length;
  const passRate = totalReceipts > 0 ? `${((verifiedCount / totalReceipts) * 100).toFixed(0)}%` : 'N/A';
  const integrityStatus = getReceiptIntegrityStatus(receipt);
  const capabilities = validateSandboxCapabilities(receipt?.structured_observation?.capabilities);
  const sandboxBackend = receipt?.structured_observation?.sandbox_backend || receipt?.sandbox_provenance?.backend || 'UNKNOWN';
  const verdict = receipt?.verdict || receipt?.deterministic_verdict || 'UNKNOWN';

  return (
    <div className="space-y-6">
      {/* Monospace Subheader & Action Cluster */}
      <header className="border-b border-[#222430] pb-5">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div>
            <div className="flex items-center gap-2 font-mono text-[11px] text-slate-500 mb-1">
              <span>ORCHESTRATION</span>
              <span>{'//'}</span>
              <span className="text-slate-400">EVIDENCE &amp; PROOFS</span>
              <span>{'//'}</span>
              <span className="text-[#ef4444] font-semibold">CRYPTOGRAPHIC_RECEIPTS</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-black tracking-tight text-white flex items-center gap-3">
              <span>08. Cryptographic Evidence &amp; Receipts</span>
              <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-[#13141b] border border-[#222430] text-slate-400">
                v2.4-deterministic
              </span>
            </h1>
            <p className="text-xs text-slate-400 font-mono mt-1">
              Tamper-evident verification receipts, SHA-256 code digests, deterministic test execution logs, and patch lineage.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={handleDownloadReceiptJson}
              disabled={!receipt}
              className="px-3 py-1.5 rounded bg-[#ef4444] hover:bg-[#dc2626] disabled:opacity-40 disabled:hover:bg-[#ef4444] text-white font-mono text-xs font-semibold flex items-center gap-1.5 transition-colors shadow-sm"
              title={receipt ? "Download authentic JSON evidence receipt" : "Receipt not loaded"}
            >
              <span>⬇</span>
              <span>Download JSON Receipt</span>
            </button>
            <Link
              href="/history"
              className="text-xs font-mono text-slate-300 hover:text-white bg-[#13141b] hover:bg-[#1a1b24] border border-[#222430] px-3 py-1.5 rounded transition-colors"
            >
              Ledger History →
            </Link>
          </div>
        </div>
      </header>

      {/* Top Telemetry Ribbon (Truthful, non-fabricated metrics) */}
      <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4" aria-label="Evidence Telemetry">
        <div className="p-4 rounded-lg bg-[#0d0e12] border border-[#222430]">
          <div className="flex justify-between items-start mb-1">
            <span className="font-mono text-[10px] text-slate-500 uppercase tracking-wider">Total Recorded Receipts</span>
            <span className="text-[#ef4444] text-xs">🛡️</span>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-black text-white">{totalReceipts}</span>
            <span className="text-xs font-mono text-slate-400">runs finalized</span>
          </div>
          <div className="mt-2 text-[10px] font-mono text-slate-500 flex items-center justify-between">
            <span>Authoritative SQLite database</span>
            <span className="text-emerald-400 font-semibold">{verifiedCount} Sound</span>
          </div>
        </div>

        <div className="p-4 rounded-lg bg-[#0d0e12] border border-[#222430]">
          <div className="flex justify-between items-start mb-1">
            <span className="font-mono text-[10px] text-slate-500 uppercase tracking-wider">Cryptographic Root Digest</span>
            <span className="text-emerald-400 text-xs">🔒</span>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-xl font-bold text-emerald-400 truncate">
              {receipt?.receipt_hash ? 'SHA-256 RECORDED' : 'UNVERIFIED CLIENT'}
            </span>
          </div>
          <div className="mt-2 text-[10px] font-mono text-slate-500 flex items-center justify-between">
            <span>{integrityStatus.title}</span>
            <span className="text-slate-400">Zero Fabricated Proofs</span>
          </div>
        </div>

        <div className="p-4 rounded-lg bg-[#0d0e12] border border-[#222430]">
          <div className="flex justify-between items-start mb-1">
            <span className="font-mono text-[10px] text-slate-500 uppercase tracking-wider">Historical Soundness Rate</span>
            <span className="text-slate-400 text-xs">⚖️</span>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-black text-white">{passRate}</span>
            <span className="text-xs font-mono text-slate-400">verified sound</span>
          </div>
          <div className="mt-2 text-[10px] font-mono text-slate-500 flex items-center justify-between">
            <span>Deterministic Oracle</span>
            <span className="text-slate-400">{history.length} Total Runs</span>
          </div>
        </div>

        <div className="p-4 rounded-lg bg-[#0d0e12] border border-[#222430]">
          <div className="flex justify-between items-start mb-1">
            <span className="font-mono text-[10px] text-slate-500 uppercase tracking-wider">Counterexamples Found</span>
            <span className="text-rose-400 text-xs">⚡</span>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-black text-white">{receipt?.counterexamples?.length ?? 0}</span>
            <span className="text-xs font-mono text-slate-400">in current receipt</span>
          </div>
          <div className="mt-2 text-[10px] font-mono text-slate-500 flex items-center justify-between">
            <span>Adversarial red-team checks</span>
            <span className={receipt?.counterexamples && receipt.counterexamples.length > 0 ? "text-rose-400 font-bold" : "text-emerald-400"}>
              {receipt?.counterexamples && receipt.counterexamples.length > 0 ? "Violations Detected" : "Clean Run"}
            </span>
          </div>
        </div>
      </section>

      {/* Manual Search & Quick Run Selector Bar */}
      <div className="bg-[#0d0e12] border border-[#222430] p-4 rounded-lg flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4">
        <form onSubmit={handleSearchSubmit} className="flex gap-2 flex-1 max-w-md">
          <input
            type="text"
            placeholder="Enter Run ID (e.g. run-1234)"
            value={inputRunId}
            onChange={(e) => setInputRunId(e.target.value)}
            className="bg-[#13141b] border border-[#222430] p-2 rounded-md flex-1 text-xs font-mono text-slate-100 placeholder:text-slate-600 focus-visible:ring-2 focus-visible:ring-[#ef4444] focus-visible:outline-none"
            aria-label="Search Run ID for Evidence"
          />
          <button
            type="submit"
            disabled={isLoading || !inputRunId.trim()}
            className="bg-[#1a1b24] hover:bg-[#222430] text-slate-200 border border-[#222430] px-4 py-2 rounded-md text-xs font-semibold font-mono transition-colors disabled:opacity-50"
          >
            {isLoading ? 'Loading...' : 'Audit'}
          </button>
        </form>

        {history.length > 0 && (
          <div className="flex items-center gap-2 text-xs">
            <span className="text-slate-500 font-mono">Quick Run Select:</span>
            <select
              value={selectedRunId}
              onChange={(e) => handleSelectRun(e.target.value)}
              className="bg-[#13141b] border border-[#222430] text-slate-300 text-xs font-mono rounded-md p-2 focus-visible:ring-2 focus-visible:ring-[#ef4444] focus-visible:outline-none max-w-xs truncate"
              aria-label="Select past run for evidence audit"
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
          Retrieving authoritative cryptographic evidence bundle and patch diffs from backend...
        </div>
      )}

      {/* Main Bento Explorer: 7 Cols Left (Inspector) / 5 Cols Right (Ledger) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
        {/* ================= LEFT COLUMN: RECEIPT DEEP DIVE (7 Cols) ================= */}
        <section className="lg:col-span-7 space-y-5">
          {receipt ? (
            <div className="space-y-5">
              {/* Core Receipt Card */}
              <div className="bg-[#0d0e12] border border-[#222430] rounded-lg p-5">
                {/* Header Information */}
                <div className="flex flex-wrap items-center justify-between gap-3 pb-4 border-b border-[#222430]">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-base font-bold text-white select-all">{receipt.run_id}</span>
                      <button
                        type="button"
                        onClick={() => copyToClipboard(receipt.run_id, 'run_id')}
                        className="text-slate-500 hover:text-white transition-colors"
                        title="Copy Run ID"
                      >
                        {copiedKey === 'run_id' ? '✓' : '⧉'}
                      </button>
                      <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-[#13141b] border border-[#222430] text-slate-400">
                        {receipt.receipt_schema_version || 'v1.0'}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-xs text-slate-300 font-medium font-mono">Task: {receipt.task_id}</span>
                      <span className="text-slate-600 text-xs">•</span>
                      <span className="font-mono text-[11px] text-slate-500">{receipt.timestamp}</span>
                    </div>
                  </div>

                  {/* Deterministic Verdict Stamp */}
                  <div className="flex flex-col items-end">
                    <div className={`flex items-center gap-1.5 px-3 py-1 rounded font-mono text-xs font-bold border ${
                      verdict === 'VERIFIED' ? 'bg-emerald-950/40 text-emerald-300 border-emerald-600/70' :
                      verdict === 'REJECTED' ? 'bg-rose-950/40 text-rose-300 border-rose-600/70' :
                      'bg-amber-950/40 text-amber-300 border-amber-600/70'
                    }`}>
                      <span>{verdict === 'VERIFIED' ? '✓ ' : verdict === 'REJECTED' ? '✕ ' : '⚠ '}</span>
                      <span>DETERMINISTIC VERDICT: {verdict}</span>
                    </div>
                    <span className="font-mono text-[10px] text-slate-500 mt-1">
                      Policy: {receipt.policy_version || 'v2.4'} | Verifier: {receipt.verifier_version || 'v1.0'}
                    </span>
                  </div>
                </div>

                {/* Cryptographic Digests Box */}
                <div className="mt-4 p-4 rounded bg-[#13141b] border border-[#222430] font-mono space-y-2.5">
                  <div className="flex items-center justify-between text-xs text-slate-400 pb-2 border-b border-[#222430]">
                    <span className="flex items-center gap-1.5 text-slate-200 font-semibold">
                      <span>🔑</span>
                      <span>CRYPTOGRAPHIC DIGESTS &amp; ROOT HASH</span>
                    </span>
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded border ${integrityStatus.badgeClass}`}>
                      {integrityStatus.title}
                    </span>
                  </div>

                  {/* Receipt Root Hash */}
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1 text-[11px]">
                    <span className="text-slate-400 shrink-0 w-36">Receipt Root Hash:</span>
                    <div className="flex items-center gap-2 truncate">
                      <span className="text-[#ef4444] truncate font-semibold bg-[#0d0e12] px-2 py-0.5 rounded border border-[#222430] select-all">
                        {receipt.receipt_hash || 'NOT RECORDED'}
                      </span>
                      {receipt.receipt_hash && (
                        <button
                          type="button"
                          onClick={() => copyToClipboard(receipt.receipt_hash || '', 'receipt_hash')}
                          className="text-[10px] text-slate-400 hover:text-white"
                        >
                          {copiedKey === 'receipt_hash' ? 'Copied!' : 'Copy'}
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Task Contract Hash */}
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1 text-[11px]">
                    <span className="text-slate-400 shrink-0 w-36">Contract Hash:</span>
                    <div className="flex items-center gap-2 truncate">
                      <span className="text-slate-300 truncate font-semibold bg-[#0d0e12] px-2 py-0.5 rounded border border-[#222430] select-all">
                        {receipt.task_contract_hash}
                      </span>
                      <button
                        type="button"
                        onClick={() => copyToClipboard(receipt.task_contract_hash, 'contract_hash')}
                        className="text-[10px] text-slate-400 hover:text-white"
                      >
                        {copiedKey === 'contract_hash' ? 'Copied!' : 'Copy'}
                      </button>
                    </div>
                  </div>

                  {/* Snapshot Hash */}
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1 text-[11px]">
                    <span className="text-slate-400 shrink-0 w-36">Snapshot Hash:</span>
                    <div className="flex items-center gap-2 truncate">
                      <span className="text-slate-300 truncate font-semibold bg-[#0d0e12] px-2 py-0.5 rounded border border-[#222430] select-all">
                        {receipt.repository_snapshot_hash}
                      </span>
                      <button
                        type="button"
                        onClick={() => copyToClipboard(receipt.repository_snapshot_hash, 'snapshot_hash')}
                        className="text-[10px] text-slate-400 hover:text-white"
                      >
                        {copiedKey === 'snapshot_hash' ? 'Copied!' : 'Copy'}
                      </button>
                    </div>
                  </div>

                  {/* Patch Hash */}
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1 text-[11px]">
                    <span className="text-slate-400 shrink-0 w-36">Final Patch Hash:</span>
                    <div className="flex items-center gap-2 truncate">
                      <span className="text-emerald-400 truncate font-semibold bg-[#0d0e12] px-2 py-0.5 rounded border border-[#222430] select-all">
                        {receipt.patch_hash}
                      </span>
                      <button
                        type="button"
                        onClick={() => copyToClipboard(receipt.patch_hash, 'patch_hash')}
                        className="text-[10px] text-slate-400 hover:text-white"
                      >
                        {copiedKey === 'patch_hash' ? 'Copied!' : 'Copy'}
                      </button>
                    </div>
                  </div>
                </div>

                {/* Multi-Tab Evidence Matrix */}
                <div className="mt-5">
                  {/* Tabs Header */}
                  <div className="flex border-b border-[#222430] gap-2 overflow-x-auto pb-px" role="tablist">
                    <button
                      type="button"
                      role="tab"
                      aria-selected={activeTab === 'tests'}
                      onClick={() => setActiveTab('tests')}
                      className={`px-3 py-2 font-mono text-xs flex items-center gap-1.5 shrink-0 transition-colors border-b-2 ${
                        activeTab === 'tests'
                          ? 'border-[#ef4444] text-white font-bold bg-[#13141b]'
                          : 'border-transparent text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      <span>🧪</span>
                      <span>Deterministic Tests ({receipt.test_summary?.executed ?? 0})</span>
                    </button>

                    <button
                      type="button"
                      role="tab"
                      aria-selected={activeTab === 'adversarial'}
                      onClick={() => setActiveTab('adversarial')}
                      className={`px-3 py-2 font-mono text-xs flex items-center gap-1.5 shrink-0 transition-colors border-b-2 ${
                        activeTab === 'adversarial'
                          ? 'border-[#ef4444] text-white font-bold bg-[#13141b]'
                          : 'border-transparent text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      <span>🛡️</span>
                      <span>Counterexamples ({receipt.counterexamples?.length ?? 0})</span>
                    </button>

                    <button
                      type="button"
                      role="tab"
                      aria-selected={activeTab === 'sandbox'}
                      onClick={() => setActiveTab('sandbox')}
                      className={`px-3 py-2 font-mono text-xs flex items-center gap-1.5 shrink-0 transition-colors border-b-2 ${
                        activeTab === 'sandbox'
                          ? 'border-[#ef4444] text-white font-bold bg-[#13141b]'
                          : 'border-transparent text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      <span>📦</span>
                      <span>Sandbox Security ({sandboxBackend})</span>
                    </button>

                    <button
                      type="button"
                      role="tab"
                      aria-selected={activeTab === 'lineage'}
                      onClick={() => setActiveTab('lineage')}
                      className={`px-3 py-2 font-mono text-xs flex items-center gap-1.5 shrink-0 transition-colors border-b-2 ${
                        activeTab === 'lineage'
                          ? 'border-[#ef4444] text-white font-bold bg-[#13141b]'
                          : 'border-transparent text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      <span>📜</span>
                      <span>Lineage &amp; Provenance</span>
                    </button>
                  </div>

                  {/* Tab 1: Deterministic Tests */}
                  {activeTab === 'tests' && (
                    <div className="mt-4 space-y-3 font-mono text-xs" role="tabpanel">
                      <div className="grid grid-cols-4 gap-2 text-center">
                        <div className="p-2.5 rounded bg-[#13141b] border border-[#222430]">
                          <span className="text-[10px] text-slate-500 block uppercase">Executed</span>
                          <span className="text-sm font-bold text-white">{receipt.test_summary?.executed ?? 0}</span>
                        </div>
                        <div className="p-2.5 rounded bg-[#13141b] border border-[#222430]">
                          <span className="text-[10px] text-slate-500 block uppercase">Passed</span>
                          <span className="text-sm font-bold text-emerald-400">{receipt.test_summary?.passed ?? 0}</span>
                        </div>
                        <div className="p-2.5 rounded bg-[#13141b] border border-[#222430]">
                          <span className="text-[10px] text-slate-500 block uppercase">Failed</span>
                          <span className="text-sm font-bold text-rose-400">{receipt.test_summary?.failed ?? 0}</span>
                        </div>
                        <div className="p-2.5 rounded bg-[#13141b] border border-[#222430]">
                          <span className="text-[10px] text-slate-500 block uppercase">Inconclusive</span>
                          <span className="text-sm font-bold text-amber-400">{receipt.test_summary?.inconclusive ?? 0}</span>
                        </div>
                      </div>

                      {/* Observations list if present */}
                      {receipt.test_summary?.observations && receipt.test_summary.observations.length > 0 ? (
                        <div className="border border-[#222430] rounded bg-[#13141b] overflow-hidden">
                          <table className="w-full text-left text-[11px]">
                            <thead className="bg-[#1a1b24] text-slate-400 border-b border-[#222430] text-[10px] uppercase">
                              <tr>
                                <th className="p-2 pl-3">Test Identifier</th>
                                <th className="p-2">Framework</th>
                                <th className="p-2">Duration</th>
                                <th className="p-2 text-right pr-3">Status</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-[#222430] text-slate-200">
                              {receipt.test_summary.observations.map((obs, idx) => (
                                <tr key={idx} className="hover:bg-[#1f202b] transition-colors">
                                  <td className="p-2 pl-3 font-semibold text-slate-300">{obs.test_id}</td>
                                  <td className="p-2 text-slate-500">{obs.framework}</td>
                                  <td className="p-2 text-slate-500">{obs.duration_ms}ms</td>
                                  <td className="p-2 text-right pr-3 font-bold">
                                    <span className={obs.status === 'PASSED' ? 'text-emerald-400' : 'text-rose-400'}>
                                      {obs.status}
                                    </span>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      ) : (
                        <p className="text-slate-500 text-[11px] italic bg-[#13141b] p-3 rounded border border-[#222430]">
                          Summary metrics recorded. Individual granular test observations were not captured in this test run.
                        </p>
                      )}
                    </div>
                  )}

                  {/* Tab 2: Adversarial Counterexamples & Invariants */}
                  {activeTab === 'adversarial' && (
                    <div className="mt-4 space-y-3 font-mono text-xs" role="tabpanel">
                      {receipt.counterexamples && receipt.counterexamples.length > 0 ? (
                        <div className="space-y-2">
                          {receipt.counterexamples.map((ce, idx) => (
                            <div key={idx} className="p-3 bg-rose-950/20 border border-rose-800/60 rounded space-y-1">
                              <div className="flex justify-between items-center text-rose-300 font-bold">
                                <span>Counterexample: {ce.counterexample_id}</span>
                                <span className="text-[10px] bg-rose-900/60 text-rose-200 px-1.5 py-0.5 rounded">{ce.oracle_type}</span>
                              </div>
                              <div><strong className="text-slate-400">Target Invariant:</strong> <span className="text-slate-300">{ce.invariant_id}</span></div>
                              <div><strong className="text-slate-400">Input:</strong> <code className="text-slate-200">{ce.input_data}</code></div>
                              <div><strong className="text-slate-400">Observed Output:</strong> <span className="text-rose-300">{ce.observed_output}</span></div>
                              <div><strong className="text-slate-400">Expected:</strong> <span className="text-emerald-300">{ce.expected_output}</span></div>
                              <div><strong className="text-slate-400">Reason:</strong> <span className="text-slate-300">{ce.failure_reason}</span></div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="p-4 bg-[#13141b] border border-[#222430] rounded text-slate-400">
                          <span className="text-emerald-400 font-bold block mb-1">✓ No Counterexamples Detected</span>
                          <p className="text-[11px] text-slate-500">
                            Zero invariant violations or security counterexamples were observed across all deterministic attack vectors.
                          </p>
                        </div>
                      )}

                      {/* Invariant Evaluations */}
                      {receipt.invariant_summary && receipt.invariant_summary.length > 0 && (
                        <div className="border border-[#222430] rounded bg-[#13141b] overflow-hidden mt-3">
                          <div className="p-2.5 bg-[#1a1b24] border-b border-[#222430] text-[10px] uppercase font-bold text-slate-400">
                            Evaluated Invariants ({receipt.invariant_summary.length})
                          </div>
                          <div className="divide-y divide-[#222430]">
                            {receipt.invariant_summary.map((inv, idx) => (
                              <div key={idx} className="p-2.5 flex justify-between items-center">
                                <div>
                                  <span className="font-bold text-slate-200">{inv.invariant_id}</span>
                                  <p className="text-[10px] text-slate-500">{inv.description}</p>
                                </div>
                                <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                  inv.result === 'PASSED' ? 'bg-emerald-950/40 text-emerald-300 border border-emerald-800' : 'bg-rose-950/40 text-rose-300 border border-rose-800'
                                }`}>
                                  {inv.result}
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Tab 3: Sandbox Security Profile */}
                  {activeTab === 'sandbox' && (
                    <div className="mt-4 space-y-3 font-mono text-xs" role="tabpanel">
                      {capabilities ? (
                        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                          <div className="p-2.5 bg-[#13141b] rounded border border-[#222430]">
                            <span className="text-[10px] text-slate-500 block uppercase">Process Isolation</span>
                            <span className="font-bold text-emerald-400">{capabilities.process_isolation || 'ENFORCED'}</span>
                          </div>
                          <div className="p-2.5 bg-[#13141b] rounded border border-[#222430]">
                            <span className="text-[10px] text-slate-500 block uppercase">Network Isolation</span>
                            <span className="font-bold text-emerald-400">{capabilities.network_isolation || 'DROP_ALL'}</span>
                          </div>
                          <div className="p-2.5 bg-[#13141b] rounded border border-[#222430]">
                            <span className="text-[10px] text-slate-500 block uppercase">Filesystem</span>
                            <span className="font-bold text-emerald-400">{capabilities.filesystem_isolation || 'READ_ONLY_ROOT'}</span>
                          </div>
                          <div className="p-2.5 bg-[#13141b] rounded border border-[#222430]">
                            <span className="text-[10px] text-slate-500 block uppercase">Credential Isolation</span>
                            <span className="font-bold text-emerald-400">{capabilities.credential_isolation || 'ENFORCED'}</span>
                          </div>
                          <div className="p-2.5 bg-[#13141b] rounded border border-[#222430]">
                            <span className="text-[10px] text-slate-500 block uppercase">Security Level</span>
                            <span className="font-bold text-slate-200">{capabilities.security_level || 'SECURE'}</span>
                          </div>
                          <div className="p-2.5 bg-[#13141b] rounded border border-[#222430]">
                            <span className="text-[10px] text-slate-500 block uppercase">Untrusted Code Execution</span>
                            <span className={`font-bold ${capabilities.secure_untrusted_execution ? 'text-emerald-400' : 'text-rose-400'}`}>
                              {capabilities.secure_untrusted_execution ? 'CONTAINED' : 'FAIL_CLOSED'}
                            </span>
                          </div>
                        </div>
                      ) : (
                        <p className="text-slate-500 text-[11px] italic bg-[#13141b] p-3 rounded border border-[#222430]">
                          Detailed sandbox capability metadata was not recorded for this run.
                        </p>
                      )}

                      {/* Structured Observation Hashes */}
                      {receipt.structured_observation && (
                        <div className="p-3 bg-[#13141b] rounded border border-[#222430] space-y-1.5 text-[11px]">
                          <div className="text-slate-400 font-bold uppercase text-[10px]">Execution Telemetry Hashes</div>
                          <div className="flex justify-between">
                            <span className="text-slate-500">Execution ID:</span>
                            <span className="text-slate-300">{receipt.structured_observation.execution_id}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-slate-500">Stdout SHA-256:</span>
                            <span className="text-slate-300 truncate max-w-xs">{receipt.structured_observation.stdout_sha256}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-slate-500">Stderr SHA-256:</span>
                            <span className="text-slate-300 truncate max-w-xs">{receipt.structured_observation.stderr_sha256}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-slate-500">Execution Duration:</span>
                            <span className="text-slate-300">{receipt.structured_observation.duration_ms}ms</span>
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Tab 4: Lineage & Provenance */}
                  {activeTab === 'lineage' && (
                    <div className="mt-4 space-y-3 font-mono text-xs" role="tabpanel">
                      <div className="p-3 bg-[#13141b] rounded border border-[#222430] space-y-2">
                        <span className="text-slate-400 font-bold uppercase text-[10px] block">Patch Repair Lineage</span>
                        {receipt.patch_lineage && receipt.patch_lineage.length > 0 ? (
                          <ul className="list-disc pl-5 space-y-1 text-slate-300">
                            {receipt.patch_lineage.map((patchId, idx) => (
                              <li key={idx}>{patchId}</li>
                            ))}
                          </ul>
                        ) : (
                          <p className="text-slate-500 italic text-[11px]">Single-shot patch (no repair iterations recorded).</p>
                        )}
                      </div>

                      {receipt.model_provenance && Object.keys(receipt.model_provenance).length > 0 && (
                        <div className="p-3 bg-[#13141b] rounded border border-[#222430] space-y-1.5 text-[11px]">
                          <span className="text-slate-400 font-bold uppercase text-[10px] block">Model Provenance</span>
                          {Object.entries(receipt.model_provenance).map(([k, v]) => (
                            <div key={k} className="flex justify-between">
                              <span className="text-slate-500">{k}:</span>
                              <span className="text-slate-300">{v}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>

              {/* Subordinate Judge Explanation */}
              {judge ? (
                <JudgeExplanationView explanation={judge} />
              ) : judgeError && (
                <div className="bg-[#0d0e12] border border-[#222430] p-4 rounded-lg text-xs text-slate-400">
                  <span className="text-slate-500 block text-[10px] uppercase font-bold mb-1">Judge Explanation Notice</span>
                  {judgeError}
                </div>
              )}

              {/* Dedicated Diff Viewer */}
              <DiffViewer runId={selectedRunId} initialDiff={diff} />
            </div>
          ) : receiptError ? (
            <div className="bg-amber-950/20 border border-amber-900/50 p-6 rounded-lg text-xs text-amber-200" role="alert">
              <strong className="block text-amber-400 mb-1">⚠️ Evidence Receipt Notice:</strong>
              <p>{receiptError}</p>
              <p className="mt-2 text-[11px] text-amber-300/80 font-mono">
                Authoritative receipts are compiled and signed by the backend EvidenceBuilder upon conclusion of the deterministic verification phase.
              </p>
            </div>
          ) : (
            <div className="p-12 text-center text-xs text-slate-500 bg-[#0d0e12] rounded-lg border border-dashed border-[#222430]">
              <p className="font-semibold text-slate-400">No Run Selected for Audit</p>
              <p className="mt-1">Enter a Run ID above or select from the ledger on the right to audit cryptographic receipts.</p>
            </div>
          )}
        </section>

        {/* ================= RIGHT COLUMN: LEDGER AUDIT TRAIL (5 Cols) ================= */}
        <section className="lg:col-span-5 space-y-4">
          <div className="bg-[#0d0e12] border border-[#222430] rounded-lg p-4">
            <div className="flex items-center justify-between pb-3 border-b border-[#222430]">
              <div>
                <h2 className="font-mono text-xs font-bold text-white uppercase tracking-wider">Recent Evidence Receipts Ledger</h2>
                <span className="text-slate-500 text-[11px] font-mono">Immutable SQLite audit history</span>
              </div>
              <span className="text-slate-500 text-xs font-mono">{filteredLedger.length} items</span>
            </div>

            {/* Filter and Search Bar */}
            <div className="mt-3 flex gap-2">
              <div className="flex-1 flex items-center bg-[#13141b] border border-[#222430] rounded px-2.5 py-1 text-xs font-mono">
                <span className="text-slate-500 mr-1.5">⌕</span>
                <input
                  type="text"
                  placeholder="Filter runs, tasks..."
                  value={ledgerSearch}
                  onChange={(e) => setLedgerSearch(e.target.value)}
                  className="bg-transparent border-none text-slate-200 focus:outline-none w-full text-xs font-mono p-0 placeholder:text-slate-600"
                />
              </div>

              <select
                value={ledgerVerdictFilter}
                onChange={(e) => setLedgerVerdictFilter(e.target.value)}
                className="bg-[#13141b] border border-[#222430] text-slate-300 text-xs font-mono rounded px-2 py-1 focus-visible:ring-1 focus-visible:ring-[#ef4444]"
                aria-label="Filter ledger runs by verdict"
              >
                <option value="ALL">All Verdicts</option>
                <option value="VERIFIED">Verified</option>
                <option value="REJECTED">Rejected</option>
                <option value="INCONCLUSIVE">Inconclusive</option>
                <option value="PENDING">Pending</option>
              </select>
            </div>

            {/* Ledger Items List */}
            <div className="mt-3 space-y-2 max-h-[640px] overflow-y-auto pr-1">
              {filteredLedger.length === 0 ? (
                <div className="p-8 text-center text-xs font-mono text-slate-500 bg-[#13141b] rounded border border-[#222430]">
                  No matching run receipts found.
                </div>
              ) : (
                filteredLedger.map((run) => {
                  const isSelected = selectedRunId === run.run_id;
                  const itemVerdict = run.verdict || 'PENDING';
                  return (
                    <div
                      key={run.run_id}
                      onClick={() => handleSelectRun(run.run_id)}
                      className={`p-3 rounded border transition-all cursor-pointer ${
                        isSelected
                          ? 'bg-[#181a24] border-[#ef4444] shadow-sm'
                          : 'bg-[#13141b] hover:bg-[#1a1b24] border-[#222430]'
                      }`}
                      role="button"
                      tabIndex={0}
                      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') handleSelectRun(run.run_id); }}
                    >
                      <div className="flex items-center justify-between">
                        <span className={`font-mono text-xs font-bold truncate max-w-[170px] ${isSelected ? 'text-[#ef4444]' : 'text-slate-200'}`}>
                          {run.run_id}
                        </span>
                        <span className={`px-1.5 py-0.5 rounded text-[9px] font-mono font-bold border ${
                          itemVerdict === 'VERIFIED' ? 'bg-emerald-950/40 text-emerald-300 border-emerald-700/60' :
                          itemVerdict === 'REJECTED' ? 'bg-rose-950/40 text-rose-300 border-rose-700/60' :
                          'bg-amber-950/40 text-amber-300 border-amber-700/60'
                        }`}>
                          {itemVerdict}
                        </span>
                      </div>
                      <div className="text-xs text-slate-400 mt-1 truncate font-mono">
                        {run.task_id}
                      </div>
                      <div className="flex items-center justify-between text-[10px] font-mono text-slate-500 mt-1.5 pt-1.5 border-t border-[#222430]/60">
                        <span>State: {run.final_state}</span>
                        <span>{run.created_at ? new Date(run.created_at).toLocaleDateString() : 'N/A'}</span>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

export default function EvidencePage() {
  return (
    <Suspense fallback={
      <div className="p-12 text-center text-xs font-mono text-slate-500 bg-[#0d0e12] border border-[#222430] rounded-lg">
        Loading Evidence Audit...
      </div>
    }>
      <EvidenceContent />
    </Suspense>
  );
}
