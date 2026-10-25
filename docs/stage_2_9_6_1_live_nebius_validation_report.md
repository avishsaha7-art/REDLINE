# Stage 2.9.6.1 — Live Nebius Credential Configuration and Orchestrator Validation Report

**Date**: 2026-10-25  
**Stage**: 2.9.6.1  
**Status**: USER_ACTION_REQUIRED  
**Baseline HEAD**: `792ace628b9725c75e709522caf023b24f155df0`  
**Branch**: `master`  
**Frozen Benchmark Tag**: `benchmark-v1.0.0` (Commit `6e476bccaba2187055254d1cd71b539d7903b34f`)  
**Frozen Benchmark Manifest SHA-256**: `d2cd37b9a588151975c992426338b0341f39bc824e1627c32d51e02ed1ac20c2` (84/84 artifacts verified)  

---

## 1. Executive Summary

In Stage 2.9.6.1, REDLINE conducted a safe credential configuration inspection and security audit for live integration with Nebius Token Factory using the selected model **`nvidia/Llama-3.1-Nemotron-70B-Instruct-HF`**.

In accordance with strict zero-leakage security protocols and Phase B requirements:
1. Environment variables and the local `.env` configuration file were safely audited for the presence of `NEBIUS_API_KEY` without exposing, printing, copying, or logging any secret values.
2. The credential `NEBIUS_API_KEY` is currently **UNSET** across all system scopes (Process, User, Machine) and is not present in `.env`.
3. In strict compliance with Phase B.7, **no live network call was fabricated or simulated**. Live API calls have been stopped pending user credential configuration.
4. Provider configuration, HTTPS-only transport, hostname allowlisting (`api.tokenfactory.nebius.com`), redirect blocking, payload size bounds, and header redaction were verified.
5. Sandbox isolation guarantees were confirmed: candidate containers run with `--network none` and an empty environment (`environment={}`), strictly preventing host API credentials from leaking into untrusted candidate execution environments.
6. The canonical Orchestrator and deterministic verification policy remain verified and fail-closed.

**Final Verdict**: **`USER_ACTION_REQUIRED`** (Credential configuration required by user before live request can proceed).

---

## 2. Git Baseline and Working-Tree Preservation

| Item | Value / Status |
| :--- | :--- |
| **Commit HEAD** | `792ace628b9725c75e709522caf023b24f155df0` |
| **Branch** | `master` |
| **Benchmark Tag** | `benchmark-v1.0.0` (matches `6e476bccaba2187055254d1cd71b539d7903b34f`) |
| **Benchmark Integrity** | 84/84 files match manifest `d2cd37b9a588151975c992426338b0341f39bc824e1627c32d51e02ed1ac20c2` |
| **Tracked Modifications** | 11 files preserved without staging, committing, or resetting |
| **Untracked Additions** | Preserved (`data/fixtures/`, `deploy/`, stage reports, `test_stage16_4_orchestrator_execution.py`) |

No files were staged, committed, reset, restored, or cleaned.

---

## 3. Credential Inspection and Safe Configuration Status

### 3.1 Credential Audit Results

| Target Scope | Inspection Method | Status | Value Handled |
| :--- | :--- | :--- | :--- |
| `os.environ["NEBIUS_API_KEY"]` | Python `os.environ.get()` | **UNSET** | None |
| Process / User / Machine Registry | PowerShell `[System.Environment]` inspection | **UNSET** | None |
| Local File `p:\REDLINE\.env` | Non-printing line prefix scan | **ABSENT** | None |
| Gitignore Enforcement | `git check-ignore -v .env` | **MATCHED** (`.gitignore:5:*.env`) | N/A |

### 3.2 Safe Configuration Protocol for User

To configure your authorized Nebius Token Factory API key without exposing it to chat or source control:

1. Obtain your API key from the authorized [Nebius Token Factory Console](https://tokenfactory.nebius.com).
2. Open your local `.env` file at `p:\REDLINE\.env` in an editor.
3. Add or update the line:
   ```bash
   NEBIUS_API_KEY=your_actual_token_here
   ```
4. **Mandatory Security Rules**:
   - **DO NOT** paste your API key into this chat.
   - **DO NOT** commit `.env` to Git (it is gitignored by rule `*.env`).
   - **DO NOT** embed the key in source code, scripts, or test fixtures.

---

## 4. Provider Security and Configuration Audit

The `NebiusProvider` implementation in `backend/models/nebius_provider.py` (inheriting from `OpenAICompatibleProvider` in `backend/models/openai_compatible_provider.py`) was inspected against all security invariants:

| Security Control | Configured Value / Implementation | Compliance |
| :--- | :--- | :--- |
| **Base URL** | `https://api.tokenfactory.nebius.com/v1` | Verified (HTTPS only, port 443) |
| **Endpoint** | `/chat/completions` | Verified |
| **Allowed Hostnames** | `["api.tokenfactory.nebius.com"]` | Verified (Strict hostname allowlist) |
| **Redirect Handling** | `allow_redirects=False` | Verified (SSRF & redirect evasion prevented) |
| **Response Size Cap** | `1,048,576` bytes (`1 MB`) | Verified (Enforced via chunked streaming) |
| **Request Timeout** | `60.0` seconds | Verified (Bounded async timeouts) |
| **Credential Redaction** | `re.sub(pattern, "[REDACTED_API_KEY]", ...)` | Verified (Authorization headers scrubbed from logs) |
| **Selected Model ID** | `nvidia/Llama-3.1-Nemotron-70B-Instruct-HF` | Verified (Default model identifier) |
| **Sandbox Isolation** | `SandboxClient.run_isolated(..., environment={})` | Verified (Host credentials never injected into container) |
| **Fail-Closed Behavior** | Missing key triggers `ModelProviderError(MODEL_CONFIGURATION_ERROR)` | Verified (Fail-closed) |

---

## 5. Live Request and Orchestrator Validation Status

### 5.1 Live Request Status
- **Execution**: **HALTED / STOPPED** (per Phase B.7: `NEBIUS_API_KEY` is unavailable).
- **Sanitized HTTP Status**: N/A (no network call dispatched).
- **Observed Latency**: N/A.
- **Fabrication Prevention**: In accordance with system instructions, no synthetic or mocked response was attributed to the live Nebius API endpoint.

### 5.2 Canonical Orchestrator Status
- **Test Suite Status**: All 44 provider tests (`tests/test_model_providers.py`) and 10 canonical orchestrator execution tests (`tests/test_stage16_4_orchestrator_execution.py`) passed.
- **Disposable Fixture**: `data/fixtures/repo-cons-1` verified end-to-end under canonical Orchestrator with `SecureSandboxBackend` in Step 2.9.6.0.
- **Deterministic Authority**: The model's suggestions remain untrusted. Verdicts (`VERIFIED` vs `FAILED_VERIFICATION`) are exclusively determined by the deterministic observer and verification policy based on container test execution results.

---

## 6. Blockers and Next Steps

1. **Current Blocker**:
   - `NEBIUS_API_KEY` is not present in `.env` or system environment.
2. **Action Required by User**:
   - Follow the instructions in Section 3.2 to place `NEBIUS_API_KEY=...` into `p:\REDLINE\.env`.
3. **Subsequent Action**:
   - Once configured, proceed to execute one live bounded query against `https://api.tokenfactory.nebius.com/v1/chat/completions` using `nvidia/Llama-3.1-Nemotron-70B-Instruct-HF` and validate the response metadata through REDLINE's Orchestrator.

---

## 7. Final Verdict

```
VERDICT: USER_ACTION_REQUIRED
```

*Reasoning*: The REDLINE architecture, sandbox isolation, hostname allowlisting, credential redaction, and deterministic verification are fully verified. However, live model interaction cannot proceed until the user sets `NEBIUS_API_KEY` in their local `.env` file. Safe stop enforced without fabricating results.
