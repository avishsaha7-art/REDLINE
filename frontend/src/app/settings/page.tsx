"use client";

import React, { useState } from 'react';
import Link from 'next/link';
import { getApiBaseUrl, apiClient } from '@/api/client';

type SettingsTab = 'gateway' | 'ceilings' | 'sandbox' | 'preferences';

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<SettingsTab>('gateway');
  const [pingStatus, setPingStatus] = useState<string | null>(null);
  const [pingLatency, setPingLatency] = useState<number | null>(null);
  const [isPinging, setIsPinging] = useState<boolean>(false);

  const testConnection = async () => {
    setIsPinging(true);
    setPingStatus(null);
    setPingLatency(null);
    const start = performance.now();
    try {
      await apiClient.getRunHistory();
      const duration = Math.round(performance.now() - start);
      setPingLatency(duration);
      setPingStatus("ONLINE: Gateway responded (GET /api/v1/runs returned 200 OK). Note: Verifies route reachability only; does not evaluate sandbox daemon or model provider health.");
    } catch (err: unknown) {
      setPingStatus(`OFFLINE: Connection failed (${err instanceof Error ? err.message : String(err)}). Ensure backend server is running on ${baseUrl}.`);
    } finally {
      setIsPinging(false);
    }
  };

  const baseUrl = getApiBaseUrl();

  return (
    <div className="space-y-6">
      {/* Header with Monospace Cyber Breadcrumbs */}
      <header className="border-b border-[#222430] pb-5">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div>
            <div className="flex items-center gap-2 font-mono text-[11px] text-slate-500 mb-1">
              <span>CORE</span>
              <span>{"//"}</span>
              <span className="text-slate-400">10. SETTINGS</span>
              <span>{"//"}</span>
              <span className="text-[#ef4444] font-semibold">GOVERNANCE_POLICY</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-black tracking-tight text-white flex items-center gap-3">
              <span>10. Platform Governance &amp; Settings</span>
              <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-[#13141b] border border-[#222430] text-slate-400">
                v2.4-deterministic
              </span>
            </h1>
            <p className="text-xs text-slate-400 font-mono mt-1">
              Backend connectivity configuration, system ceilings, and sandbox security policies.
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

      {/* Settings Horizontal Navigation Tabs */}
      <div className="flex items-center gap-1 border-b border-[#222430] overflow-x-auto pb-px" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'gateway'}
          onClick={() => setActiveTab('gateway')}
          className={`flex items-center gap-2 px-4 py-2.5 font-mono text-xs transition-colors border-b-2 whitespace-nowrap ${
            activeTab === 'gateway'
              ? 'border-[#ef4444] text-white font-bold bg-[#13141b]'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <span>🌐</span>
          <span>API Gateway Probe</span>
        </button>

        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'ceilings'}
          onClick={() => setActiveTab('ceilings')}
          className={`flex items-center gap-2 px-4 py-2.5 font-mono text-xs transition-colors border-b-2 whitespace-nowrap ${
            activeTab === 'ceilings'
              ? 'border-[#ef4444] text-white font-bold bg-[#13141b]'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <span>📊</span>
          <span>System Ceilings (Policy)</span>
        </button>

        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'sandbox'}
          onClick={() => setActiveTab('sandbox')}
          className={`flex items-center gap-2 px-4 py-2.5 font-mono text-xs transition-colors border-b-2 whitespace-nowrap ${
            activeTab === 'sandbox'
              ? 'border-[#ef4444] text-white font-bold bg-[#13141b]'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <span>🛡️</span>
          <span>Sandbox Isolation Rules</span>
        </button>

        <button
          type="button"
          role="tab"
          aria-selected={activeTab === 'preferences'}
          onClick={() => setActiveTab('preferences')}
          className={`flex items-center gap-2 px-4 py-2.5 font-mono text-xs transition-colors border-b-2 whitespace-nowrap ${
            activeTab === 'preferences'
              ? 'border-[#ef4444] text-white font-bold bg-[#13141b]'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <span>⚙️</span>
          <span>Interface Preferences</span>
        </button>
      </div>

      {/* Tab 1: API Gateway Configuration & Live Probe */}
      {activeTab === 'gateway' && (
        <div className="space-y-6" role="tabpanel">
          <section aria-label="API Gateway" className="bg-[#0d0e12] border border-[#222430] p-6 rounded-lg shadow-lg space-y-4">
            <div className="flex justify-between items-center border-b border-[#222430] pb-3">
              <div>
                <h2 className="text-sm font-bold text-white uppercase tracking-wider font-mono">
                  Backend API Gateway Connectivity
                </h2>
                <p className="text-[11px] font-mono text-slate-500 mt-0.5">
                  Route connectivity verification to the FastAPI server gateway.
                </p>
              </div>
              <span className="text-[10px] font-mono text-emerald-400 bg-emerald-950/60 px-2 py-0.5 rounded border border-emerald-900/60 font-bold">
                LIVE PROBE
              </span>
            </div>

            <div className="space-y-4 text-xs font-mono">
              <div>
                <span className="text-slate-500 text-[10px] uppercase font-bold block mb-1">
                  Configured Base URL
                </span>
                <div className="bg-[#13141b] border border-[#222430] p-3 rounded font-mono text-slate-200 select-all flex justify-between items-center">
                  <span className="text-[#ef4444] font-bold">{baseUrl}</span>
                  <span className="text-[10px] text-slate-500">
                    (NEXT_PUBLIC_API_BASE_URL)
                  </span>
                </div>
              </div>

              <div>
                <button
                  type="button"
                  onClick={testConnection}
                  disabled={isPinging}
                  className="bg-[#1a1b24] hover:bg-[#222430] text-slate-200 border border-[#222430] font-semibold px-4 py-2.5 rounded text-xs transition-colors disabled:opacity-50 font-mono shadow-sm"
                >
                  {isPinging ? 'Pinging Gateway...' : 'Test Backend Connection'}
                </button>
                <p className="text-[11px] text-slate-500 mt-2">
                  Sends an authentic HTTP GET request to <code className="text-slate-400">/api/v1/runs</code>. Verifies HTTP route reachability only; does not evaluate sandbox daemon or model provider health.
                </p>
              </div>

              {pingStatus && (
                <div className={`p-4 rounded border text-xs font-mono ${
                  pingStatus.startsWith('ONLINE') 
                    ? 'bg-emerald-950/30 border-emerald-800 text-emerald-300' 
                    : 'bg-rose-950/30 border-rose-800 text-rose-300'
                }`} role="status">
                  <span className="block">{pingStatus}</span>
                  {pingLatency !== null && (
                    <span className="block text-[10px] text-slate-400 mt-1 font-bold">
                      Roundtrip HTTP Latency: {pingLatency}ms
                    </span>
                  )}
                </div>
              )}
            </div>
          </section>
        </div>
      )}

      {/* Tab 2: System Ceilings Governance (Static Policy / Read-Only) */}
      {activeTab === 'ceilings' && (
        <div className="space-y-6" role="tabpanel">
          <section aria-label="System Ceilings" className="bg-[#0d0e12] border border-[#222430] p-6 rounded-lg shadow-lg space-y-4">
            <div className="flex justify-between items-center border-b border-[#222430] pb-3">
              <div>
                <h2 className="text-sm font-bold text-white uppercase tracking-wider font-mono">
                  Enforced System Ceilings &amp; Resource Limits
                </h2>
                <p className="text-[11px] font-mono text-slate-500 mt-0.5">
                  Hardcoded backend governance constants enforced at runtime on submitted TaskContracts.
                </p>
              </div>
              <span className="text-[10px] font-mono text-blue-400 bg-blue-950/60 px-2 py-0.5 rounded border border-blue-900/60 font-bold">
                STATIC POLICY
              </span>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs font-mono">
              <div className="bg-[#13141b] p-3 rounded border border-[#222430]">
                <span className="text-slate-500 text-[10px] block uppercase font-bold">MAX_ITERATIONS</span>
                <span className="font-bold text-white text-base">50</span>
                <span className="text-[10px] text-slate-500 block mt-1">Per-task repair loop</span>
              </div>
              <div className="bg-[#13141b] p-3 rounded border border-[#222430]">
                <span className="text-slate-500 text-[10px] block uppercase font-bold">MAX_TOOL_CALLS</span>
                <span className="font-bold text-white text-base">100</span>
                <span className="text-[10px] text-slate-500 block mt-1">Total invocation budget</span>
              </div>
              <div className="bg-[#13141b] p-3 rounded border border-[#222430]">
                <span className="text-slate-500 text-[10px] block uppercase font-bold">MAX_RUNTIME</span>
                <span className="font-bold text-white text-base">3600s</span>
                <span className="text-[10px] text-slate-500 block mt-1">1 hour wall-clock limit</span>
              </div>
              <div className="bg-[#13141b] p-3 rounded border border-[#222430]">
                <span className="text-slate-500 text-[10px] block uppercase font-bold">MAX_PATCH_SIZE</span>
                <span className="font-bold text-white text-base">1 MB</span>
                <span className="text-[10px] text-slate-500 block mt-1">1,048,576 bytes</span>
              </div>
              <div className="bg-[#13141b] p-3 rounded border border-[#222430]">
                <span className="text-slate-500 text-[10px] block uppercase font-bold">MAX_REPO_FILES</span>
                <span className="font-bold text-white text-base">1,000</span>
                <span className="text-[10px] text-slate-500 block mt-1">Max files per snapshot</span>
              </div>
              <div className="bg-[#13141b] p-3 rounded border border-[#222430]">
                <span className="text-slate-500 text-[10px] block uppercase font-bold">MAX_CONTEXT_BYTES</span>
                <span className="font-bold text-white text-base">128 KB</span>
                <span className="text-[10px] text-slate-500 block mt-1">131,072 bytes</span>
              </div>
              <div className="bg-[#13141b] p-3 rounded border border-[#222430]">
                <span className="text-slate-500 text-[10px] block uppercase font-bold">MAX_FAILED_ATTEMPTS</span>
                <span className="font-bold text-white text-base">5</span>
                <span className="text-[10px] text-slate-500 block mt-1">Consecutive failure threshold</span>
              </div>
              <div className="bg-[#13141b] p-3 rounded border border-[#222430]">
                <span className="text-slate-500 text-[10px] block uppercase font-bold">MAX_ATTACK_CASES</span>
                <span className="font-bold text-white text-base">20</span>
                <span className="text-[10px] text-slate-500 block mt-1">Red team attack budget</span>
              </div>
            </div>

            <div className="p-3 bg-[#13141b] rounded border border-[#222430] text-[11px] font-mono text-slate-400">
              <strong className="text-slate-300 block mb-0.5 uppercase">Read-Only Governance Invariant:</strong>
              These ceilings are fail-closed parameters enforced by <code className="text-slate-300">backend/orchestrator/limits.py</code>.
              Dynamic modification from the web client is intentionally not supported to protect compute infrastructure against denial-of-service.
            </div>
          </section>
        </div>
      )}

      {/* Tab 3: Sandbox Isolation & Security Guardrails (Read-Only) */}
      {activeTab === 'sandbox' && (
        <div className="space-y-6" role="tabpanel">
          <section aria-label="Security Policy" className="bg-[#0d0e12] border border-[#222430] p-6 rounded-lg shadow-lg space-y-4">
            <div className="flex justify-between items-center border-b border-[#222430] pb-3">
              <div>
                <h2 className="text-sm font-bold text-white uppercase tracking-wider font-mono">
                  Sandbox Isolation &amp; Security Guardrails
                </h2>
                <p className="text-[11px] font-mono text-slate-500 mt-0.5">
                  Design invariants guaranteed by backend security architecture.
                </p>
              </div>
              <span className="text-[10px] font-mono text-purple-400 bg-purple-950/60 px-2 py-0.5 rounded border border-purple-900/60 font-bold">
                POLICY SPECIFICATION
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 font-mono text-xs">
              <div className="bg-[#13141b] p-4 rounded border border-[#222430] space-y-2">
                <span className="text-emerald-400 font-bold block flex items-center gap-1.5">
                  <span>✓</span>
                  <span>Working Directory Hardening</span>
                </span>
                <p className="text-[11px] text-slate-400 leading-relaxed">
                  Stage 16.1 path sanitization blocks <code className="text-slate-300">../</code> path traversal sequences, root directory escapes, and symbolic link exploitation.
                </p>
              </div>

              <div className="bg-[#13141b] p-4 rounded border border-[#222430] space-y-2">
                <span className="text-emerald-400 font-bold block flex items-center gap-1.5">
                  <span>✓</span>
                  <span>Deterministic Verifier Authority</span>
                </span>
                <p className="text-[11px] text-slate-400 leading-relaxed">
                  Verdicts are calculated exclusively by deterministic tests, invariants, and counterexamples. No agent can independently declare its work verified.
                </p>
              </div>

              <div className="bg-[#13141b] p-4 rounded border border-[#222430] space-y-2">
                <span className="text-emerald-400 font-bold block flex items-center gap-1.5">
                  <span>✓</span>
                  <span>Subordinate Judge Advisory</span>
                </span>
                <p className="text-[11px] text-slate-400 leading-relaxed">
                  Natural language explanations provided by the Judge Agent are strictly advisory and can never overturn verification verdicts.
                </p>
              </div>
            </div>

            <div className="p-4 bg-[#13141b] rounded border border-[#222430] space-y-2 font-mono text-xs">
              <div className="text-slate-300 font-bold uppercase text-[11px]">Container Sandbox Execution Profile</div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px]">
                <div className="p-2 bg-[#0d0e12] rounded border border-[#222430]">
                  <span className="text-slate-500 block text-[10px]">NETWORK</span>
                  <span className="text-emerald-400 font-bold">DISABLED (--net none)</span>
                </div>
                <div className="p-2 bg-[#0d0e12] rounded border border-[#222430]">
                  <span className="text-slate-500 block text-[10px]">CAPABILITIES</span>
                  <span className="text-emerald-400 font-bold">DROP_ALL</span>
                </div>
                <div className="p-2 bg-[#0d0e12] rounded border border-[#222430]">
                  <span className="text-slate-500 block text-[10px]">FILESYSTEM</span>
                  <span className="text-emerald-400 font-bold">READ_ONLY_ROOT</span>
                </div>
                <div className="p-2 bg-[#0d0e12] rounded border border-[#222430]">
                  <span className="text-slate-500 block text-[10px]">LIFECYCLE</span>
                  <span className="text-slate-300 font-bold">EPHEMERAL TEARDOWN</span>
                </div>
              </div>
            </div>
          </section>
        </div>
      )}

      {/* Tab 4: Interface & Accessibility Preferences */}
      {activeTab === 'preferences' && (
        <div className="space-y-6" role="tabpanel">
          <section aria-label="Interface Preferences" className="bg-[#0d0e12] border border-[#222430] p-6 rounded-lg shadow-lg space-y-4">
            <div className="flex justify-between items-center border-b border-[#222430] pb-3">
              <div>
                <h2 className="text-sm font-bold text-white uppercase tracking-wider font-mono">
                  Interface &amp; Accessibility Preferences
                </h2>
                <p className="text-[11px] font-mono text-slate-500 mt-0.5">
                  Display themes and accessibility configurations for the engineering console.
                </p>
              </div>
              <span className="text-[10px] font-mono text-slate-400 bg-[#13141b] px-2 py-0.5 rounded border border-[#222430]">
                CLIENT_DISPLAY
              </span>
            </div>

            <div className="space-y-4 font-mono text-xs">
              <div className="p-3 bg-[#13141b] rounded border border-[#222430] flex items-center justify-between">
                <div>
                  <span className="text-slate-200 font-bold block">Color Palette</span>
                  <span className="text-slate-500 text-[11px]">Obsidian Void with restrained crimson accents (#ef4444)</span>
                </div>
                <span className="text-emerald-400 font-bold text-[11px]">ACTIVE (WCAG 2.2 AA)</span>
              </div>

              <div className="p-3 bg-[#13141b] rounded border border-[#222430] flex items-center justify-between">
                <div>
                  <span className="text-slate-200 font-bold block">Motion Safety</span>
                  <span className="text-slate-500 text-[11px]">Respects prefers-reduced-motion media query</span>
                </div>
                <span className="text-emerald-400 font-bold text-[11px]">ENFORCED</span>
              </div>

              <div className="p-3 bg-[#13141b] rounded border border-[#222430] flex items-center justify-between">
                <div>
                  <span className="text-slate-200 font-bold block">Keyboard Navigation</span>
                  <span className="text-slate-500 text-[11px]">Visible focus rings on all interactive elements</span>
                </div>
                <span className="text-emerald-400 font-bold text-[11px]">ENABLED</span>
              </div>
            </div>
          </section>
        </div>
      )}

      {/* Cross Navigation Quick Links */}
      <div className="bg-[#0d0e12] border border-[#222430] p-4 rounded-lg font-mono text-xs flex flex-wrap items-center justify-between gap-3 text-slate-400">
        <span className="text-slate-300 font-semibold">Platform Architecture &amp; Execution Links:</span>
        <div className="flex flex-wrap items-center gap-2">
          <Link
            href="/agents"
            className="px-3 py-1.5 rounded bg-[#13141b] hover:bg-[#1a1b24] text-slate-200 border border-[#222430] text-xs transition-colors"
          >
            Agents Architecture →
          </Link>
          <Link
            href="/models"
            className="px-3 py-1.5 rounded bg-[#13141b] hover:bg-[#1a1b24] text-slate-200 border border-[#222430] text-xs transition-colors"
          >
            Models Configuration →
          </Link>
          <Link
            href="/sessions"
            className="px-3 py-1.5 rounded bg-[#13141b] hover:bg-[#1a1b24] text-slate-200 border border-[#222430] text-xs transition-colors"
          >
            Mission Control Sessions →
          </Link>
        </div>
      </div>
    </div>
  );
}
