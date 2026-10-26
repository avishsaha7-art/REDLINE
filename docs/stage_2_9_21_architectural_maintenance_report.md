# Stage 2.9.21 — Non-Breaking Architectural Maintenance Report

**Date:** 2026-10-26  
**System:** REDLINE Autonomous Vulnerability Remediation & Deterministic Verification Platform  
**Environment:** Windows 11 Pro, Python 3.14.8 (pytest 9.1.1), Node.js v20.19.4, Docker Desktop 29.9.1 (`desktop-linux` context)  
**Status:** Complete  
**Stage Verdict:** `MAINTENANCE PASS`

---

## 1. Executive Summary

In accordance with the **REDLINE Architectural Audit & Compliance Assessment** and directives for **Stage 2.9.21**, only justified, low-risk architectural maintenance improvements have been implemented. The core architectural invariant boundaries, security fail-closed protections, deterministic state machine semantics, and the frozen benchmark have been strictly preserved.

### Key Outcomes:
1. **Deterministic Offline Test Isolation**: Isolated tests verifying Docker-unavailable or fail-closed behavior from host environment dependencies by injecting mock runtime probes into offline unit/API tests. Tests no longer fail or become flaky when Docker happens to be running on the developer's workstation. Separate live Docker integration tests remain intact.
2. **SQLite Schema & Conflict Target Alignment**: Diagnosed and resolved the `ON CONFLICT clause does not match any PRIMARY KEY or UNIQUE constraint` warning in `run_artifacts`. Added an authoritative backward-compatible migration (`_migrate_schema`) in `backend/storage/database.py` and declared `uidx_run_artifacts_run_art` on `(run_id, artifact_id)`. Upgraded existing databases while preserving all historical data and verified fresh-database initialization.
3. **Repository Hygiene Confirmed**: Verified that `Degine.md/stitch_poject_redline` is purely design-export material; confirmed zero runtime code references. Preserved in place without disturbing existing git history, `README.md` media links, or milestone reports. Confirmed that scratch directory in the active repo contains only canonical tools (such as `scratch/demo_rehearsal.py`), while ephemeral reproduction scripts were maintained strictly within isolated IDE scratch spaces.
4. **Comprehensive Multi-Suite Verification**:
   - Full Backend Suite: **509 passed**, **2 skipped**, **0 failed** (511 collected) in 212.30s.
   - Frontend Suite: **111 passed**, **0 failed**, **0 skipped** in 5.15s.
   - Benchmark Integrity: **17 passed**, **1 skipped** (Windows symlink privilege test skipped by design); **100% verified** against anchor `6e476bcc...` and manifest `d2cd37b9...` across all 84 artifacts.
   - Offline Demo Rehearsal: **VERIFIED** in 10.1s with cryptographically sealed receipt `5b33e0e7...`.
   - Real Docker Orchestration: Verified live container isolation for an untrusted repository via Docker Desktop.

---

## 2. Baseline State (Phase 1)

### 2.1 Git Status & Commit Baseline
- **Current Branch:** `master`
- **HEAD Commit:** `e6746036b382a427b8f2087e6f7040799eafe207` ("Release REDLINE hackathon submission candidate")
- **Working Tree State:** Retained prior non-breaking test line-ending adjustments (`test_stage7_e2e.py`, `test_stage8a.py`) and documentation reports without resetting, stashing, staging, or committing.

### 2.2 Benchmark Baseline Audit
- **Annotated Tag:** `benchmark-v1.0.0`
- **Target Commit SHA:** `6e476bccaba2187055254d1cd71b539d7903b34f`
- **Manifest Raw-Byte SHA-256:** `d2cd37b9a588151975c992426338b0341f39bc824e1627c32d51e02ed1ac20c2`
- **Artifact Verification:** 84 of 84 artifacts verified with SHA-256 integrity match.
- **Strict Working Tree Status:** Non-strict check passed; zero dataset files modified or untracked.

### 2.3 Pre-Maintenance Backend Suite Execution
- **Command:** `pytest tests/ --tb=short -q`
- **Pre-Change Result:** 499 passed, 10 failed, 2 skipped, 8 warnings in 287.10s (511 collected).
- **Diagnosis of 10 Failures:**
  1. `test_benchmark_api.py::test_api_start_benchmark_run_fails_closed_without_container_runtime`: Failed because Docker was running on the host, causing the capability check to report `SECURE` rather than failing closed to `OPERATIONAL_FAILURE`.
  2. `test_stage8a_security.py::test_fail_closed_untrusted_repository`: Failed because the running Docker engine accepted execution rather than triggering the offline capability gate.
  3. `test_stage8a_security.py::test_orchestrator_gate_prevents_execute_call`: Failed because the client gate permitted execution when Docker was active.
  4. `test_stage15_security_regression.py::test_untrusted_repo_via_api_reaches_policy_blocked`: Failed because the API dispatched to the active Docker container rather than blocking.
  5. `test_stage15_security_regression.py::test_caller_self_promotion_attempt_blocked_at_api_boundary`: Failed for identical runtime detection reasons.
  6. `test_stage15_security_regression.py::test_missing_trust_classification_fails_closed_to_untrusted`: Failed for identical runtime detection reasons.
  7. `test_stage15_security_regression.py::test_malformed_trust_classification_fails_closed`: Failed for identical runtime detection reasons.
  8. `test_stage15_demo_scenarios.py::test_scenario_d_sandbox_security_boundary`: Failed because untrusted request routed to active Docker rather than asserting the offline boundary.
  9. `test_stage16_3_1_persistence.py::test_4_reading_historical_runs_via_api_after_restart`: Timed out after 2.5s because trusted development was routed to Docker without `REDLINE_ENABLE_LOCAL_BACKEND=1`.
  10. `test_stage16_3_2_artifact_storage.py::test_11_api_artifact_endpoints`: Timed out after 2.5s for the same reason.

---

## 3. SQLite Constraint Diagnosis & Correction (Phase 3)

### 3.1 Root Cause Diagnosis
In `backend/storage/artifacts.py:219`, artifact metadata rows are inserted via an UPSERT statement:
```sql
INSERT INTO run_artifacts (
    artifact_id, run_id, artifact_type, media_type, storage_path,
    size_bytes, sha256, created_at, lineage_ref, metadata_json
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(run_id, artifact_id) DO UPDATE SET ...
```
SQLite's UPSERT syntax mandates that the conflict target columns declared in `ON CONFLICT(...)` must match either:
1. A declared `PRIMARY KEY` covering exactly those columns, or
2. A declared `UNIQUE` index covering exactly those columns.

In `P:\REDLINE\data\redline.db` (and legacy databases initialized prior to composite primary key adoption), table `run_artifacts` had been created with:
```sql
CREATE TABLE run_artifacts (
    artifact_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    ...
);
```
Because `Database._initialize()` only ran `CREATE TABLE IF NOT EXISTS`, existing databases retained the legacy single-column primary key on `artifact_id`. Consequently:
- `ON CONFLICT(run_id, artifact_id)` produced SQLite runtime error: `ON CONFLICT clause does not match any PRIMARY KEY or UNIQUE constraint`.
- Every attempt by `backend/api/routes/runs.py` to persist artifacts during API runs was caught and emitted warnings: `Failed to persist artifact metadata in database`.
- All `run_artifacts` inserts in existing databases failed.

### 3.2 Correction Implementation
In `backend/storage/database.py`:
1. **Schema DDL Addition:**
   Added explicit unique index definition matching the conflict target:
   ```sql
   CREATE UNIQUE INDEX IF NOT EXISTS uidx_run_artifacts_run_art ON run_artifacts(run_id, artifact_id);
   ```
2. **Backward-Compatible Migration Method:**
   Implemented `_migrate_schema(self, conn: sqlite3.Connection)`:
   - Inspects `PRAGMA table_info(run_artifacts)`.
   - Checks if `run_id` is part of the primary key. If not (or if `len(pk_cols) < 2`):
     - Safely renames `run_artifacts` to `_run_artifacts_legacy`.
     - Creates `run_artifacts` with composite `PRIMARY KEY (run_id, artifact_id)`.
     - Copies all existing rows using `INSERT OR IGNORE INTO run_artifacts SELECT ... FROM _run_artifacts_legacy`.
     - Drops `_run_artifacts_legacy`.
     - Recreates performance indexes (`idx_run_artifacts_run_id`, `idx_run_artifacts_created_at`) and unique index (`uidx_run_artifacts_run_art`).
3. **Execution on Startup:**
   Called `self._migrate_schema(conn)` in `_initialize()` for both file-based and in-memory databases.

### 3.3 Verification
- Tested migration on `data/redline.db`: verified table schema updated to `PRIMARY KEY (run_id, artifact_id)` and `uidx_run_artifacts_run_art` created.
- Tested UPSERT: confirmed `INSERT INTO run_artifacts ... ON CONFLICT(run_id, artifact_id)` executes with zero warnings and zero errors.
- Both fresh-database initialization and existing-database upgrade verified.

---

## 4. Offline Test Isolation (Phase 2)

### 4.1 Principle
Tests asserting that an untrusted repository fails closed or that an operational failure is reported when no container runtime is available must not depend on whether the developer's machine happens to have Docker running. Conversely, live integration tests exercising real container isolation should continue to execute against the active daemon.

### 4.2 Targeted Isolation Applied
1. **`tests/test_benchmark_api.py::test_api_start_benchmark_run_fails_closed_without_container_runtime`**:
   - Injected monkeypatched `ContainerRuntimeProbe.detect_runtime` returning `(False, "NONE", {"error": "Mocked: container daemon not present"})`.
   - Result: Deterministically tests the `CAPABILITY_CHECK` fail-closed gate and `OPERATIONAL_FAILURE` state.
2. **`tests/test_stage8a_security.py::test_fail_closed_untrusted_repository`**:
   - Injected offline runtime probe returning `(False, "NONE", ...)`.
   - Result: Deterministically tests that untrusted execution without container isolation fails closed with `policy_blocked=True`.
3. **`tests/test_stage8a_security.py::test_orchestrator_gate_prevents_execute_call`**:
   - Injected offline runtime probe.
   - Result: Deterministically verifies that `client.backend.execute` is never invoked when the security gate rejects the workload.
4. **`tests/test_stage15_security_regression.py::clean_store`**:
   - Updated autouse fixture to patch `ContainerRuntimeProbe.detect_runtime` to simulate an unavailable runtime for the 4 API boundary fail-closed tests (`test_untrusted_repo_via_api_reaches_policy_blocked`, `test_caller_self_promotion_attempt_blocked_at_api_boundary`, `test_missing_trust_classification_fails_closed_to_untrusted`, `test_malformed_trust_classification_fails_closed`).
   - Trusted development test (`test_authorized_trusted_development_repo_executes_successfully`) continues to use `LocalDevelopmentBackend` via `REDLINE_ENABLE_LOCAL_BACKEND=1`.
5. **`tests/test_stage15_demo_scenarios.py::test_scenario_d_sandbox_security_boundary`**:
   - Injected offline runtime mock into Scenario D so that the development boundary rejection of untrusted workloads executes deterministically.
6. **`tests/test_stage16_3_1_persistence.py` & `tests/test_stage16_3_2_artifact_storage.py`**:
   - Added `monkeypatch.setenv("REDLINE_ENABLE_LOCAL_BACKEND", "1")` to fixtures `temp_db` and `temp_storage`.
   - Result: Resolves the 2.5s polling timeout; allows fast local mock execution of trusted development test workloads.

---

## 5. Repository Hygiene Decisions (Phase 4)

### 5.1 `Degine.md/stitch_poject_redline`
- **Path Reference Search:**
  - `README.md` lines 190–193 actively link to 4 UI screenshots:
    - `Degine.md/stitch_poject_redline/session_detail_mission_control/screen.png`
    - `Degine.md/stitch_poject_redline/evidence_cryptographic_receipts/screen.png`
    - `Degine.md/stitch_poject_redline/playground_sandbox_deep_dive/screen.png`
    - `Degine.md/stitch_poject_redline/dashboard_overview/screen.png`
  - Over 10 stage reports in `docs/` cite `Degine.md/stitch_poject_redline/`.
  - Zero Python backend code or TypeScript frontend code imports from `Degine.md`.
- **Git Status:** All 50+ files in `Degine.md` are tracked in git under commit `e674603`.
- **Decision:** In accordance with the prompt condition (*"If there is any uncertainty, leave the file in place and document the reason"*), `Degine.md` is left in place. Moving 50+ tracked files in an uncommitted working tree would create a massive deletion/addition git diff churn without any architectural benefit.

### 5.2 Scratch Scripts
- **Audit:** Checked `p:\REDLINE\scratch` for `test_repro.py`, `test_lf.py`, and `test_orch_docker.py`.
- **Finding:** None of these three scripts exist in the repository's `scratch/` directory. They were ephemeral reproduction files created in the external IDE artifact workspace during previous debugging sessions.
- **Canonical Tools Preserved:**
  - `scratch/demo_rehearsal.py` (canonical end-to-end demo rehearsal)
  - `scratch/build_benchmark_dataset.py`
  - `scratch/verify_dataset_freeze.py`
  - `scratch/scan_staged_secrets.py`
  - All canonical rehearsal and verification tools preserved intact.

---

## 6. Verification Results (Phase 5)

| Test Suite | Collected | Passed | Failed | Skipped | Warnings | Execution Time | Verdict |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Full Backend Suite** (`pytest tests/`) | 511 | 509 | 0 | 2 | 8 | 212.30s | **PASS** |
| **Frontend Suite** (`npm test`) | 111 | 111 | 0 | 0 | 0 | 5.15s | **PASS** |
| **Benchmark Integrity** (`test_benchmark_integrity.py`) | 18 | 17 | 0 | 1 | 0 | 51.97s | **PASS** |
| **Security & Sandbox Regressions** (`test_stage8a_security.py`) | 10 | 10 | 0 | 0 | 0 | 11.54s | **PASS** |
| **Security API Regressions** (`test_stage15_security_regression.py`) | 7 | 7 | 0 | 0 | 1 | 7.89s | **PASS** |
| **Persistence & Artifact Storage** (`test_stage16_3_*.py`) | 28 | 28 | 0 | 0 | 1 | 23.37s | **PASS** |
| **Offline Demo Rehearsal** (`scratch/demo_rehearsal.py`) | 1 | 1 | 0 | 0 | 0 | 10.10s | **PASS** |
| **Real Docker Untrusted Orchestration** (Live Container) | 1 | 1 | 0 | 0 | 0 | 12.40s | **PASS** |

### 6.1 Note on Skipped Tests
- `tests/test_stage16_4_orchestrator_execution.py::test_orchestrator_model_failure_fallback_behavior`: Skipped by design (asserts fallback policy pending external model failure hooks).
- `tests/test_stage5.py::test_stage5_stub`: Skipped by design (early stage placeholder).
- `tests/test_benchmark_integrity.py::test_symlink_escape_fails_closed`: Skipped on Windows because unprivileged accounts cannot create symlinks without Developer Mode enabled.

### 6.2 Note on Warnings
- 1 warning: `StarletteDeprecationWarning` regarding `httpx` vs `httpx2` import in Starlette TestClient (third-party package warning).
- 7 warnings: `PytestCollectionWarning` on Pydantic models prefixed with `Test` (`TestResultSummary`, `TestObservation`, `TestStatus`) in `backend/verification/models.py`.
- **0 SQLite warnings**: `ON CONFLICT` mismatch warnings completely eliminated.

---

## 7. Benchmark Integrity Audit (Phase 6)

Executed programmatic verification via `BenchmarkIntegrityChecker(strict_working_tree=False).verify_all()`:
```json
{
  "status": "VERIFIED",
  "dataset_name": "REDLINE-Held-Out-Security-Benchmark",
  "dataset_version": "1.0.0",
  "commit_sha": "6e476bccaba2187055254d1cd71b539d7903b34f",
  "tag_name": "benchmark-v1.0.0",
  "manifest_sha256": "d2cd37b9a588151975c992426338b0341f39bc824e1627c32d51e02ed1ac20c2",
  "tasks_verified": 12,
  "artifacts_verified": 84,
  "checks_passed": [
    "GIT_ANCHOR_VERIFIED",
    "WORKING_TREE_CLEAN",
    "MANIFEST_RAW_BYTE_DIGEST_VERIFIED",
    "ALL_ARTIFACT_DIGESTS_VERIFIED"
  ],
  "failure_reason": null
}
```
**Benchmark Integrity:** 100% frozen, unmutated, and cryptographically verified.

---

## 8. Final Diff Summary

### Modified Files in Stage 2.9.21:
1. `backend/storage/database.py`:
   - Added `uidx_run_artifacts_run_art` index to `SCHEMA_SQL`.
   - Added `_migrate_schema()` to automatically migrate existing legacy `run_artifacts` tables to composite primary key `(run_id, artifact_id)`.
   - Zero changes to queries, schemas, or foreign key semantics in other tables.
2. `tests/test_benchmark_api.py`:
   - Injected offline probe mock into `test_api_start_benchmark_run_fails_closed_without_container_runtime`.
3. `tests/test_stage8a_security.py`:
   - Injected offline probe mock into `test_fail_closed_untrusted_repository` and `test_orchestrator_gate_prevents_execute_call`.
4. `tests/test_stage15_security_regression.py`:
   - Injected offline probe mock into `clean_store` fixture for fail-closed API boundary tests.
5. `tests/test_stage15_demo_scenarios.py`:
   - Injected offline probe mock into `test_scenario_d_sandbox_security_boundary`.
6. `tests/test_stage16_3_1_persistence.py`:
   - Added `monkeypatch.setenv("REDLINE_ENABLE_LOCAL_BACKEND", "1")` to `temp_db` fixture.
7. `tests/test_stage16_3_2_artifact_storage.py`:
   - Added `monkeypatch.setenv("REDLINE_ENABLE_LOCAL_BACKEND", "1")` to `temp_storage` fixture.

**Total Files Changed for Stage 2.9.21:** 7 files.  
**Sweeping Refactors:** None.  
**Core Model / Domain Reorganization:** None.  
**Git Working Tree Status:** Untouched by destructive Git commands; unstaged, uncommitted, unpushed.

---

## 9. Stage 2.9.21 Verdict

$$\mathbf{MAINTENANCE\ PASS}$$

All implemented changes are verified, deterministic offline test isolation is achieved, the SQLite constraint mismatch is resolved with full backward-compatibility and zero data loss, the frozen benchmark is 100% intact, and the full backend and frontend test suites pass with zero failures.
