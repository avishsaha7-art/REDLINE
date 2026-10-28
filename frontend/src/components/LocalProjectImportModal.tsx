"use client";

import React, { useState, useRef, ChangeEvent } from 'react';
import { apiClient } from '../api/client';
import { ProjectRecord, ProjectFileEntry } from '../models/types';

interface LocalProjectImportModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (project: ProjectRecord) => void;
}

export const LocalProjectImportModal: React.FC<LocalProjectImportModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
}) => {
  const [projectName, setProjectName] = useState<string>('');
  const [files, setFiles] = useState<ProjectFileEntry[]>([]);
  const [excludedCount, setExcludedCount] = useState<number>(0);
  const [isReadingFiles, setIsReadingFiles] = useState<boolean>(false);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  if (!isOpen) return null;

  // Filter rules matching backend LocalProjectImporter
  const isExcluded = (path: string): boolean => {
    const norm = path.replace(/\\/g, '/').toLowerCase();
    const parts = norm.split('/');
    const bannedDirs = ['.git', 'node_modules', 'venv', '.venv', '__pycache__', '.next', 'dist', 'build', '.idea', '.vscode'];
    if (parts.some(p => bannedDirs.includes(p))) return true;
    const filename = parts[parts.length - 1];
    if (filename.startsWith('.env') || filename === 'id_rsa' || filename === 'credentials.json') return true;
    const ext = filename.includes('.') ? filename.substring(filename.lastIndexOf('.')) : '';
    if (['.pem', '.key', '.exe', '.dll', '.pyc'].includes(ext)) return true;
    return false;
  };

  const handleDirectorySelect = async (e: ChangeEvent<HTMLInputElement>) => {
    setError(null);
    const selectedFiles = e.target.files;
    if (!selectedFiles || selectedFiles.length === 0) return;

    setIsReadingFiles(true);
    let excluded = 0;
    const accepted: ProjectFileEntry[] = [];

    // Extract directory name as default project name
    const firstRel = (selectedFiles[0] as unknown as { webkitRelativePath?: string }).webkitRelativePath || selectedFiles[0].name;
    const rootDirName = firstRel.includes('/') ? firstRel.split('/')[0] : 'Local Project';
    if (!projectName) {
      setProjectName(rootDirName);
    }

    try {
      for (let i = 0; i < selectedFiles.length; i++) {
        const file = selectedFiles[i];
        const relPath = (file as unknown as { webkitRelativePath?: string }).webkitRelativePath || file.name;

        // Strip top-level directory prefix if present
        const normalizedRel = relPath.includes('/') ? relPath.substring(relPath.indexOf('/') + 1) : relPath;

        if (isExcluded(relPath) || isExcluded(normalizedRel)) {
          excluded++;
          continue;
        }

        // Read text content (max 2MB per file)
        if (file.size <= 2 * 1024 * 1024) {
          try {
            const text = await file.text();
            accepted.push({
              path: normalizedRel,
              content: text,
              size_bytes: file.size,
            });
          } catch {
            // Binary or unreadable file: skip
            excluded++;
          }
        } else {
          excluded++;
        }
      }

      setFiles(accepted);
      setExcludedCount(excluded);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsReadingFiles(false);
    }
  };

  const loadDemoPreset = () => {
    setError(null);
    setProjectName('demo-auth-service');
    setExcludedCount(3);
    setFiles([
      {
        path: 'src/main.py',
        content: `"""
Authentication Microservice
Vulnerable to unvalidated input injection in login token parsing.
"""
import re

def parse_user_token(raw_token: str) -> dict:
    # BUG: No length check, whitespace check, or null byte guard
    parts = raw_token.split(":")
    return {"user_id": parts[0], "role": parts[1] if len(parts) > 1 else "guest"}

def verify_session(user_id: str) -> bool:
    if not user_id:
        return False
    return True
`,
        size_bytes: 380,
      },
      {
        path: 'tests/test_auth.py',
        content: `import pytest
from src.main import parse_user_token, verify_session

def test_valid_token():
    res = parse_user_token("alice:admin")
    assert res["user_id"] == "alice"
    assert res["role"] == "admin"

def test_missing_role_defaults_to_guest():
    res = parse_user_token("bob")
    assert res["user_id"] == "bob"
    assert res["role"] == "guest"

def test_empty_or_malformed_token():
    with pytest.raises(ValueError):
        parse_user_token("")
`,
        size_bytes: 410,
      },
      {
        path: 'requirements.txt',
        content: `pytest>=8.0.0\nfastapi>=0.110.0\nuvicorn>=0.28.0\n`,
        size_bytes: 42,
      },
      {
        path: 'README.md',
        content: `# Demo Auth Service\n\nSample project for REDLINE Stage 3 Workspace verification.\n`,
        size_bytes: 75,
      }
    ]);
  };

  const handleImportSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!projectName.trim()) {
      setError('Please provide a project name.');
      return;
    }
    if (files.length === 0) {
      setError('No valid source files selected. Please select a folder or load a preset.');
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const record = await apiClient.importLocalProject({
        name: projectName.trim(),
        files: files,
      });
      onSuccess(record);
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  const totalBytes = files.reduce((acc, f) => acc + (f.size_bytes || 0), 0);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
      <div
        role="dialog"
        aria-labelledby="import-modal-title"
        className="w-full max-w-2xl bg-[#0f1015] border border-[#222430] rounded-xl shadow-2xl flex flex-col max-h-[90vh] overflow-hidden"
      >
        {/* Modal Header */}
        <div className="px-6 py-4 border-b border-[#222430] flex items-center justify-between bg-[#13141b]">
          <div className="flex items-center gap-2.5">
            <span className="p-1.5 rounded-lg bg-[#ef4444]/10 text-[#ef4444] border border-[#ef4444]/20 text-base">
              📁
            </span>
            <div>
              <h2 id="import-modal-title" className="text-base font-bold text-white tracking-wide">
                Import Local Project Workspace
              </h2>
              <p className="text-xs text-[#a1a1aa]">
                Upload local source code into an isolated, fail-closed UNTRUSTED workspace.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-[#71717a] hover:text-white p-1 rounded transition-colors"
            aria-label="Close modal"
          >
            ✕
          </button>
        </div>

        {/* Modal Body */}
        <form onSubmit={handleImportSubmit} className="p-6 overflow-y-auto space-y-5 flex-1">
          {error && (
            <div role="alert" className="p-3 rounded-lg bg-[#ef4444]/10 border border-[#ef4444]/30 text-xs text-[#f87171] flex items-start gap-2.5">
              <span className="text-sm">⚠</span>
              <div className="flex-1">
                <strong>Import Error:</strong> {error}
              </div>
            </div>
          )}

          {/* Project Name Input */}
          <div>
            <label htmlFor="project-name-input" className="block text-xs font-mono font-medium text-[#a1a1aa] mb-1.5">
              Project Identifier / Name <span className="text-[#ef4444]">*</span>
            </label>
            <input
              id="project-name-input"
              type="text"
              value={projectName}
              onChange={(e) => setProjectName(e.target.value)}
              placeholder="e.g. customer-api-service"
              className="w-full px-3 py-2 text-xs font-mono bg-[#090a0d] border border-[#222430] rounded-lg text-white placeholder-[#52525b] focus:outline-none focus:border-[#ef4444] focus:ring-1 focus:ring-[#ef4444]"
              required
            />
          </div>

          {/* Selection Actions */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {/* Folder Picker */}
            <div className="p-4 rounded-lg bg-[#13141b] border border-[#222430] flex flex-col justify-between">
              <div>
                <span className="text-xs font-bold text-white block mb-1">Select Local Folder</span>
                <p className="text-[11px] text-[#71717a] leading-relaxed mb-3">
                  Upload an entire directory using your browser folder picker.
                </p>
              </div>
              <input
                ref={fileInputRef}
                type="file"
                // @ts-expect-error webkitdirectory is standard in Chromium/Firefox
                webkitdirectory=""
                directory=""
                multiple
                onChange={handleDirectorySelect}
                className="hidden"
                id="local-folder-picker"
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={isReadingFiles || isSubmitting}
                className="w-full py-2 px-3 text-xs font-bold bg-[#1e2029] hover:bg-[#282a36] text-white border border-[#2f3242] rounded-md transition-colors flex items-center justify-center gap-2"
              >
                <span>📂</span>
                <span>{isReadingFiles ? 'Scanning Files...' : 'Browse Computer...'}</span>
              </button>
            </div>

            {/* Demo Preset */}
            <div className="p-4 rounded-lg bg-[#13141b] border border-[#222430] flex flex-col justify-between">
              <div>
                <span className="text-xs font-bold text-white block mb-1">Quick Demo Preset</span>
                <p className="text-[11px] text-[#71717a] leading-relaxed mb-3">
                  Load a sample Python microservice with test cases and an input validation bug.
                </p>
              </div>
              <button
                type="button"
                onClick={loadDemoPreset}
                disabled={isReadingFiles || isSubmitting}
                className="w-full py-2 px-3 text-xs font-bold bg-[#ef4444]/15 hover:bg-[#ef4444]/25 text-[#ef4444] border border-[#ef4444]/30 rounded-md transition-colors flex items-center justify-center gap-2"
              >
                <span>⚡</span>
                <span>Load Sample Project</span>
              </button>
            </div>
          </div>

          {/* Staged Files Preview */}
          {files.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs font-mono">
                <span className="text-[#a1a1aa]">
                  Staged Files ({files.length}) &bull; {(totalBytes / 1024).toFixed(1)} KB
                </span>
                {excludedCount > 0 && (
                  <span className="text-amber-400 text-[11px]">
                    Excluded {excludedCount} sensitive/build files (.git, .env, build)
                  </span>
                )}
              </div>

              <div className="max-h-40 overflow-y-auto border border-[#222430] rounded-lg bg-[#090a0d] p-2 space-y-1 font-mono text-[11px]">
                {files.map((f, idx) => (
                  <div key={idx} className="flex items-center justify-between py-1 px-2 hover:bg-[#13141b] rounded text-[#d4d4d8]">
                    <span className="truncate max-w-[400px] text-white/90">📄 {f.path}</span>
                    <span className="text-[#71717a] shrink-0">{f.size_bytes} B</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Security Notice */}
          <div className="p-3 rounded-lg bg-[#181920] border border-[#222430] text-[11px] text-[#a1a1aa] flex items-start gap-2.5">
            <span className="text-[#f59e0b]">🛡️</span>
            <div>
              <strong className="text-white block font-sans">Authoritative Security Gate:</strong>
              Imported local projects are strictly assigned <code className="text-[#ef4444] font-mono">UNTRUSTED</code> trust tier.
              Host execution is blocked under local development backend policies, and all verified operations execute inside quarantined containment.
            </div>
          </div>

          {/* Modal Footer */}
          <div className="pt-2 flex items-center justify-end gap-3 border-t border-[#222430]">
            <button
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
              className="px-4 py-2 text-xs font-bold text-[#a1a1aa] hover:text-white transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting || files.length === 0 || !projectName.trim()}
              className="px-5 py-2 text-xs font-bold bg-[#ef4444] hover:bg-[#dc2626] disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg shadow-md transition-all flex items-center gap-2"
            >
              {isSubmitting ? (
                <>
                  <span className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
                  <span>Importing Workspace...</span>
                </>
              ) : (
                <>
                  <span>Import &amp; Quarantine Project</span>
                  <span>&rarr;</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
