import { 
  TaskContract, 
  RunStatus, 
  EvidenceReceipt, 
  JudgeExplanation, 
  RunHistoryItem,
  RunDiff
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
}

export const apiClient = new RedlineApiClient();
