# Stage 2.9.5.4 Runtime Recovery and Controlled Vertical-Slice Validation Report

## 1. Initial and Final Git Baseline & Working-Tree Status

### Repository Baseline
- **Git Commit HEAD**: `792ace628b9725c75e709522caf023b24f155df0`
- **Current Branch**: `master`
- **Frozen Benchmark Tag**: `benchmark-v1.0.0`
- **Target Benchmark Commit**: `6e476bccaba2187055254d1cd71b539d7903b34f`
- **Benchmark Manifest Root SHA-256**: `d2cd37b9a588151975c992426338b0341f39bc824e1627c32d51e02ed1ac20c2`
- **Benchmark Tag Object Hash**: `a5c6256917839cfe1fff3938ac2bf6d5a4886692`

### Working-Tree Status (`git status --short`)
```text
 M backend/models/deterministic_provider.py
 M backend/orchestrator/orchestrator.py
 M backend/sandbox/client.py
 M backend/sandbox/models.py
 M backend/sandbox/secure_backend.py
 M backend/verification/attack_executor.py
 M backend/verification/observer.py
 D data/artifacts/.gitkeep
 M tests/test_secure_sandbox_backend.py
?? data/fixtures/
?? deploy/
?? docs/stage_2_9_5_1_demo_readiness_audit.md
?? docs/stage_2_9_5_2_orchestrator_execution_remediation_report.md
?? docs/stage_2_9_5_3_runtime_integration_preflight.md
?? docs/stage_2_9_5_4_runtime_vertical_slice_report.md
?? tests/test_stage16_4_orchestrator_execution.py
```
*All existing unstaged modifications, deploy scripts, test fixtures, and prior audit reports have been strictly preserved. No files were staged, committed, or discarded.*

---

## 2. Runtime and Image Identity

### Host Container Runtime Assessment
- **Host OS**: Windows 11 (AMD64 / Windows-x86_64)
- **Docker CLI Location**: `C:\Program Files\Docker\Docker\resources\bin\docker.EXE`
- **Docker CLI Version**: `29.9.1` (API v1.56, Git commit `dfc520d`)
- **Docker Daemon Endpoint**: `npipe:////./pipe/docker_engine`
- **Daemon Accessibility State**: **INACTIVE / UNREACHABLE**
  - Error: `open //./pipe/docker_engine: The system cannot find the file specified.`
- **Underlying Root Cause**:
  - Probing Windows Subsystem for Linux via `wsl -l -v` reveals:
    ```text
    Windows Subsystem for Linux has no installed distributions.
    ```
  - Docker Desktop on Windows requires an operational WSL2 Linux backend or Hyper-V container host. Without installed WSL distributions, Docker Desktop cannot initialize its Linux virtualization engine or open the named pipe.

### REDLINE ContainerRuntimeProbe Findings
- Invocation: `backend.sandbox.secure_backend.ContainerRuntimeProbe.detect_runtime()`
  - `is_operational`: `False`
  - `engine`: `"docker"`
  - `executable`: `C:\Program Files\Docker\Docker\resources\bin\docker.EXE`
  - `error`: `"Daemon unreachable or permission denied"`
  - `stderr`: `"failed to connect to the docker API at npipe:////./pipe/docker_engine; ..."`

### Reviewed Sandbox Image Specification
- **Dockerfile**: [`deploy/sandbox/Dockerfile`](file:///p:/REDLINE/deploy/sandbox/Dockerfile)
- **Target Image Tag**: `redline-sandbox-runner:latest`
- **Upstream Base Image**: `python:3.11-slim-bookworm`
- **Pinned Multi-Arch Index Digest**: `sha256:f06d01d4ba3f8ad5af45a3ec87df19c1d317d8e8961edc0fabda61811af6f7cf`
- **Linux/amd64 Layer Digest**: `sha256:8fb0b110b022c70cbe09d3ff1fb313654f31f9c814abb0d48180af56d906a199`
- **Pinned Dependency Set**:
  - `iniconfig==2.0.0`
  - `packaging==24.1`
  - `pluggy==1.5.0`
  - `pytest==8.3.3`
  - `pytest-json-report==1.5.0`
  - `coverage==7.6.1`
- **Hardening Directives in Image**:
  - Non-root user: `redline` (`UID 1000:GID 1000`)
  - Setuid/setgid bits purged: `find / -perm /6000 -type f -exec chmod a-s {} +`
  - Working directory: `/workspace` (`chown 1000:1000`)
  - Safe default entrypoint: `["python3", "-c", "import sys; sys.exit(0)"]`

---

## 3. Configured vs. Observed Isolation Controls

| Security Control | Specification & Configured Flag | Observable State on Host | Status |
| :--- | :--- | :--- | :--- |
| **Execution Identity** | `--user 1000:1000` (non-root runner) | Verified in `deploy/sandbox/Dockerfile` and `build_container_args()` | **CONFIGURED** |
| **Filesystem Root** | `--read-only` root filesystem | Enforced in `build_container_args()` | **CONFIGURED** |
| **Scratch Space** | `--tmpfs /tmp:rw,noexec,nosuid,size=64m` | Enforced in `build_container_args()` | **CONFIGURED** |
| **Network Isolation** | `--network none` (disabled by default) | Enforced in `build_container_args()` | **CONFIGURED** |
| **Privilege Escalation** | `--cap-drop=ALL --security-opt=no-new-privileges` | Enforced in `build_container_args()` | **CONFIGURED** |
| **Resource Limits** | `--cpus 1.0 --pids-limit 64 --memory 512m` | Bound by server-side `SandboxPolicy` validation | **CONFIGURED** |
| **Workspace Mount** | `-v <canonical_workspace>:/workspace:rw` | Ephemeral `redline_sandbox_*` bind mount | **CONFIGURED** |
| **Runtime Availability** | Container engine daemon connectivity | `probe.detect_runtime()` returns `False` | **UNAVAILABLE** |
| **Host Fallback Gate** | Prohibit host subprocess execution for untrusted tasks | `SecureSandboxBackend.execute()` fails closed with `exit_code=-1`, `policy_blocked=True` | **OBSERVED & VERIFIED** |
| **Local Backend Lock** | `REDLINE_ENABLE_LOCAL_BACKEND=1` | Strictly unset; ignored for `UNTRUSTED` repositories | **OBSERVED & VERIFIED** |

---

## 4. Exact Fixture and Patch Cryptographic Hashes

Validation target: disposable, non-benchmark fixture [`data/fixtures/repo-cons-1`](file:///p:/REDLINE/data/fixtures/repo-cons-1).

- **Defective Baseline File**: [`data/fixtures/repo-cons-1/main.py`](file:///p:/REDLINE/data/fixtures/repo-cons-1/main.py)
  - Content: `old\n`
  - SHA-256 Digest: `01d09d19c2139a46aebfb577780d123d7396e97201bc7ead210a2ebff8239dee`
- **Deterministic Test Suite**: [`data/fixtures/repo-cons-1/test_main.py`](file:///p:/REDLINE/data/fixtures/repo-cons-1/test_main.py)
  - Content: Fails if `main.py == "old"`, exits 0 if patched.
  - SHA-256 Digest: `2be7f342ac2d34a84f8875de9141e586d8992e6bd9acad8cec4b7c2f6c06087c`
- **Corrective Patch**:
  ```diff
  --- a/main.py
  +++ b/main.py
  @@ -1 +1 @@
  -old
  +new
  ```
  - Diff SHA-256 Digest: `d2d00fe6eff534dd191d444aefdbd8beb40fe373134dc845812d55b5e96ecbe3`

---

## 5. Actual Execution Results and Failure-Path Behavior

### Active Host Dynamic Test Result
When the canonical Orchestrator and `SecureSandboxBackend` run against `repo-cons-1` under the active host conditions:
1. `resolve_repository_trust("repo-cons-1")` maps to `TRUSTED_DEVELOPMENT`.
2. Because `REDLINE_ENABLE_LOCAL_BACKEND` is **not enabled**, `get_sandbox_backend()` authoritatively routes to `SecureSandboxBackend`.
3. `SecureSandboxBackend.execute()` checks runtime status:
   - Command: `["python", "test_main.py"]` (passes allowlist check).
   - Probe check: `detect_runtime()` reports daemon unreachable.
   - Fail-closed trigger:
     ```python
     return ExecutionResult(
         run_id=run_id,
         exit_code=-1,
         stdout="",
         stderr="OPERATIONAL_FAILURE: Secure sandbox runtime (Docker/Podman) is UNAVAILABLE. Untrusted candidate execution is refused fail-closed.",
         policy_blocked=True,
         backend_provenance={
             "backend": "SecureSandboxBackend",
             "status": "OPERATIONAL_FAILURE",
             "reason": "RUNTIME_UNAVAILABLE",
             "security_level": "UNAVAILABLE",
             "capabilities": caps.model_dump()
         }
     )
     ```
4. Orchestrator receives `OPERATIONAL_FAILURE`, advances `OperationalResult.POLICY_BLOCKED`, transitions to `RunState.ABORTED`, and synthesizes a signed fail-closed `EvidenceReceipt`.
5. **Observed Host Execution: 0 processes spawned on host.** Candidate code was never executed.

---

## 6. Expected vs. Actual Transition Table

| Scenario | Input Condition | Expected State Transitions | Actual State Transition | Authoritative Verdict |
| :--- | :--- | :--- | :--- | :--- |
| **A. Passing Verification** (Planned) | Clean patch applied in live container | `INIT` &rarr; `PLAN` &rarr; `BUILD` &rarr; `TEST` &rarr; `TESTS_PASSED` &rarr; `ATTACK` &rarr; `VERIFY` &rarr; `JUDGE` &rarr; `VERIFIED` | N/A (Blocked by runtime offline) | `VERIFIED` |
| **B. Failing Candidate** (Tested via double) | Candidate exits code 1 with `AssertionError` | `INIT` &rarr; `PLAN` &rarr; `BUILD` &rarr; `TEST` &rarr; `COUNTEREXAMPLE_FOUND` &rarr; `TEST_FAILED` &rarr; `ABORTED` | `TEST` &rarr; `COUNTEREXAMPLE_FOUND` &rarr; `TEST_FAILED` &rarr; `ABORTED` | `REJECTED` / `INCONCLUSIVE` (Never `VERIFIED`) |
| **C. Invalid Patch** (Tested via double) | Git patch conflict / syntax error | `TEST` &rarr; `PATCH_APPLY_FAILED` &rarr; `COUNTEREXAMPLE_FOUND` &rarr; `TEST_FAILED` &rarr; `ABORTED` | `TEST` &rarr; `PATCH_APPLY_FAILED` &rarr; `COUNTEREXAMPLE_FOUND` &rarr; `TEST_FAILED` &rarr; `ABORTED` | `REJECTED` / `INCONCLUSIVE` (Never `VERIFIED`) |
| **D. Runtime Offline** (**Active Host**) | Docker daemon offline | `TEST` &rarr; `OPERATIONAL_FAILURE` &rarr; `OperationalResult.POLICY_BLOCKED` &rarr; `ABORTED` | `TEST` &rarr; `OPERATIONAL_FAILURE` &rarr; `OperationalResult.POLICY_BLOCKED` &rarr; `ABORTED` | `POLICY_BLOCKED` (Zero host fallback) |
| **E. Timeout** (Tested via double) | Execution exceeds 30s | `TEST` &rarr; `TIMEOUT` &rarr; `OperationalResult.TIMEOUT` &rarr; `ABORTED` | `TEST` &rarr; `TIMEOUT` &rarr; `OperationalResult.TIMEOUT` &rarr; `ABORTED` | `TIMEOUT` (Never `VERIFIED`) |
| **F. Tampered Receipt** (Tested via double) | Merkle root mismatch or altered verdict | `JUDGE` &rarr; `EVIDENCE_INTEGRITY_FAILURE` &rarr; `JUDGE_FAIL` &rarr; `ABORTED` | `JUDGE` &rarr; `EVIDENCE_INTEGRITY_FAILURE` &rarr; `JUDGE_FAIL` &rarr; `ABORTED` | `ABORTED` (Judge cannot override) |

---

## 7. Evidence Receipt Integrity and Verdict Authority

1. **Receipt Cryptographic Invariant**:
   - Every run terminating in `VERIFIED` or `ABORTED` records a structured `EvidenceReceipt` with SHA-256 Merkle root computation over:
     - Task contract hash
     - Repository snapshot hash
     - Patch diff hash
     - Structured observations hash
     - Verification policy result hash
     - Selected attacks hash
   - Evaluated by `backend.models.evidence.verify_receipt_integrity(receipt)`.
2. **Deterministic Verdict Primacy**:
   - An LLM Judge generates natural-language explanations but has **zero authority** over the verdict.
   - `Orchestrator.run()` in `RunState.JUDGE` enforces:
     ```python
     if receipt.verdict == VerificationStatus.VERIFIED:
         self.state_machine.advance("JUDGE_PASS")
     else:
         self.state_machine.advance("JUDGE_FAIL")
     ```
   - If the receipt verdict is `POLICY_BLOCKED`, `INCONCLUSIVE`, or `REJECTED`, the state advances to `JUDGE_FAIL` &rarr; `RunState.ABORTED`.

---

## 8. Test Execution Summary

| Test Suite | Tests Run | Passed | Failed | Skipped | Purpose |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `tests/test_stage16_4_orchestrator_execution.py` | 10 | 10 | 0 | 0 | Remediated Orchestrator real execution gates |
| `tests/test_secure_sandbox_backend.py` | 33 | 32 | 0 | 1 | Container security boundary & fail-closed invariants |
| `tests/test_stage14_3_lifecycle_consistency.py` | 9 | 9 | 0 | 0 | Lifecycle consistency & tamper resistance |
| `tests/test_stage15_demo_scenarios.py` | 6 | 6 | 0 | 0 | Multi-agent demo scenarios & boundary tests |
| **Total Test Invariants** | **58** | **57** | **0** | **1** | **All automated invariants verified** |

*(Skipped test: `test_real_file_symlink_pointing_outside_workspace_if_supported`, skipped on Windows platforms requiring elevated symlink creation privileges).*

---

## 9. Limitations and Unverified Security Claims

1. **Missing Container Daemon on Host**:
   - Live execution inside a running Linux container requires an active Docker daemon.
   - On this host, WSL2 has no installed distributions. Docker Desktop cannot start without user intervention to install a WSL2 distro (e.g., `wsl --install Ubuntu`) or enable Windows Hyper-V containers.
2. **Unverified Live Kernel Controls**:
   - Because live containers could not be launched on this host, Linux kernel-level cgroups enforcement (`--cpus`, `--memory`, `--pids-limit`, tmpfs mount flags) could not be directly observed via `/sys/fs/cgroup` during this run.
   - These controls are verified by argument construction tests and Docker specification audits, but remain dynamically unverified in live kernel execution on this machine.
3. **Reactive Disk Measurement Limitation (Findings F-01 & F-02)**:
   - Post-execution disk measurement is reactive. Docker bind mounts do not enforce proactive write quotas during execution without host project quotas or loopback volumes.

---

## 10. Final Verdict

### Final Verdict: **BLOCKED**

### Rationale:
1. **Container Runtime Unreachable**: The host Docker daemon is offline because WSL2 has no installed Linux distributions.
2. **Zero Host Fallback Enforced**: In accordance with REDLINE frozen invariants, candidate code was **not** executed on the host, and `REDLINE_ENABLE_LOCAL_BACKEND=1` was **not** enabled as a workaround.
3. **Controlled Fail-Closed Behavior**: The Orchestrator and `SecureSandboxBackend` performed strictly as designed: untrusted execution was refused, operational failure was truthfully reported, and state transitions remained fail-closed.
4. **Resolution Path**: To transition from `BLOCKED` to `PASS`, the user must install a WSL2 distribution (e.g. `wsl --install -d Ubuntu`) or configure the Docker daemon, after which `deploy/sandbox/Dockerfile` can be built and live container slice execution can proceed.
