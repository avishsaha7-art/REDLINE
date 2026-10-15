import React from 'react';
import { RunStatus, RunState } from '../models/types';

interface Props {
  status: RunStatus | null;
}

export const LIFECYCLE_STAGES: RunState[] = [
  'INIT',
  'RECON',
  'PLAN',
  'BASELINE',
  'BUILD',
  'TEST',
  'ATTACK',
  'ANALYZE',
  'REPAIR',
  'VERIFY',
  'JUDGE',
  'VERIFIED',
  'ABORTED'
];

export interface StageVisuals {
  containerClass: string;
  dotClass: string;
  badgeText: string;
  icon: string;
}

export function computeStageVisuals(
  stage: RunState,
  currentState: RunState,
  currentIndex: number,
  stageIndex: number,
  isAborted: boolean
): StageVisuals {
  const isCurrent = currentState === stage;
  const isPast = !isAborted && currentIndex >= 0 && stageIndex < currentIndex;
  
  let containerClass = "text-gray-400 bg-transparent";
  let dotClass = "bg-gray-300";
  let badgeText = "[Pending]";
  let icon = "○";

  if (isCurrent) {
    if (stage === 'ABORTED') {
      containerClass = "text-red-700 font-bold bg-red-50 border border-red-200 p-1.5 rounded";
      dotClass = "bg-red-600";
      badgeText = "[Aborted]";
      icon = "✕";
    } else if (stage === 'VERIFIED') {
      containerClass = "text-emerald-700 font-bold bg-emerald-50 border border-emerald-200 p-1.5 rounded";
      dotClass = "bg-emerald-600";
      badgeText = "[Completed]";
      icon = "✓";
    } else {
      containerClass = "text-blue-700 font-bold bg-blue-50 border border-blue-200 p-1.5 rounded motion-safe:animate-pulse";
      dotClass = "bg-blue-600";
      badgeText = "[Active]";
      icon = "●";
    }
  } else if (isPast && stage !== 'ABORTED' && stage !== 'VERIFIED') {
    containerClass = "text-emerald-700 font-medium";
    dotClass = "bg-emerald-600";
    badgeText = "[Done]";
    icon = "✓";
  } else if (isAborted && stage !== 'ABORTED') {
    containerClass = "text-gray-400";
    dotClass = "bg-gray-200";
    badgeText = "[Halted]";
    icon = "—";
  }

  return { containerClass, dotClass, badgeText, icon };
}

export const OrchestrationVisualizer: React.FC<Props> = ({ status }) => {
  if (!status) {
    return (
      <div className="orchestration-visualizer border border-[#1e2638] p-5 rounded-lg mt-4 bg-[#0d1117] shadow-lg text-slate-200" role="region" aria-label="Lifecycle Monitor">
        <h3 className="text-base font-bold text-white mb-2 tracking-wide">Run Lifecycle Visualization</h3>
        <p className="text-slate-500 text-xs font-mono">Awaiting run status from backend...</p>
      </div>
    );
  }

  const currentIndex = LIFECYCLE_STAGES.indexOf(status.state);
  const isAborted = status.state === 'ABORTED';
  const isCompleted = status.state === 'VERIFIED';

  return (
    <div className="orchestration-visualizer border border-[#1e2638] p-5 rounded-lg mt-4 bg-[#0d1117] shadow-lg text-slate-200" role="region" aria-label="Lifecycle Monitor">
      <div className="flex justify-between items-center mb-4 border-b border-[#1e2638] pb-3">
        <div>
          <h3 className="text-base font-bold text-white tracking-wide">Run Lifecycle Visualization</h3>
          <p className="text-[11px] text-slate-400 mt-0.5">Authoritative state machine transitions</p>
        </div>
        <span className={`text-xs uppercase font-mono font-bold px-2 py-1 rounded border ${
          isAborted ? 'bg-red-950/60 text-red-300 border-red-800' :
          isCompleted ? 'bg-emerald-950/60 text-emerald-300 border-emerald-800' :
          'bg-blue-950/60 text-blue-300 border-blue-800'
        }`}>
          State: {status.state}
        </span>
      </div>

      <div className="flex flex-col gap-1.5" role="list" aria-label="Lifecycle stages">
        {LIFECYCLE_STAGES.map((stage, idx) => {
          const isCurrent = status.state === stage;
          const { containerClass, dotClass, badgeText, icon } = computeStageVisuals(
            stage,
            status.state,
            currentIndex,
            idx,
            isAborted
          );

          return (
            <div 
              key={stage} 
              role="listitem"
              aria-current={isCurrent ? 'step' : undefined}
              className={`flex items-center justify-between text-xs transition-colors p-1.5 rounded ${containerClass}`}
            >
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs w-4 text-center" aria-hidden="true">{icon}</span>
                <div className={`w-2.5 h-2.5 rounded-full ${dotClass}`} aria-hidden="true" />
                <span className="tracking-wide font-mono text-xs">{stage}</span>
              </div>
              <span className="text-[10px] font-mono opacity-80" aria-label={`Status: ${badgeText}`}>
                {badgeText}
              </span>
            </div>
          );
        })}
      </div>
      
      <div className="mt-4 pt-3 border-t border-[#1e2638] text-xs space-y-1 font-mono">
        <p><strong className="font-sans text-slate-400">Run ID:</strong> <span className="select-all text-red-400">{status.run_id}</span></p>
        <p><strong className="font-sans text-slate-400">Task ID:</strong> <span className="text-slate-300">{status.task_id}</span></p>
        <p><strong className="font-sans text-slate-400">Iteration:</strong> <span className="text-slate-300">{status.iteration} / {status.resource_status?.iterations_limit ?? 'N/A'}</span></p>
        {status.started_at && <p><strong className="font-sans text-slate-400">Started:</strong> <span className="text-slate-400">{status.started_at}</span></p>}
        {status.updated_at && <p><strong className="font-sans text-slate-400">Updated:</strong> <span className="text-slate-400">{status.updated_at}</span></p>}
        {status.operational_error && (
          <div className="text-red-300 bg-red-950/40 border border-red-800 p-2.5 rounded mt-2 font-sans">
            <strong className="block text-xs uppercase tracking-wide text-red-400">Operational Failure Notice:</strong>
            <span className="font-mono text-xs break-all">{status.operational_error}</span>
          </div>
        )}
      </div>
    </div>
  );
};

