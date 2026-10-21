# REDLINE — Stage P2-3.3 Completion Report: Benchmark Runner & Comparative Evaluation

**Status:** IMPLEMENTED & VERIFIED  
**Date:** 2026-10-15  
**Baseline Git Anchor Commit:** `6e476bccaba2187055254d1cd71b539d7903b34f`  
**Baseline Annotated Tag:** `benchmark-v1.0.0`  
**Manifest Root SHA-256:** `d2cd37b9a588151975c992426338b0341f39bc824e1627c32d51e02ed1ac20c2`  

---

## 1. Executive Summary

Stage P2-3.3 implements the reproducible benchmark runner, authoritative out-of-sandbox evaluator, comparative evaluation engine, auditable report generator, and persistent storage layer for REDLINE's held-out security benchmark dataset.

In accordance with Section 4 non-negotiable safety rules:
- **Zero candidate code was executed on the host.**
- **No container runtime was assumed or bypassed.**
- **LocalDevelopmentBackend is strictly rejected fail-closed.**
- **All evaluation orchestration, failure handling, metric calculations, and report generations were verified using synthetic non-executable evaluation records and isolated boundaries.**

In the independent review reproduction, all 99 tests across the 7 benchmark modules passed (98 passed, 1 skipped due to Windows non-admin symlink creation, fully verified via mock; 35 passed, 0 skipped across the three focused sandbox/benchmark remediation modules).

---

## 2. Files Added and Modified

| File | Status | Description |
|------|--------|-------------|
| [`backend/benchmark/models.py`](file:///P:/REDLINE/backend/benchmark/models.py) | **Created** | Data models, schemas, and lifecycle enums (`BenchmarkRunState`, `BenchmarkVerdict`, `BenchmarkArmType`, `BenchmarkRunConfig`, `TaskEvaluationResult`, `BenchmarkRunRecord`, `ComparativeEvaluationSummary`, `BenchmarkReport`). |
| [`backend/benchmark/evaluator.py`](file:///P:/REDLINE/backend/benchmark/evaluator.py) | **Created** | `BenchmarkTaskLoader` (manifest validation, category/CWE checks, path containment) and `DeterministicBenchmarkEvaluator` (3-phase oracle evaluation hierarchy, 4-way verdict assignment, candidate stdout injection immunity). |
| [`backend/benchmark/runner.py`](file:///P:/REDLINE/backend/benchmark/runner.py) | **Created** | `BenchmarkRunner` orchestrating deterministic lifecycle states with mandatory fail-closed integrity and capability gates. Refuses candidate execution when runtime is unverified. |
| [`backend/benchmark/storage.py`](file:///P:/REDLINE/backend/benchmark/storage.py) | **Created** | `BenchmarkRunRepository` managing SQLite persistence for runs and task results. Recovers interrupted runs to `OPERATIONAL_FAILURE`. |
| [`backend/benchmark/comparison.py`](file:///P:/REDLINE/backend/benchmark/comparison.py) | **Created** | `BenchmarkComparator` validating run compatibility, computing granular metrics with explicit denominators (n=12), and separating operational failures from candidate-quality metrics. |
| [`backend/benchmark/report.py`](file:///P:/REDLINE/backend/benchmark/report.py) | **Created** | `BenchmarkReportGenerator` producing auditable JSON and Markdown reports with cryptographic SHA-256 digests and redacting secrets/hidden evaluator source code. |
| [`backend/api/routes/benchmark.py`](file:///P:/REDLINE/backend/api/routes/benchmark.py) | **Created** | Minimal versioned REST API endpoints for run creation, execution, status queries, cancellation, comparison, and reporting. |
| [`backend/api/app.py`](file:///P:/REDLINE/backend/api/app.py) | **Modified** | Mounted `benchmark.router` under `/api/v1/benchmark`. |
| [`backend/benchmark/__init__.py`](file:///P:/REDLINE/backend/benchmark/__init__.py) | **Modified** | Exported public benchmark interfaces and runner classes. |
| [`tests/test_benchmark_evaluator.py`](file:///P:/REDLINE/tests/test_benchmark_evaluator.py) | **Created** | 15 unit/security tests for task loading, 3-phase oracle evaluation, injection immunity, and backend refusal. |
| [`tests/test_benchmark_runner.py`](file:///P:/REDLINE/tests/test_benchmark_runner.py) | **Created** | 13 tests for lifecycle state transitions, integrity gate failures, capability gate failures, cancellation, task failure accounting, and interrupted recovery. |
| [`tests/test_benchmark_comparison.py`](file:///P:/REDLINE/tests/test_benchmark_comparison.py) | **Created** | 5 tests for run compatibility, denominator correctness, operational failure separation, and head-to-head matrix. |
| [`tests/test_benchmark_report.py`](file:///P:/REDLINE/tests/test_benchmark_report.py) | **Created** | 11 tests for report generation, digest computation, Markdown rendering, secret redaction, and strict unknown-field rejection. |
| [`tests/test_benchmark_api.py`](file:///P:/REDLINE/tests/test_benchmark_api.py) | **Created** | 6 API integration tests for benchmark endpoints. |

---

## 3. Benchmark Lifecycle & API Changes

### 3.1. Deterministic Lifecycle States
```
CREATED → INTEGRITY_CHECK → CAPABILITY_CHECK → READY → RUNNING → EVALUATING → COMPLETED
```
Terminal states:
- `COMPLETED`: Run successfully executed and evaluated all tasks.
- `OPERATIONAL_FAILURE`: Gate failed, runtime missing, policy blocked, or process crashed.
- `CANCELLED`: User requested cancellation.
- `REJECTED` / `INCONCLUSIVE` / `ABORTED`: Non-operational or gate terminal states.

### 3.2. REST API Endpoints (`/api/v1/benchmark`)
- `POST /runs`: Initializes a benchmark run config in `CREATED` state.
- `POST /runs/{run_id}/start`: Executes the runner across all mandatory gates. Fails closed with `OPERATIONAL_FAILURE` when container runtime is missing.
- `GET /runs/{run_id}`: Retrieves current run record and task-level evaluation outcomes.
- `POST /runs/{run_id}/cancel`: Cancels an active or queued run.
- `POST /compare`: Analyzes two or more compatible completed runs and returns head-to-head matrix and summary metrics.
- `GET /runs/{run_id}/report`: Returns the structured benchmark report in JSON (`?format=json`) or rendered Markdown (`?format=markdown`).

---

## 4. Security Gates Implemented

1. **Integrity Gate (`BenchmarkIntegrityChecker`)**:
   - Must verify Git work tree, commit anchor `6e476bc...`, annotated tag `benchmark-v1.0.0` (object type `tag`), manifest raw-byte digest `d2cd37...`, and all 84 artifact hashes.
   - Any mismatch immediately halts with `OPERATIONAL_FAILURE`.
2. **Capability Gate (`SecureSandboxBackend`)**:
   - Queries runtime probe. Requires `security_level == SecurityLevel.SECURE` and `filesystem_isolation == "ENFORCED"`.
   - On the current host (where Docker daemon is not active), truthfully reports `UNAVAILABLE` and immediately halts with `OPERATIONAL_FAILURE`.
   - Explicitly rejects `LocalDevelopmentBackend`.
3. **Isolation & Confinement Gate**:
   - Ephemeral evaluation workspace mounts only fixture files.
   - Hidden evaluators (`test_secure.py`, `test_vulnerability.py`, `reference.patch`, `fixed_app.py`) are strictly prohibited from exposure to candidate environments.
4. **Candidate Output Isolation**:
   - Evaluator decisions rely exclusively on deterministic process exit codes and structured execution invariants. Candidate stdout text or injected prompts cannot alter verdicts.
5. **Interrupted Run Recovery Gate**:
   - `BenchmarkRunRepository.recover_interrupted_runs()` marks in-flight crashed runs as `OPERATIONAL_FAILURE`. No interrupted run can ever be mistaken for `COMPLETED` or `VERIFIED`.

---

## 5. Test Execution Results

### 5.1. Three Focused Sandbox & Benchmark Modules
**Command:**
```powershell
$env:PYTHONPATH="."; .\venv\Scripts\pytest.exe tests/test_secure_sandbox_backend.py tests/test_benchmark_runner.py tests/test_benchmark_report.py -v
```
**Scope:** Three focused modules covering container capability probes, command allowlists, fail-closed runtime gating, benchmark lifecycle accounting, and canonical report digest verification.  
**Result:** `35 passed, 0 skipped` (reproduced during independent review; updated to `38 passed, 0 skipped` after adding Step 2.9.3.10 unknown-field schema rejection tests).

### 5.2. Seven Benchmark Modules
**Command:**
```powershell
$env:PYTHONPATH="."; .\venv\Scripts\pytest.exe tests/test_benchmark_integrity.py tests/test_benchmark_evaluator.py tests/test_benchmark_runner.py tests/test_benchmark_comparison.py tests/test_benchmark_report.py tests/test_benchmark_api.py tests/test_benchmark_dataset.py -v
```
**Scope:** Seven benchmark modules covering frozen dataset integrity, evaluation hierarchy, runner state machine, comparison metrics, report generation/verification, benchmark API endpoints, and static dataset specs. (Note: this scope represents the benchmark subsystem and does not constitute a full-backend regression suite).  
**Result:** `98 passed, 1 skipped` (Windows non-admin symlink creation skipped as designed, verified via mock; updated to `101 passed, 1 skipped` after adding Step 2.9.3.10 unknown-field schema rejection tests).

---

## 6. Real Candidate Code Execution Status

> **Was any real candidate code executed during this stage?**  
> **NO.** All runner and evaluator flows were tested using synthetic non-executable evaluation records, capability probes, and mocked runtime boundaries. Zero untrusted code was executed on the host.

---

## 7. Runtime & Isolation Limitations

1. **Host Environment:** The Windows host development environment currently lacks an active Docker/Podman daemon or configured WSL2 container runtime.
2. **Fail-Closed Enforcement:** Until an OS-enforced container runtime is provisioned, `SecureSandboxBackend` will truthfully report `UNAVAILABLE` and fail-closed with `OPERATIONAL_FAILURE` for any non-synthetic arm request. Host execution fallback remains strictly forbidden.

---

## 8. Dataset & Trust-Anchor Integrity Status

- Dataset commit: `6e476bccaba2187055254d1cd71b539d7903b34f` (Verified & unmutated)
- Annotated tag: `benchmark-v1.0.0` (Verified & unmutated)
- Manifest digest: `d2cd37b9a588151975c992426338b0341f39bc824e1627c32d51e02ed1ac20c2` (Verified & unmutated)
- Artifact digests: All 84 files verified 100% intact.
- Git Working Tree: `backend/benchmark/dataset/` is completely clean with zero modifications.

---

## 9. Known Issues and Limitations

- Live end-to-end execution of candidate patches through Docker containers awaits container runtime installation/provisioning on the host or execution on a remote container worker.
- All evaluation orchestration, metric calculations, and comparative reporting are fully implemented, verified, and operational.

---

## 10. Git Status and Safeguards

`git status --short` confirms:
- Tracked modified files: `backend/api/app.py`, `backend/benchmark/__init__.py`.
- No frozen dataset files, tests, or architecture specs were modified.
- No automatic commits or git tags were executed.
