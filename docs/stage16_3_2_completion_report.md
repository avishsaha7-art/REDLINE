# REDLINE — Stage 16.3.2 Completion Report
**Enhanced Artifact Storage**

**Date:** 2026-10-14  
**Stage:** 16.3.2  
**Status:** IMPLEMENTATION COMPLETE — READY FOR INDEPENDENT REVIEW  

---

## 1. Executive Summary & Objective

In Stage 16.3.1, SQLite persistence and a fail-closed restart-recovery protocol were successfully introduced and independently validated. However, raw artifact payload bytes (diff patches, evidence receipts, test execution reports, security findings, and execution event logs) lacked a dedicated durable, secure filesystem storage layer with cryptographic integrity checking and containment defenses.

**Stage 16.3.2** delivers a dedicated, security-hardened artifact storage layer complementing SQLite persistence, strictly aligned with Section 49 ("Storage Architecture") of `docs/REDLINE_v1.1_ARCHITECTURE_FROZEN.md`:
1. **Durable Local Artifact Storage**: Implemented `ArtifactStorage` (`backend/storage/artifacts.py`) to persist raw artifact bytes partitioned safely by `run_id` under a dedicated, configurable root (`REDLINE_ARTIFACTS_DIR` / default `data/artifacts`), while synchronizing metadata and indexes in SQLite (`run_artifacts` table).
2. **Cryptographic Integrity & Verification**: Calculates streaming SHA-256 digests over raw bytes at write time. On retrieval, independently calculates SHA-256 and validates it against the authoritative database record. Fails closed with `ArtifactIntegrityError` if bytes are modified, corrupted, or tampered with.
3. **Safe Filesystem Handling**: Strict path-traversal prevention (`SAFE_ID_REGEX`, `os.path.commonpath`, normalization for Win32 `\\?\` long paths, and `normcase`). Atomic file writes using staging temporary files (`.tmp.{uuid}`), buffer flushes, `os.fsync`, and atomic `os.replace`. Configurable size ceilings (`REDLINE_MAX_ARTIFACT_BYTES`, default 50 MB) enforced prior to write operations. Chunk streaming (`stream_artifact_chunks`) avoids memory exhaustion on large artifacts.
4. **Consistency & Partial-Failure Handling**: In case of a database transaction failure during metadata commit, previously written filesystem files are automatically rolled back and removed, preventing phantom/orphaned files on disk. Database cascades cleanly delete corresponding metadata rows on run deletion, while teardown safely prunes disk trees.
5. **REST API Integration**: Added `/api/v1/runs/{run_id}/artifacts`, `/api/v1/runs/{run_id}/artifacts/{artifact_id}`, and `/api/v1/runs/{run_id}/artifacts/{artifact_id}/content` with standard security response headers (`X-Artifact-ID`, `X-Artifact-SHA256`, `X-Artifact-Size`, `Content-Disposition`, `X-Content-Type-Options: nosniff`), preventing code execution of retrieved content.
6. **Preservation of Core Invariants**: Stage 16.3.1 crash recovery and deterministic verdict authority remain strictly intact. A Judge explanation can never override deterministic evidence. Incomplete, corrupted, or missing evidence never produces a false `VERIFIED` state.

---

## 2. Created and Modified Files

### Files Created:
1. `backend/storage/artifacts.py`:
   - `ArtifactStorage` core implementation.
   - Pydantic models: `ArtifactMetadata`.
   - Domain exceptions: `ArtifactError`, `ArtifactNotFoundError`, `ArtifactIntegrityError`, `ArtifactPathTraversalError`, `ArtifactSizeLimitError`, `ArtifactWriteError`.
   - Helper functions: `get_default_artifacts_root`, `get_max_artifact_bytes`, `get_artifact_storage`, `_normalize_path_for_containment`.
2. `tests/test_stage16_3_2_artifact_storage.py`:
   - 12 comprehensive unit and integration tests covering artifact creation, restart survival, isolation, SHA-256 integrity verification, corrupted byte fail-closed behavior, path traversal attacks, size limits, atomic concurrent writes, database rollback cleanup, lineage preservation, missing disk file fail-closed behavior, REST API endpoints, and required-evidence verdict invariants.
3. `docs/stage16_3_2_completion_report.md`:
   - This architectural completion report.

### Files Modified:
1. `backend/storage/database.py`:
   - Extended `SCHEMA_SQL` with `run_artifacts` table schema and performance indexes (`idx_run_artifacts_run_id`, `idx_run_artifacts_created_at`) with composite primary key `(run_id, artifact_id)`.
2. `backend/storage/repositories.py`:
   - Updated `SQLiteRunRepository.clear()` to clean up `run_artifacts` safely during test isolation and teardown.
   - Added `import sqlite3`.
3. `backend/storage/__init__.py`:
   - Exported `ArtifactStorage`, `get_artifact_storage`, `ArtifactMetadata`, and all artifact exception classes.
4. `backend/api/routes/runs.py`:
   - Registered `_artifact_storage` and exported `get_artifact_storage_instance()` and `set_artifact_storage()`.
   - Implemented `_persist_run_artifacts(run: Run)` to store patch diffs, evidence receipts, test reports, security observation summaries, judge explanations, and execution logs upon run completion or abort.
   - Added REST endpoints:
     - `GET /api/v1/runs/{run_id}/artifacts`: List artifact metadata for a run.
     - `GET /api/v1/runs/{run_id}/artifacts/{artifact_id}`: Retrieve single artifact metadata.
     - `GET /api/v1/runs/{run_id}/artifacts/{artifact_id}/content`: Stream raw bytes with integrity verification and security headers.
   - Updated `reset_run_store()` to clear both SQLite and artifact filesystem storage.
   - Guarded `status_str` against race conditions by checking worker thread liveness (`_threads[run_id].is_alive()`).
5. `docs/REDLINE_IMPLEMENTATION_STATE.md`:
   - Appended Stage 16.3.2 completion summary.

---

## 3. Storage Architecture and Data Flow

```
   ┌───────────────────────────────────────────────────────────────┐
   │                       REDLINE Runtime                         │
   │  (Orchestrator -> Sandbox -> Verifier -> Evidence Builder)    │
   └───────────────────────────────┬───────────────────────────────┘
                                   │
                                   ▼
                   Authoritative State & Metadata
                   ┌───────────────────────────────┐
                   │    SQLite Persistence Layer   │
                   │  - runs                       │
                   │  - run_events                 │
                   │  - run_patches                │
                   │  - run_artifacts (metadata)   │
                   └───────────────┬───────────────┘
                                   │
            Synchronized Atomic    │  Storage Path & SHA-256
            Metadata Registration  │  Integrity Check
                                   ▼
                   ┌───────────────────────────────┐
                   │   ArtifactStorage (Disk)      │
                   │  <artifacts_root>/<run_id>/   │
                   │   ├── diff-patch-1.diff       │
                   │   ├── receipt-<run_id>.json   │
                   │   ├── test-report.json        │
                   │   ├── security-report.json    │
                   │   ├── judge-explanation.json  │
                   │   └── execution-log.json      │
                   └───────────────────────────────┘
                                   ▲
                                   │ Raw Bytes Stream + SHA-256 Check
                                   │
   ┌───────────────────────────────┴───────────────────────────────┐
   │                         REST API Layer                        │
   │  GET /api/v1/runs/{run_id}/artifacts                          │
   │  GET /api/v1/runs/{run_id}/artifacts/{art_id}                 │
   │  GET /api/v1/runs/{run_id}/artifacts/{art_id}/content         │
   └───────────────────────────────────────────────────────────────┘
```

### Storage Directory Structure:
```
data/artifacts/
  └── <run_id>/
        ├── diff-<patch_id>.diff
        ├── receipt-<run_id>.json
        ├── test-report-<run_id>.json
        ├── security-report-<run_id>.json
        ├── judge-explanation-<run_id>.json
        └── execution-log-<run_id>.json
```

---

## 4. Metadata Schema & Integrity Verification Strategy

### SQLite Table Schema:
```sql
CREATE TABLE IF NOT EXISTS run_artifacts (
    artifact_id TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    artifact_type TEXT NOT NULL,
    media_type TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    lineage_ref TEXT,
    metadata_json TEXT,
    PRIMARY KEY (run_id, artifact_id)
);

CREATE INDEX IF NOT EXISTS idx_run_artifacts_run_id ON run_artifacts(run_id);
CREATE INDEX IF NOT EXISTS idx_run_artifacts_created_at ON run_artifacts(created_at DESC);
```

### Cryptographic Integrity Verification:
- **Write Path**: When storing an artifact:
  1. Content bytes are received as `bytes` or `str` (deterministic UTF-8 encoding).
  2. Byte length is verified against `max_bytes` or `REDLINE_MAX_ARTIFACT_BYTES`.
  3. SHA-256 digest is calculated over the raw bytes: `hashlib.sha256(content_bytes).hexdigest()`.
  4. File is written to a temporary staging file `.tmp.{uuid}` on the target partition, flushed, fsynced, and atomically renamed.
  5. Authoritative metadata row is committed to SQLite with the computed `sha256`.
- **Read Path**: When fetching artifact content via API or storage layer:
  1. Authoritative metadata is retrieved from `run_artifacts` using `(run_id, artifact_id)`.
  2. Safe path containment is resolved and verified.
  3. Content is read from disk.
  4. Real-time SHA-256 digest is recalculated from the read bytes.
  5. If `calculated_sha256 != meta.sha256`, the system raises `ArtifactIntegrityError`. The endpoint returns HTTP 500 Internal Server Error with detail: `"Artifact integrity verification failed: cryptographic digest mismatch"` and strictly refuses to return corrupted bytes.
  6. Response headers include `X-Artifact-SHA256: <digest>` and `X-Artifact-Size: <size>`.

---

## 5. Safe Filesystem Handling & Partial-Failure Strategy

### Path Traversal Defense:
1. **Identifier Validation**: Both `run_id` and `artifact_id` are strictly validated against `SAFE_ID_REGEX = ^[a-zA-Z0-9_\.\-]+$`. Any identifier containing `..`, `/`, `\`, or null bytes is immediately rejected with `ArtifactPathTraversalError`.
2. **Path Resolution & Containment**:
   - Computes target path relative to `self.root_dir`.
   - Resolves both `self.root_dir` and `abs_path` via `os.path.realpath`.
   - Normalizes Windows NT extended-length path prefixes (`\\?\`) and applies `os.path.normcase`.
   - Verifies containment via `os.path.commonpath([norm_root, norm_path]) == norm_root`.
   - Rejects any attempted directory escapes, symlinks, or alternate drives with `ArtifactPathTraversalError`.

### Atomic File Writes:
- File writes do NOT directly overwrite destination files.
- Bytes are written to a unique staging file: `<abs_path>.tmp.<uuid>`.
- The file handle is explicitly flushed (`f.flush()`) and synced to physical media (`os.fsync(f.fileno())`).
- The completed temporary file is atomically renamed to `<abs_path>` via `os.replace`.
- In the event of write failure, the staging file is unlinked.

### Database Commit Failure & Rollback:
- If SQLite metadata commit fails after the filesystem write has succeeded, the storage layer catches the database exception and removes the newly written disk file:
  ```python
  except Exception as db_exc:
      if os.path.exists(abs_path):
          try:
              os.remove(abs_path)
          except OSError:
              pass
      raise ArtifactWriteError(f"Database error committing artifact metadata: {db_exc}")
  ```
- This ensures zero orphaned/phantom artifact files exist on disk without corresponding authoritative database metadata.

### Non-Execution Guarantee:
- Stored artifact files are never executed.
- When serving content over HTTP, the endpoint sets `Content-Type: application/octet-stream` (or explicitly designated safe media types) and sets `X-Content-Type-Options: nosniff` and `Content-Disposition: attachment; filename="..."`.

---

## 6. Verification and Regression Gates

All 6 mandatory gates passed completely with zero regressions:

### Gate 1: Stage 16.3.2 Enhanced Artifact Storage Tests
- **Command:** `.\venv\Scripts\python.exe -m pytest tests/test_stage16_3_2_artifact_storage.py -v`
- **Working Directory:** `P:\REDLINE`
- **Result:** Exit Code 0, **15 passed** in 3.48s
  - `test_1_artifact_creation_persistence_and_restart`: PASSED
  - `test_2_stable_artifact_ids_and_run_associations`: PASSED
  - `test_3_sha256_integrity_verification`: PASSED
  - `test_4_corrupted_artifact_bytes_fails_closed`: PASSED
  - `test_5_path_traversal_and_invalid_identifiers_rejected`: PASSED
  - `test_6_configured_size_limits_enforced`: PASSED
  - `test_7_atomic_writes_and_concurrent_access`: PASSED
  - `test_8_metadata_commit_failure_cleans_up_disk_file`: PASSED
  - `test_9_patch_and_evidence_lineage_preservation`: PASSED
  - `test_10_missing_file_on_disk_fails_closed`: PASSED
  - `test_11_api_artifact_endpoints`: PASSED
  - `test_12_required_evidence_missing_preserves_non_success_verdict`: PASSED
  - `test_13_api_corrupted_artifact_returns_500_no_content`: PASSED
  - `test_14_safe_attachment_filename_handling_and_header_injection_defense`: PASSED
  - `test_15_consistent_http_status_codes_for_artifact_endpoints`: PASSED

### Gate 2: Stage 16.3.1 Persistence & Recovery Tests
- **Command:** `.\venv\Scripts\python.exe -m pytest tests/test_stage16_3_1_persistence.py -v`
- **Working Directory:** `P:\REDLINE`
- **Result:** Exit Code 0, **13 passed** in 2.86s

### Gate 3: Stage 16.1 Sandbox Working-Directory Hardening Tests
- **Command:** `.\venv\Scripts\python.exe -m pytest tests/test_stage16_1_working_dir_hardening.py -v`
- **Working Directory:** `P:\REDLINE`
- **Result:** Exit Code 0, **11 passed** in 0.57s

### Gate 4: Stage 15 Security Regression & Demo Scenarios
- **Command:** `.\venv\Scripts\python.exe -m pytest tests/test_stage15_security_regression.py tests/test_stage15_demo_scenarios.py -v`
- **Working Directory:** `P:\REDLINE`
- **Result:** Exit Code 0, **13 passed** in 4.31s

### Gate 5: Full Backend Suite
- **Command:** `.\venv\Scripts\python.exe -m pytest -q`
- **Working Directory:** `P:\REDLINE`
- **Result:** Exit Code 0, **253 passed, 1 skipped** in 25.05s

### Gate 6: Full Frontend Suite
- **Commands:**
  1. `npm test -- --watchAll=false` -> Exit Code 0, **53 passed, 0 failed** in 896ms
  2. `npx tsc --noEmit` -> Exit Code 0 (clean, no type errors)
  3. `npm run lint` -> Exit Code 0 (clean, no linter warnings or errors)
  4. `npm run build` -> Exit Code 0 (production Next.js build completed successfully across all 17 routes)
- **Working Directory:** `P:\REDLINE\frontend`

---

## 7. Remaining Limitations and Known Risks

1. **Local Single-Node Storage Model**:
   - Artifacts are currently persisted to the local filesystem. While fully suitable for single-machine deployment and production MVP, scaling to distributed multi-node clusters will require an S3/Blob storage backend. The `ArtifactStorage` abstraction is structured to facilitate this transition cleanly.
2. **Explicit Garbage Collection / Retention Policy**:
   - Old artifacts remain on disk indefinitely until manually pruned or until the associated run is deleted from the database. Automatic retention lifecycle policies (e.g. 90-day retention) are deferred to future stages.
3. **OS-Level Disk Full Scenarios**:
   - If the underlying physical disk runs out of space during atomic file staging, the operation fails cleanly with `ArtifactWriteError`, and no corrupt or partial records are committed to SQLite.

---

## 8. Confirmation of Architectural Invariants

- **Stage 16.3.1 Behavior**: Intact. SQLite remains the authoritative store for run lifecycle states, event logs, patch candidates, and restart recovery.
- **Deterministic Verdict Authority**: Intact. LLM and Judge opinions remain strictly advisory. A run can never reach `VERIFIED` without an authoritative deterministic `VERIFIED` receipt.
- **Fail-Closed Evidence Integrity**: Intact. If an artifact cannot be verified or its SHA-256 digest fails, it is rejected with an integrity error. Missing or corrupted evidence never yields a false positive.

---

## 9. Stage Status

**IMPLEMENTATION COMPLETE — READY FOR INDEPENDENT REVIEW**
