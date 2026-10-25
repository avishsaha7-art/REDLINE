# Stage 2.9.6.4 — Architect Structured-Output Remediation and Live End-to-End Validation Report

**Date**: 2026-10-25  
**Stage**: 2.9.6.4  
**Stage Verdict**: **PASS**  
**Live End-to-End Validation**: **PASS**  
**Baseline HEAD**: `792ace628b9725c75e709522caf023b24f155df0`  
**Branch**: `master`  
**Frozen Benchmark Tag**: `benchmark-v1.0.0` (commit `6e476bccaba2187055254d1cd71b539d7903b34f`)  
**Frozen Benchmark Manifest SHA-256**: `d2cd37b9a588151975c992426338b0341f39bc824e1627c32d51e02ed1ac20c2` (84/84 artifacts verified)  

---

## 1. Executive Summary

In Stage 2.9.6.4, REDLINE diagnosed and remediated the structured-output schema mismatch observed during live Nebius Token Factory inference in Step 2.9.6.3. Following strict, bounded schema hardening and targeted unit regression validation, REDLINE executed a genuine, bounded live end-to-end task using live Nebius inference (`nvidia/Nemotron-3_5-Lightning`), the canonical `Orchestrator`, `SecureSandboxBackend` in Docker Desktop (`redline-sandbox-runner:latest`), deterministic test verification, and cryptographic evidence receipt generation.

### Primary Results:
1. **Schema Mismatch Remediated**:
   - `ArchitectPlan` strictly forbids unknown fields (`extra="forbid"`).
   - Added bounded field validators on list fields (`acceptance_criteria`, `constraints`, `risks`, `implementation_steps`, `expected_tests`) that safely normalize single descriptive strings emitted by LLMs into single-item lists without weakening schema constraints or converting non-strings.
   - Enhanced Architect agent prompt to explicitly instruct JSON object output with list fields and added robust fenced codeblock parsing with outer-bracket fallback extraction.
2. **Comprehensive Regression Suite**:
   - 10 targeted regression tests in `tests/test_architect_structured_output.py` covering all 10 required conditions (valid plans, normalized string fields, malformed JSON, missing fields, unexpected extra fields, empty/primitive plans, provider timeouts, sandbox isolation, verdict authority, and receipt integrity).
   - All 10 targeted tests passed.
   - Full regression suite across orchestrator, lifecycle, provider, and sandbox components: **129 passed, 1 skipped, 0 failed**.
3. **Live End-to-End Validation Success**:
   - Outbound live inference call to Nebius Token Factory (`https://api.tokenfactory.nebius.com/v1/chat/completions`) using model `nvidia/Nemotron-3_5-Lightning`.
   - `ArchitectAgent` generated a valid, normalized `ArchitectPlan`.
   - `BuilderAgent` generated a valid `PatchCandidate` (`PATCH-6C5437B2`) modifying `main.py`.
   - `SecureSandboxBackend` executed tests inside Docker container `redline-sandbox-runner:latest` with `--network none` and `environment={}`.
   - Test execution (`python test_main.py`) passed cleanly (**Exit Code 0**, stdout: `"1 passed"`, runtime 7,545 ms).
   - Deterministic verification approved the patch, and the canonical Orchestrator reached final state **`VERIFIED`**.
   - Generated tamper-evident `EvidenceReceipt` signed with hash `2bdaedbd5f6501b39792433151985dab20dce0c0ef9b6eefe57df950fd807c9c`; cryptographic integrity verified (`verify_receipt_integrity == True`).
4. **Deterministic Authority & Untrusted Model Proven**:
   - When the downstream `Judge` agent output failed schema validation on live model output (`JUDGE_FAILURE`), the deterministic verification policy remained the sole verdict authority, cleanly completing workflow transition to `VERIFIED`.
5. **Zero Secret Disclosure & Isolation Preserved**:
   - `NEBIUS_API_KEY` remains gitignored in `.env` and was never printed, logged, or passed into candidate containers.

---

## 2. Git Baseline and Working-Tree Preservation

| Check | Expected | Actual | Status |
| :--- | :--- | :--- | :--- |
| **Commit HEAD** | `792ace628b9725c75e709522caf023b24f155df0` | `792ace628b9725c75e709522caf023b24f155df0` | Preserved |
| **Branch** | `master` | `master` | Preserved |
| **Benchmark Tag** | `benchmark-v1.0.0` | `object 6e476bccaba2187055254d1cd71b539d7903b34f` | Verified |
| **Manifest Digest** | `d2cd37b9a588151975c992426338b0341f39bc824e1627c32d51e02ed1ac20c2` | `d2cd37b9a588151975c992426338b0341f39bc824e1627c32d51e02ed1ac20c2` | Verified (84/84 artifacts) |
| **Integrity Engine** | `verify_dataset_anchor()` | Status: `VERIFIED`, 4/4 checks passed, 84 artifacts | Verified |

### Final Git Status (`git status --short`):
```text
 M backend/agents/architect.py
 M backend/agents/builder.py
 M backend/models/deterministic_provider.py
 M backend/models/nebius_provider.py
 M backend/models/schemas.py
 M backend/orchestrator/orchestrator.py
 M backend/sandbox/client.py
 M backend/sandbox/models.py
 M backend/sandbox/secure_backend.py
 M backend/verification/attack_executor.py
 M backend/verification/observer.py
 D data/artifacts/.gitkeep
 M tests/test_model_providers.py
 M tests/test_secure_sandbox_backend.py
?? data/fixtures/
?? deploy/
?? docs/stage_2_9_5_1_demo_readiness_audit.md
?? docs/stage_2_9_5_2_orchestrator_execution_remediation_report.md
?? docs/stage_2_9_5_3_runtime_integration_preflight.md
?? docs/stage_2_9_5_4_runtime_vertical_slice_report.md
?? docs/stage_2_9_5_5_docker_diagnostics_report.md
?? docs/stage_2_9_5_6_docker_recovery_report.md
?? docs/stage_2_9_5_7_docker_service_verification_report.md
?? docs/stage_2_9_5_8_sandbox_image_audit_report.md
?? docs/stage_2_9_5_9_vertical_slice_validation_report.md
?? docs/stage_2_9_6_0_nebius_model_integration_report.md
?? docs/stage_2_9_6_1_live_nebius_validation_report.md
?? docs/stage_2_9_6_2_live_nebius_orchestrator_report.md
?? docs/stage_2_9_6_3_live_nebius_validation_report.md
?? docs/stage_2_9_6_4_structured_output_remediation_report.md
?? tests/test_architect_structured_output.py
?? tests/test_stage16_4_orchestrator_execution.py
```
No files were staged, committed, reset, restored, or cleaned. All existing uncommitted changes, reports, fixtures, and deploy scripts are preserved.

---

## 3. Root Cause Diagnosis with Code Evidence

In Step 2.9.6.3, live inference with `nvidia/Nemotron-3_5-Lightning` halted with Pydantic validation errors during Architect plan ingestion.

### 3.1 Code & Empirical Evidence:
1. **Schema Expectation vs Model Generation**:
   - `ArchitectPlan` defined fields `acceptance_criteria: List[str]`, `constraints: List[str]`, and `risks: List[str]`.
   - When generating plans, reasoning models like `Nemotron-3_5-Lightning` frequently return natural single-sentence strings for these fields (e.g. `"constraints": "Only main.py may be modified"`, `"acceptance_criteria": "test_calculate in test_main.py succeeds"`).
   - In Pydantic v2, passing a `str` to a `List[str]` field does not auto-coerce into `[str]`; it raises a `ValidationError` (`Input should be a valid list`).
2. **Provider Response Format**:
   - Nebius Token Factory returned a valid JSON string wrapped in markdown fences (` ```json\n{...}\n``` `) or preceded by reasoning tokens.
   - Plain `json.loads(response.response_text)` failed when markdown fences or preamble text accompanied the JSON payload.
3. **Model Override Configuration**:
   - In `NebiusProvider.__init__`, resolving `default_model` evaluated an empty string `""` as falsy (`default_model or os.environ.get(...) or self.DEFAULT_MODEL`), causing explicit empty overrides to fall back to the default model rather than triggering expected configuration errors.

---

## 4. Implementation: Strict, Bounded Structured-Output Contract

The remediation followed the principle of the smallest robust fix consistent with existing architecture without weakening security:

1. **Schema Hardening (`backend/models/schemas.py`)**:
   - Added `model_config = ConfigDict(extra="forbid")` to `ArchitectPlan` so unauthorized, unexpected fields are strictly rejected.
   - Added bounded `@field_validator("acceptance_criteria", "constraints", "risks", "implementation_steps", "expected_tests", mode="before")`:
     - If the value is a string, strips whitespace, bounds length to 4,096 characters, and normalizes to `[stripped_value]`.
     - Non-string, non-list types (e.g. dicts, ints, booleans) are not coerced and fail validation closed.
2. **Robust Extraction & Prompting (`backend/agents/architect.py`)**:
   - Updated system prompt to explicitly require JSON objects with string arrays.
   - Implemented multi-tier JSON extraction:
     - Direct `json.loads` attempt.
     - Extraction from markdown code blocks (` ```json ... ``` `).
     - Outermost balanced brace extraction (`{ ... }`).
   - If parsing or validation fails, records `ARCHITECT_OUTPUT_PARSE_FAILED` or `ARCHITECT_SCHEMA_VALIDATION_FAILED` in the event stream and returns `OperationalResult.MODEL_FAILURE`.
3. **Builder JSON Extraction (`backend/agents/builder.py`)**:
   - Added matching markdown code block and outer-brace extraction to prevent builder failures from markdown formatting.
4. **Model Override Resolution (`backend/models/nebius_provider.py`)**:
   - Updated model resolution to `default_model if default_model is not None else ...`, preserving empty string configuration testing.
5. **Patch Formatting Safety (`backend/sandbox/client.py` & `backend/verification/attack_executor.py`)**:
   - Ensured candidate patch diff text ends with a newline (`diff_text if diff_text.endswith("\n") else diff_text + "\n"`) before writing `candidate.patch`, preventing git diff line-count corruption during `git apply`.

---

## 5. Targeted Regression Test Results

### 5.1 Focused Suite: `tests/test_architect_structured_output.py`

| # | Test Name | Target Behavior | Result |
| :- | :--- | :--- | :--- |
| 1 | `test_valid_json_plan_with_list_fields` | Valid JSON plan with list fields is accepted | **PASS** |
| 2 | `test_list_fields_returned_as_strings_normalized` | Single strings safely normalized to lists | **PASS** |
| 3 | `test_malformed_json_fails_closed` | Malformed JSON fails closed to `MODEL_FAILURE` | **PASS** |
| 4 | `test_missing_required_fields_fails_closed` | Missing required fields fail closed | **PASS** |
| 5 | `test_unexpected_fields_forbidden_and_fails_closed` | Extra forbidden fields fail closed (`extra="forbid"`) | **PASS** |
| 6 | `test_empty_or_structurally_invalid_plans` | Empty object, array, or primitive fails closed | **PASS** |
| 7 | `test_provider_timeout_or_request_failure` | Provider timeout fails closed to `MODEL_FAILURE` | **PASS** |
| 8 | `test_invalid_output_never_reaches_patch_or_sandbox` | Malformed output prevents builder and sandbox calls | **PASS** |
| 9 | `test_failed_run_cannot_receive_verified_verdict` | Aborted run yields `INCONCLUSIVE`, never `VERIFIED` | **PASS** |
| 10 | `test_evidence_receipt_integrity_preserved` | Receipt hash integrity is preserved on failure | **PASS** |

**Focused Suite Summary**: **10 passed, 0 failed** in 0.52s.

### 5.2 Full Component Regression Suite

Executed command:
`.\venv\Scripts\python.exe -m pytest tests/test_architect_structured_output.py tests/test_model_providers.py tests/test_stage4.py tests/test_stage5.py tests/test_stage16_4_orchestrator_execution.py tests/test_secure_sandbox_backend.py`

| Test File | Total | Passed | Skipped | Failed |
| :--- | :---: | :---: | :---: | :---: |
| `tests/test_architect_structured_output.py` | 10 | 10 | 0 | 0 |
| `tests/test_model_providers.py` | 44 | 44 | 0 | 0 |
| `tests/test_stage4.py` | 21 | 21 | 0 | 0 |
| `tests/test_stage5.py` | 12 | 12 | 0 | 0 |
| `tests/test_stage16_4_orchestrator_execution.py` | 10 | 10 | 0 | 0 |
| `tests/test_secure_sandbox_backend.py` | 33 | 32 | 1* | 0 |
| **TOTAL** | **130** | **129** | **1** | **0** |

*\*Note: 1 test skipped in `test_secure_sandbox_backend.py` is `test_cgroups_memory_limit_enforced` due to WSL2 cgroups v2 platform differences on Windows 11 Desktop.*

---

## 6. Live End-to-End Integration Validation

### 6.1 Configuration & Model Metadata
- **Provider**: `nebius` (`NebiusProvider`)
- **Target Endpoint**: `https://api.tokenfactory.nebius.com/v1/chat/completions`
- **Configured Model**: `nvidia/Nemotron-3_5-Lightning`
- **Task Contract**: `TASK-E2E-LIVE-1`
- **Target Repository**: `data/fixtures/repo-cons-1` (`snap-cons-1`)
- **Task Description**: `"Repair calculate() in main.py so test_calculate() in test_main.py succeeds"`
- **Allowed Scope**: `["main.py"]`
- **Repository Trust**: `UNTRUSTED`
- **Sandbox Backend**: `SecureSandboxBackend` (Docker image `redline-sandbox-runner:latest`, security level `SECURE`)

### 6.2 Live Workflow Execution Trace

1. **Reconnaissance & Snapshot**:
   - Snapshot hash: `4ff9c200b228b7c3605ef537883f2ba0b1c5f687e73d921e87d06bcaa6255e17` (2 files, 341 bytes).
2. **Architect Inference**:
   - Live call ID: `chatcmpl-27ad3aa80b74a04f0daf8d4aedc22407`
   - Latency: `9,641 ms` (347 input tokens, 1,799 output tokens including reasoning).
   - Generated `ArchitectPlan`:
     - Objective: `"Repair calculate() in main.py so that test_calculate() in test_main.py succeeds"`
     - Files to modify: `['main.py']`
     - Constraints: `['Only main.py may be modified', "main.py must not contain stripped content equal to 'old'"]`
     - Risks: `['Incorrect syntax in calculate() could cause runtime errors', "If main.py remains 'old', the test will fail"]`
     - Acceptance Criteria: `["test_main.py exits with code 0 and prints '1 passed'"]`
   - Plan validation: **SUCCESS** (normalized to lists without schema errors).
3. **Builder Inference**:
   - Live call ID: `chatcmpl-fe84fa393d5852b030ce872bb949d65a`
   - Latency: `13,190 ms` (371 input tokens, 1,678 output tokens).
   - Generated `PatchCandidate` (`PATCH-6C5437B2`):
     ```diff
     --- a/main.py
     +++ b/main.py
     @@ -1 +1,2 @@
     -old
     +def calculate(a, b):
     +    return a + b
     ```
   - Scope validation: `changed_files == ['main.py']` (allowed scope `['main.py']`). Accepted.
4. **Sandbox Execution (`SecureSandboxBackend`)**:
   - Isolated container launched with image `redline-sandbox-runner:latest`.
   - Candidate patch applied cleanly in isolated workspace.
   - Command: `python test_main.py`
   - Isolation verified: `--network none`, non-root execution, `environment={}`.
   - Execution Results:
     - **Exit Code**: `0`
     - **Duration**: `7,545 ms`
     - **Timed Out**: `False`
     - **Policy Blocked**: `False`
     - **Stdout**: `"1 passed\n"`
     - **Stderr**: `""`
5. **Adversarial / Red Team Phase**:
   - Red team attack strategies evaluated against candidate workspace.
   - Attack strategies validated; non-applicable strategies fail closed without compromising run integrity.
6. **Judge Subordination & Deterministic Verification**:
   - The live Judge agent call generated 6 validation errors for `JudgeExplanation` (`JUDGE_FAILURE`).
   - The canonical Orchestrator correctly treated the Judge as strictly advisory and non-authoritative.
   - Because `test_main.py` passed with exit code 0 inside the secure sandbox, the deterministic verification policy governed the outcome, transitioning state to **`VERIFIED`**.
7. **Evidence Receipt**:
   - Receipt Hash: `2bdaedbd5f6501b39792433151985dab20dce0c0ef9b6eefe57df950fd807c9c`
   - Final Verdict: `VERIFIED`
   - Cryptographic Integrity Check: `verify_receipt_integrity(receipt) == True`
   - Execution IDs: `['run-e2e-live-1']`
   - Total Workflow Duration: `72.89s`

---

## 7. Security and Integrity Attestations

1. **Zero Secret Disclosure**:
   - `NEBIUS_API_KEY` was loaded solely via application config from local gitignored `.env`.
   - Never logged, displayed, committed, or echoed in shell output or reports.
   - Candidate container launched with empty environment dictionary (`environment={}`), guaranteeing zero credential transmission into the sandbox.
2. **Network Isolation**:
   - All sandbox test executions ran inside Docker Desktop WSL2 with `--network none`.
3. **Deterministic Authority**:
   - Model predictions remain untrusted inputs. Workflow state transitions and the final verdict (`VERIFIED`) were strictly determined by test exit codes and deterministic policy.
4. **Frozen Benchmark Anchor**:
   - Anchor tag `benchmark-v1.0.0` commit `6e476bccaba2187055254d1cd71b539d7903b34f` untouched.
   - Manifest SHA-256 `d2cd37b9a588151975c992426338b0341f39bc824e1627c32d51e02ed1ac20c2` verified on all 84 artifacts.

---

## 8. Remaining Limitations and Next Smallest Action

1. **Judge Agent Schema Normalization**:
   - The live `Judge` agent output experienced validation errors due to extra fields emitted by `Nemotron-3_5-Lightning` (`verdict`, `details`, `justification`). While the deterministic verification policy correctly overrode this and prevented workflow failure, applying the same schema hardening pattern to `JudgeExplanation` is recommended for clean explanatory metadata in future releases.
2. **Reasoning Model Token Latencies**:
   - `nvidia/Nemotron-3_5-Lightning` produces extensive internal thinking tokens before generating JSON content (~1,200 to 1,800 tokens per call, taking 9-13s per call). Calling timeouts and token ceilings should continue to be configured to allow full reasoning completion.
3. **Next Smallest Action**:
   - Proceed to Stage 2.9.7 or final release packaging, with live Nebius inference, secure container sandboxing, and deterministic verification fully validated.
