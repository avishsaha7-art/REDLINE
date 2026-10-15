# REDLINE Held-Out Security Benchmark Dataset (v1.0.0)

## Overview

The REDLINE Held-Out Security Benchmark Dataset is a frozen, reproducible, hermetically testable dataset designed to evaluate autonomous AI software engineering platforms (such as REDLINE) on vulnerability detection, repair, and deterministic verification.

This dataset was created during **Stage P2-2** in accordance with Section 54 of the frozen architecture document (`docs/REDLINE_v1.1_ARCHITECTURE_FROZEN.md`) and the post-UI-A7 baseline audit.

## Key Design Principles

1. **Deterministic Ground Truth**: Every task defines an explicit security invariant and reproducible acceptance tests. Code correctness is verified using pytest and deterministic invariants—never LLM self-evaluation or subjective text review.
2. **Evaluator Isolation**: Candidate-visible files (`fixtures/<task_id>/`) contain only the vulnerable application and public regression tests. Evaluator ground-truth tests (`evaluators/<task_id>/test_vulnerability.py`, `evaluators/<task_id>/test_secure.py`) and reference patches are stored separately in `evaluators/` and must not be exposed to candidates during evaluation.
3. **Hermetic & Safe**: All fixtures are synthetic, local-only Python testbeds requiring zero external network connectivity, zero external services/daemons, and zero production credentials. They can run cleanly on Windows or Linux inside any isolated sandbox.
4. **Frozen & Cryptographically Verified**: Every artifact in the dataset is tracked with its SHA-256 digest in `manifest.json`. Any unintended modification or tampering is immediately detectable.

## Taxonomy & Tasks (12 Tasks)

| Task ID | Category | CWE | Severity | Target File | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `SEC-BENCH-001` | `SQL_INJECTION` | CWE-89 | CRITICAL | `app.py` | String-concatenated search query allows authentication and data extraction bypass. |
| `SEC-BENCH-002` | `PATH_TRAVERSAL` | CWE-22 | HIGH | `app.py` | Missing root path containment check allows reading and writing outside storage vault. |
| `SEC-BENCH-003` | `RACE_CONDITION` | CWE-362 | HIGH | `app.py` | Check-then-act balance decrement allows concurrent overdrafts in wallet ledger. |
| `SEC-BENCH-004` | `AUTH_BYPASS` | CWE-287 | CRITICAL | `app.py` | Unverified `algorithm="none"` header and unverified claims in token authentication. |
| `SEC-BENCH-005` | `IDOR_ACCESS_CONTROL` | CWE-639 | HIGH | `app.py` | Insecure direct object reference exposes sensitive user profile documents to other users. |
| `SEC-BENCH-006` | `CACHE_INVALIDATION` | CWE-403 | MEDIUM | `app.py` | Role changes do not invalidate authorization session cache, retaining revoked access. |
| `SEC-BENCH-007` | `RESOURCE_LEAK` | CWE-404 | MEDIUM | `app.py` | Unclosed file descriptors during bulk processing lead to descriptor exhaustion. |
| `SEC-BENCH-008` | `COMMAND_INJECTION` | CWE-78 | CRITICAL | `app.py` | Shell concatenation in diagnostic ping endpoint allows arbitrary command execution. |
| `SEC-BENCH-009` | `DUPLICATE_TRANSACTION` | CWE-799 | HIGH | `app.py` | Missing idempotency verification allows replay and double-execution of charges. |
| `SEC-BENCH-010` | `UNBOUNDED_PAGINATION` | CWE-770 | MEDIUM | `app.py` | Query endpoints without maximum limit ceiling cause denial of service memory spike. |
| `SEC-BENCH-011` | `PRIVILEGE_ESCALATION` | CWE-269 | HIGH | `app.py` | Unsanitized request dictionary merges into tenant user state, allowing self-promoted roles. |
| `SEC-BENCH-012` | `SECRET_LEAKAGE` | CWE-532 | HIGH | `app.py` | Debug logs dump authorization tokens and sensitive credentials in cleartext. |

## Dataset Layout

```
backend/benchmark/dataset/
├── manifest.json                  # Top-level manifest with SHA-256 digests and task metadata
├── schema.json                    # Formal JSON Schema for benchmark task specifications
├── README.md                      # This documentation
├── tasks/                         # Task metadata & contracts
│   ├── SEC-BENCH-001.json
│   └── ... (SEC-BENCH-002 through 012)
├── fixtures/                      # Candidate-visible starting fixtures
│   ├── SEC-BENCH-001/
│   │   ├── app.py                 # Intentionally vulnerable starting source code
│   │   └── test_public.py         # Legitimate regression tests (candidate can run)
│   └── ... (SEC-BENCH-002 through 012)
└── evaluators/                    # Ground-truth tests & reference patches (evaluator-only)
    ├── SEC-BENCH-001/
    │   ├── test_vulnerability.py  # Passes against vulnerable code (verifies exploitability)
    │   ├── test_secure.py         # Passes against secure code, fails against vulnerable code
    │   ├── reference.patch        # Unified diff applying minimal secure patch
    │   └── fixed_app.py           # Golden reference implementation satisfying all invariants
    └── ... (SEC-BENCH-002 through 012)
```

## Task Specification Schema

Each `tasks/<task_id>.json` file complies with `schema.json` and defines:

- `task_id`: Unique identifier formatted as `SEC-BENCH-###`.
- `dataset_version`: Dataset semver (e.g., `1.0.0`).
- `category`: Vulnerability category from the canonical taxonomy enum.
- `severity`: `LOW`, `MEDIUM`, `HIGH`, or `CRITICAL`.
- `title` & `description`: Clear description of the vulnerability and subsystem.
- `cwe_id`: Common Weakness Enumeration ID (e.g., `CWE-89`).
- `repository_fixture`: Relative path to candidate fixture workspace.
- `target_file`: Relative file path within fixture where fix is required.
- `allowed_scope`: List of files permitted to be modified during repair.
- `security_invariant`: Formal statement of the security requirement.
- `expected_vulnerable_behavior`: Documented flaw and exploit trigger.
- `required_secure_behavior`: Required secure handling and edge-case behavior.
- `candidate_visible_tests`: Tests provided to candidate agent.
- `evaluator_tests`: Hidden ground-truth tests (`vulnerability_test` and `secure_acceptance_test`).
- `reference_patch`: Relative path to verified minimal patch.
- `provenance`: Author metadata, review status, and environmental limitations.

## Evaluator Protocol & Testing Phases

For any benchmark evaluation cycle (to be executed by runners in stage P2-3):

1. **Pre-Flight / Baseline Check**:
   - `test_vulnerability.py` MUST PASS on the starting fixture (`app.py`). This guarantees the vulnerability is truly present and reproducible.
   - `test_secure.py` MUST FAIL on the starting fixture (`app.py`). This guarantees the acceptance criteria cannot pass against unpatched code.
   - `test_public.py` MUST PASS on the starting fixture (`app.py`). This guarantees baseline application behavior is working.
2. **Candidate Execution**:
   - Candidate is given `fixtures/<task_id>/` and `tasks/<task_id>.json` (sanitized without evaluator references).
   - Candidate modifies only files within `allowed_scope`.
3. **Post-Repair Verification**:
   - `test_public.py` MUST PASS on the candidate-repaired code (no functional regressions).
   - `test_vulnerability.py` MUST FAIL on the candidate-repaired code (exploit vector is eliminated).
   - `test_secure.py` MUST PASS on the candidate-repaired code (formal security invariant satisfied).

## Resetting Fixtures

To reset a fixture to its initial frozen baseline:
- Re-copy `fixtures/<task_id>/app.py` from the frozen baseline or revert via git (`git checkout -- backend/benchmark/dataset/fixtures/<task_id>/app.py`).
- Validate file integrity against `manifest.json` using the automated dataset test suite.
