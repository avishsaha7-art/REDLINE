import React from 'react';
import { JudgeExplanation } from '../models/types';

interface Props {
  explanation: JudgeExplanation | null;
}

export const JudgeExplanationView: React.FC<Props> = ({ explanation }) => {
  if (!explanation) {
    return null;
  }

  return (
    <div 
      className="judge-explanation-view border border-[#1e2638] p-5 rounded-md mt-4 bg-[#0d1117] shadow-lg text-slate-200"
      role="region"
      aria-label="Judge Explanation (Advisory)"
    >
      <div className="flex flex-wrap justify-between items-center gap-2 mb-3 border-b border-[#1e2638] pb-3">
        <div className="flex items-center gap-2">
          <h3 className="text-base font-bold text-white">JUDGE EXPLANATION</h3>
          <span className="bg-[#18202f] text-slate-300 border border-[#2b3952] text-xs px-2 py-0.5 rounded font-bold uppercase tracking-wider">
            Non-Authoritative Advisory
          </span>
        </div>
        
        {explanation.confidence && (
          <div className="text-xs font-mono text-slate-400 bg-[#131822] border border-[#20293d] px-2 py-0.5 rounded">
            Model Confidence: <span className="font-bold text-slate-200">{explanation.confidence}</span>
          </div>
        )}
      </div>
      
      <p className="text-xs text-slate-400 italic mb-4 border-l-4 border-slate-600 pl-3 py-1 bg-[#131822]">
        The Judge explains the evidence; it does NOT determine the verdict. 
        If this explanation conflicts with the deterministic verdict, the deterministic verdict remains authoritative.
      </p>

      <div className="space-y-4 text-sm">
        <div className="bg-[#131822] p-3 rounded border border-[#20293d]">
          <h4 className="font-bold text-xs uppercase tracking-wide text-slate-400 mb-1">Executive Summary</h4>
          <p className="text-slate-200 text-xs leading-relaxed">{explanation.summary}</p>
        </div>

        {explanation.verified_claims && explanation.verified_claims.length > 0 && (
          <div className="bg-[#131822] p-3 rounded border border-[#20293d]">
            <h4 className="font-bold text-xs uppercase tracking-wide text-emerald-400 mb-2 flex items-center gap-1.5">
              <span aria-hidden="true">✓</span>
              <span>Verified Claims ({explanation.verified_claims.length})</span>
            </h4>
            <ul className="list-disc pl-5 text-xs space-y-1 text-slate-300" role="list">
              {explanation.verified_claims.map((claim, idx) => (
                <li key={idx}>{claim}</li>
              ))}
            </ul>
          </div>
        )}

        {explanation.failed_claims && explanation.failed_claims.length > 0 && (
          <div className="bg-[#131822] p-3 rounded border border-[#20293d]">
            <h4 className="font-bold text-xs uppercase tracking-wide text-red-400 mb-2 flex items-center gap-1.5">
              <span aria-hidden="true">✕</span>
              <span>Failed Claims / Violations ({explanation.failed_claims.length})</span>
            </h4>
            <ul className="list-disc pl-5 text-xs space-y-1 text-slate-300" role="list">
              {explanation.failed_claims.map((claim, idx) => (
                <li key={idx}>{claim}</li>
              ))}
            </ul>
          </div>
        )}

        {explanation.evidence_references && explanation.evidence_references.length > 0 && (
          <div className="bg-[#131822] p-3 rounded border border-[#20293d]">
            <h4 className="font-bold text-xs uppercase tracking-wide text-slate-400 mb-1">Evidence References</h4>
            <ul className="list-disc pl-5 font-mono text-xs text-slate-400 space-y-0.5" role="list">
              {explanation.evidence_references.map((ref, idx) => (
                <li key={idx} className="break-all">{ref}</li>
              ))}
            </ul>
          </div>
        )}

        {explanation.limitations && (
          <div className="bg-[#131822] p-3 rounded border border-[#20293d]">
            <h4 className="font-bold text-xs uppercase tracking-wide text-amber-400 mb-1">Scope Limitations</h4>
            <p className="text-slate-300 text-xs leading-relaxed">{explanation.limitations}</p>
          </div>
        )}
      </div>
    </div>
  );
};

