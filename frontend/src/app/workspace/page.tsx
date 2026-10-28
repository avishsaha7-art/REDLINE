"use client";

import React, { useState, useEffect, useRef, useMemo, Suspense } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { apiClient } from '@/api/client';
import {
  ProjectRecord,
  ProjectFileEntry,
  ConversationRecord,
  MessageRecord,
  ProposalRecord,
  ProjectFileContentResponse,
  RunStatus,
} from '@/models/types';
import { LocalProjectImportModal } from '@/components/LocalProjectImportModal';
import { DiffViewer } from '@/components/DiffViewer';

function WorkspaceContent() {
  const searchParams = useSearchParams();
  const queryProjectId = searchParams.get('projectId');

  // Core Workspace State
  const [projects, setProjects] = useState<ProjectRecord[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(queryProjectId);
  const [files, setFiles] = useState<ProjectFileEntry[]>([]);
  const [selectedFile, setSelectedFile] = useState<ProjectFileContentResponse | null>(null);
  const [fileFilter, setFileFilter] = useState<string>('');

  // Conversation State
  const [conversations, setConversations] = useState<ConversationRecord[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<MessageRecord[]>([]);
  const [inputPrompt, setInputPrompt] = useState<string>('');
  const [isSending, setIsSending] = useState<boolean>(false);
  const [chatError, setChatError] = useState<string | null>(null);

  // Mention State
  const [showMentionPopup, setShowMentionPopup] = useState<boolean>(false);
  const [mentionQuery, setMentionQuery] = useState<string>('');
  const [activeContextFiles, setActiveContextFiles] = useState<string[]>([]);

  // Proposals & Verification State
  const [activeProposal, setActiveProposal] = useState<ProposalRecord | null>(null);
  const [activeTab, setActiveTab] = useState<'diff' | 'verification' | 'file'>('diff');
  const [isApplyingProposal, setIsApplyingProposal] = useState<boolean>(false);
  const [proposalActionMessage, setProposalActionMessage] = useState<string | null>(null);

  // Verification Run State
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [runStatus, setRunStatus] = useState<RunStatus | null>(null);
  const [isVerifying, setIsVerifying] = useState<boolean>(false);

  // Modal State
  const [isImportModalOpen, setIsImportModalOpen] = useState<boolean>(false);

  // Refs
  const messageEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // 1. Initial Load of Projects
  useEffect(() => {
    let ignore = false;
    apiClient.listProjects().then((projs) => {
      if (!ignore) {
        setProjects(projs);
        if (projs.length > 0 && !selectedProjectId) {
          setSelectedProjectId(queryProjectId || projs[0].project_id);
        }
      }
    }).catch(() => {});
    return () => { ignore = true; };
  }, [queryProjectId]);

  // 2. Load Project Details & Files on Project Change
  useEffect(() => {
    if (!selectedProjectId) return;
    let ignore = false;

    // Fetch files
    apiClient.listProjectFiles(selectedProjectId).then((flist) => {
      if (!ignore) setFiles(flist);
    }).catch(() => {});

    // Fetch conversations
    apiClient.listConversations(selectedProjectId).then((convs) => {
      if (!ignore) {
        setConversations(convs);
        if (convs.length > 0) {
          setActiveConversationId(convs[0].conversation_id);
        } else {
          // Auto create initial conversation
          apiClient.createConversation(selectedProjectId, "Workspace Chat").then((newConv) => {
            if (!ignore) {
              setConversations([newConv]);
              setActiveConversationId(newConv.conversation_id);
            }
          }).catch(() => {});
        }
      }
    }).catch(() => {});

    // Fetch proposals
    apiClient.listProposals(selectedProjectId).then((props) => {
      if (!ignore && props.length > 0) {
        const pending = props.find(p => p.status === 'PENDING') || props[0];
        setActiveProposal(pending);
      }
    }).catch(() => {});

    return () => { ignore = true; };
  }, [selectedProjectId]);

  // 3. Load Messages on Conversation Change
  useEffect(() => {
    if (!selectedProjectId || !activeConversationId) return;
    let ignore = false;
    apiClient.listMessages(selectedProjectId, activeConversationId).then((msgs) => {
      if (!ignore) {
        setMessages(msgs);
        setTimeout(() => messageEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 50);
      }
    }).catch(() => {});
    return () => { ignore = true; };
  }, [selectedProjectId, activeConversationId]);

  // 4. Poll Active Run Status
  useEffect(() => {
    if (!activeRunId) return;
    let ignore = false;
    const interval = setInterval(async () => {
      try {
        const status = await apiClient.getRunStatus(activeRunId);
        if (!ignore) {
          setRunStatus(status);
          if (['VERIFIED', 'ABORTED', 'COMPLETED', 'FAILED'].includes(status.state)) {
            clearInterval(interval);
            setIsVerifying(false);
          }
        }
      } catch {
        clearInterval(interval);
      }
    }, 1500);
    return () => {
      ignore = true;
      clearInterval(interval);
    };
  }, [activeRunId]);

  const activeProject = useMemo(() => {
    return projects.find(p => p.project_id === selectedProjectId) || null;
  }, [projects, selectedProjectId]);

  // Filtered files for tree
  const filteredFiles = useMemo(() => {
    if (!fileFilter.trim()) return files;
    const q = fileFilter.toLowerCase();
    return files.filter(f => f.path.toLowerCase().includes(q));
  }, [files, fileFilter]);

  // Autocomplete file matches
  const mentionMatches = useMemo(() => {
    if (!mentionQuery) return files.slice(0, 8);
    const q = mentionQuery.toLowerCase();
    return files.filter(f => f.path.toLowerCase().includes(q)).slice(0, 8);
  }, [files, mentionQuery]);

  // Handle Input Changes & Mention Trigger
  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const text = e.target.value;
    setInputPrompt(text);

    // Detect if cursor is preceded by @...
    const cursor = e.target.selectionStart;
    const prefix = text.slice(0, cursor);
    const match = prefix.match(/@([\w\.\-\/]*)$/);

    if (match) {
      setShowMentionPopup(true);
      setMentionQuery(match[1]);
    } else {
      setShowMentionPopup(false);
    }
  };

  const insertMention = (filepath: string) => {
    if (!textareaRef.current) return;
    const cursor = textareaRef.current.selectionStart;
    const prefix = inputPrompt.slice(0, cursor);
    const suffix = inputPrompt.slice(cursor);
    const atIndex = prefix.lastIndexOf('@');

    const newText = prefix.slice(0, atIndex) + `@${filepath} ` + suffix;
    setInputPrompt(newText);
    setShowMentionPopup(false);

    if (!activeContextFiles.includes(filepath)) {
      setActiveContextFiles([...activeContextFiles, filepath]);
    }

    setTimeout(() => textareaRef.current?.focus(), 10);
  };

  const removeContextFile = (filepath: string) => {
    setActiveContextFiles(activeContextFiles.filter(f => f !== filepath));
  };

  // Send Message Action
  const handleSendMessage = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!inputPrompt.trim() || !selectedProjectId || !activeConversationId || isSending) return;

    setIsSending(true);
    setChatError(null);

    const userText = inputPrompt;
    setInputPrompt('');
    setShowMentionPopup(false);

    // Optimistically show user message
    const tempUserMsg: MessageRecord = {
      message_id: `temp-${Date.now()}`,
      conversation_id: activeConversationId,
      role: 'user',
      content: userText,
      mentioned_files: activeContextFiles,
      timestamp: new Date().toISOString(),
    };
    setMessages(prev => [...prev, tempUserMsg]);
    setTimeout(() => messageEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 50);

    try {
      const resp = await apiClient.sendMessage(
        selectedProjectId,
        activeConversationId,
        userText,
        activeContextFiles
      );

      // Append assistant message
      const asstMsg: MessageRecord = {
        message_id: resp.message_id,
        conversation_id: resp.conversation_id,
        role: 'assistant',
        content: resp.content,
        mentioned_files: resp.mentioned_files,
        proposal_id: resp.proposal?.proposal_id,
        timestamp: new Date().toISOString(),
      };
      setMessages(prev => [...prev.filter(m => m.message_id !== tempUserMsg.message_id), tempUserMsg, asstMsg]);

      // If a code proposal was returned, open and focus diff tab
      if (resp.proposal) {
        setActiveProposal(resp.proposal);
        setActiveTab('diff');
        setProposalActionMessage('AI generated a change proposal. Review the unified diff below.');
      }

      setTimeout(() => messageEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 50);
    } catch (err: unknown) {
      setChatError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsSending(false);
    }
  };

  // Inspect File Content
  const handleFileSelect = async (path: string) => {
    if (!selectedProjectId) return;
    try {
      const fileData = await apiClient.getProjectFileContent(selectedProjectId, path);
      setSelectedFile(fileData);
      setActiveTab('file');
    } catch (err) {
      console.error(err);
    }
  };

  // Apply Proposal Action
  const handleApplyProposal = async () => {
    if (!selectedProjectId || !activeProposal || isApplyingProposal) return;
    setIsApplyingProposal(true);
    try {
      const updated = await apiClient.applyProposal(selectedProjectId, activeProposal.proposal_id);
      setActiveProposal(updated);
      setProposalActionMessage('✓ Change proposal successfully applied to project workspace.');
      // Refresh files and project metadata
      const flist = await apiClient.listProjectFiles(selectedProjectId);
      setFiles(flist);
      const proj = await apiClient.getProject(selectedProjectId);
      setProjects(prev => prev.map(p => p.project_id === proj.project_id ? proj : p));
      if (selectedFile) {
        try {
          const reloaded = await apiClient.getProjectFileContent(selectedProjectId, selectedFile.path);
          setSelectedFile(reloaded);
        } catch {
          // keep previous if missing
        }
      }
    } catch (err: unknown) {
      setProposalActionMessage(`Error applying proposal: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setIsApplyingProposal(false);
    }
  };

  // Reject Proposal Action
  const handleRejectProposal = async () => {
    if (!selectedProjectId || !activeProposal || isApplyingProposal) return;
    setIsApplyingProposal(true);
    try {
      const updated = await apiClient.rejectProposal(selectedProjectId, activeProposal.proposal_id);
      setActiveProposal(updated);
      setProposalActionMessage('✕ Proposal rejected. Workspace files remain untouched.');
    } catch (err: unknown) {
      setProposalActionMessage(`Error rejecting proposal: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setIsApplyingProposal(false);
    }
  };

  // Launch Verification Action
  const handleLaunchVerification = async () => {
    if (!selectedProjectId || isVerifying) return;
    setIsVerifying(true);
    setActiveTab('verification');
    try {
      const resp = await apiClient.verifyProject(selectedProjectId, "Autonomous workspace invariant verification");
      setActiveRunId(resp.run_id);
    } catch (err: unknown) {
      setIsVerifying(false);
      setChatError(err instanceof Error ? err.message : String(err));
    }
  };

  // Create New Chat
  const handleNewChat = async () => {
    if (!selectedProjectId) return;
    try {
      const conv = await apiClient.createConversation(selectedProjectId, `Chat ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`);
      setConversations([conv, ...conversations]);
      setActiveConversationId(conv.conversation_id);
      setMessages([]);
      setActiveContextFiles([]);
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] max-w-[1600px] mx-auto overflow-hidden">
      {/* ================= WORKSPACE TOPBAR ================= */}
      <header className="px-4 py-3 bg-[#0d0e12] border-b border-[#222430] flex flex-wrap items-center justify-between gap-3 shrink-0">
        <div className="flex items-center gap-3">
          <span className="p-1.5 rounded bg-[#ef4444]/10 text-[#ef4444] border border-[#ef4444]/20 text-sm">
            🤖
          </span>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-sm font-bold text-white tracking-wide font-sans">
                AI PROJECT WORKSPACE
              </h1>
              <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-[#ef4444]/20 text-[#fca5a5] border border-[#ef4444]/30">
                UNTRUSTED SANDBOX
              </span>
            </div>
            <p className="text-[11px] text-[#71717a] font-mono">
              Deterministic Invariant Verification &bull; Conversational Code Audit &bull; Controlled Patch Review
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            onClick={() => setIsImportModalOpen(true)}
            className="px-3 py-1.5 rounded-lg bg-[#ef4444] hover:bg-[#dc2626] text-white text-xs font-bold transition-all flex items-center gap-1.5 shadow-sm"
          >
            <span>📁</span>
            <span>Import Local Project</span>
          </button>
          <Link
            href="/repositories"
            className="px-3 py-1.5 rounded-lg bg-[#181920] hover:bg-[#222430] text-[#a1a1aa] hover:text-white text-xs font-bold border border-[#2f3242] transition-colors flex items-center gap-1.5"
          >
            <span>🌐</span>
            <span>Import GitHub</span>
          </Link>
          <button
            onClick={handleLaunchVerification}
            disabled={!selectedProjectId || isVerifying}
            className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-xs font-bold transition-colors flex items-center gap-1.5 shadow-sm"
          >
            <span>⚡</span>
            <span>{isVerifying ? 'Verifying...' : 'Run Verification'}</span>
          </button>
        </div>
      </header>

      {/* ================= MAIN 3-PANEL LAYOUT ================= */}
      <div className="flex-1 flex overflow-hidden">
        {/* ================= LEFT SIDEBAR (Projects, Tree, History) ================= */}
        <aside className="w-72 bg-[#0c0d11] border-r border-[#222430] flex flex-col shrink-0 overflow-hidden">
          {/* Project Selector */}
          <div className="p-3 border-b border-[#222430]">
            <label htmlFor="workspace-project-select" className="text-[10px] font-mono text-[#71717a] uppercase tracking-wider block mb-1">
              Active Project Workspace
            </label>
            <select
              id="workspace-project-select"
              value={selectedProjectId || ''}
              onChange={(e) => setSelectedProjectId(e.target.value)}
              className="w-full text-xs font-mono bg-[#13141b] border border-[#222430] rounded-md px-2.5 py-1.5 text-white focus:outline-none focus:border-[#ef4444]"
            >
              {projects.length === 0 && <option value="">No projects imported</option>}
              {projects.map((p) => (
                <option key={p.project_id} value={p.project_id}>
                  {p.name} ({p.file_count} files)
                </option>
              ))}
            </select>

            {activeProject && (
              <div className="mt-2 text-[10px] font-mono text-[#71717a] flex items-center justify-between">
                <span>Digest: {activeProject.snapshot_hash.slice(0, 10)}...</span>
                <span className="text-emerald-400">{(activeProject.total_bytes / 1024).toFixed(1)} KB</span>
              </div>
            )}
          </div>

          {/* Project File Tree */}
          <div className="flex-1 flex flex-col overflow-hidden border-b border-[#222430]">
            <div className="p-2.5 border-b border-[#1b1d27] flex items-center justify-between">
              <span className="text-[11px] font-bold text-[#d4d4d8] font-mono flex items-center gap-1.5">
                <span>🗂️</span>
                <span>PROJECT FILES ({files.length})</span>
              </span>
            </div>

            <div className="p-2 border-b border-[#1b1d27]">
              <input
                type="text"
                placeholder="Filter files (e.g. main.py)..."
                value={fileFilter}
                onChange={(e) => setFileFilter(e.target.value)}
                className="w-full px-2 py-1 text-[11px] font-mono bg-[#13141b] border border-[#222430] rounded text-white placeholder-[#52525b] focus:outline-none focus:border-[#ef4444]"
              />
            </div>

            <div className="flex-1 overflow-y-auto p-1.5 space-y-0.5 font-mono text-xs">
              {filteredFiles.length === 0 ? (
                <div className="p-4 text-center text-xs text-[#71717a]">
                  No matching files.
                </div>
              ) : (
                filteredFiles.map((file) => (
                  <div
                    key={file.path}
                    className="group flex items-center justify-between px-2 py-1 rounded hover:bg-[#181922] cursor-pointer transition-colors"
                  >
                    <span
                      onClick={() => handleFileSelect(file.path)}
                      className="truncate text-[#a1a1aa] group-hover:text-white flex-1"
                    >
                      📄 {file.path}
                    </span>
                    <button
                      onClick={() => insertMention(file.path)}
                      title="Mention in chat context (@)"
                      className="opacity-0 group-hover:opacity-100 px-1 py-0.5 text-[10px] bg-[#222430] hover:bg-[#ef4444] text-white rounded transition-all shrink-0 ml-1"
                    >
                      +@
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Conversations List */}
          <div className="h-44 flex flex-col overflow-hidden">
            <div className="p-2 border-b border-[#1b1d27] flex items-center justify-between">
              <span className="text-[11px] font-bold text-[#a1a1aa] font-mono">
                CHATS ({conversations.length})
              </span>
              <button
                onClick={handleNewChat}
                className="text-[10px] font-bold text-[#ef4444] hover:underline"
              >
                + New Chat
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-1.5 space-y-1 font-mono text-[11px]">
              {conversations.map((c) => (
                <div
                  key={c.conversation_id}
                  onClick={() => setActiveConversationId(c.conversation_id)}
                  className={`px-2 py-1.5 rounded cursor-pointer truncate transition-colors ${
                    activeConversationId === c.conversation_id
                      ? 'bg-[#ef4444]/20 text-[#fca5a5] border border-[#ef4444]/30'
                      : 'text-[#71717a] hover:bg-[#181922] hover:text-white'
                  }`}
                >
                  💬 {c.title}
                </div>
              ))}
            </div>
          </div>
        </aside>

        {/* ================= CENTER PANEL (ChatGPT-like Conversational Stream) ================= */}
        <main className="flex-1 flex flex-col bg-[#090a0d] overflow-hidden relative">
          {/* Chat Messages Stream */}
          <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4">
            {messages.length === 0 ? (
              <div className="h-full flex flex-col items-center justify-center text-center max-w-lg mx-auto py-12">
                <div className="w-12 h-12 rounded-2xl bg-[#ef4444]/10 border border-[#ef4444]/20 flex items-center justify-center text-2xl mb-3 shadow-[0_0_20px_rgba(239,68,68,0.15)]">
                  🛡️
                </div>
                <h2 className="text-base font-bold text-white mb-1">
                  REDLINE AI Coding Assistant
                </h2>
                <p className="text-xs text-[#a1a1aa] mb-6 leading-relaxed">
                  Ask questions about your project, audit code for security flaws, mention files with <code className="text-[#ef4444] font-mono">@</code>, and review AI proposed fixes.
                </p>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 w-full text-left">
                  <button
                    onClick={() => setInputPrompt("Explain how this project is structured and what components exist.")}
                    className="p-3 rounded-lg bg-[#13141b] border border-[#222430] hover:border-[#ef4444]/40 text-xs text-[#d4d4d8] hover:text-white transition-colors"
                  >
                    🔍 <strong className="block text-white mb-0.5">Explain Architecture</strong>
                    Summarize high-level structure &amp; tests.
                  </button>
                  <button
                    onClick={() => setInputPrompt("Audit this project for potential input validation and injection flaws.")}
                    className="p-3 rounded-lg bg-[#13141b] border border-[#222430] hover:border-[#ef4444]/40 text-xs text-[#d4d4d8] hover:text-white transition-colors"
                  >
                    🛡️ <strong className="block text-white mb-0.5">Security Audit</strong>
                    Scan for unvalidated inputs &amp; invariants.
                  </button>
                  <button
                    onClick={() => {
                      const firstFile = files[0]?.path || 'src/main.py';
                      setInputPrompt(`Repair the input validation bug in @${firstFile} and add defensive assertions.`);
                      if (!activeContextFiles.includes(firstFile)) setActiveContextFiles([...activeContextFiles, firstFile]);
                    }}
                    className="p-3 rounded-lg bg-[#13141b] border border-[#222430] hover:border-[#ef4444]/40 text-xs text-[#d4d4d8] hover:text-white transition-colors"
                  >
                    ⚡ <strong className="block text-white mb-0.5">Generate Repair</strong>
                    Propose patch with unified diff review.
                  </button>
                  <button
                    onClick={handleLaunchVerification}
                    className="p-3 rounded-lg bg-[#13141b] border border-[#222430] hover:border-[#ef4444]/40 text-xs text-[#d4d4d8] hover:text-white transition-colors"
                  >
                    🛰️ <strong className="block text-white mb-0.5">Run Invariants</strong>
                    Execute BUILD &rarr; ATTACK &rarr; VERIFY.
                  </button>
                </div>
              </div>
            ) : (
              messages.map((m) => (
                <div
                  key={m.message_id}
                  className={`flex gap-3 text-xs leading-relaxed max-w-3xl ${
                    m.role === 'user' ? 'ml-auto' : 'mr-auto w-full'
                  }`}
                >
                  {m.role === 'assistant' && (
                    <div className="w-7 h-7 rounded-lg bg-[#ef4444]/15 border border-[#ef4444]/30 text-[#ef4444] flex items-center justify-center shrink-0 mt-0.5 font-bold">
                      R
                    </div>
                  )}

                  <div
                    className={`rounded-xl px-4 py-3 space-y-2 ${
                      m.role === 'user'
                        ? 'bg-[#ef4444] text-white shadow-md'
                        : 'bg-[#13141b] border border-[#222430] text-[#e4e4e7] w-full'
                    }`}
                  >
                    {/* Mentions badge */}
                    {m.mentioned_files && m.mentioned_files.length > 0 && (
                      <div className="flex flex-wrap items-center gap-1 text-[10px] font-mono mb-1.5 opacity-90">
                        <span className="text-[#a1a1aa]">Context:</span>
                        {m.mentioned_files.map((mf) => (
                          <span
                            key={mf}
                            className="px-1.5 py-0.5 rounded bg-black/30 border border-white/10 text-emerald-300"
                          >
                            @{mf}
                          </span>
                        ))}
                      </div>
                    )}

                    {/* Message Text with Pre block formatting */}
                    <div className="whitespace-pre-wrap font-sans text-xs">
                      {m.content}
                    </div>

                    {/* Proposal CTA banner if proposal was produced */}
                    {m.proposal_id && (
                      <div className="mt-3 p-2.5 rounded-lg bg-[#1e2029] border border-[#ef4444]/30 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="text-emerald-400">📝</span>
                          <span className="text-[11px] font-mono text-white">
                            Change Proposal generated ({m.proposal_id})
                          </span>
                        </div>
                        <button
                          onClick={() => setActiveTab('diff')}
                          className="px-2.5 py-1 text-[10px] font-bold bg-[#ef4444] text-white rounded hover:bg-[#dc2626] transition-colors"
                        >
                          Review Diff &rarr;
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              ))
            )}
            <div ref={messageEndRef} />
          </div>

          {/* Error Banner */}
          {chatError && (
            <div className="mx-4 p-2.5 rounded bg-[#ef4444]/15 border border-[#ef4444]/30 text-xs text-[#f87171] flex items-center justify-between">
              <span>{chatError}</span>
              <button onClick={() => setChatError(null)} className="text-white ml-2">✕</button>
            </div>
          )}

          {/* Autocomplete Popup */}
          {showMentionPopup && (
            <div className="absolute bottom-24 left-6 right-6 max-w-xl bg-[#13141b] border border-[#222430] rounded-lg shadow-2xl p-2 z-40 max-h-48 overflow-y-auto font-mono text-xs">
              <div className="text-[10px] uppercase tracking-wider text-[#71717a] px-2 py-1">
                Mention Project File ({mentionMatches.length} matches)
              </div>
              {mentionMatches.length === 0 ? (
                <div className="px-2 py-2 text-xs text-[#71717a]">No matching file found.</div>
              ) : (
                mentionMatches.map((f) => (
                  <div
                    key={f.path}
                    onClick={() => insertMention(f.path)}
                    className="px-2 py-1.5 hover:bg-[#1e202a] text-[#e4e4e7] hover:text-white rounded cursor-pointer flex items-center justify-between"
                  >
                    <span className="text-emerald-400">@{f.path}</span>
                    <span className="text-[#71717a] text-[10px]">{f.size_bytes} B</span>
                  </div>
                ))
              )}
            </div>
          )}

          {/* Active Context Chips Bar */}
          {activeContextFiles.length > 0 && (
            <div className="px-4 py-1.5 bg-[#0f1015] border-t border-[#1f202b] flex items-center gap-2 overflow-x-auto text-[11px] font-mono">
              <span className="text-[#71717a] shrink-0">Included Context:</span>
              {activeContextFiles.map((cf) => (
                <span
                  key={cf}
                  className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded bg-[#181922] border border-emerald-500/30 text-emerald-300"
                >
                  <span>@{cf}</span>
                  <button
                    onClick={() => removeContextFile(cf)}
                    className="hover:text-white text-[#71717a] ml-0.5"
                  >
                    ✕
                  </button>
                </span>
              ))}
            </div>
          )}

          {/* Composer */}
          <div className="p-3 sm:p-4 bg-[#0d0e12] border-t border-[#222430]">
            <form onSubmit={handleSendMessage} className="relative flex flex-col gap-2">
              <textarea
                ref={textareaRef}
                value={inputPrompt}
                onChange={handleInputChange}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSendMessage();
                  }
                }}
                placeholder="Ask about project code, request repairs, or type @ to mention files..."
                rows={2}
                className="w-full p-3 text-xs font-mono bg-[#13141b] border border-[#222430] rounded-xl text-white placeholder-[#52525b] focus:outline-none focus:border-[#ef4444] resize-none"
              />

              <div className="flex items-center justify-between">
                <span className="text-[11px] text-[#71717a] font-mono">
                  Tip: Type <code className="text-[#ef4444]">@</code> to autocomplete file mentions &bull; Press Enter to send
                </span>

                <button
                  type="submit"
                  disabled={!inputPrompt.trim() || isSending}
                  className="px-4 py-1.5 rounded-lg bg-[#ef4444] hover:bg-[#dc2626] disabled:opacity-40 text-white font-bold text-xs transition-colors flex items-center gap-1.5 shadow-sm"
                >
                  {isSending ? (
                    <>
                      <span className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
                      <span>Thinking...</span>
                    </>
                  ) : (
                    <>
                      <span>Send</span>
                      <span>&uarr;</span>
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </main>

        {/* ================= RIGHT PANEL (Diffs, Verification, File Inspector) ================= */}
        <aside className="w-96 bg-[#0c0d11] border-l border-[#222430] flex flex-col shrink-0 overflow-hidden">
          {/* Tabs Header */}
          <div className="px-3 pt-2 border-b border-[#222430] flex items-center gap-2 bg-[#0d0e12]">
            <button
              onClick={() => setActiveTab('diff')}
              className={`pb-2 px-2 text-xs font-mono font-bold border-b-2 transition-colors ${
                activeTab === 'diff'
                  ? 'border-[#ef4444] text-[#ef4444]'
                  : 'border-transparent text-[#71717a] hover:text-white'
              }`}
            >
              Changes &amp; Diffs
            </button>
            <button
              onClick={() => setActiveTab('verification')}
              className={`pb-2 px-2 text-xs font-mono font-bold border-b-2 transition-colors ${
                activeTab === 'verification'
                  ? 'border-[#ef4444] text-[#ef4444]'
                  : 'border-transparent text-[#71717a] hover:text-white'
              }`}
            >
              Verification
            </button>
            <button
              onClick={() => setActiveTab('file')}
              className={`pb-2 px-2 text-xs font-mono font-bold border-b-2 transition-colors ${
                activeTab === 'file'
                  ? 'border-[#ef4444] text-[#ef4444]'
                  : 'border-transparent text-[#71717a] hover:text-white'
              }`}
            >
              File Preview
            </button>
          </div>

          {/* Tab Content */}
          <div className="flex-1 overflow-y-auto p-3">
            {/* TAB 1: PROPOSED CHANGES & DIFF */}
            {activeTab === 'diff' && (
              <div className="space-y-4">
                {proposalActionMessage && (
                  <div className="p-2.5 rounded bg-[#181922] border border-[#222430] text-xs font-mono text-[#a1a1aa]">
                    {proposalActionMessage}
                  </div>
                )}

                {activeProposal ? (
                  <div className="space-y-3">
                    <div className="p-3 rounded-lg bg-[#13141b] border border-[#222430] space-y-2 font-mono text-xs">
                      <div className="flex items-center justify-between">
                        <strong className="text-white">{activeProposal.proposal_id}</strong>
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          activeProposal.status === 'APPLIED' ? 'bg-emerald-950 text-emerald-400 border border-emerald-800' :
                          activeProposal.status === 'REJECTED' ? 'bg-red-950 text-red-400 border border-red-800' :
                          'bg-amber-950 text-amber-400 border border-amber-800'
                        }`}>
                          {activeProposal.status}
                        </span>
                      </div>
                      <p className="text-[#a1a1aa] font-sans text-xs">
                        {activeProposal.description}
                      </p>
                      <div className="text-[10px] text-[#71717a]">
                        Modified: {activeProposal.changed_files.join(', ')}
                      </div>

                      {activeProposal.status === 'PENDING' && (
                        <div className="grid grid-cols-2 gap-2 pt-1 border-t border-[#222430]">
                          <button
                            id="btn-approve-proposal-top"
                            onClick={handleApplyProposal}
                            disabled={isApplyingProposal}
                            className="py-1.5 px-3 rounded bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs transition-colors shadow-sm flex items-center justify-center gap-1.5"
                          >
                            <span>✓</span>
                            <span>Approve &amp; Apply</span>
                          </button>
                          <button
                            id="btn-reject-proposal-top"
                            onClick={handleRejectProposal}
                            disabled={isApplyingProposal}
                            className="py-1.5 px-3 rounded bg-[#1e2029] hover:bg-[#282a36] text-[#f87171] border border-red-900/40 font-bold text-xs transition-colors flex items-center justify-center gap-1.5"
                          >
                            <span>✕</span>
                            <span>Discard</span>
                          </button>
                        </div>
                      )}
                    </div>

                    {/* Diff Viewer Component */}
                    <div className="rounded-lg border border-[#222430] overflow-hidden">
                      <DiffViewer
                        initialDiff={{
                          run_id: activeProposal.proposal_id,
                          diff: activeProposal.diff,
                          changed_files: activeProposal.changed_files,
                        }}
                      />
                    </div>

                    {/* Approval & Rejection Actions */}
                    {activeProposal.status === 'PENDING' && (
                      <div className="grid grid-cols-2 gap-2 pt-2">
                        <button
                          onClick={handleApplyProposal}
                          disabled={isApplyingProposal}
                          className="py-2 px-3 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs transition-colors shadow-sm flex items-center justify-center gap-1.5"
                        >
                          <span>✓</span>
                          <span>Approve &amp; Apply</span>
                        </button>
                        <button
                          onClick={handleRejectProposal}
                          disabled={isApplyingProposal}
                          className="py-2 px-3 rounded-lg bg-[#1e2029] hover:bg-[#282a36] text-[#f87171] border border-red-900/40 font-bold text-xs transition-colors flex items-center justify-center gap-1.5"
                        >
                          <span>✕</span>
                          <span>Discard</span>
                        </button>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="p-8 text-center text-xs text-[#71717a] font-mono space-y-2">
                    <span className="text-2xl block">📝</span>
                    <span>No active change proposal.</span>
                    <p className="text-[11px] text-[#52525b]">
                      Ask REDLINE AI in chat to edit or repair a file to inspect unified diffs here.
                    </p>
                  </div>
                )}
              </div>
            )}

            {/* TAB 2: VERIFICATION STAGES & RESULTS */}
            {activeTab === 'verification' && (
              <div className="space-y-4">
                <div className="p-3 rounded-lg bg-[#13141b] border border-[#222430] space-y-2">
                  <span className="text-xs font-bold text-white block">Autonomous Pipeline</span>
                  <p className="text-[11px] text-[#a1a1aa] leading-relaxed">
                    Executes BUILD &rarr; ATTACK &rarr; REPAIR &rarr; VERIFY under fail-closed isolation.
                  </p>
                  <button
                    onClick={handleLaunchVerification}
                    disabled={isVerifying}
                    className="w-full py-2 px-3 rounded bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs transition-colors flex items-center justify-center gap-2"
                  >
                    <span>⚡</span>
                    <span>{isVerifying ? 'Pipeline Active...' : 'Launch Verification'}</span>
                  </button>
                </div>

                {activeRunId && (
                  <div className="p-3 rounded-lg bg-[#13141b] border border-[#222430] space-y-2 font-mono text-xs">
                    <div className="flex items-center justify-between">
                      <span className="text-[#a1a1aa]">Run ID:</span>
                      <span className="text-white font-bold">{activeRunId}</span>
                    </div>

                    {runStatus && (
                      <>
                        <div className="flex items-center justify-between">
                          <span className="text-[#a1a1aa]">State:</span>
                          <span className="px-2 py-0.5 rounded bg-blue-950 text-blue-400 border border-blue-800 text-[10px]">
                            {runStatus.state}
                          </span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-[#a1a1aa]">Iteration:</span>
                          <span className="text-white">{runStatus.iteration}</span>
                        </div>
                        {runStatus.evidence_receipt && (
                          <div className="pt-2 border-t border-[#222430] space-y-1">
                            <span className="text-[10px] text-[#71717a] block">AUTHORITATIVE VERDICT</span>
                            <div className="text-emerald-400 font-bold text-sm">
                              {runStatus.evidence_receipt.verdict}
                            </div>
                            <div className="text-[10px] text-[#71717a]">
                              Hash: {runStatus.evidence_receipt.receipt_hash.slice(0, 16)}...
                            </div>
                          </div>
                        )}
                      </>
                    )}

                    <div className="pt-2">
                      <Link
                        href={`/results?runId=${activeRunId}`}
                        className="text-[11px] text-[#ef4444] hover:underline block"
                      >
                        Open Detailed Results &rarr;
                      </Link>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* TAB 3: FILE PREVIEW */}
            {activeTab === 'file' && (
              <div>
                {selectedFile ? (
                  <div className="space-y-2">
                    <div className="flex items-center justify-between font-mono text-xs text-[#a1a1aa]">
                      <span className="text-white font-bold">📄 {selectedFile.path}</span>
                      <span>{selectedFile.size_bytes} B</span>
                    </div>
                    <pre className="p-3 rounded-lg bg-[#090a0d] border border-[#222430] font-mono text-[11px] text-[#e4e4e7] overflow-x-auto max-h-[500px]">
                      {selectedFile.content}
                    </pre>
                  </div>
                ) : (
                  <div className="p-8 text-center text-xs text-[#71717a] font-mono">
                    Select a file from the project tree to preview its content.
                  </div>
                )}
              </div>
            )}
          </div>
        </aside>
      </div>

      {/* ================= MODAL ================= */}
      <LocalProjectImportModal
        isOpen={isImportModalOpen}
        onClose={() => setIsImportModalOpen(false)}
        onSuccess={(newProj) => {
          setProjects([newProj, ...projects]);
          setSelectedProjectId(newProj.project_id);
        }}
      />
    </div>
  );
}

export default function WorkspacePage() {
  return (
    <Suspense fallback={<div className="p-6 text-xs font-mono text-[#a1a1aa]">Loading REDLINE Workspace...</div>}>
      <WorkspaceContent />
    </Suspense>
  );
}
