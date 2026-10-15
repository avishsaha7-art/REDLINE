export type RunState =
  | 'INIT'
  | 'RECON'
  | 'PLAN'
  | 'BASELINE'
  | 'BUILD'
  | 'TEST'
  | 'ATTACK'
  | 'ANALYZE'
  | 'REPAIR'
  | 'VERIFY'
  | 'JUDGE'
  | 'VERIFIED'
  | 'ABORTED';

export type VerificationStatus =
  | 'VERIFIED'
  | 'REJECTED'
  | 'INCONCLUSIVE'
  | 'POLICY_BLOCKED'
  | 'SANDBOX_FAILURE'
  | 'RESOURCE_LIMIT'
  | 'TIMEOUT'
  | 'EXECUTION_FAILURE';

export type OperationalResult =
  | 'SANDBOX_FAILURE'
  | 'RESOURCE_LIMIT'
  | 'POLICY_BLOCKED'
  | 'TIMEOUT'
  | 'INVALID_REPOSITORY'
  | 'INVALID_TASK'
  | 'MODEL_FAILURE'
  | 'TOOL_FAILURE';

export interface ResourceBudget {
  max_iterations: number;
  max_runtime: number;
  max_patch_size: number;
  max_tool_calls: number;
  max_failed_attempts: number;
  max_attack_cases: number;
  max_file_size: number;
  max_repo_files: number;
  max_repo_bytes: number;
  max_context_bytes: number;
}

export interface TaskContract {
  task_id: string;
  repository_id: string;
  base_commit_or_snapshot: string;
  task_description: string;
  constraints?: string[];
  acceptance_criteria?: string[];
  allowed_scope?: string[];
  resource_budget?: ResourceBudget;
}

export interface PatchCandidate {
  patch_id: string;
  task_id: string;
  base_commit_or_snapshot: string;
  diff: string;
  diff_sha256?: string;
  changed_files: string[];
  patch_metadata?: Record<string, unknown>;
  generation_provenance?: Record<string, unknown>;
}

export interface RepairCandidate {
  repair_id: string;
  base_patch_hash: string;
  diff: string;
  changed_files: string[];
  target_failure: string;
  reasoning_summary: string;
  counterexample_reference?: string;
}

export interface JudgeExplanation {
  summary: string;
  verified_claims: string[];
  failed_claims: string[];
  evidence_references: string[];
  limitations: string;
  confidence: string;
}

export interface VerificationScope {
  execution: string;
  tests: string;
  invariants: string;
  security: string;
}

export type SecurityLevel = 'SECURE' | 'DEVELOPMENT_ONLY' | 'UNAVAILABLE';

export interface SandboxCapabilities {
  security_level?: SecurityLevel | string;
  filesystem_isolation?: string;
  process_isolation?: string;
  network_isolation?: string;
  credential_isolation?: string;
  resource_enforcement?: string;
  timeout_enforcement?: string;
  workspace_isolation?: string;
  cleanup_guarantee?: string;
  secure_untrusted_execution?: boolean;
}

export interface StructuredObservation {
  execution_id: string;
  command_identifier: string;
  exit_code?: number | null;
  stdout_sha256: string;
  stderr_sha256: string;
  stdout_bytes: number;
  stderr_bytes: number;
  duration_ms: number;
  status: string;
  sandbox_backend: string;
  security_level: string;
  capabilities?: SandboxCapabilities | null;
  workspace_id: string;
  repository_snapshot_hash: string;
  patch_hash: string;
}

export interface TestObservation {
  test_id: string;
  status: string;
  duration_ms: number;
  framework: string;
  output_summary: string;
}

export interface TestResultSummary {
  discovered: number;
  executed: number;
  passed: number;
  failed: number;
  errored: number;
  skipped: number;
  inconclusive: number;
  observations: TestObservation[];
}

export interface InvariantEvaluation {
  invariant_id: string;
  description: string;
  result: string;
  failure_reason?: string | null;
  evidence_hash: string;
}

export interface SecurityObservation {
  hook_id: string;
  status: string;
  evidence: string;
}

export interface Counterexample {
  counterexample_id: string;
  invariant_id: string;
  test_id?: string | null;
  input_data: string;
  observed_output: string;
  expected_output: string;
  failure_reason: string;
  oracle_type: string;
  execution_id: string;
  evidence_hash: string;
}

export interface OracleResult {
  oracle_type: string;
  result: string;
  evidence: string;
}

export interface EvidenceReceipt {
  receipt_schema_version: string;
  run_id: string;
  task_id: string;
  repository_snapshot_hash: string;
  task_contract_hash: string;
  patch_hash: string;
  patch_lineage: string[];
  execution_ids: string[];
  attack_fingerprints: string[];
  verdict: VerificationStatus;
  verification_scope: VerificationScope;
  structured_observation?: StructuredObservation | null;
  test_summary?: TestResultSummary | null;
  invariant_summary: InvariantEvaluation[];
  security_summary: SecurityObservation[];
  counterexamples: Counterexample[];
  oracle_results: OracleResult[];
  policy_version: string;
  verifier_version: string;
  sandbox_provenance: Record<string, string>;
  model_provenance: Record<string, string>;
  evidence_hashes: string[];
  timestamp: string;
  receipt_hash?: string | null;
  // Backward compatibility alias for UI
  deterministic_verdict?: string;
}

export interface RunHistoryItem {
  run_id: string;
  task_id: string;
  final_state: RunState | string;
  verdict?: VerificationStatus | string;
  created_at: string;
  completed_at?: string | null;
}

export interface RunStatus {
  run_id: string;
  task_id: string;
  state: RunState;
  status: string; // e.g. "active", "completed", "failed"
  iteration: number;
  resource_status: {
    iterations_used: number;
    iterations_limit: number;
    tool_calls_used?: number;
    tool_calls_limit?: number;
  };
  started_at: string;
  updated_at: string;
  patch_candidate?: PatchCandidate | null;
  patch_lineage: string[];
  evidence_receipt?: EvidenceReceipt | null;
  judge_explanation?: JudgeExplanation | null;
  operational_result?: OperationalResult | null;
  operational_error?: string | null;
}

// Attack Evidence Summary
export interface AttackEvidenceSummary {
  attack_id: string;
  status: string;
  result: string;
  oracle_type: string;
  evidence: string;
}

export interface RunDiff {
  run_id: string;
  patch_id?: string | null;
  diff?: string | null;
  changed_files: string[];
}
