"use client";

import React, { useState, useEffect, useCallback } from 'react';
import { apiClient, ApiError } from '../api/client';
import { RunDiff } from '../models/types';

interface DiffViewerProps {
  runId?: string;
  initialDiff?: RunDiff | null;
  className?: string;
}

export const DiffViewer: React.FC<DiffViewerProps> = ({ runId, initialDiff, className = '' }) => {
  const [fetchedDiff, setFetchedDiff] = useState<RunDiff | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(Boolean(initialDiff === undefined && runId));
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<boolean>(false);

  const diffData = initialDiff !== undefined ? initialDiff : fetchedDiff;

  const fetchDiff = useCallback(async (targetRunId: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await apiClient.getRunDiff(targetRunId);
      setFetchedDiff(data);
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 404) {
        setError("Patch diff not yet available for this run (no patch candidate generated or run aborted prior to BUILD).");
      } else {
        setError(err instanceof Error ? err.message : String(err));
      }
      setFetchedDiff(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (initialDiff !== undefined || !runId) {
      return;
    }
    let ignore = false;
    apiClient.getRunDiff(runId).then((data) => {
      if (!ignore) {
        setFetchedDiff(data);
        setError(null);
        setIsLoading(false);
      }
    }).catch((err: unknown) => {
      if (!ignore) {
        if (err instanceof ApiError && err.status === 404) {
          setError("Patch diff not yet available for this run (no patch candidate generated or run aborted prior to BUILD).");
        } else {
          setError(err instanceof Error ? err.message : String(err));
        }
        setFetchedDiff(null);
        setIsLoading(false);
      }
    });
    return () => {
      ignore = true;
    };
  }, [runId, initialDiff]);

  const copyDiff = () => {
    if (!diffData?.diff) return;
    if (typeof navigator !== 'undefined' && navigator.clipboard) {
      navigator.clipboard.writeText(diffData.diff).catch(() => {});
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const renderDiffLines = (diffText: string) => {
    const lines = diffText.split('\n');
    return (
      <pre className="font-mono text-xs leading-5 overflow-x-auto p-4 bg-[#07090e] rounded-b border-t border-[#1e2638] text-slate-200 select-text">
        <code>
          {lines.map((line, idx) => {
            let lineClass = "text-slate-400";
            let bgClass = "";
            let marker = " ";

            if (line.startsWith('+') && !line.startsWith('+++')) {
              lineClass = "text-emerald-300";
              bgClass = "bg-emerald-950/30 border-l-2 border-emerald-500 pl-2 -ml-2";
              marker = "+";
            } else if (line.startsWith('-') && !line.startsWith('---')) {
              lineClass = "text-red-300";
              bgClass = "bg-red-950/30 border-l-2 border-red-500 pl-2 -ml-2";
              marker = "-";
            } else if (line.startsWith('@@')) {
              lineClass = "text-cyan-400 font-bold bg-cyan-950/20";
              marker = "@";
            } else if (line.startsWith('diff --git') || line.startsWith('index ')) {
              lineClass = "text-slate-500 font-semibold";
            }

            return (
              <div 
                key={idx} 
                className={`py-0.5 px-1 rounded-sm flex items-start ${bgClass} hover:bg-slate-800/40 transition-colors`}
              >
                <span className="w-10 select-none text-slate-600 text-right pr-3 font-mono text-[10px]">
                  {idx + 1}
                </span>
                <span className="w-4 select-none text-slate-500 text-center font-bold">
                  {marker !== " " ? marker : ""}
                </span>
                <span className={`flex-1 break-all whitespace-pre-wrap ${lineClass}`}>
                  {line}
                </span>
              </div>
            );
          })}
        </code>
      </pre>
    );
  };

  return (
    <div 
      className={`border border-[#1e2638] rounded-lg bg-[#0d1117] shadow-lg overflow-hidden ${className}`}
      role="region" 
      aria-label="Patch Diff Viewer"
    >
      {/* Header bar */}
      <div className="p-4 bg-[#131822] border-b border-[#1e2638] flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-red-500 font-black text-sm tracking-wide">PATCH DIFF</span>
          {diffData?.patch_id && (
            <span className="text-xs font-mono bg-[#1a2233] text-slate-300 px-2 py-0.5 rounded border border-[#26334d]">
              ID: {diffData.patch_id}
            </span>
          )}
          {runId && (
            <span className="text-xs font-mono text-slate-400">
              Run: {runId}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {diffData?.diff && (
            <button
              type="button"
              onClick={copyDiff}
              className="text-xs bg-[#1a2233] hover:bg-[#253047] text-slate-200 px-3 py-1.5 rounded border border-[#26334d] font-mono transition-colors focus-visible:ring-2 focus-visible:ring-red-500 focus-visible:outline-none"
              aria-label="Copy patch diff to clipboard"
            >
              {copied ? '✓ Copied' : 'Copy Raw Diff'}
            </button>
          )}
          {runId && (
            <button
              type="button"
              onClick={() => fetchDiff(runId)}
              disabled={isLoading}
              className="text-xs text-slate-400 hover:text-slate-200 px-2 py-1 rounded border border-[#1e2638] hover:border-[#2e3b56] transition-colors disabled:opacity-50 focus-visible:ring-2 focus-visible:ring-red-500 focus-visible:outline-none"
              aria-label="Reload patch diff"
            >
              {isLoading ? 'Loading...' : '↻'}
            </button>
          )}
        </div>
      </div>

      {/* Security Advisory Notice */}
      <div className="bg-[#141217] border-b border-red-950/60 px-4 py-2 flex items-center gap-2 text-[11px] text-red-400">
        <span aria-hidden="true" className="font-bold">⚠️</span>
        <span>
          <strong>CODE AUDIT ADVISORY:</strong> Inspecting a diff is for human review only and does NOT prove code safety. Deterministic adversarial verification remains authoritative.
        </span>
      </div>

      {/* Changed files summary */}
      {diffData?.changed_files && diffData.changed_files.length > 0 && (
        <div className="px-4 py-2.5 bg-[#0f141e] border-b border-[#1e2638] text-xs flex flex-wrap items-center gap-2">
          <span className="text-slate-400 font-semibold">Modified Files ({diffData.changed_files.length}):</span>
          {diffData.changed_files.map((file, i) => (
            <span key={i} className="font-mono text-[11px] bg-[#1a2233] text-emerald-400 px-2 py-0.5 rounded border border-[#24334f]">
              {file}
            </span>
          ))}
        </div>
      )}

      {/* Content body */}
      {isLoading ? (
        <div className="p-8 text-center text-xs font-mono text-slate-400" role="status">
          <span className="inline-block motion-safe:animate-spin mr-2">◷</span>
          Fetching authoritative patch diff...
        </div>
      ) : error ? (
        <div className="p-6 text-center text-xs" role="alert">
          <p className="text-amber-400 font-mono mb-2">{error}</p>
          <p className="text-slate-500 text-[11px]">
            If this run is still active in an earlier stage (INIT, RECON, PLAN), the candidate patch has not yet been synthesized.
          </p>
        </div>
      ) : diffData?.diff ? (
        renderDiffLines(diffData.diff)
      ) : (
        <div className="p-8 text-center text-xs text-slate-500 bg-[#07090e]">
          <p className="font-semibold text-slate-400">No patch candidate diff available.</p>
          <p className="mt-1 text-[11px]">Select a completed verification run to inspect synthesized patches and lineage.</p>
        </div>
      )}
    </div>
  );
};
