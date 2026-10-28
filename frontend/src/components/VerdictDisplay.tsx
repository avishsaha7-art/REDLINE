import React from 'react';

interface Props {
  verdict: string | null;
  error?: string | null;
  lifecycleState?: string | null;
}

export type VerdictDisplayMode = 'OPERATIONAL_FAILURE' | 'VERDICT_PENDING' | 'DETERMINISTIC_VERDICT';

export function getVerdictDisplayMode(verdict: string | null, error?: string | null): VerdictDisplayMode {
  if (error) return 'OPERATIONAL_FAILURE';
  if (!verdict) return 'VERDICT_PENDING';
  return 'DETERMINISTIC_VERDICT';
}

export interface VerdictVisualProps {
  bgClass: string;
  textClass: string;
  icon: string;
  isStateMismatch: boolean;
}

export function getVerdictVisuals(verdict: string | null, lifecycleState?: string | null): VerdictVisualProps {
  const isVerified = verdict === 'VERIFIED';
  const isRejected = verdict === 'REJECTED';
  const isInconclusive = verdict === 'INCONCLUSIVE';
  
  let bgClass = 'bg-amber-950/40 border-amber-500/80';
  let textClass = 'text-amber-300';
  let icon = '⚠';

  if (isVerified) {
    bgClass = 'bg-emerald-950/40 border-emerald-500/80';
    textClass = 'text-emerald-300';
    icon = '✓';
  } else if (isRejected) {
    bgClass = 'bg-red-950/40 border-red-500/80';
    textClass = 'text-red-300';
    icon = '✕';
  } else if (isInconclusive) {
    bgClass = 'bg-amber-950/40 border-amber-500/80';
    textClass = 'text-amber-300';
    icon = '⚠';
  } else if (verdict === 'POLICY_BLOCKED') {
    bgClass = 'bg-rose-950/50 border-rose-600/90';
    textClass = 'text-rose-300';
    icon = '🛡️';
  } else if (verdict === 'TIMEOUT') {
    bgClass = 'bg-orange-950/50 border-orange-600/90';
    textClass = 'text-orange-300';
    icon = '⏱️';
  } else if (verdict === 'RESOURCE_LIMIT') {
    bgClass = 'bg-purple-950/50 border-purple-600/90';
    textClass = 'text-purple-300';
    icon = '🛑';
  } else if (verdict === 'SANDBOX_FAILURE' || verdict === 'EXECUTION_FAILURE') {
    bgClass = 'bg-red-950/60 border-red-700';
    textClass = 'text-red-300';
    icon = '⛔';
  }

  // Detect state vs verdict mismatch (technical debt handling)
  const isStateMismatch = lifecycleState === 'VERIFIED' && isInconclusive;

  return {
    bgClass,
    textClass,
    icon,
    isStateMismatch,
  };
}

export const VerdictDisplay: React.FC<Props> = ({ verdict, error, lifecycleState }) => {
  const mode = getVerdictDisplayMode(verdict, error);

  if (mode === 'OPERATIONAL_FAILURE') {
    return (
      <div 
        className="verdict-display bg-[#180e12] border-2 border-red-700 p-6 rounded-md mt-4 text-center shadow-lg"
        role="alert"
        aria-live="assertive"
      >
        <h2 className="text-xs uppercase tracking-widest text-red-400 font-bold block mb-1">
          Execution Environment
        </h2>
        <h3 className="text-2xl font-black text-red-300 flex items-center justify-center gap-2">
          <span aria-hidden="true">⛔</span>
          <span>OPERATIONAL FAILURE</span>
        </h3>
        <p className="text-red-200 font-mono text-xs mt-3 bg-[#241014] p-3 rounded border border-red-900/60 break-all select-all">
          {error}
        </p>
        <p className="text-[11px] text-red-400 mt-2">
          Operational failures represent execution environment or policy aborts, not deterministic code rejection.
        </p>
      </div>
    );
  }

  if (mode === 'VERDICT_PENDING') {
    return (
      <div 
        className="verdict-display bg-[#0d1117] border-2 border-[#1e2638] p-6 rounded-md mt-4 text-center shadow-md"
        role="status"
        aria-live="polite"
      >
        <h2 className="text-xs uppercase tracking-widest text-slate-500 font-semibold block mb-1">
          Deterministic Verification
        </h2>
        <h3 className="text-2xl font-bold text-slate-400 flex items-center justify-center gap-2">
          <span aria-hidden="true">⏳</span>
          <span>VERDICT PENDING</span>
        </h3>
        <p className="text-slate-500 text-xs mt-2">Waiting for deterministic verification to complete...</p>
      </div>
    );
  }

  const { bgClass, textClass, icon, isStateMismatch } = getVerdictVisuals(verdict, lifecycleState);

  return (
    <div 
      className={`verdict-display border-2 p-6 rounded-md mt-4 text-center shadow-md ${bgClass}`}
      role="status"
      aria-live="polite"
    >
      <h2 className="text-xs uppercase tracking-widest text-slate-400 mb-1 font-semibold">
        Authoritative Deterministic Verdict
      </h2>
      <h3 className={`text-4xl font-black tracking-tight flex items-center justify-center gap-3 ${textClass}`}>
        <span aria-hidden="true">{icon}</span>
        <span>{verdict}</span>
      </h3>

      {isStateMismatch && (
        <div className="mt-4 p-3 bg-amber-950/60 text-amber-200 border border-amber-800 rounded text-xs text-left">
          <strong className="block font-bold mb-0.5 text-amber-300">⚠️ Technical Notice (State/Verdict Separation):</strong>
          <span>
            Pipeline lifecycle state reached <code>VERIFIED</code>, but authoritative verification concluded <code>INCONCLUSIVE</code>. 
            Code soundness is NOT certified. Deterministic verdict remains authoritative.
          </span>
        </div>
      )}

      {verdict === 'POLICY_BLOCKED' && (
        <div className="mt-4 p-3 bg-rose-950/60 text-rose-200 border border-rose-800 rounded text-xs text-left">
          <strong className="block font-bold mb-0.5 text-rose-300">🛡️ Policy Blocked Notice:</strong>
          <span>
            Untrusted code execution was safely halted by the backend sandbox policy. Remote and untrusted workloads cannot execute on host development backends.
          </span>
        </div>
      )}
    </div>
  );
};

