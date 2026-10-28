import {
  TaskContract,
  RunStatus,
  EvidenceReceipt,
  JudgeExplanation,
  RunHistoryItem,
  RunDiff,
  ImportRepositoryRequest,
  RepositoryResponse,
  LocalProjectImportRequest,
  ProjectRecord,
  ProjectFileEntry,
  ProjectFileContentResponse,
  ConversationRecord,
  MessageRecord,
  ProposalRecord,
  ChatResponse,
  ProjectVerifyResponse
} from '../models/types';

export class ApiError extends Error {
  status: number;
  detail?: string;

  constructor(status: number, message: string, detail?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

export class NotImplementedError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'NotImplementedError';
  }
}

const DEFAULT_API_BASE_URL = 'http://127.0.0.1:8000/api/v1';

export function getApiBaseUrl(): string {
  if (typeof process !== 'undefined' && process.env && process.env.NEXT_PUBLIC_API_BASE_URL) {
    return process.env.NEXT_PUBLIC_API_BASE_URL;
  }
  return DEFAULT_API_BASE_URL;
}

/**
 * REDLINE API Client Foundation
 */
export class RedlineApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = getApiBaseUrl()) {
    this.baseUrl = baseUrl;
  }

  private async fetchOrThrow(url: string, options?: RequestInit) {
    const response = await fetch(url, options);
    if (!response.ok) {
      let errorMessage = response.statusText;
      let detailStr: string | undefined;
      try {
        const data = await response.json();
        if (data && data.detail) {
          const formatted = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
          detailStr = formatted;
          errorMessage = formatted;
        }
      } catch {
        // ignore JSON parse error
      }
      throw new ApiError(response.status, `API Error ${response.status}: ${errorMessage}`, detailStr);
    }
    return response.json();
  }

  /**
   * Submits a TaskContract to the backend to create a Run.
   * The backend is responsible for creating and returning the authoritative Run ID.
   */
  async createRun(contract: TaskContract): Promise<{ run_id: string }> {
    return this.fetchOrThrow(`${this.baseUrl}/runs`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(contract),
    });
  }

  /**
   * Retrieves the authoritative status of a Run.
   */
  async getRunStatus(runId: string, signal?: AbortSignal): Promise<RunStatus> {
    return this.fetchOrThrow(`${this.baseUrl}/runs/${runId}`, { signal });
  }

  /**
   * Retrieves the authoritative Evidence Receipt for a completed run.
   */
  async getEvidenceReceipt(runId: string): Promise<EvidenceReceipt> {
    return this.fetchOrThrow(`${this.baseUrl}/runs/${runId}/receipt`);
  }

  /**
   * Retrieves the authoritative Judge Explanation for a completed run.
   */
  async getJudgeExplanation(runId: string): Promise<JudgeExplanation> {
    return this.fetchOrThrow(`${this.baseUrl}/runs/${runId}/judge`);
  }

  /**
   * Retrieves the authoritative history of all runs.
   */
  async getRunHistory(): Promise<RunHistoryItem[]> {
    return this.fetchOrThrow(`${this.baseUrl}/runs`);
  }

  /**
   * Retrieves the authoritative patch diff and changed files for a run.
   */
  async getRunDiff(runId: string, signal?: AbortSignal): Promise<RunDiff> {
    return this.fetchOrThrow(`${this.baseUrl}/runs/${runId}/diff`, { signal });
  }

  /**
   * Imports and quarantines a remote public HTTPS repository at a pinned Git commit SHA.
   */
  async importRepository(req: ImportRepositoryRequest): Promise<RepositoryResponse> {
    return this.fetchOrThrow(`${this.baseUrl}/repositories/import`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(req),
    });
  }

  /**
   * Lists all registered repository targets.
   */
  async listRepositories(): Promise<RepositoryResponse[]> {
    return this.fetchOrThrow(`${this.baseUrl}/repositories`);
  }

  /**
   * Retrieves metadata for a registered repository target.
   */
  async getRepository(repositoryId: string): Promise<RepositoryResponse> {
    return this.fetchOrThrow(`${this.baseUrl}/repositories/${encodeURIComponent(repositoryId)}`);
  }

  /**
   * Imports a local project workspace from structured files.
   */
  async importLocalProject(req: LocalProjectImportRequest): Promise<ProjectRecord> {
    return this.fetchOrThrow(`${this.baseUrl}/projects/import`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    });
  }

  /**
   * Lists all imported project workspaces.
   */
  async listProjects(): Promise<ProjectRecord[]> {
    return this.fetchOrThrow(`${this.baseUrl}/projects`);
  }

  /**
   * Retrieves metadata for an imported project.
   */
  async getProject(projectId: string): Promise<ProjectRecord> {
    return this.fetchOrThrow(`${this.baseUrl}/projects/${encodeURIComponent(projectId)}`);
  }

  /**
   * Deletes a project workspace.
   */
  async deleteProject(projectId: string): Promise<{ deleted: boolean; project_id: string }> {
    return this.fetchOrThrow(`${this.baseUrl}/projects/${encodeURIComponent(projectId)}`, {
      method: 'DELETE',
    });
  }

  /**
   * Lists all files in a project workspace.
   */
  async listProjectFiles(projectId: string): Promise<ProjectFileEntry[]> {
    return this.fetchOrThrow(`${this.baseUrl}/projects/${encodeURIComponent(projectId)}/files`);
  }

  /**
   * Reads content of a specific file in a project workspace.
   */
  async getProjectFileContent(projectId: string, path: string): Promise<ProjectFileContentResponse> {
    return this.fetchOrThrow(`${this.baseUrl}/projects/${encodeURIComponent(projectId)}/file?path=${encodeURIComponent(path)}`);
  }

  /**
   * Lists conversations for a project.
   */
  async listConversations(projectId: string): Promise<ConversationRecord[]> {
    return this.fetchOrThrow(`${this.baseUrl}/projects/${encodeURIComponent(projectId)}/conversations`);
  }

  /**
   * Creates a new conversation thread for a project.
   */
  async createConversation(projectId: string, title?: string): Promise<ConversationRecord> {
    return this.fetchOrThrow(`${this.baseUrl}/projects/${encodeURIComponent(projectId)}/conversations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    });
  }

  /**
   * Lists messages in a conversation.
   */
  async listMessages(projectId: string, conversationId: string): Promise<MessageRecord[]> {
    return this.fetchOrThrow(`${this.baseUrl}/projects/${encodeURIComponent(projectId)}/conversations/${encodeURIComponent(conversationId)}/messages`);
  }

  /**
   * Sends a user chat message with optional @ mentions.
   */
  async sendMessage(
    projectId: string,
    conversationId: string,
    message: string,
    mentionedFiles?: string[]
  ): Promise<ChatResponse> {
    return this.fetchOrThrow(`${this.baseUrl}/projects/${encodeURIComponent(projectId)}/conversations/${encodeURIComponent(conversationId)}/messages`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, mentioned_files: mentionedFiles }),
    });
  }

  /**
   * Lists proposals for a project.
   */
  async listProposals(projectId: string): Promise<ProposalRecord[]> {
    return this.fetchOrThrow(`${this.baseUrl}/projects/${encodeURIComponent(projectId)}/proposals`);
  }

  /**
   * Retrieves a specific proposal by ID.
   */
  async getProposal(projectId: string, proposalId: string): Promise<ProposalRecord> {
    return this.fetchOrThrow(`${this.baseUrl}/projects/${encodeURIComponent(projectId)}/proposals/${encodeURIComponent(proposalId)}`);
  }

  /**
   * Approves and applies a proposed code change to the project workspace.
   */
  async applyProposal(projectId: string, proposalId: string): Promise<ProposalRecord> {
    return this.fetchOrThrow(`${this.baseUrl}/projects/${encodeURIComponent(projectId)}/proposals/${encodeURIComponent(proposalId)}/apply`, {
      method: 'POST',
    });
  }

  /**
   * Rejects a proposed code change without modifying files.
   */
  async rejectProposal(projectId: string, proposalId: string): Promise<ProposalRecord> {
    return this.fetchOrThrow(`${this.baseUrl}/projects/${encodeURIComponent(projectId)}/proposals/${encodeURIComponent(proposalId)}/reject`, {
      method: 'POST',
    });
  }

  /**
   * Launches an authoritative verification run for the project workspace.
   */
  async verifyProject(
    projectId: string,
    taskDescription?: string,
    testCommand?: string[]
  ): Promise<ProjectVerifyResponse> {
    return this.fetchOrThrow(`${this.baseUrl}/projects/${encodeURIComponent(projectId)}/verify`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_description: taskDescription, test_command: testCommand }),
    });
  }
}

export const apiClient = new RedlineApiClient();
