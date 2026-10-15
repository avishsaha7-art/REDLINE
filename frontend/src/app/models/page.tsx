"use client";

import React, { useState } from 'react';
import Link from 'next/link';

interface ModelProviderSpec {
  providerName: string;
  backendClass: string;
  badge: string;
  badgeColor: string;
  roleDescription: string;
  supportedModels: string[];
  endpoint: string;
  offlineAvailable: boolean;
  securityGuardrails: string;
  provenanceTracking: string;
  contextCeiling: string;
}

const PROVIDERS: ModelProviderSpec[] = [
  {
    providerName: "Nebius Token Factory Provider",
    backendClass: "backend/models/nebius_provider.py:NebiusProvider",
    badge: "SERVER_CONFIGURED",
    badgeColor: "text-emerald-400 border-emerald-800/60 bg-emerald-950/30",
    roleDescription: "Primary inference runtime for autonomous agent planning, code generation, and counterexample generation on Nebius Cloud.",
    supportedModels: [
      "deepseek-ai/DeepSeek-R1",
      "meta-llama/Meta-Llama-3.1-70B-Instruct",
      "Qwen/Qwen2.5-Coder-32B-Instruct"
    ],
    endpoint: "https://api.tokenfactory.nebius.com/v1/chat/completions",
    offlineAvailable: false,
    securityGuardrails: "Server-side NEBIUS_API_KEY environment variable. Zero credentials exposed to frontend. Pydantic extra='forbid' validation on structured outputs.",
    provenanceTracking: "Recorded in EvidenceReceipt.model_provenance with exact model name, temperature (0.0), and max_tokens ceiling.",
    contextCeiling: "128k context ceiling (1MB max response payload)"
  },
  {
    providerName: "NVIDIA Nemotron / Cloud Gateway",
    backendClass: "Nebius Token Factory Gateway Route",
    badge: "GATEWAY_ROUTED",
    badgeColor: "text-blue-400 border-blue-800/60 bg-blue-950/30",
    roleDescription: "High-parameter reasoning models for complex patch synthesis and zero-day defense pipelines routed via Token Factory infrastructure.",
    supportedModels: [
      "nvidia/nemotron-4-340b-instruct",
      "nvidia/nemotron-70b-instruct"
    ],
    endpoint: "Token Factory Gateway Endpoint (Server Dispatched)",
    offlineAvailable: false,
    securityGuardrails: "Strict temperature 0.0 enforcement for deterministic reproducibility. Automated output truncation on response limit breach.",
    provenanceTracking: "Model identifier and response latency tracked in structured observation metadata.",
    contextCeiling: "128k context ceiling (FP8 inference)"
  },
  {
    providerName: "Deterministic Test Mock Provider",
    backendClass: "backend/models/deterministic_provider.py:DeterministicTestProvider",
    badge: "OFFLINE_AVAILABLE",
    badgeColor: "text-cyan-400 border-cyan-800/60 bg-cyan-950/30",
    roleDescription: "Hermetic offline mock provider for local verification, CI/CD regression tests, and reproducible offline benchmarking.",
    supportedModels: [
      "deterministic-mock-v1"
    ],
    endpoint: "Internal Python Process (No Network Egress)",
    offlineAvailable: true,
    securityGuardrails: "Zero external network calls. Guaranteed identical outputs across test runs for hermetic regression verification.",
    provenanceTracking: "Recorded as offline deterministic test fixture in EvidenceReceipt.",
    contextCeiling: "Unbounded (In-Memory Fixture)"
  }
];

export default function ModelsPage() {
  const [selectedProvider, setSelectedProvider] = useState<string>("Nebius Token Factory Provider");

  return (
    <div className="space-y-6">
      {/* Header with Monospace Cyber Breadcrumbs */}
      <header className="border-b border-[#222430] pb-5">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div>
            <div className="flex items-center gap-2 font-mono text-[11px] text-slate-500 mb-1">
              <span>CORE</span>
              <span>{"//"}</span>
              <span className="text-slate-400">09. MODELS</span>
              <span>{"//"}</span>
              <span className="text-[#ef4444] font-semibold">INFRASTRUCTURE</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-black tracking-tight text-white flex items-center gap-3">
              <span>09. Models &amp; Provider Infrastructure</span>
              <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-[#13141b] border border-[#222430] text-slate-400">
                Configuration Reference
              </span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded border border-[#222430] bg-[#171822] text-slate-400">
                v2.4-deterministic
              </span>
            </h1>
            <p className="text-xs text-slate-400 font-mono mt-1">
              Configuration Reference: Supported model providers, server-side credential isolation, and model provenance tracking.
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

      {/* Top Telemetry Ribbon (Truthful, non-fabricated metrics) */}
      <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4" aria-label="Models Telemetry">
        <div className="p-4 rounded-lg bg-[#0d0e12] border border-[#222430]">
          <div className="flex justify-between items-start mb-1">
            <span className="font-mono text-[10px] text-slate-500 uppercase tracking-wider">Configured Providers</span>
            <span className="text-slate-400 text-xs">🧠</span>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold text-white font-mono">2 Active</span>
          </div>
          <div className="mt-2 text-[10px] font-mono text-slate-500">
            Nebius Token Factory + Offline Mock
          </div>
        </div>

        <div className="p-4 rounded-lg bg-[#0d0e12] border border-[#222430]">
          <div className="flex justify-between items-start mb-1">
            <span className="font-mono text-[10px] text-slate-500 uppercase tracking-wider">Credential Storage</span>
            <span className="text-emerald-400 text-xs">🔒</span>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-lg font-bold text-emerald-400 font-mono">Server Environment</span>
          </div>
          <div className="mt-2 text-[10px] font-mono text-slate-500">
            NEBIUS_API_KEY (Zero Client Exposure)
          </div>
        </div>

        <div className="p-4 rounded-lg bg-[#0d0e12] border border-[#222430]">
          <div className="flex justify-between items-start mb-1">
            <span className="font-mono text-[10px] text-slate-500 uppercase tracking-wider">Browser Secret Leakage</span>
            <span className="text-emerald-400 text-xs">✓</span>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold text-emerald-400 font-mono">0 Keys in UI</span>
          </div>
          <div className="mt-2 text-[10px] font-mono text-slate-500">
            No localStorage / sessionStorage storage
          </div>
        </div>

        <div className="p-4 rounded-lg bg-[#0d0e12] border border-[#222430]">
          <div className="flex justify-between items-start mb-1">
            <span className="font-mono text-[10px] text-slate-500 uppercase tracking-wider">Provenance Tracking</span>
            <span className="text-purple-400 text-xs">📜</span>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-lg font-bold text-purple-400 font-mono">Evidence Receipts</span>
          </div>
          <div className="mt-2 text-[10px] font-mono text-slate-500">
            Exact model name &amp; temperature logged
          </div>
        </div>
      </section>

      {/* Security Mandate: Zero Frontend Credentials */}
      <div className="bg-[#141217] border border-rose-900/60 p-4 rounded-lg text-xs font-mono text-rose-300 space-y-1">
        <div className="flex items-center gap-2 font-bold text-rose-400 uppercase tracking-wider text-[11px]">
          <span aria-hidden="true">🔒</span>
          <span>Zero Frontend Credential Mandate:</span>
        </div>
        <p className="text-[11px] text-slate-300 leading-relaxed">
          No API keys or model tokens are ever handled, displayed, or cached by the browser. Model requests are strictly dispatched by the backend Python Orchestrator using server-side environment variables. Output parsing enforces Pydantic schemas with <code className="text-rose-300 font-bold">extra=&apos;forbid&apos;</code> to reject unauthorized model mutations.
        </p>
      </div>

      {/* Provider Cards Grid (Matching Stitch 3-card layout) */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5" aria-label="Model Providers List">
        {PROVIDERS.map((p) => {
          const isSelected = selectedProvider === p.providerName;
          return (
            <div
              key={p.providerName}
              onClick={() => setSelectedProvider(p.providerName)}
              className={`p-5 rounded-lg border flex flex-col justify-between space-y-4 transition-all cursor-pointer ${
                isSelected
                  ? 'bg-[#12131a] border-[#ef4444] shadow-[0_0_15px_rgba(239,68,68,0.15)]'
                  : 'bg-[#0d0e12] hover:bg-[#12131a] border-[#222430]'
              }`}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') setSelectedProvider(p.providerName); }}
            >
              <div className="space-y-4">
                {/* Header & Badges */}
                <div className="flex items-start justify-between">
                  <div>
                    <h2 className="font-mono text-sm font-bold text-white">{p.providerName}</h2>
                    <span className="font-mono text-[10px] text-slate-500 block mt-0.5">{p.backendClass}</span>
                  </div>
                  <span className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold border ${p.badgeColor}`}>
                    {p.badge}
                  </span>
                </div>

                {/* Role Description */}
                <p className="text-xs text-slate-300 font-mono leading-relaxed">
                  {p.roleDescription}
                </p>

                {/* Endpoint & Limits */}
                <div className="p-3 bg-[#13141b] rounded border border-[#222430] font-mono text-[11px] space-y-1.5">
                  <div className="flex justify-between">
                    <span className="text-slate-500 text-[10px] uppercase">Endpoint:</span>
                    <span className="text-slate-300 truncate max-w-[180px]">{p.endpoint}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500 text-[10px] uppercase">Ceiling:</span>
                    <span className="text-slate-300">{p.contextCeiling}</span>
                  </div>
                </div>

                {/* Supported Models List */}
                <div className="space-y-1.5 font-mono text-xs">
                  <span className="text-[10px] text-slate-500 uppercase font-bold block">
                    Supported Architectures ({p.supportedModels.length}):
                  </span>
                  <ul className="space-y-1">
                    {p.supportedModels.map((m) => (
                      <li key={m} className="bg-[#13141b] text-slate-300 p-2 rounded border border-[#222430] text-[11px] select-all">
                        {m}
                      </li>
                    ))}
                  </ul>
                </div>

                {/* Guardrails and Provenance */}
                <div className="space-y-2 pt-2 border-t border-[#222430] text-[11px] font-mono text-slate-400">
                  <div>
                    <span className="text-[10px] text-slate-500 uppercase block font-bold">Security Guardrails:</span>
                    <p className="text-slate-300 mt-0.5 leading-snug">{p.securityGuardrails}</p>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-500 uppercase block font-bold">Provenance Logging:</span>
                    <p className="text-slate-300 mt-0.5 leading-snug">{p.provenanceTracking}</p>
                  </div>
                </div>
              </div>

              {/* Bottom Policy Status */}
              <div className="pt-3 border-t border-[#222430] flex items-center justify-between font-mono text-[10px] text-slate-500">
                <span>Deterministic Mode: Active</span>
                <span className="text-emerald-400 font-semibold">Temp 0.0</span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Configuration & Diagnostics Notice Box */}
      <div className="bg-[#0d0e12] border border-[#222430] p-5 rounded-lg font-mono text-xs text-slate-400 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <span className="text-white font-bold block text-sm mb-0.5">Need to adjust resource quotas or sandbox ceilings?</span>
          <p className="text-[11px] text-slate-500">
            System iteration ceilings, tool call budgets, and gateway routes are managed under platform governance.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Link
            href="/agents"
            className="px-4 py-2 rounded bg-[#13141b] hover:bg-[#1a1b24] text-slate-200 border border-[#222430] text-xs font-semibold whitespace-nowrap transition-colors"
          >
            Agent Fleet Architecture →
          </Link>
          <Link
            href="/settings"
            className="px-4 py-2 rounded bg-[#13141b] hover:bg-[#1a1b24] text-slate-200 border border-[#222430] text-xs font-semibold whitespace-nowrap transition-colors"
          >
            View Governance Ceilings in Settings →
          </Link>
        </div>
      </div>
    </div>
  );
}
