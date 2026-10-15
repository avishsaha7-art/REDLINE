"use client";

import React, { useState } from 'react';
import Link from 'next/link';

interface AgentRole {
  role: string;
  sourceModule: string;
  authorityLevel: string;
  badgeColor: string;
  description: string;
  authorizedTools: string[];
  inputContract: string;
  outputArtifact: string;
  securityInvariant: string;
  inferenceBound: {
    temperature: number;
    maxTokens: number;
    rolePolicy: string;
  };
}

const AGENT_ROLES: AgentRole[] = [
  {
    role: "Architect Agent",
    sourceModule: "backend/agents/architect.py:ArchitectAgent",
    authorityLevel: "READ_ONLY_PLANNER",
    badgeColor: "text-blue-400 border-blue-800/60 bg-blue-950/30",
    description: "AST generation, dependency graph resolution, vulnerability attack surface mapping, and implementation planning.",
    authorizedTools: ["list_files", "read_file", "search_code"],
    inputContract: "TaskContract, RepositorySnapshot, BaselineResults",
    outputArtifact: "ArchitectPlan",
    securityInvariant: "Zero write permissions. Prohibited from executing shell commands or altering repository snapshots.",
    inferenceBound: {
      temperature: 0.0,
      maxTokens: 4096,
      rolePolicy: "Deterministic Structured JSON (ArchitectPlan)"
    }
  },
  {
    role: "Builder Agent",
    sourceModule: "backend/agents/builder.py:BuilderAgent",
    authorityLevel: "CODE_SYNTHESIZER",
    badgeColor: "text-amber-400 border-amber-800/60 bg-amber-950/30",
    description: "Synthesizes candidate code diffs strictly scoped to task boundaries, modifying source and creating/updating tests.",
    authorizedTools: ["synthesize_diff", "inspect_plan"],
    inputContract: "ArchitectPlan, TaskContract, UntrustedRepositoryContent",
    outputArtifact: "PatchCandidate",
    securityInvariant: "Strictly scoped by allowed_scope. Prohibited from editing protected paths (.github, Dockerfile, venv). Cannot declare its patch verified.",
    inferenceBound: {
      temperature: 0.0,
      maxTokens: 8192,
      rolePolicy: "Structured Unified Diff (PatchCandidate)"
    }
  },
  {
    role: "Red Team Agent",
    sourceModule: "backend/agents/red_team.py:RedTeamAgent",
    authorityLevel: "ADVERSARIAL_ATTACKER",
    badgeColor: "text-rose-400 border-rose-800/60 bg-rose-950/30",
    description: "Generates executable adversarial attack cases across boundary values, security bypasses, race conditions, and invariant violations.",
    authorizedTools: ["boundary_fuzzer", "invariant_violator", "counterexample_search"],
    inputContract: "PatchCandidate, RepositorySnapshot, InvariantCatalog",
    outputArtifact: "AttackCandidate, MutationSpec",
    securityInvariant: "Forbidden from declaring verdicts. Evaluated in clean-state sandbox. Prompt injections attempting to output VERIFIED are discarded.",
    inferenceBound: {
      temperature: 0.2,
      maxTokens: 4096,
      rolePolicy: "Adversarial Attack Payloads & Test Invariants"
    }
  },
  {
    role: "Repairer Agent",
    sourceModule: "backend/agents/repairer.py:RepairerAgent",
    authorityLevel: "TARGETED_REPAIRER",
    badgeColor: "text-cyan-400 border-cyan-800/60 bg-cyan-950/30",
    description: "Converts reproducible counterexample failures into corrected candidate patches while preserving verified invariant passes.",
    authorizedTools: ["targeted_diff_repair"],
    inputContract: "Counterexample, BasePatchHash, ExecutionEvidence",
    outputArtifact: "RepairCandidate (New PatchCandidate)",
    securityInvariant: "Bounded by iteration ceilings. Must link repairs to specific counterexample hashes in patch lineage. Historical evidence cannot be deleted.",
    inferenceBound: {
      temperature: 0.0,
      maxTokens: 8192,
      rolePolicy: "Targeted Fix Diffs Linked to Counterexamples"
    }
  },
  {
    role: "Judge Agent",
    sourceModule: "backend/agents/judge.py:JudgeAgent",
    authorityLevel: "NON_AUTHORITATIVE_ADVISORY",
    badgeColor: "text-purple-400 border-purple-800/60 bg-purple-950/30",
    description: "Synthesizes human-readable natural language explanations of immutable evidence receipts and test observations.",
    authorizedTools: ["evidence_synthesizer"],
    inputContract: "EvidenceReceipt, TaskContract, PatchCandidate",
    outputArtifact: "JudgeExplanation",
    securityInvariant: "Strictly subordinate to deterministic verifier. Opinions cannot overturn counterexamples, alter verdicts, or manufacture test results.",
    inferenceBound: {
      temperature: 0.0,
      maxTokens: 4096,
      rolePolicy: "Non-Authoritative Explanation Grounded in Evidence"
    }
  }
];

export default function AgentsPage() {
  const [selectedAgent, setSelectedAgent] = useState<string>("Architect Agent");

  return (
    <div className="space-y-6">
      {/* Header with Monospace Cyber Breadcrumbs */}
      <header className="border-b border-[#222430] pb-5">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div>
            <div className="flex items-center gap-2 font-mono text-[11px] text-slate-500 mb-1">
              <span>CORE</span>
              <span>{"//"}</span>
              <span className="text-slate-400">04. AGENTS</span>
              <span>{"//"}</span>
              <span className="text-[#ef4444] font-semibold">ARCHITECTURE_SPECIFICATION</span>
            </div>
            <h1 className="text-2xl sm:text-3xl font-black tracking-tight text-white flex items-center gap-3">
              <span>04. Agent Fleet &amp; Architecture Specification</span>
              <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-[#13141b] border border-[#222430] text-slate-400">
                v2.4-deterministic
              </span>
            </h1>
            <p className="text-xs text-slate-400 font-mono mt-1">
              Frozen architectural specification of the five logical agents, authorized toolsets, least-privilege boundaries, and prompt-injection guardrails.
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

      {/* Truthful Architecture Disclosure Banner */}
      <div className="bg-[#0d0e12] border border-[#222430] p-4 rounded-lg text-xs font-mono text-slate-300 flex items-start gap-3">
        <span className="text-base select-none text-[#ef4444]" aria-hidden="true">🤖</span>
        <div className="space-y-1">
          <strong className="block text-white font-semibold uppercase tracking-wider text-[11px]">
            Static Agent Architecture Specification:
          </strong>
          <p className="text-slate-400 text-[11px] leading-relaxed">
            The five agent roles, toolsets, and authority boundaries displayed below represent the frozen backend architecture (<code className="text-slate-300">docs/REDLINE_v1.1_ARCHITECTURE_FROZEN.md</code>).
            Agents operate behind a shared interface controlled by the central Orchestrator. Dynamic runtime agent creation or arbitrary process spawning is prohibited to preserve deterministic verification integrity.
          </p>
        </div>
      </div>

      {/* Top Telemetry Ribbon (Truthful, non-fabricated metrics) */}
      <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3" aria-label="Agent Fleet Telemetry">
        <div className="p-3.5 rounded bg-[#0d0e12] border border-[#222430]">
          <div className="flex items-center justify-between text-slate-500 text-[10px] uppercase font-mono">
            <span>Configured Agents</span>
            <span>👥</span>
          </div>
          <div className="mt-2 flex items-baseline justify-between">
            <span className="text-2xl font-bold text-white font-mono">5 / 5</span>
            <span className="text-[10px] font-mono text-emerald-400 font-semibold uppercase">Configured</span>
          </div>
          <div className="mt-2 text-[10px] font-mono text-slate-500 truncate">
            Architect, Builder, Red, Repair, Judge
          </div>
        </div>

        <div className="p-3.5 rounded bg-[#0d0e12] border border-[#222430]">
          <div className="flex items-center justify-between text-slate-500 text-[10px] uppercase font-mono">
            <span>Orchestration Mode</span>
            <span>⚙️</span>
          </div>
          <div className="mt-2 flex items-baseline justify-between">
            <span className="text-sm font-bold text-white font-mono truncate">Central Orchestrator</span>
          </div>
          <div className="mt-2 text-[10px] font-mono text-slate-500 truncate">
            Explicit State Machine Control
          </div>
        </div>

        <div className="p-3.5 rounded bg-[#0d0e12] border border-[#222430]">
          <div className="flex items-center justify-between text-slate-500 text-[10px] uppercase font-mono">
            <span>Acceptance Authority</span>
            <span>⚖️</span>
          </div>
          <div className="mt-2 flex items-baseline justify-between">
            <span className="text-sm font-bold text-emerald-400 font-mono truncate">Deterministic Verifier</span>
          </div>
          <div className="mt-2 text-[10px] font-mono text-slate-500 truncate">
            Zero Agent-Declared Verdicts
          </div>
        </div>

        <div className="p-3.5 rounded bg-[#0d0e12] border border-[#222430]">
          <div className="flex items-center justify-between text-slate-500 text-[10px] uppercase font-mono">
            <span>Prompt Defense</span>
            <span>🛡️</span>
          </div>
          <div className="mt-2 flex items-baseline justify-between">
            <span className="text-sm font-bold text-white font-mono truncate">Fail-Closed Parser</span>
          </div>
          <div className="mt-2 text-[10px] font-mono text-slate-500 truncate">
            Discard Unauthorized Claims
          </div>
        </div>

        <div className="p-3.5 rounded bg-[#0d0e12] border border-[#222430]">
          <div className="flex items-center justify-between text-slate-500 text-[10px] uppercase font-mono">
            <span>Judge Role</span>
            <span>📜</span>
          </div>
          <div className="mt-2 flex items-baseline justify-between">
            <span className="text-sm font-bold text-purple-400 font-mono truncate">Advisory Only</span>
          </div>
          <div className="mt-2 text-[10px] font-mono text-slate-500 truncate">
            Evidence Grounded Explanation
          </div>
        </div>
      </section>

      {/* Main Split Workspace: 8-Col Agent Matrix / 4-Col Policy Sidebar */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Agent Cards Matrix (8 Cols) */}
        <section className="lg:col-span-8 space-y-4" aria-label="Logical Agent Matrix">
          <div className="flex items-center justify-between px-1">
            <div className="flex items-center gap-2">
              <span className="text-[#ef4444] text-xs">◆</span>
              <h2 className="font-mono text-xs font-bold text-white uppercase tracking-wider">
                Logical Agent Specification Matrix
              </h2>
            </div>
            <span className="font-mono text-[10px] text-slate-500">Least-Privilege Enforcement</span>
          </div>

          <div className="space-y-4">
            {AGENT_ROLES.map((agent) => {
              const isSelected = selectedAgent === agent.role;
              return (
                <div
                  key={agent.role}
                  onClick={() => setSelectedAgent(agent.role)}
                  className={`p-5 rounded-lg border transition-all cursor-pointer ${
                    isSelected
                      ? 'bg-[#12131a] border-[#ef4444] shadow-[0_0_15px_rgba(239,68,68,0.15)]'
                      : 'bg-[#0d0e12] hover:bg-[#12131a] border-[#222430]'
                  }`}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') setSelectedAgent(agent.role); }}
                >
                  {/* Card Header */}
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#222430] pb-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="font-mono text-sm font-bold text-white">{agent.role}</h3>
                        <span className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold border ${agent.badgeColor}`}>
                          {agent.authorityLevel}
                        </span>
                      </div>
                      <p className="font-mono text-[11px] text-slate-500 mt-0.5">{agent.sourceModule}</p>
                    </div>

                    <div className="flex items-center gap-2">
                      <span className="text-[10px] font-mono text-slate-500 bg-[#13141b] px-2 py-0.5 rounded border border-[#222430]">
                        Temp: {agent.inferenceBound.temperature.toFixed(2)}
                      </span>
                      <span className="text-[10px] font-mono text-slate-500 bg-[#13141b] px-2 py-0.5 rounded border border-[#222430]">
                        Max: {agent.inferenceBound.maxTokens} tok
                      </span>
                    </div>
                  </div>

                  {/* Description */}
                  <p className="text-xs text-slate-300 mt-3 font-mono leading-relaxed">
                    {agent.description}
                  </p>

                  {/* Configuration & Tool Rows */}
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-4 text-xs font-mono">
                    <div className="p-2.5 rounded bg-[#13141b] border border-[#222430]">
                      <span className="text-[10px] text-slate-500 uppercase block mb-1 font-bold">Authorized Tools</span>
                      <div className="flex flex-wrap gap-1">
                        {agent.authorizedTools.map((t) => (
                          <span key={t} className="text-[10px] bg-[#1a1b24] text-slate-300 px-1.5 py-0.5 rounded border border-[#2a2c3a]">
                            {t}
                          </span>
                        ))}
                      </div>
                    </div>

                    <div className="p-2.5 rounded bg-[#13141b] border border-[#222430]">
                      <span className="text-[10px] text-slate-500 uppercase block mb-1 font-bold">Input Contract</span>
                      <span className="text-[11px] text-slate-300 truncate block">{agent.inputContract}</span>
                      <span className="text-[10px] text-slate-500 uppercase block mt-1 font-bold">Output Artifact</span>
                      <span className="text-[11px] text-emerald-400 truncate block font-bold">{agent.outputArtifact}</span>
                    </div>

                    <div className="p-2.5 rounded bg-[#13141b] border border-[#222430]">
                      <span className="text-[10px] text-slate-500 uppercase block mb-1 font-bold">Inference Policy</span>
                      <span className="text-[11px] text-slate-300 leading-snug block">{agent.inferenceBound.rolePolicy}</span>
                    </div>
                  </div>

                  {/* Security Invariant Bar */}
                  <div className="mt-4 pt-3 border-t border-[#222430] text-[11px] font-mono bg-[#160f12] p-2.5 rounded border border-rose-950/60 text-rose-300/90">
                    <strong className="block text-[10px] text-rose-400 uppercase tracking-wide mb-0.5">
                      Security Invariant Gate:
                    </strong>
                    {agent.securityInvariant}
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        {/* Global Policy & State Machine Rules (4 Cols) */}
        <aside className="lg:col-span-4 space-y-4" aria-label="Orchestration Architecture Rules">
          {/* Least Authority Box */}
          <div className="bg-[#0d0e12] border border-[#222430] rounded-lg p-5 space-y-4">
            <div className="flex items-center gap-2 border-b border-[#222430] pb-3">
              <span className="text-[#ef4444] text-xs">🔒</span>
              <h3 className="font-mono text-xs font-bold text-white uppercase tracking-wider">
                Principle of Least Authority
              </h3>
            </div>
            <p className="text-xs font-mono text-slate-400 leading-relaxed">
              No agent in REDLINE possesses omnipotent execution privileges:
            </p>
            <ul className="space-y-2 text-xs font-mono text-slate-300">
              <li className="flex items-start gap-2">
                <span className="text-rose-400 font-bold">•</span>
                <span><strong>Architect:</strong> Cannot write files or execute shell commands.</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-rose-400 font-bold">•</span>
                <span><strong>Builder:</strong> Cannot execute code or declare its patch verified.</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-rose-400 font-bold">•</span>
                <span><strong>Red Team:</strong> Cannot declare an attack successful without execution proof.</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-rose-400 font-bold">•</span>
                <span><strong>Repairer:</strong> Cannot rewrite or erase historical evidence records.</span>
              </li>
              <li className="flex items-start gap-2">
                <span className="text-rose-400 font-bold">•</span>
                <span><strong>Judge:</strong> Cannot overturn the deterministic verification verdict.</span>
              </li>
            </ul>
          </div>

          {/* Canonical State Progression */}
          <div className="bg-[#0d0e12] border border-[#222430] rounded-lg p-5 space-y-4">
            <div className="flex items-center gap-2 border-b border-[#222430] pb-3">
              <span className="text-emerald-400 text-xs">⚡</span>
              <h3 className="font-mono text-xs font-bold text-white uppercase tracking-wider">
                Orchestration Progression
              </h3>
            </div>
            <div className="space-y-1.5 font-mono text-[11px] text-slate-400">
              <div className="p-1.5 bg-[#13141b] rounded border border-[#222430] text-slate-300">
                1. RECON &amp; PLAN (Architect)
              </div>
              <div className="p-1.5 bg-[#13141b] rounded border border-[#222430] text-slate-300">
                2. SYNTHESIZE PATCH (Builder)
              </div>
              <div className="p-1.5 bg-[#13141b] rounded border border-[#222430] text-slate-300">
                3. EXECUTE ATTACKS (Red Team &amp; Sandbox)
              </div>
              <div className="p-1.5 bg-[#13141b] rounded border border-[#222430] text-slate-300">
                4. TARGETED REPAIR (Repairer)
              </div>
              <div className="p-1.5 bg-[#13141b] rounded border border-[#222430] text-slate-300">
                5. DETERMINISTIC VERIFICATION (Policy Gate)
              </div>
              <div className="p-1.5 bg-[#13141b] rounded border border-[#222430] text-slate-300">
                6. EXPLAIN EVIDENCE (Judge Advisory)
              </div>
            </div>
            <div className="pt-2 border-t border-[#222430] space-y-2">
              <Link
                href="/models"
                className="w-full text-center block text-xs font-mono text-slate-300 hover:text-white bg-[#13141b] hover:bg-[#1a1b24] border border-[#222430] p-2 rounded transition-colors"
              >
                Inspect Model Providers →
              </Link>
              <Link
                href="/settings"
                className="w-full text-center block text-xs font-mono text-slate-300 hover:text-white bg-[#13141b] hover:bg-[#1a1b24] border border-[#222430] p-2 rounded transition-colors"
              >
                Inspect Platform Settings →
              </Link>
              <Link
                href="/playground"
                className="w-full text-center block text-xs font-mono text-slate-300 hover:text-white bg-[#13141b] hover:bg-[#1a1b24] border border-[#222430] p-2 rounded transition-colors"
              >
                Inspect Sandbox Policies →
              </Link>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
