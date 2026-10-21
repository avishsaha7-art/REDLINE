# REDLINE — STAGE P2-3 IMPLEMENTATION PLAN: COMPARATIVE EVALUATION HARNESS
## Security Remediation Revision (Post Independent Review)

**Date:** 2026-10-15  
**Stage:** Stage P2-3 Comparative Evaluation Harness  
**Current Baseline Commit:** `98f26d3f5f8267b70344c8c905f9b4f1cfb0cceb` (Pre-Dataset Commit)  
**Target Dataset Anchor Commit:** *Pending Dedicated Dataset Commit* (Requires `chore: freeze P2-2 benchmark dataset v1.0.0`)  
**Dataset Version:** `1.0.0` (12 Frozen Tasks under `backend/benchmark/dataset/`)  
**Status:** Preflight Plan — Remediation Revision (Planning & Inspection Only — No Code Modifications)  
**Independent Review Verdict Addressed:** **FAIL** (Independent Architecture & Security Review, 2026-10-15)

---

## 1. Executive Summary & Phasing Context

Stage P2-3 specifies the implementation of a reproducible, authoritative comparative evaluation harness for REDLINE. The objective is to measure and compare the vulnerability detection, repair, and verification capabilities of two distinct execution arms across the 12-task held-out security benchmark dataset developed in Stage P2-2:

- **Arm A (REDLINE Governed Agentic Workflow):** The full multi-agent governance pipeline (Architect → Builder → Red Team → Verifier → Repairer → Advisory Judge) operating under strict state machine transitions, deterministic verification, and cryptographic evidence generation.
- **Arm B (Vanilla LLM Baseline):** A direct, single-turn LLM code generation baseline receiving the identical task contract and candidate-visible repository context, without REDLINE's adversarial verification, iterative repair loops, or multi-agent debate.

### Independent Review Findings & Remediation Mandate

An independent architecture and security review conducted on the initial Stage P2-3 plan returned a **FAIL** verdict based on two critical blocking findings:

1. **False Filesystem Isolation Claim (CRITICAL):**
   The initial plan asserted that `LocalDevelopmentBackend`, `sandbox_root`, `allowed_workspaces`, and `resolve_and_validate_cwd` enforced runtime filesystem boundary isolation. In reality, `LocalDevelopmentBackend` explicitly documents that it provides **no filesystem isolation, no process isolation, and no network isolation** (`backend/sandbox/capabilities.py:15-17`, `backend/sandbox/backend.py:23-32`). `resolve_and_validate_cwd` is merely a pre-launch working directory check. Once a subprocess starts, arbitrary candidate Python code can execute `os.chdir("..")`, use absolute paths, create symlinks, spawn child processes, or invoke Win32 APIs, thereby reading hidden evaluator files (`backend/benchmark/dataset/evaluators/`) and golden reference patches. This invalidates the entire held-out evaluation model.

2. **Incorrect Dataset Commit Anchor (CRITICAL):**
   The initial plan anchored the benchmark dataset to commit `98f26d3f5f8267b70344c8c905f9b4f1cfb0cceb`. Git status inspection reveals that commit `98f26d3` was created during Stage P2-1 lint cleanup and **does not contain the P2-2 dataset files**; all 12 tasks, fixtures, evaluators, and `manifest.json` under `backend/benchmark/dataset/` remain untracked. Anchoring to `98f26d3` would either fail preflight checks or evaluate untracked, mutable files without cryptographic provenance.

3. **Untrusted Workload Refusal (HIGH):**
   `LocalDevelopmentBackend.execute()` enforces a fail-closed gate refusing workloads where `repository_trust != "TRUSTED_DEVELOPMENT"` (`backend/sandbox/backend.py:144-160`). Candidate code is by definition untrusted; executing untrusted code requires a secure backend.

4. **Fair Comparison Confounders (HIGH):**
   Arm A and Arm B must have strictly normalized starting contexts, identical task contracts, comparable resource budget ceilings, recorded provider configurations (`temperature=0.0`, seeds, request IDs), and identical evaluation by the authoritative ground-truth evaluator.

### Core Remediation Principles in this Revised Plan

- **Zero False Isolation Claims:** All claims that `LocalDevelopmentBackend` or working-directory checks provide runtime isolation are eliminated.
- **OS-Enforced Sandbox Prerequisite:** A genuine OS-enforced sandbox backend (`SecurityLevel.SECURE`, `filesystem_isolation="ENFORCED"`) is established as a mandatory prerequisite for executing untrusted candidate code.
- **Fail-Closed Execution Gate:** If an OS-enforced sandbox is unavailable, the benchmark harness **refuses candidate execution** and records an `OPERATIONAL_FAILURE`.
- **Dedicated Dataset Commit Anchor:** Benchmark execution is gated on committing the P2-2 dataset in a dedicated commit, tagging it, and anchoring to that commit SHA and manifest root hash.
- **Authoritative Out-of-Sandbox Evaluator:** Ground-truth evaluation occurs strictly outside the candidate boundary using clean fixtures and hidden tests.
- **Preservation of Core Architecture:** Canonical orchestrator, state machine, deterministic verification policy, and evidence architecture are 100% preserved.

---

## 2. Architecture & Authority Reconciliation

The frozen architecture document ([`docs/REDLINE_v1.1_ARCHITECTURE_FROZEN.md`](file:///p:/REDLINE/docs/REDLINE_v1.1_ARCHITECTURE_FROZEN.md)) governs all decisions in this plan:

- **Section 6 & 7 (Trust Boundaries & Layer Separation):**
  - **Layer A (Untrusted):** Candidate code (both Arm A generated code and Arm B baseline output) resides in the untrusted layer. It must be strictly isolated by OS-enforced boundaries.
  - **Layer B (Controlled Sandbox Execution):** Execution must occur through a secure sandbox backend providing hardware- or kernel-enforced confinement.
  - **Layer C (Deterministic Verifier):** Ground-truth verification occurs out-of-sandbox via deterministic test execution (`test_public.py`, `test_vulnerability.py`, `test_secure.py`).
  - **Layer D (Deterministic Policy):** Final verdicts are assigned by immutable policy logic, not model judgment. Model opinions are strictly advisory and non-authoritative.
- **Section 54 (Benchmark Architecture):**
  - Mandates a held-out benchmark of 10–20 vulnerable tasks (12 tasks frozen in P2-2) comparing the Baseline and the Governed Verification System.
  - Mandates empirical measurement of task success, false acceptances, regressions, iterations, runtime, token consumption, and resource utilization.
- **Section 55 (Baseline Fairness):**
  - Mandates constant parameters: identical repository fixture, identical task description, identical starting code, identical model/version, identical environment constraints, comparable resource budget ceilings, and the identical evaluation harness.
- **Section 56 (Security Test Matrix):**
  - Requires automated regression testing of host isolation, path traversal, symlink attacks, credential isolation, and state/evidence integrity.

---

## 3. Mandatory Security Requirements & Threat Model

### Threat Model: Hostile Candidate Code & Context Leakage

During evaluation, candidate code (either generated by Arm A's builder/repairer or Arm B's direct baseline) is executed in the sandbox. The candidate code must be treated as untrusted and potentially adversarial:

1. **Evaluator Peeking / Cheating:** Candidate code inspects the filesystem to find `test_secure.py`, `test_vulnerability.py`, or `reference.patch` under `backend/benchmark/dataset/evaluators/` to reverse-engineer the hidden test oracle or copy the golden patch.
2. **Filesystem Traversal & Escape:** Candidate code calls `os.chdir("..")`, uses relative paths (`../../evaluators/...`), or accesses absolute paths (`C:\REDLINE\...`) to escape the workspace.
3. **Symlink Attacks:** Candidate code creates symlinks inside the workspace pointing to parent or evaluator directories to bypass path checks.
4. **Subprocess Spawning:** Candidate code spawns child processes or shell commands hoping to escape environment or directory restrictions.
5. **Cross-Task Contamination:** Candidate code drops malicious files, modifies global temp directories, or alters shared state affecting subsequent benchmark tasks.
6. **Model Context Leakage:** Evaluator contents, hidden test names, or reference patch diffs leak into prompt context, tool outputs, logs, or error messages presented to the models.
7. **Dataset Tampering & Drift:** Uncommitted dataset files are modified between runs, silently altering the benchmark without cryptographic traceability.
8. **False Acceptance Manufacture:** Candidate code tampers with test runners, mocks pytest or sys.modules, or emits fake terminal sequences to forge verification.

### Mandatory Security Controls (Requirements 1–10)

| ID | Mandatory Security Requirement | Implementation Mechanism in P2-3 |
| :--- | :--- | :--- |
| **REQ-1** | Candidate environment receives ONLY `fixtures/<task_id>/` | Ephemeral provisioning copies only `fixtures/<task_id>/` into an isolated temporary workspace directory. Zero evaluator files exist in that directory. |
| **REQ-2** | Evaluator files remain strictly outside candidate boundary | Evaluator files and reference patches reside outside candidate directory; `discover_repository` context discovery is anchored strictly to the candidate root; candidate-facing tools have no access to evaluator paths. |
| **REQ-3** | Genuine OS-enforced filesystem isolation required for untrusted execution | `LocalDevelopmentBackend` does NOT provide filesystem isolation. A container-backed or OS-enforced sandbox (`SecurityLevel.SECURE`, `filesystem_isolation="ENFORCED"`) is a mandatory prerequisite for running untrusted candidate code. |
| **REQ-4** | Mandatory Fail-Closed capability gate | If an OS-enforced sandbox backend is unavailable in the execution environment, the benchmark harness refuses candidate execution and reports `OPERATIONAL_FAILURE`. It NEVER executes untrusted candidate code on the host. |
| **REQ-5** | Dedicated Dataset Commit Anchor & Verified Manifest SHA-256 | The untracked P2-2 dataset must be committed in a dedicated Git commit and tagged. The harness anchors to this dedicated commit SHA and the verified SHA-256 digest of `manifest.json`, verifying working-tree cleanliness before execution. |
| **REQ-6** | Automated security isolation test matrix | Automated regression tests verify that path traversal, absolute paths, symlinks, subprocess escapes, cross-task contamination, and hidden evaluator access are strictly blocked by the sandbox. |
| **REQ-7** | Fair comparison controls between Arm A and Arm B | Identical `TaskContract`, identical discovered context string, comparable `ResourceBudget` ceilings, recorded model provider parameters (`temperature=0.0`, fixed seed, request ID), and the same authoritative evaluator. |
| **REQ-8** | Authoritative Out-of-Sandbox Evaluator | Ground-truth verification runs strictly outside the candidate boundary using clean fixtures and hidden tests across three deterministic phases: public regression, vulnerability exploit, and secure invariant. |
| **REQ-9** | Strict 4-way verdict distinction | Outputs strictly classified as `VERIFIED`, `REJECTED`, `INCONCLUSIVE`, or `OPERATIONAL_FAILURE`. Missing sandbox capabilities, timeouts, and crashes are classified as `OPERATIONAL_FAILURE`, never conflated with code rejections. |
| **REQ-10**| Zero architectural divergence | Reuse canonical `Orchestrator`, `StateMachine`, `DeterministicVerificationPolicy`, and `EvidenceAggregator`. Zero modifications to frozen architecture or unauthorized dependencies. |

---

## 4. Evaluation Harness Design

```
+---------------------------------------------------------------------------------------------------+
|                                  BENCHMARK HARNESS CONTROLLER                                     |
|                                                                                                   |
|  1. Verify Dataset Commit Anchor (<DATASET_COMMIT_SHA>) & Manifest SHA-256 Digest                |
|  2. Verify Sandbox Security Capabilities: SecurityLevel.SECURE & filesystem_isolation=ENFORCED    |
|     --> FAIL-CLOSED: If secure sandbox unavailable -> ABORT with OPERATIONAL_FAILURE              |
|  3. Iterate 12 Tasks in Deterministic Order (SEC-BENCH-001 -> SEC-BENCH-012)                     |
+---------------------------------------------------------------------------------------------------+
                               |                                    |
              [PROVISION EPHEMERAL WORKSPACE A]    [PROVISION EPHEMERAL WORKSPACE B]
              (Copy ONLY fixtures/<id>/)           (Copy ONLY fixtures/<id>/)
                               |                                    |
                               v                                    v
            +------------------------------------+  +------------------------------------+
            |               ARM A                |  |               ARM B                |
            |     REDLINE Governed Agentic       |  |      Vanilla Baseline (LLM)        |
            |                                    |  |                                    |
            | - Canonical Orchestrator           |  | - Single-turn Direct Patch Prompt  |
            | - Secure Sandbox Backend           |  | - Secure Sandbox Backend           |
            | - Discovered Context String        |  | - Identical Context String         |
            | - ResourceBudget Enforced          |  | - ResourceBudget Ceiling Enforced  |
            | - Multi-agent Lifecycle            |  | - Direct validate_patch() Check   |
            | - Full State Machine               |  | - Zero Iterative Repair Loops      |
            +------------------------------------+  +------------------------------------+
                               |                                    |
                      Produced: Patch A                    Produced: Patch B
                               |                                    |
                               +-----------------+------------------+
                                                 |
                                                 v
            +----------------------------------------------------------------------------+
            |                   AUTHORITATIVE OUT-OF-SANDBOX EVALUATOR                   |
            |                     (Outside Candidate Trust Boundary)                     |
            |                                                                            |
            |  For each Arm's Patch (against clean reference fixture in fresh sandbox):  |
            |  1. Public Regression: test_public.py            -> MUST PASS              |
            |  2. Vulnerability Exploitation: test_vulnerability.py -> MUST FAIL (Neutralized) |
            |  3. Formal Invariant: test_secure.py             -> MUST PASS (Verified)   |
            |                                                                            |
            |  Deterministic Verdict: VERIFIED | REJECTED | INCONCLUSIVE                 |
            |  Operational Verdict:   OPERATIONAL_FAILURE (if timeout / crash / abort)   |
            +----------------------------------------------------------------------------+
                                                 |
                                                 v
            +----------------------------------------------------------------------------+
            |                    COMPARATIVE METRICS & REPORT AGGREGATOR                 |
            |                                                                            |
            |  - Task Success Rate (n=12)         - False Acceptance Rate                |
            |  - Vulnerability Neutralization Rate- Token & Runtime Consumption          |
            |  - Functional Regression Rate       - Audit Receipts & SHA-256 Provenance  |
            |  - Mandatory Non-Statistical Limitation Disclaimer                         |
            +----------------------------------------------------------------------------+
```

### 4.1 Arm A: REDLINE Governed Agentic Workflow
- **Invocation:** Instantiates standard `Orchestrator(run_id, task_contract, model_provider, sandbox_backend=secure_backend)` with `repository_id` pointing to the ephemeral candidate workspace.
- **Environment:** `REDLINE_REPO_ROOT` points to ephemeral workspace.
- **Workflow:** Runs the full canonical lifecycle: `INIT → RECON → PLAN → BASELINE → BUILD → TEST → ATTACK → ANALYZE → REPAIR → VERIFY → JUDGE → VERIFIED/ABORTED`.
- **Sandbox Boundary:** Subprocess execution within the pipeline flows through the verified secure sandbox backend.
- **Output:** Final state, generated patch lineage, candidate patch, deterministic verification result, and cryptographic evidence receipt.

### 4.2 Arm B: Vanilla LLM Baseline
- **Invocation:** Executes `VanillaBaselineRunner(task_contract, model_provider, sandbox_backend=secure_backend)`.
- **Environment:** Ephemeral workspace identical to Arm A.
- **Context Parity:** Ingests the exact discovered context string generated by `discover_repository` on `fixtures/<task_id>/`.
- **Prompt:** Receives equivalent structured prompt containing task description, allowed scope, constraints, and workspace files:
  ```text
  You are an autonomous software engineering assistant.
  Task: {task_contract.task_description}
  Allowed Scope: {task_contract.allowed_scope}
  Constraints: {task_contract.constraints}
  Workspace Files:
  {untrusted_context}

  Provide your code repair as a JSON object containing 'changed_files' and a unified 'diff'.
  ```
- **Policy Enforcement:** The generated diff is parsed into a `PatchCandidate` and validated using `backend.verification.patch_validation.validate_patch(patch, task_contract)`. If the patch exceeds `max_patch_size`, touches disallowed files, or fails syntax validation, it is rejected with `OperationalResult.POLICY_BLOCKED`.
- **Fairness Ceilings:** Bound by identical `ResourceBudget` (max runtime, max tokens, timeout). A budget monitor tracks usage and terminates execution if ceilings are exceeded.

### 4.3 Sandbox Backend Requirements & Host Capability Investigation

#### Investigation of Current Windows Development Environment
A direct inspection of the host system revealed the following:
1. `docker`: Command not found / Docker Desktop is not installed or not in PATH.
2. `podman`: Command not found / Podman is not installed.
3. `wsl`: WSL is present, but reports: `"Windows Subsystem for Linux has no installed distributions."`
4. `vmcompute`: Hyper-V Host Compute Service exists but is in `Stopped` status.
5. `gVisor` (`runsc`): Requires a Linux kernel/container runtime; not available natively on Windows without Linux VM.
6. `LocalDevelopmentBackend`: Currently the only concrete `SandboxBackend` in the repository, explicitly declaring `filesystem_isolation="NOT_AVAILABLE"`, `process_isolation="NOT_AVAILABLE"`, `network_isolation="NOT_AVAILABLE"`, and `secure_untrusted_execution=False`.

#### Feasible OS-Enforced Sandbox Options for This Environment
To run untrusted candidate code securely, one of the following OS-enforced isolation options must be provisioned:

1. **Option A: Docker Engine / Docker Desktop on Windows (Recommended Standard)**
   - Requires installing Docker Desktop or starting Docker daemon with WSL2 engine.
   - Confinement: Containers mount only the ephemeral workspace directory (`-v <workspace>:/workspace:rw`). Root filesystem is read-only (`--read-only`), network is disabled (`--network none`), memory and CPU limits enforced (`--memory`, `--cpus`), dropped capabilities (`--cap-drop=ALL`). Evaluator directory is physically invisible to the container.

2. **Option B: WSL2 Linux Distro with Container / Sandbox Tools**
   - Requires running `wsl --install -d Ubuntu`.
   - Confinement: Rootless Podman, Docker, or `bubblewrap` (`bwrap`) / Linux user namespaces providing unshare of mount, PID, and network namespaces.

3. **Option C: Windows Native Process Isolation (AppContainer / Restricted Token)**
   - Uses Win32 security APIs (`CreateAppContainerProfile`, `CreateRestrictedToken`, Job Objects).
   - Confinement: Drops all administrative and write tokens; restricts filesystem DACLs such that only the ephemeral directory grants read/write, while all other host directories (including repository root and evaluators) grant ZERO access; Job Object enforces kill-on-close and resource quotas.

4. **Option D: Remote Secure Execution Sandbox Service**
   - As envisioned in Architecture Section 54 / Stage 9.2: offload subprocess execution over gRPC/HTTP to an external Linux/gVisor worker node that returns cryptographically signed `ExecutionResult` payloads.

#### Mandatory Fail-Closed Capability Gate
The harness must query `backend.capabilities()` before executing any candidate code:
```python
def check_sandbox_capabilities_or_fail_closed(backend: SandboxBackend) -> None:
    caps = backend.capabilities()
    if caps.security_level != SecurityLevel.SECURE or caps.filesystem_isolation != "ENFORCED":
        raise OperationalFailureError(
            "FAIL_CLOSED: OS-enforced filesystem isolation is NOT_AVAILABLE. "
            "Untrusted candidate execution is refused on this host. "
            "A container-backed or OS-enforced sandbox is a mandatory prerequisite."
        )
```
If this check fails, the benchmark halts immediately with verdict `OPERATIONAL_FAILURE`. **Under no circumstances will untrusted candidate code be executed via `LocalDevelopmentBackend` on the host.**

### 4.4 Ephemeral Workspace Provisioning & Confinement
1. **Creation:** A fresh temporary directory `workspace_dir` is created under OS temporary storage (or `data/scratch/benchmark_<uuid>`).
2. **File Population:** The contents of `backend/benchmark/dataset/fixtures/<task_id>/` are recursively copied into `workspace_dir`.
3. **Strict Separation:** Zero evaluator files, zero hidden tests (`test_secure.py`, `test_vulnerability.py`), and zero reference patches are copied.
4. **No Upward References:** No symlinks, relative pointers, or git clones referencing the parent repository exist inside `workspace_dir`.
5. **Teardown & Cleanup:** Workspaces are registered in a cleanup registry with `try...finally` deletion, guaranteeing zero disk accumulation even on exceptions.

### 4.5 Authoritative Out-of-Sandbox Evaluator
The candidate arm produces a candidate patch or modified files. Ground-truth evaluation occurs **strictly outside** the candidate's workspace and execution environment:

1. A fresh evaluation workspace is provisioned.
2. The pristine fixture `app.py` is copied into the evaluation workspace.
3. The candidate's patch is applied (or candidate `app.py` copied in).
4. Three distinct evaluation phases are executed via `SandboxBackend.execute` (using trusted evaluator files mounted read-only):
   - **Phase 1: Public Functional Regression**
     - Executes `test_public.py`.
     - Invariant: `exit_code == 0` (No regression of baseline features).
   - **Phase 2: Vulnerability Exploitation Test**
     - Executes `test_vulnerability.py`.
     - Invariant: `exit_code != 0` (The vulnerability exploit MUST FAIL / be neutralized).
   - **Phase 3: Secure Acceptance Invariant Test**
     - Executes `test_secure.py`.
     - Invariant: `exit_code == 0` (The formal security invariant MUST PASS).
5. **Deterministic Verdict Assignment:**
   - `VERIFIED`: Phase 1 PASS + Phase 2 FAIL (neutralized) + Phase 3 PASS.
   - `REJECTED`: Any phase fails its security invariant (regression, exploit persists, or secure invariant fails).
   - `INCONCLUSIVE`: Execution output truncated, contradictory test results, or non-deterministic outcome.
   - `OPERATIONAL_FAILURE`: Execution timed out, crashed, was blocked by security policy, or secure sandbox was unavailable.

### 4.6 Dataset Commit Anchoring & Cryptographic Integrity

To satisfy **Mandatory Requirement 5** and resolve BLOCKER-2 from the independent review:
- The benchmark dataset must be committed to Git in a dedicated commit before benchmark execution:
  - Commit message: `chore: freeze P2-2 benchmark dataset v1.0.0`
  - Tag: `benchmark-v1.0.0`
- The harness defines a hardcoded anchor constant referencing that dedicated commit and the verified manifest digest:
  ```python
  TRUSTED_DATASET_ANCHOR = {
      "dataset_commit_sha": "<ACTUAL_DEDICATED_DATASET_COMMIT_SHA>",
      "manifest_root_sha256": "3cbdd0ea03bb8022a105086d499292a1835db6667e411b7fcf70e3037213898f",
      "dataset_version": "1.0.0",
      "task_count": 12,
  }
  ```
- Before running any evaluations, `integrity.py` performs preflight verification:
  1. Verifies git repository is clean in `backend/benchmark/dataset/` (`git status --porcelain`).
  2. Verifies current git HEAD contains `TRUSTED_DATASET_ANCHOR["dataset_commit_sha"]` as an ancestor.
  3. Verifies `manifest.json` SHA-256 matches `TRUSTED_DATASET_ANCHOR["manifest_root_sha256"]`.
  4. Recalculates all 84 SHA-256 digests in `manifest.json` and verifies 100% match.
  5. If any check fails, aborts execution with `BenchmarkIntegrityError`.

### 4.7 Metrics Collection & Truthful Reporting

The harness collects and compares:
1. **Task Resolution / Verification Rate:** Percentage of tasks achieving authoritative `VERIFIED` status (`verified_count / 12`).
2. **Vulnerability Neutralization Rate:** Percentage of tasks where the exploit test was blocked (`exploit_blocked_count / 12`).
3. **Regression Rate:** Percentage of tasks where public tests failed after repair (`regression_count / 12`).
4. **False Acceptance Count:** Cases where an arm claimed success, but the authoritative evaluator found the vulnerability still exploitable or insecure.
5. **Resource Consumption:** Total iterations, total tool calls, total runtime (seconds and p95), total input/output tokens.
6. **Operational Failure Rate:** Count of timeouts, crashes, policy blocks, or sandbox capability aborts.

#### Truthful Non-Statistical Reporting Requirement
In strict adherence to Section 54:
- The report will state exact, qualified counts:
  > **"X observed secure acceptances on the held-out evaluation set (n=12)."**
- The report will explicitly disclaim general statistical significance:
  > *"Notice: The evaluation set contains n=12 tasks across 12 distinct CWE vulnerability classes. Results demonstrate concrete comparative performance on this held-out set and do not assert statistical significance for general population extrapolation."*

---

## 5. Proposed File-by-File Implementation Plan

All files will be added under `backend/benchmark/`, `backend/sandbox/`, and `tests/`. No modifications to existing frozen architecture files.

```text
backend/sandbox/
├── backend.py                         <- Existing (Preserved unchanged)
├── capabilities.py                    <- Existing (Preserved unchanged)
├── models.py                          <- Existing (Preserved unchanged)
└── secure_backend.py                  <- NEW: Container-backed / OS-enforced SandboxBackend implementation

backend/benchmark/
├── __init__.py                        <- Already exists
├── models.py                          <- Benchmark evaluation data models, result schemas, and anchor definitions
├── integrity.py                       <- Dataset commit anchor and cryptographic digest verification
├── isolation.py                       <- Ephemeral workspace provisioning, capability checking, fail-closed gate
├── evaluator.py                       <- Authoritative out-of-sandbox ground truth evaluation engine
├── arms/
│   ├── __init__.py
│   ├── base.py                        <- Abstract BenchmarkArm interface
│   ├── arm_a_redline.py               <- Arm A: REDLINE Governed Agentic Workflow runner
│   └── arm_b_baseline.py              <- Arm B: Vanilla Single-Turn LLM Baseline runner
├── runner.py                          <- Comparative evaluation orchestrator and report generator
└── reports.py                         <- Markdown & JSON report formatting

tests/
├── test_benchmark_isolation.py        <- Security regression tests proving OS sandbox blocks escape & traversal
├── test_benchmark_integrity.py        <- Tests verifying commit anchor, manifest digest, and tamper detection
├── test_benchmark_evaluator.py        <- Tests for out-of-sandbox evaluator engine & verdict mapping
└── test_benchmark_comparative.py      <- End-to-end comparative evaluation tests (mock provider & fair comparison)
```

### Detailed File Specifications

#### 1. `backend/sandbox/secure_backend.py`
- Implements `SecureSandboxBackend(SandboxBackend)`:
  - Extends canonical `SandboxBackend`.
  - Returns `SandboxCapabilities` with `security_level=SecurityLevel.SECURE`, `filesystem_isolation="ENFORCED"`, `process_isolation="ENFORCED"`, `network_isolation="ENFORCED"`, `secure_untrusted_execution=True`.
  - Executes subprocesses inside an isolated container (Docker/Podman) or OS-enforced boundary with mounted ephemeral directory only.
  - Enforces read-only root, no network, dropped privileges, memory/time limits, and complete filesystem isolation.

#### 2. `backend/benchmark/models.py`
- `ArmType(str, Enum)`: `ARM_A_REDLINE = "ARM_A_REDLINE"`, `ARM_B_VANILLA_BASELINE = "ARM_B_VANILLA_BASELINE"`.
- `TaskEvaluationResult(BaseModel)`: Captures `task_id`, `arm`, `verdict` (`VERIFIED`, `REJECTED`, `INCONCLUSIVE`, `OPERATIONAL_FAILURE`), `operational_result`, `vulnerability_neutralized`, `secure_acceptance_passed`, `regression_passed`, `patch_id`, `patch_sha256`, `runtime_ms`, `iterations`, `tokens_used`, `failure_reason`, `sandbox_provenance`.
- `ComparativeRunReport(BaseModel)`: Captures `benchmark_version`, `dataset_anchor_commit`, `manifest_root_sha256`, `timestamp`, `sandbox_backend_type`, `tasks_evaluated`, `arm_a_summary`, `arm_b_summary`, `head_to_head_matrix`, `disclaimer`.

#### 3. `backend/benchmark/integrity.py`
- `verify_dataset_anchor() -> bool`: Verifies current git commit contains the dedicated dataset anchor commit, verifies manifest root digest, verifies working tree cleanliness in `backend/benchmark/dataset/`.
- `verify_all_task_digests() -> Dict[str, bool]`: Computes and compares SHA-256 for all 84 files against manifest.

#### 4. `backend/benchmark/isolation.py`
- `EphemeralWorkspace`: Context manager provisioning a fresh temporary directory, copying only `fixtures/<task_id>/`, setting strict permissions, and securely cleaning up on exit.
- `enforce_sandbox_security_gate(backend: SandboxBackend) -> None`: Validates backend capabilities; raises `OperationalFailureError` if OS-level filesystem isolation is not enforced.

#### 5. `backend/benchmark/evaluator.py`
- `AuthoritativeEvaluator`: Independent evaluation engine.
  - Takes `task_id` and candidate `PatchCandidate`.
  - Copies clean fixture + candidate patch into fresh evaluator sandbox.
  - Runs `test_public.py`, `test_vulnerability.py`, and `test_secure.py` using secure backend.
  - Returns deterministic boolean results and final 4-way `VerificationStatus`.

#### 6. `backend/benchmark/arms/base.py`
- `BenchmarkArm(ABC)`: Abstract class defining `execute_task(task_id: str, workspace_dir: str, budget: ResourceBudget) -> ArmOutput`.

#### 7. `backend/benchmark/arms/arm_a_redline.py`
- `RedlineArm(BenchmarkArm)`: Constructs `TaskContract`, initializes canonical `Orchestrator` with secure sandbox backend, runs full state machine, extracts patch candidate, execution metrics, and evidence receipt.

#### 8. `backend/benchmark/arms/arm_b_baseline.py`
- `VanillaBaselineArm(BenchmarkArm)`: Ingests workspace context string, queries `ModelProvider` with single-turn prompt, validates patch syntax and scope via `validate_patch`, applies patch to ephemeral workspace using secure backend, and captures runtime/token metrics against resource budget ceiling.

#### 9. `backend/benchmark/runner.py`
- `ComparativeBenchmarkRunner`:
  - Enforces preflight integrity check (`verify_dataset_anchor()`).
  - Enforces preflight sandbox capability gate (`enforce_sandbox_security_gate()`).
  - Iterates 12 tasks in deterministic order.
  - Runs Arm A and Arm B under identical conditions.
  - Invokes `AuthoritativeEvaluator` on both patches.
  - Compiles results into `ComparativeRunReport`.
  - Writes durable JSON and Markdown artifacts under `data/benchmark_reports/`.

---

## 6. Security Invariant to Regression Test Matrix

In accordance with Section 56 and Mandatory Requirement 6, the test matrix maps each security invariant directly to its automated regression test:

| Invariant ID | Security Invariant | Attack / Failure Mode Tested | Regression Test File & Function | Expected Behavior |
| :--- | :--- | :--- | :--- | :--- |
| **INV-SEC-01** | Relative path traversal containment | Candidate executes `../../evaluators/<id>/test_secure.py` | `tests/test_benchmark_isolation.py::test_relative_path_traversal_blocked` | OS sandbox prevents reading parent directory; `PermissionDenied` or `FileNotFoundError` raised; 0 bytes leaked. |
| **INV-SEC-02** | Symlink escape containment | Candidate creates symlink pointing to `backend/benchmark/dataset/evaluators/` | `tests/test_benchmark_isolation.py::test_symlink_escape_blocked` | OS sandbox forbids creating symlink or following out-of-boundary link; access blocked. |
| **INV-SEC-03** | Absolute path access prohibition | Candidate passes absolute host path (`C:\REDLINE\...`) to evaluator file | `tests/test_benchmark_isolation.py::test_absolute_path_evaluator_access_blocked` | OS sandbox filesystem confinement blocks access; returns file not found / access denied. |
| **INV-SEC-04** | Subprocess spawn confinement | Candidate spawns child process (`subprocess.Popen`) attempting traversal | `tests/test_benchmark_isolation.py::test_subprocess_spawn_confined_to_sandbox` | Child process inherits sandbox restrictions; cannot traverse or read host files. |
| **INV-SEC-05** | Ephemeral workspace cross-task isolation | Candidate modifies files or drops artifacts; next task begins | `tests/test_benchmark_isolation.py::test_cross_task_workspace_isolation` | Workspace is cleanly purged; Task 2 ephemeral workspace is completely pristine. |
| **INV-SEC-06** | Context discovery exclusion | `discover_repository` called on candidate workspace | `tests/test_benchmark_isolation.py::test_context_discovery_excludes_evaluators` | Discovered context string contains 0 evaluator files, 0 reference patches, 0 hidden tests. |
| **INV-SEC-07** | Mandatory fail-closed capability gate | Benchmark executed on backend with `filesystem_isolation="NOT_AVAILABLE"` | `tests/test_benchmark_isolation.py::test_insecure_backend_fails_closed` | Benchmark refuses candidate execution; raises `OperationalFailureError`; assigns `OPERATIONAL_FAILURE`. |
| **INV-SEC-08** | Dataset commit anchor verification | Git commit modified or dataset files tampered / untracked | `tests/test_benchmark_integrity.py::test_tampered_dataset_fails_anchor_check` | `BenchmarkIntegrityError` raised; execution refused fail-closed. |
| **INV-SEC-09** | Deterministic evaluator override prevention | Candidate patch attempts to mock pytest or override test runner | `tests/test_benchmark_evaluator.py::test_evaluator_ignores_candidate_mocks` | Evaluator uses external pytest process in fresh sandbox; candidate mocks cannot alter verdict. |
| **INV-SEC-10** | Operational vs Code failure separation | Subprocess times out, crashes, or backend blocked | `tests/test_benchmark_evaluator.py::test_timeout_reports_operational_failure` | Result reports `status=TIMEOUT` / `OPERATIONAL_FAILURE`, strictly separated from `REJECTED`. |
| **INV-SEC-11** | Arm A vs Arm B fair comparison controls | Arm B exceeds token or runtime ceiling; context divergence | `tests/test_benchmark_comparative.py::test_fair_comparison_controls_enforced` | Identical context provided; resource ceilings enforced; provider metadata logged. |
| **INV-SEC-12** | Truthful metrics representation | Aggregator generates scorecard for small sample | `tests/test_benchmark_comparative.py::test_metrics_truthful_non_statistical_reporting` | Scorecard displays exact counts `(n=12)` and includes mandatory statistical limitation notice. |

---

## 7. Blockers, Required Environment Capabilities & Security Risks

### Blocking Issues (Must Be Resolved Before Stage Execution)

1. **BLOCKER 1: Lack of OS-Enforced Sandbox Runtime on Host Development Machine**
   - *Investigation Finding:* The host machine has no Docker daemon running, no Podman, no WSL distributions installed, and the Hyper-V compute service is stopped.
   - *Security Implication:* `LocalDevelopmentBackend` cannot be used for untrusted candidate execution because it lacks OS-level filesystem isolation. Executing untrusted candidate code via host Python would allow candidate code to read hidden evaluators, violating the benchmark security model.
   - *Required Action:* An OS-enforced sandbox runtime (Docker Desktop with WSL2 backend, a WSL2 Linux distribution, or a remote secure sandbox service) must be provisioned and verified before executing untrusted candidate code.
   - *Fail-Closed Policy:* Until a secure backend is available, the benchmark runner must refuse candidate execution and report `OPERATIONAL_FAILURE`.

2. **BLOCKER 2: Untracked P2-2 Benchmark Dataset**
   - *Investigation Finding:* Commit `98f26d3` does not contain the P2-2 benchmark dataset. All dataset files under `backend/benchmark/dataset/` are currently untracked in Git.
   - *Security Implication:* Cryptographic commit anchoring cannot verify dataset provenance against a commit that predates the dataset.
   - *Required Action:* A dedicated dataset commit must be created (`chore: freeze P2-2 benchmark dataset v1.0.0`) and tagged (`benchmark-v1.0.0`). The commit SHA must be recorded in `TRUSTED_DATASET_ANCHOR["dataset_commit_sha"]`.

### Operational & Methodological Risks

1. **Fair Comparison Confounders (Section 55 Compliance):**
   - *Risk:* Arm A executes a multi-agent iterative loop while Arm B executes a single-turn prompt. If resource ceilings or prompt contexts diverge, comparison validity is compromised.
   - *Mitigation:* Both arms receive the identical `TaskContract` and identical discovered context string. Both arms are bound by identical resource budget ceilings (max runtime, max tokens). The prompt for Arm B uses the exact task contract and context provided to Arm A's Architect.
2. **Model Sampling Variance:**
   - *Risk:* Live LLMs exhibit non-deterministic outputs across calls unless sampling parameters are pinned.
   - *Mitigation:* Enforce `temperature=0.0`, fixed random seed where supported by API, and record full request/response metadata (`model`, `seed`, `provider_request_id`, prompt hash, completion hash).
3. **Execution Latency for Full 12-Task Matrix:**
   - *Observation:* Running 12 tasks across both arms takes ~3–5 minutes with deterministic test providers and ~15–20 minutes with live models.
   - *Mitigation:* The runner supports a `--task-id <id>` flag for single-task development testing while enforcing the complete 12-task matrix for official comparative reports.

---

## 8. Acceptance Criteria & Validation Commands

Stage P2-3 implementation will be accepted when:

1. **Dataset Anchor Verified:**
   - Dedicated dataset commit SHA and `manifest.json` SHA-256 verify cleanly via `integrity.py`.
   - Tamper detection verifies that any altered file digest aborts preflight.
2. **Secure Sandbox Capability & Fail-Closed Gate Verified:**
   - `enforce_sandbox_security_gate()` verifies `SecurityLevel.SECURE` and `filesystem_isolation="ENFORCED"`.
   - Running the harness with an insecure backend (or simulated capability failure) deterministically raises `OperationalFailureError` and assigns `OPERATIONAL_FAILURE` without executing candidate code.
3. **Filesystem Isolation Tests Pass:**
   - All isolation regression tests in `test_benchmark_isolation.py` pass against the secure sandbox backend (traversal, absolute paths, symlinks, subprocesses, cross-task contamination, evaluator access).
4. **Authoritative Out-of-Sandbox Evaluator Verified:**
   - `test_benchmark_evaluator.py` passes all unit tests for 3-phase verification and 4-way verdict mapping across all 12 tasks.
5. **Arm A & Arm B Comparative Run Verified:**
   - `test_benchmark_comparative.py` runs both arms under identical context and resource ceilings using `DeterministicTestProvider`.
   - Fair comparison controls, token monitoring, and timeout handling pass validation.
6. **Scorecard & Report Generated:**
   - Complete comparative report generated with exact counts `(n=12)`, zero fabricated metrics, and truthful statistical disclaimer.
7. **Zero Regressions in Existing Suites:**
   - Full backend regression suite (`pytest tests/`) passes with 0 regressions.
   - Frontend test suite (`npm test`), type check (`tsc --noEmit`), and lint (`npm run lint`) pass cleanly.

### Exact Commands for Stage P2-3 Verification
```powershell
# 1. Dataset Integrity & Commit Anchor Test
$env:PYTHONPATH='.'; .\venv\Scripts\pytest tests/test_benchmark_integrity.py -v

# 2. Filesystem Boundary Isolation Regression Tests
$env:PYTHONPATH='.'; .\venv\Scripts\pytest tests/test_benchmark_isolation.py -v

# 3. Out-of-Sandbox Evaluator Tests
$env:PYTHONPATH='.'; .\venv\Scripts\pytest tests/test_benchmark_evaluator.py -v

# 4. Comparative Runner End-to-End Suite
$env:PYTHONPATH='.'; .\venv\Scripts\pytest tests/test_benchmark_comparative.py -v

# 5. Full Backend Regression Suite (Must remain green)
$env:PYTHONPATH='.'; .\venv\Scripts\pytest tests/

# 6. Frontend Test Suite (Must remain green)
cd frontend; npm test; npx tsc --noEmit; npm run lint; cd ..
```

---

## 9. Revised Implementation Order

To maintain strict risk management and fail-closed security, the implementation of Stage P2-3 must proceed in the following revised sequence:

1. **Step 0 (Prerequisite): Commit & Tag P2-2 Benchmark Dataset**
   - Stage and commit `backend/benchmark/dataset/`, `tests/test_benchmark_dataset.py`, and P2-2 documentation:
     ```bash
     git add backend/benchmark/dataset/ tests/test_benchmark_dataset.py docs/stage_p2_2_*.md
     git commit -m "chore: freeze P2-2 benchmark dataset v1.0.0"
     git tag -a benchmark-v1.0.0 -m "Frozen benchmark dataset v1.0.0 for Stage P2-3"
     ```
   - Record the resulting commit SHA and `manifest.json` SHA-256 digest.

2. **Step 1 (Mandatory Prerequisite): Provision Secure Sandbox Backend (`backend/sandbox/secure_backend.py`)**
   - Implement `SecureSandboxBackend` extending `SandboxBackend` with genuine OS-level isolation (`filesystem_isolation="ENFORCED"`, `secure_untrusted_execution=True`).
   - If container runtime (Docker/Podman/WSL) is not available in the environment, implement the capability gate and document that candidate execution is blocked fail-closed.

3. **Step 2: Dataset Anchor & Integrity Engine (`backend/benchmark/integrity.py`)**
   - Implement commit SHA anchoring, git tree status checks, and manifest SHA-256 verification using the dedicated dataset commit.
   - Author `tests/test_benchmark_integrity.py` to confirm tamper detection.

4. **Step 3: Ephemeral Workspace & Fail-Closed Gate (`backend/benchmark/isolation.py`)**
   - Implement ephemeral workspace provisioning (fixtures only) and `enforce_sandbox_security_gate()`.
   - Author `tests/test_benchmark_isolation.py` to verify fail-closed behavior and boundary enforcement.

5. **Step 4: Authoritative Out-of-Sandbox Evaluator (`backend/benchmark/evaluator.py`)**
   - Implement 3-phase ground-truth verification (`test_public.py`, `test_vulnerability.py`, `test_secure.py`) and deterministic 4-way verdict mapping.
   - Author `tests/test_benchmark_evaluator.py`.

6. **Step 5: Arm A & Arm B Adapters with Fair Comparison (`backend/benchmark/arms/`)**
   - Implement `RedlineArm` wrapping canonical `Orchestrator` with secure sandbox backend.
   - Implement `VanillaBaselineArm` wrapping single-turn model provider with identical context, resource budget monitoring, and patch validation.

7. **Step 6: Comparative Benchmark Runner & Reporting (`backend/benchmark/runner.py`, `backend/benchmark/reports.py`)**
   - Implement harness controller, metric computation, and truthful non-statistical markdown/JSON report output.
   - Author `tests/test_benchmark_comparative.py`.

8. **Step 7: Full System Verification & Stage Report**
   - Run complete test matrix, record exact outputs, author `docs/stage_p2_3_completion_report.md`, and present for independent review.
