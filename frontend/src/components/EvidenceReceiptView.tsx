import React, { useState } from 'react';
import { EvidenceReceipt, SandboxCapabilities } from '../models/types';

interface Props {
  receipt: EvidenceReceipt | null;
}

export interface ReceiptIntegrityStatus {
  hasHash: boolean;
  title: string;
  subtitle: string;
  badgeClass: string;
}

export function getReceiptIntegrityStatus(receipt: Partial<EvidenceReceipt> | null): ReceiptIntegrityStatus {
  const hasHash = Boolean(receipt?.receipt_hash && receipt.receipt_hash.trim().length > 0);
  if (hasHash) {
    return {
      hasHash: true,
      title: 'HASH RECORDED (UNVERIFIED CLIENT-SIDE)',
      subtitle: 'Integrity not independently verified by frontend',
      badgeClass: 'bg-[#18202f] text-slate-300 border-[#2b3952]',
    };
  }
  return {
    hasHash: false,
    title: 'RECEIPT HASH MISSING',
    subtitle: 'No cryptographic signature recorded',
    badgeClass: 'bg-amber-950/60 text-amber-300 border-amber-800',
  };
}

export function validateSandboxCapabilities(data: unknown): SandboxCapabilities | null {
  if (!data || typeof data !== 'object' || Array.isArray(data)) {
    return null;
  }
  const obj = data as Record<string, unknown>;
  const keys = Object.keys(obj);
  if (keys.length === 0) {
    return null;
  }

  const hasKnownField = 
    'security_level' in obj ||
    'filesystem_isolation' in obj ||
    'process_isolation' in obj ||
    'network_isolation' in obj ||
    'credential_isolation' in obj ||
    'resource_enforcement' in obj ||
    'timeout_enforcement' in obj ||
    'workspace_isolation' in obj ||
    'cleanup_guarantee' in obj ||
    'secure_untrusted_execution' in obj;

  if (!hasKnownField) {
    return null;
  }

  return {
    security_level: typeof obj.security_level === 'string' ? obj.security_level : undefined,
    filesystem_isolation: typeof obj.filesystem_isolation === 'string' ? obj.filesystem_isolation : undefined,
    process_isolation: typeof obj.process_isolation === 'string' ? obj.process_isolation : undefined,
    network_isolation: typeof obj.network_isolation === 'string' ? obj.network_isolation : undefined,
    credential_isolation: typeof obj.credential_isolation === 'string' ? obj.credential_isolation : undefined,
    resource_enforcement: typeof obj.resource_enforcement === 'string' ? obj.resource_enforcement : undefined,
    timeout_enforcement: typeof obj.timeout_enforcement === 'string' ? obj.timeout_enforcement : undefined,
    workspace_isolation: typeof obj.workspace_isolation === 'string' ? obj.workspace_isolation : undefined,
    cleanup_guarantee: typeof obj.cleanup_guarantee === 'string' ? obj.cleanup_guarantee : undefined,
    secure_untrusted_execution: typeof obj.secure_untrusted_execution === 'boolean' ? obj.secure_untrusted_execution : false,
  };
}

export const EvidenceReceiptView: React.FC<Props> = ({ receipt }) => {
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  if (!receipt) {
    return null;
  }

  const verdict = receipt.verdict || receipt.deterministic_verdict || 'UNKNOWN';
  const integrityStatus = getReceiptIntegrityStatus(receipt);

  const copyToClipboard = (text: string, key: string) => {
    if (typeof navigator !== 'undefined' && navigator.clipboard) {
      navigator.clipboard.writeText(text).catch(() => {});
      setCopiedKey(key);
      setTimeout(() => setCopiedKey(null), 2000);
    }
  };

  // Safely validate structured sandbox capabilities without unsafe casts
  const capabilities = validateSandboxCapabilities(receipt.structured_observation?.capabilities);

  const sandboxBackend = receipt.structured_observation?.sandbox_backend || receipt.sandbox_provenance?.backend || 'UNKNOWN';
  const securityLevel = capabilities?.security_level || receipt.structured_observation?.security_level || 'UNKNOWN';

  return (
    <div className="evidence-receipt-view border border-[#1e2638] p-6 rounded-md bg-[#0d1117] mt-4 shadow-lg text-slate-200" role="region" aria-label="Evidence Receipt">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-6 border-b border-[#1e2638] pb-4 gap-3">
        <div>
          <h2 className="text-2xl font-bold text-white">EVIDENCE RECEIPT</h2>
          <p className="text-xs text-slate-400 font-mono mt-0.5">Authoritative Verification Bundle</p>
        </div>
        
        {/* Truthful integrity badge */}
        <div className="text-left sm:text-right" role="status">
          <span className={`inline-block border px-3 py-1 rounded text-xs font-bold uppercase tracking-wide ${integrityStatus.badgeClass}`}>
            {integrityStatus.title}
          </span>
          <p className="text-[10px] text-slate-400 mt-1">
            {integrityStatus.subtitle}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs font-mono bg-[#131822] p-4 rounded mb-6 border border-[#20293d] text-slate-300">
        <div><span className="text-slate-500 block">Schema:</span> {receipt.receipt_schema_version}</div>
        <div><span className="text-slate-500 block">Run ID:</span> <span className="select-all text-slate-200">{receipt.run_id}</span></div>
        <div><span className="text-slate-500 block">Task ID:</span> <span className="text-slate-200">{receipt.task_id}</span></div>
        <div><span className="text-slate-500 block">Timestamp:</span> <span className="text-slate-200">{receipt.timestamp}</span></div>
      </div>

      <div className="space-y-4 text-sm">
        {/* Cryptographic Hashes */}
        <div className="border border-[#1e2638] p-4 rounded bg-[#10141e]">
          <h3 className="font-bold text-slate-200 mb-3 text-sm flex items-center justify-between">
            <span>Cryptographic Hashes</span>
            <span className="text-xs font-normal text-slate-500 font-mono">SHA-256</span>
          </h3>
          
          <div className="space-y-2 text-xs">
            <div>
              <div className="flex justify-between items-center mb-1">
                <span className="font-semibold text-slate-400">Receipt Root Hash:</span>
                {receipt.receipt_hash && (
                  <button 
                    type="button" 
                    onClick={() => copyToClipboard(receipt.receipt_hash || '', 'receipt_hash')}
                    className="text-[10px] text-red-400 hover:text-red-300 hover:underline focus-visible:ring-2 focus-visible:ring-red-500 rounded px-1"
                  >
                    {copiedKey === 'receipt_hash' ? 'Copied!' : 'Copy'}
                  </button>
                )}
              </div>
              <code className="font-mono break-all text-xs bg-[#090d14] p-2.5 rounded border border-[#20293d] text-slate-200 block select-all">
                {receipt.receipt_hash || 'NOT RECORDED'}
              </code>
            </div>

            <div>
              <div className="flex justify-between items-center mb-1">
                <span className="font-semibold text-slate-400">Task Contract Hash:</span>
                <button 
                  type="button" 
                  onClick={() => copyToClipboard(receipt.task_contract_hash, 'contract_hash')}
                  className="text-[10px] text-red-400 hover:text-red-300 hover:underline focus-visible:ring-2 focus-visible:ring-red-500 rounded px-1"
                >
                  {copiedKey === 'contract_hash' ? 'Copied!' : 'Copy'}
                </button>
              </div>
              <code className="font-mono break-all text-xs bg-[#090d14] p-2.5 rounded border border-[#20293d] text-slate-200 block select-all">
                {receipt.task_contract_hash}
              </code>
            </div>

            <div>
              <div className="flex justify-between items-center mb-1">
                <span className="font-semibold text-slate-400">Repository Snapshot Hash:</span>
                <button 
                  type="button" 
                  onClick={() => copyToClipboard(receipt.repository_snapshot_hash, 'snapshot_hash')}
                  className="text-[10px] text-red-400 hover:text-red-300 hover:underline focus-visible:ring-2 focus-visible:ring-red-500 rounded px-1"
                >
                  {copiedKey === 'snapshot_hash' ? 'Copied!' : 'Copy'}
                </button>
              </div>
              <code className="font-mono break-all text-xs bg-[#090d14] p-2.5 rounded border border-[#20293d] text-slate-200 block select-all">
                {receipt.repository_snapshot_hash}
              </code>
            </div>

            <div>
              <div className="flex justify-between items-center mb-1">
                <span className="font-semibold text-slate-400">Final Patch Hash:</span>
                <button 
                  type="button" 
                  onClick={() => copyToClipboard(receipt.patch_hash, 'patch_hash')}
                  className="text-[10px] text-red-400 hover:text-red-300 hover:underline focus-visible:ring-2 focus-visible:ring-red-500 rounded px-1"
                >
                  {copiedKey === 'patch_hash' ? 'Copied!' : 'Copy'}
                </button>
              </div>
              <code className="font-mono break-all text-xs bg-[#090d14] p-2.5 rounded border border-[#20293d] text-slate-200 block select-all">
                {receipt.patch_hash}
              </code>
            </div>
          </div>
        </div>

        {/* Verdict & Patch Lineage */}
        <div className="border border-[#1e2638] p-4 rounded bg-[#10141e]">
          <h3 className="font-bold text-slate-200 mb-2">Verdict & Lineage</h3>
          <div className="flex items-center gap-2 mb-3">
            <span className="text-slate-400 text-xs">Deterministic Verdict:</span>
            <span className={`font-mono text-xs px-2 py-0.5 rounded font-bold border ${
              verdict === 'VERIFIED' ? 'bg-emerald-950/60 text-emerald-300 border-emerald-800' : 
              verdict === 'REJECTED' ? 'bg-red-950/60 text-red-300 border-red-800' : 
              'bg-amber-950/60 text-amber-300 border-amber-800'
            }`}>
              {verdict === 'VERIFIED' ? '✓ ' : verdict === 'REJECTED' ? '✕ ' : '⚠ '}
              {verdict}
            </span>
          </div>

          <div>
            <span className="text-slate-400 text-xs block mb-1 font-semibold">Patch Lineage History:</span>
            {receipt.patch_lineage && receipt.patch_lineage.length > 0 ? (
              <ul className="list-disc pl-5 font-mono text-xs space-y-0.5" role="list">
                {receipt.patch_lineage.map((patchId, idx) => (
                  <li key={idx} className="text-slate-300">{patchId}</li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-slate-500 italic">No iterative repair lineage recorded.</p>
            )}
          </div>
        </div>

        {/* Deterministic Test Results Summary */}
        <div className="border border-[#1e2638] p-4 rounded bg-[#10141e]" role="region" aria-label="Test Execution Summary">
          <h3 className="font-bold text-slate-200 mb-3 text-sm flex items-center justify-between">
            <span>Deterministic Test Execution Summary</span>
            <span className="text-xs font-mono bg-[#18202f] text-slate-300 px-2 py-0.5 rounded border border-[#2b3952]">
              Executed: {receipt.test_summary?.executed ?? 0}
            </span>
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs font-mono">
            <div className="p-2 bg-[#131822] rounded border border-[#20293d]">
              <span className="text-slate-500 block text-[10px]">Total Executed</span>
              <span className="font-bold text-slate-200">{receipt.test_summary?.executed ?? 0}</span>
            </div>
            <div className="p-2 bg-[#131822] rounded border border-[#20293d]">
              <span className="text-slate-500 block text-[10px]">Passed</span>
              <span className="font-bold text-emerald-400">{receipt.test_summary?.passed ?? 0}</span>
            </div>
            <div className="p-2 bg-[#131822] rounded border border-[#20293d]">
              <span className="text-slate-500 block text-[10px]">Failed</span>
              <span className="font-bold text-red-400">{receipt.test_summary?.failed ?? 0}</span>
            </div>
            <div className="p-2 bg-[#131822] rounded border border-[#20293d]">
              <span className="text-slate-500 block text-[10px]">Inconclusive</span>
              <span className="font-bold text-amber-400">{receipt.test_summary?.inconclusive ?? 0}</span>
            </div>
          </div>
        </div>

        {/* Adversarial Red-Team Findings & Counterexamples */}
        <div className="border border-[#1e2638] p-4 rounded bg-[#10141e]" role="region" aria-label="Red-Team Findings">
          <h3 className="font-bold text-slate-200 mb-2 text-sm flex items-center justify-between">
            <span>Red-Team Adversarial Findings</span>
            <span className={`text-xs font-mono px-2 py-0.5 rounded ${
              receipt.counterexamples && receipt.counterexamples.length > 0
                ? 'bg-red-950/60 text-red-300 border border-red-800 font-bold'
                : 'bg-emerald-950/60 text-emerald-300 border border-emerald-800'
            }`}>
              {receipt.counterexamples?.length ?? 0} Counterexample(s)
            </span>
          </h3>

          {receipt.counterexamples && receipt.counterexamples.length > 0 ? (
            <div className="space-y-2 mt-2">
              {receipt.counterexamples.map((ce, idx) => (
                <div key={idx} className="p-3 bg-red-950/40 rounded border border-red-800/80 text-xs font-mono space-y-1">
                  <div className="flex justify-between items-center text-red-300 font-bold">
                    <span>ID: {ce.counterexample_id}</span>
                    <span className="text-[10px] bg-red-900/60 text-red-200 px-1.5 py-0.5 rounded">{ce.oracle_type}</span>
                  </div>
                  <div><strong className="text-slate-400">Target:</strong> <span className="text-slate-300">{ce.invariant_id}</span></div>
                  <div><strong className="text-slate-400">Input:</strong> <code className="text-slate-200">{ce.input_data}</code></div>
                  <div><strong className="text-slate-400">Observed Output:</strong> <span className="text-red-300">{ce.observed_output}</span></div>
                  <div><strong className="text-slate-400">Expected:</strong> <span className="text-emerald-300">{ce.expected_output}</span></div>
                  <div><strong className="text-slate-400">Reason:</strong> <span className="text-slate-300">{ce.failure_reason}</span></div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-slate-500 italic mt-1">
              Zero counterexamples detected across evaluated adversarial attack vectors.
            </p>
          )}
        </div>

        {/* Finding C: Sandbox Capabilities Schema Alignment */}
        <div className="border border-[#1e2638] p-4 rounded bg-[#10141e]" role="region" aria-label="Sandbox Capabilities">
          <div className="flex justify-between items-center mb-3">
            <h3 className="font-bold text-slate-200 text-sm">Sandbox Capabilities & Isolation Profile</h3>
            <span className="text-xs font-mono bg-[#18202f] text-slate-300 px-2 py-0.5 rounded border border-[#2b3952]">
              Backend: {sandboxBackend}
            </span>
          </div>

          {capabilities ? (
            <div className="space-y-3">
              <div className="grid grid-cols-2 md:grid-cols-3 gap-2 text-xs font-mono">
                <div className="p-2 bg-[#131822] rounded border border-[#20293d]">
                  <span className="text-slate-500 block text-[10px]">Process Isolation:</span>
                  <span className={`font-bold ${capabilities.process_isolation === 'ENFORCED' ? 'text-emerald-400' : 'text-slate-300'}`}>
                    {capabilities.process_isolation || 'UNKNOWN'}
                  </span>
                </div>

                <div className="p-2 bg-[#131822] rounded border border-[#20293d]">
                  <span className="text-slate-500 block text-[10px]">Network Isolation:</span>
                  <span className={`font-bold ${capabilities.network_isolation === 'ENFORCED' ? 'text-emerald-400' : 'text-slate-300'}`}>
                    {capabilities.network_isolation || 'UNKNOWN'}
                  </span>
                </div>

                <div className="p-2 bg-[#131822] rounded border border-[#20293d]">
                  <span className="text-slate-500 block text-[10px]">Filesystem Isolation:</span>
                  <span className={`font-bold ${capabilities.filesystem_isolation === 'ENFORCED' ? 'text-emerald-400' : 'text-slate-300'}`}>
                    {capabilities.filesystem_isolation || 'UNKNOWN'}
                  </span>
                </div>

                <div className="p-2 bg-[#131822] rounded border border-[#20293d]">
                  <span className="text-slate-500 block text-[10px]">Credential Isolation:</span>
                  <span className={`font-bold ${capabilities.credential_isolation === 'ENFORCED' ? 'text-emerald-400' : 'text-slate-300'}`}>
                    {capabilities.credential_isolation || 'UNKNOWN'}
                  </span>
                </div>

                <div className="p-2 bg-[#131822] rounded border border-[#20293d]">
                  <span className="text-slate-500 block text-[10px]">Security Level:</span>
                  <span className={`font-bold ${securityLevel === 'SECURE' ? 'text-emerald-400' : 'text-amber-400'}`}>
                    {securityLevel}
                  </span>
                </div>

                <div className="p-2 bg-[#131822] rounded border border-[#20293d]">
                  <span className="text-slate-500 block text-[10px]">Untrusted Code Execution:</span>
                  <span className={`font-bold ${capabilities.secure_untrusted_execution === true ? 'text-emerald-400' : 'text-red-400'}`}>
                    {capabilities.secure_untrusted_execution === true ? 'ALLOWED (SECURE)' : 'BLOCKED / UNSAFE'}
                  </span>
                </div>
              </div>

              <p className="text-[11px] text-slate-400 italic border-l-2 border-[#2b3952] pl-2">
                Configured capabilities indicate backend policy profile, not standalone runtime proof of containment.
              </p>
            </div>
          ) : (
            <div className="p-3 bg-[#131822] rounded text-xs text-slate-400 border border-[#20293d]">
              <span className="font-semibold block mb-0.5 text-slate-300">Capability Information Unavailable</span>
              <p className="text-[11px] text-slate-500">
                Sandbox capability profile was not recorded in the structured observation for this run.
              </p>
            </div>
          )}
        </div>

        {/* Evidence Hashes */}
        {receipt.evidence_hashes && receipt.evidence_hashes.length > 0 && (
          <div className="border border-[#1e2638] p-4 rounded bg-[#10141e]">
            <h3 className="font-bold text-slate-200 mb-2 text-sm">Evidence Hashes ({receipt.evidence_hashes.length})</h3>
            <ul className="space-y-1 font-mono text-xs max-h-40 overflow-y-auto" role="list">
              {receipt.evidence_hashes.map((hash, idx) => (
                <li key={idx} className="bg-[#090d14] p-1.5 rounded border border-[#20293d] text-slate-300">
                  <span className="break-all select-all">{hash}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
      
      {/* Disclaimer Footer */}
      <div className="mt-6 text-[11px] text-slate-500 text-center border-t border-[#1e2638] pt-4 space-y-1">
        <p className="font-semibold text-slate-400">REDLINE DETERMINISTIC EVIDENCE RECEIPT</p>
        <p>
          Receipt retrieved from backend. Cryptographic hashes reflect backend recordings.
          Frontend is a presentation surface and does not independently authenticate Merkle root.
        </p>
      </div>
    </div>
  );
};

