# REDLINE — STAGE P2-2 IMPLEMENTATION PLAN: HELD-OUT SECURITY BENCHMARK DATASET

**Date:** 2026-10-15  
**Stage:** Stage P2-2 Held-Out Security Benchmark Dataset  
**Baseline Commit:** `98f26d3f5f8267b70344c8c905f9b4f1cfb0cceb` (`chore: resolve frontend lint diagnostics`)  
**Status:** Preflight Plan  

---

### 1. Objective & Scope

As identified in the post-UI-A7 baseline audit and Section 54 of [`docs/REDLINE_v1.1_ARCHITECTURE_FROZEN.md`](file:///p:/REDLINE/docs/REDLINE_v1.1_ARCHITECTURE_FROZEN.md), REDLINE requires a dedicated, frozen security benchmark dataset containing 10–20 vulnerable software tasks across major defect classes.

**Stage P2-2 Scope:**
- Assemble and freeze a dataset of **12 distinct, high-quality, reproducible software security benchmark tasks**.
- Implement a versioned schema, manifest, SHA-256 integrity digests, candidate-visible fixtures, evaluator-only tests, and reference secure patches.
- Create an automated test suite [`tests/test_benchmark_dataset.py`](file:///p:/REDLINE/tests/test_benchmark_dataset.py) verifying manifest validity, structural isolation, vulnerability reproducibility, secure acceptance execution, anti-tampering digests, and zero secret leakage.
- Author documentation in `backend/benchmark/dataset/README.md` and [`docs/stage_p2_2_completion_report.md`](file:///p:/REDLINE/docs/stage_p2_2_completion_report.md).
- **Strict Boundaries:** Do NOT implement the comparative benchmark runner (Arm A vs. Arm B) or any benchmark API endpoints in this stage. Do NOT modify the core orchestrator, sandbox, or frontend. Do NOT commit automatically.

---

### 2. Dataset Architecture & Organization

The benchmark dataset will be organized under `backend/benchmark/dataset/` with clear physical separation between candidate-visible workspace fixtures and evaluator-only ground truth:

```text
backend/benchmark/dataset/
├── README.md
├── schema.json               <- Formal JSON Schema for benchmark tasks
├── manifest.json             <- Manifest listing all 12 tasks with SHA-256 digests
├── tasks/                    <- Task contracts and metadata
│   ├── SEC-BENCH-001.json
│   ├── ...
│   └── SEC-BENCH-012.json
├── fixtures/                 <- Candidate-visible vulnerable codebases & public tests
│   ├── SEC-BENCH-001/
│   │   ├── app.py
│   │   └── test_public.py
│   └── ...
└── evaluators/               <- Evaluator-only ground truth (vulnerability exploit, secure invariant, reference patch)
    ├── SEC-BENCH-001/
    │   ├── test_vulnerability.py
    │   ├── test_secure.py
    │   └── reference.patch
    └── ...
```

---

### 3. Task Catalog & Vulnerability Taxonomy (12 Tasks)

| Task ID | Flaw Category | CWE | Target Component | Vulnerability Mechanism | Invariant & Ground Truth |
|---------|---------------|:---:|------------------|-------------------------|--------------------------|
| `SEC-BENCH-001` | SQL Injection | CWE-89 | `user_portal/app.py` | String formatting into raw SQLite query | Query parameterization; SQL injection payloads (`' OR 1=1 --`) treated as literal data |
| `SEC-BENCH-002` | Path Traversal | CWE-22 | `file_vault/app.py` | Unchecked `os.path.join` with untrusted filename | Canonical path boundary enforcement; `../` sequences rejected |
| `SEC-BENCH-003` | Race Condition | CWE-362 | `wallet_ledger/app.py` | Check-then-act balance debit without atomic lock | Thread synchronization / atomic deduction; overdraft prevented under concurrency |
| `SEC-BENCH-004` | Authentication Bypass | CWE-287 | `auth_gateway/app.py` | Accepts JWT with `"alg": "none"` or missing signature | Strict cryptographic signature validation; `none` algorithm rejected |
| `SEC-BENCH-005` | Insecure Direct Object Reference | CWE-639 | `document_service/app.py` | Entity lookup by ID without tenant/owner authorization | Tenant isolation check (`doc.owner_id == caller.id`); unauthorized fetch yields 403 |
| `SEC-BENCH-006` | Cache Invalidation Defect | CWE-300 | `session_cache/app.py` | Revocation updates database but leaves cached authorization token valid | Immediate cache eviction / version bump on credential revocation |
| `SEC-BENCH-007` | Resource Leak | CWE-400 | `log_streamer/app.py` | Unclosed file handles across error paths in stream processor | Context manager cleanup (`with open(...)`); open file descriptors bounded |
| `SEC-BENCH-008` | Command Injection | CWE-78 | `system_diagnostics/app.py` | `shell=True` invocation with concatenated user host parameter | `shell=False` tokenization and strict hostname/IP format regex |
| `SEC-BENCH-009` | Non-Idempotent Transaction | CWE-799 | `payment_webhook/app.py` | Webhook handler processes transfer without deduplication key check | Idempotency key tracking; duplicate transfer payload returns cached receipt |
| `SEC-BENCH-010` | Unbounded Pagination (DoS) | CWE-770 | `analytics_api/app.py` | Raw `limit` integer passed directly into SQL query without ceiling | Hard upper bound ceiling (`min(max(1, limit), 100)`); prevents memory exhaustion |
| `SEC-BENCH-011` | Authorization Privilege Escalation | CWE-276 | `admin_rbac/app.py` | Default fallback allows action when user role is unknown | Default-deny (fail-closed) access control; admin endpoints require verified role |
| `SEC-BENCH-012` | Sensitive Token Leakage | CWE-532 | `webhook_dispatcher/app.py` | Error handler dumps full HTTP headers and tokens into logs and responses | Sensitive header sanitization (`Authorization`, `token`, `key` scrubbed) |

---

### 4. Implementation Details

1. **Manifest & Schema:**
   - Define `schema.json` validating task structure (ID, category, severity, paths, invariants, digests).
   - Compute real SHA-256 hex digests for all fixture files, evaluator scripts, and reference patches in `manifest.json`.
2. **Hermetic Task Fixtures:**
   - Pure Python 3 standard library / pytest compatible code.
   - Self-contained, zero network calls, zero external API keys or credentials.
3. **Independent Ground Truth Verification:**
   - Every task includes:
     - `test_vulnerability.py`: Reproduces the security flaw, asserting failure against the vulnerable fixture.
     - `test_secure.py`: Asserts that the security invariant holds and legitimate usage succeeds.
     - `reference.patch`: An expertly crafted minimal diff fixing the flaw. Applying it causes `test_vulnerability.py` to pass (or report the attack neutralized) and `test_secure.py` to pass.
4. **Automated Validation Test Suite (`tests/test_benchmark_dataset.py`):**
   - Validates manifest schema compliance and dataset version (`1.0.0`).
   - Asserts uniqueness of task IDs and deterministic sort order.
   - Verifies SHA-256 integrity digests of all files match the manifest.
   - Verifies no directory escape / path traversal in file references.
   - Scans dataset files for accidental secrets, passwords, private keys, or API tokens.
   - Executes vulnerability reproduction on each vulnerable fixture to confirm flaws are genuine and reproducible.
   - Verifies each reference patch applies cleanly and satisfies secure acceptance criteria.

---

### 5. Verification Gates

1. Run dataset validation tests:
   `pytest tests/test_benchmark_dataset.py`
2. Run full backend regression suite to confirm zero regressions:
   `pytest tests/`
3. Run frontend tests to confirm zero regressions:
   `npm test` in `frontend/`
4. Inspect `git status` and working-tree diff.
5. Create `docs/stage_p2_2_completion_report.md`.
6. Stop and present for independent review without committing.
