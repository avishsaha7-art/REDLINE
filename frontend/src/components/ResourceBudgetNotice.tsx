import React from 'react';

interface ResourceBudgetNoticeProps {
  iterationsUsed?: number;
  iterationsLimit?: number;
  toolCallsUsed?: number;
  toolCallsLimit?: number;
  maxRuntime?: number;
  className?: string;
}

export const ResourceBudgetNotice: React.FC<ResourceBudgetNoticeProps> = ({
  iterationsUsed = 0,
  iterationsLimit = 20,
  toolCallsUsed = 0,
  toolCallsLimit = 100,
  maxRuntime = 3600,
  className = '',
}) => {
  return (
    <div 
      className={`border border-[#1e2638] rounded-md bg-[#0f141e] p-3 text-xs text-slate-300 ${className}`}
      role="status"
      aria-label="Authoritative Resource Budget Ceilings"
    >
      <div className="flex items-center justify-between mb-2 pb-1.5 border-b border-[#1e2638]">
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-red-500 inline-block" aria-hidden="true"></span>
          <span className="font-bold text-[11px] tracking-wider text-slate-300 uppercase">
            Effective Budget & System Ceilings
          </span>
        </div>
        <span className="text-[10px] font-mono text-red-400 bg-red-950/40 px-1.5 py-0.5 rounded border border-red-900/40">
          BACKEND ENFORCED
        </span>
      </div>

      <div className="grid grid-cols-3 gap-2 font-mono text-[11px] mb-2">
        <div className="bg-[#141a27] p-2 rounded border border-[#20293d]">
          <span className="text-slate-500 block text-[10px]">Iterations</span>
          <span className="font-bold text-slate-200">
            {iterationsUsed} / {iterationsLimit}
          </span>
          <span className="text-[9px] text-slate-500 block">(Max 50)</span>
        </div>
        <div className="bg-[#141a27] p-2 rounded border border-[#20293d]">
          <span className="text-slate-500 block text-[10px]">Tool Calls</span>
          <span className="font-bold text-slate-200">
            {toolCallsUsed} / {toolCallsLimit}
          </span>
          <span className="text-[9px] text-slate-500 block">(Max 100)</span>
        </div>
        <div className="bg-[#141a27] p-2 rounded border border-[#20293d]">
          <span className="text-slate-500 block text-[10px]">Wall Timeout</span>
          <span className="font-bold text-slate-200">{maxRuntime}s</span>
          <span className="text-[9px] text-slate-500 block">(Max 3600s)</span>
        </div>
      </div>

      <p className="text-[10px] text-slate-400 leading-relaxed">
        Backend resource governance caps client budgets to prevent runaway loops or unbounded execution.
      </p>
    </div>
  );
};
