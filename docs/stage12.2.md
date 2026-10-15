# Stage 12.2 Implementation Notes: API ↔ Authoritative Orchestrator Integration Remediation

## 1. Why Stage 12.1 Failed & Duplicate Orchestrator Root Cause

Stage 12.1 was independently reviewed and FAILED due to a critical architectural divergence:
- During Stage 12.1, a secondary, non-authoritative Orchestrator was introduced in `backend/orchestrator/run_manager.py:Orchestrator`.
- The FastAPI route (`backend/api/routes/runs.py`) called this duplicate `run_manager.Orchestrator` instead of the canonical `backend/orchestrator/orchestrator.py:Orchestrator`.
- `run_manager.Orchestrator` expected methods on `StateMachine` such as `transition_to()` and `fail_with()`. However, the authoritative `StateMachine` (`backend/orchestrator/state_machine.py`) provides `advance()` and `_abort()` driven strictly by `TransitionPolicy`.
- As a result, any run initiated via `POST /api/v1/runs` immediately crashed on `transition_to()` in the background task. Because background exceptions were caught or silently swallowed, the run remained frozen indefinitely at `RunState.INIT` with no operational failure recorded and no pipeline progression.

## 2. Authoritative Orchestrator & Deletion of Broken Duplicate

In Stage 12.2:
- The duplicate `backend/orchestrator/run_manager.py` has been completely deleted.
- All references across the repository (such as `tests/test_stage6.py` and `tests/test_stage7.py`) have been migrated to the single authoritative Orchestrator:
  ```python
  from backend.orchestrator.orchestrator import Orchestrator
  ```
- An audit of the repository confirms that exactly ONE `class Orchestrator` exists (`backend/orchestrator/orchestrator.py`), and 0 imports of `run_manager` remain.

## 3. API Integration Design & Background Execution Semantics

The FastAPI route layer is an adapter around the backend architecture and does NOT contain orchestration logic or reimplement pipeline phases:
- `POST /api/v1/runs`:
  1. Validates the incoming `TaskContract` payload.
  2. Applies backend resource budget caps (`enforce_resource_budget_limits`) ensuring the client cannot exceed system ceilings (CPU, memory, disk, timeout, tool calls, iterations).
  3. Instantiates a canonical `Run` record with `RunState.INIT`.
  4. Launches execution in a dedicated daemon thread running `execute_run()`.
  5. Returns HTTP 201 with `CreateRunResponse(run_id=..., state=INIT, status=PENDING)`.
- `execute_run(run_id, contract)`:
  1. Instantiates the authoritative `backend.orchestrator.orchestrator.Orchestrator(run_id, contract)`.
  2. Invokes `orchestrator.run()`, driving the true state machine across all phases: `INIT -> RECON -> PLAN -> BASELINE -> BUILD -> TEST -> ATTACK -> ANALYZE -> REPAIR -> VERIFY -> JUDGE -> (VERIFIED / ABORTED)`.
  3. Records all intermediate state transitions dynamically into the run record.
  4. Persists the authoritative `EvidenceReceipt` (`orchestrator.evidence_receipt`).
  5. Persists the authoritative `JudgeExplanation` (`orchestrator.judge_explanation`).
  6. Explicitly catches any unexpected exception or operational error. Exceptions are **never** swallowed (`except Exception: pass` is strictly prohibited). On failure, the run state transitions to `RunState.ABORTED`, `operational_result` is set to `OperationalResult.FAILED`, and a sanitized `operational_error` description is persisted and exposed via the API.

## 4. Receipt & Judge Persistence and Retrieval Endpoints

- **Authoritative Receipt Persistence (`GET /api/v1/runs/{run_id}/receipt`)**:
  - Exposes the exact `backend.models.evidence.EvidenceReceipt` produced by the authoritative verification pipeline.
  - Returns HTTP 404 if the run is unknown or if verification/receipt generation has not completed yet.
  - Preserves exact cryptographic hashes, `patch_lineage`, `verification_scope`, `model_provenance`, `sandbox_provenance`, and deterministic `verdict`. The API never synthesizes or alters receipt fields.
- **Authoritative Judge Persistence (`GET /api/v1/runs/{run_id}/judge`)**:
  - Exposes the exact `backend.models.evidence.JudgeExplanation` produced by `backend.agents.judge.JudgeAgent`.
  - Returns HTTP 404 if the run is unknown or if the Judge phase has not completed.
  - The API does not synthesize Judge outputs or permit Judge text to override deterministic verification.

## 5. Frontend Type Synchronization & RunState vs. Verdict Separation

- The previous review incorrectly suggested adding `REJECTED` and `INCONCLUSIVE` to `RunState`.
- In Stage 12.2, we preserve the authoritative architectural separation defined in `docs/REDLINE_v1.1_ARCHITECTURE_FROZEN.md`:
  - **RunState (Lifecycle States)**: `INIT`, `RECON`, `PLAN`, `BASELINE`, `BUILD`, `TEST`, `ATTACK`, `ANALYZE`, `REPAIR`, `VERIFY`, `JUDGE`, `VERIFIED`, `ABORTED`.
  - **VerificationStatus (Deterministic Verdicts)**: `VERIFIED`, `REJECTED`, `INCONCLUSIVE`, `POLICY_BLOCKED`, `SANDBOX_TIMEOUT`.
- `frontend/src/models/types.ts` has been synchronized with `backend/models/evidence.py` and `backend/models/schemas.py`:
  - `RunState` strictly mirrors backend lifecycle states.
  - `VerificationStatus` defines deterministic verdicts.
  - `EvidenceReceipt` frontend type mirrors backend fields: `receipt_schema_version`, `run_id`, `task_contract_hash`, `repository_snapshot_hash`, `patch_hash`, `patch_lineage`, `evidence_hashes` (`string[]`), `verdict` (`VerificationStatus`), `verification_scope`, `policy_version`, `sandbox_provenance`, `model_provenance`, `test_summary`, `invariant_summary`, `security_summary`, `counterexamples`, `oracle_results`, `receipt_hash`.
  - Obsolete fabricated fields like `receipt_id` have been removed.
  - `JudgeConfidence` matches backend enum: `HIGH`, `MEDIUM`, `LOW`.

## 6. Frontend API Base URL Configuration

- Hardcoded API URLs have been replaced in `frontend/src/api/client.ts`.
- The API base URL is now configurable via the environment variable `NEXT_PUBLIC_API_BASE_URL`:
  ```typescript
  const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8000/api/v1';
  ```
- **Security Constraint**: `NEXT_PUBLIC_*` variables must never contain API keys, tokens, or credentials. For production deployment, configure `NEXT_PUBLIC_API_BASE_URL` in the frontend hosting environment to point to the secure REDLINE API gateway.

## 7. Integration Tests

- Comprehensive end-to-end integration tests have been implemented in `tests/test_stage12_2_api_integration.py`:
  1. `test_stage12_2_end_to_end_orchestrator_integration`: Initiates a run via `POST /api/v1/runs`, polls `GET /api/v1/runs/{id}` through state machine progression until terminal state, verifies `GET /receipt` returns the authoritative `EvidenceReceipt` matching `run_id` and preserving `patch_lineage`, and verifies `GET /judge` returns the authoritative `JudgeExplanation`.
  2. `test_stage12_2_failure_path_operational`: Injects an operational abort via missing required target in the task contract, verifies the run reaches `RunState.ABORTED` with `OperationalResult.FAILED`, records `operational_error`, and confirms no `VERIFIED` verdict or receipt is issued.
  3. `test_stage12_2_background_exception_captured_and_not_swallowed`: Simulates an unexpected runtime exception in the orchestrator background thread; proves the exception is safely caught, run transitions to `RunState.ABORTED`, and the run is not left frozen in `INIT`.
  4. `test_stage12_2_adversarial_security_injections`: Sends adversarial payloads attempting to inject state (`VERIFIED`), verdict, `authorize_sandbox`, `trust_level`, `policy_override`, `skip_verification`, and fake evidence receipts. Asserts backend rejects or ignores all unauthorized fields.
  5. `test_stage12_2_resource_budget_ceiling_enforcement`: Sends excessive resource budget values; asserts the backend caps them to system ceilings (`max_iterations <= 5`, `timeout_seconds <= 300`).
  6. `test_stage12_2_nonexistent_and_pending_endpoints`: Verifies 404 responses for nonexistent runs and pending receipt/judge calls.
- Full backend regression: **184 passed, 1 skipped** (100% pass rate).
- Frontend tests: **16 passed, 0 failed**; TypeScript, ESLint, and Next.js build all pass with 0 errors.

## 8. Known MVP Limitations

1. **In-Memory Run Store**:
   - The current MVP run store (`backend/api/routes/runs.py:RUNS_STORE`) is held in-memory.
   - Runs do not survive process restarts. In-memory synchronization prevents race conditions and data corruption during process lifetime. Persistent database storage (SQLite) is scheduled for subsequent infrastructure stages.
2. **Authentication Deferral**:
   - Authentication and authorization mechanisms (API tokens, OAuth, RBAC) are deferred per roadmap.
   - Current endpoints are designed for local and sandboxed development environments.
3. **Idempotency Deferral**:
   - Each `POST /api/v1/runs` generates a distinct UUID `run_id`. Full request idempotency keys (e.g. `Idempotency-Key` header) are not implemented for the MVP stage. Runs operate in isolated working directories and do not corrupt each other's state or evidence.

---
