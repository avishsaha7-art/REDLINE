"use client";

import React, { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { apiClient } from '../api/client';
import { RunHistoryItem } from '../models/types';

interface Props {
  onSelectRun?: (runId: string) => void;
  selectedRunId?: string;
  showLinks?: boolean;
}

export const RunHistory: React.FC<Props> = ({ onSelectRun, selectedRunId, showLinks = true }) => {
  const [history, setHistory] = useState<RunHistoryItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const refreshHistory = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await apiClient.getRunHistory();
      setHistory(data);
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    let ignore = false;
    apiClient.getRunHistory().then((data) => {
      if (!ignore) {
        setHistory(data);
        setIsLoading(false);
      }
    }).catch((err: unknown) => {
      if (!ignore) {
        setError(err instanceof Error ? err.message : String(err));
        setIsLoading(false);
      }
    });
    return () => {
      ignore = true;
    };
  }, []);

  return (
    <div className="run-history border border-[#222430] p-5 rounded bg-[#0d0e12] card-laser-border shadow-lg text-[#f4f4f5]" role="region" aria-label="Run History">
      <div className="flex justify-between items-center mb-4 border-b border-[#222430] pb-3">
        <div className="flex items-center gap-2">
          <h2 className="text-base font-bold text-[#f4f4f5] tracking-wide font-sans">Verification History</h2>
          <span className="text-xs font-mono bg-[#13141b] text-[#a1a1aa] px-2 py-0.5 rounded border border-[#222430]">
            {history.length} {history.length === 1 ? 'run' : 'runs'}
          </span>
        </div>
        <button
          type="button"
          onClick={refreshHistory}
          disabled={isLoading}
          className="text-xs text-[#a1a1aa] hover:text-[#f4f4f5] font-mono focus-visible:ring-2 focus-visible:ring-[#ef4444] rounded px-2.5 py-1 border border-[#222430] bg-[#13141b] hover:bg-[#1a1b24] transition-colors disabled:opacity-50"
        >
          {isLoading ? 'Refreshing...' : '↻ Refresh'}
        </button>
      </div>

      {isLoading && history.length === 0 ? (
        <div className="text-[#71717a] text-xs py-8 text-center font-mono" role="status">
          <span className="inline-block motion-safe:animate-spin mr-2">◷</span>
          Loading history from backend...
        </div>
      ) : error ? (
        <div className="bg-[#ef4444]/15 p-3 border border-[#ef4444]/30 rounded text-[#f87171] text-xs font-mono" role="alert">
          <strong className="block mb-0.5">Error Loading History:</strong>
          <span>{error}</span>
          <button 
            type="button" 
            onClick={refreshHistory} 
            className="block mt-2 text-[#fca5a5] underline font-semibold"
          >
            Retry
          </button>
        </div>
      ) : history.length === 0 ? (
        <div className="text-center py-8 text-[#71717a] text-xs bg-[#09090b] rounded border border-dashed border-[#222430]">
          <p className="font-semibold text-[#a1a1aa]">No verification runs recorded.</p>
          <p className="mt-1 font-mono text-[11px]">Submit a Task Contract above to initiate testing.</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <caption className="sr-only">List of past verification runs and their final verdicts</caption>
            <thead>
              <tr className="border-b border-[#222430] bg-[#09090b] font-semibold text-[#71717a] uppercase tracking-wider text-[10px] font-mono">
                <th scope="col" className="p-2.5">Run ID</th>
                <th scope="col" className="p-2.5">Task</th>
                <th scope="col" className="p-2.5">Final State</th>
                <th scope="col" className="p-2.5">Verdict</th>
                <th scope="col" className="p-2.5">Created</th>
                <th scope="col" className="p-2.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {history.map(run => {
                const isSelected = selectedRunId === run.run_id;
                const v = run.verdict;
                return (
                  <tr 
                    key={run.run_id} 
                    className={`border-b border-[#13141b] last:border-0 hover:bg-[#13141b] transition-colors ${
                      isSelected ? 'bg-[#ef4444]/10 border-[#ef4444]/30' : ''
                    }`}
                  >
                    <td className="p-2.5 font-mono font-bold text-[#f4f4f5]">
                      <span className="select-all text-[#ef4444]">{run.run_id}</span>
                    </td>
                    <td className="p-2.5 font-mono text-[#a1a1aa] truncate max-w-[130px]" title={run.task_id}>
                      {run.task_id}
                    </td>
                    <td className="p-2.5">
                      <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-mono font-bold border ${
                        run.final_state === 'VERIFIED' ? 'bg-[#10b981]/15 text-[#10b981] border-[#10b981]/30' :
                        run.final_state === 'ABORTED' ? 'bg-[#ef4444]/15 text-[#f87171] border-[#ef4444]/30' :
                        'bg-[#06b6d4]/15 text-[#06b6d4] border-[#06b6d4]/30'
                      }`}>
                        {run.final_state}
                      </span>
                    </td>
                    <td className="p-2.5 font-bold font-mono">
                      {v ? (
                        <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] border ${
                          v === 'VERIFIED' ? 'bg-[#10b981]/15 text-[#10b981] border-[#10b981]/30' :
                          v === 'REJECTED' ? 'bg-[#ef4444]/15 text-[#f87171] border-[#ef4444]/30' :
                          'bg-[#f59e0b]/15 text-[#fbbf24] border-[#f59e0b]/30'
                        }`}>
                          {v === 'VERIFIED' ? '✓ ' : v === 'REJECTED' ? '✕ ' : '⚠ '}
                          {v}
                        </span>
                      ) : (
                        <span className="text-[#71717a] font-normal">—</span>
                      )}
                    </td>
                    <td className="p-2.5 text-[#71717a] font-mono text-[11px] whitespace-nowrap">
                      {run.created_at ? new Date(run.created_at).toLocaleTimeString() : 'N/A'}
                    </td>
                    <td className="p-2.5 text-right whitespace-nowrap">
                      <div className="flex items-center justify-end gap-1.5">
                        <button
                          type="button"
                          onClick={() => onSelectRun && onSelectRun(run.run_id)}
                          className={`text-xs px-2.5 py-1 rounded font-medium focus-visible:ring-2 focus-visible:ring-[#ef4444] transition-colors font-mono ${
                            isSelected 
                              ? 'bg-[#ef4444] text-white' 
                              : 'bg-[#13141b] text-[#a1a1aa] hover:bg-[#1a1b24] hover:text-[#f4f4f5] border border-[#222430]'
                          }`}
                          aria-label={`Inspect run ${run.run_id}`}
                        >
                          {isSelected ? 'Viewing' : 'Inspect'}
                        </button>
                        {showLinks && (
                          <>
                            <Link
                              href={`/results?runId=${encodeURIComponent(run.run_id)}`}
                              className="text-[11px] text-[#71717a] hover:text-[#f4f4f5] px-1.5 py-1 rounded hover:bg-[#13141b] transition-colors font-mono"
                              title="View Verdict & Results"
                            >
                              Results
                            </Link>
                            <Link
                              href={`/evidence?runId=${encodeURIComponent(run.run_id)}`}
                              className="text-[11px] text-[#71717a] hover:text-[#f4f4f5] px-1.5 py-1 rounded hover:bg-[#13141b] transition-colors font-mono"
                              title="Audit Evidence & Diff"
                            >
                              Evidence
                            </Link>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
