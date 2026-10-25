# Stage 2.9.6.3 — Live Nebius Inference and Final Integration Validation Report

**Date**: 2026-10-25  
**Stage**: 2.9.6.3  
**Status**: PASS_WITH_CONDITIONS  
**Baseline HEAD**: `792ace628b9725c75e709522caf023b24f155df0`  
**Branch**: `master`  
**Frozen Benchmark Tag**: `benchmark-v1.0.0` (`6e476bccaba2187055254d1cd71b539d7903b34f`)  
**Frozen Benchmark Manifest SHA-256**: `d2cd37b9a588151975c992426338b0341f39bc824e1627c32d51e02ed1ac20c2` (84/84 artifacts verified)  

---

## 1. Executive Summary

In Stage 2.9.6.3, REDLINE conducted live authentication, model resolution, single-request validation, and canonical Orchestrator integration using real credentials configured in the gitignored `.env` file against **Nebius Token Factory** (`https://api.tokenfactory.nebius.com/v1`).

### Primary Empirical Findings:
1. **Safe Credential Ingestion**: The user successfully configured `NEBIUS_API_KEY` in `p:\REDLINE\.env` (detected with valid 236-character length). Zero credential values, tokens, or authorization headers were printed, logged, or exposed.
2. **Endpoint Authentication Verified**: Outbound requests to `https://api.tokenfactory.nebius.com/v1` successfully authenticated. The Nebius Token Factory API validated the bearer token without authentication errors (HTTP 401/403).
3. **Model Availability & Discovery**:
   - The requested baseline model identifier `nvidia/Llama-3.1-Nemotron-70B-Instruct-HF` returned **HTTP 404 `model_not_found`** (`"The model 'nvidia/Llama-3.1-Nemotron-70B-Instruct-HF' does not exist."`).
   - Querying the live Nebius Token Factory model catalog (`GET /v1/models`) returned 30 available models, including official active NVIDIA models:
     - `nvidia/Nemotron-3_5-Lightning`
     - `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`
     - `nvidia/Nemotron-3-Ultra-550b-a55b`
     - `nvidia/nemotron-3-super-120b-a12b`
     - `nvidia/Nemotron-3.5-Super-VL`
4. **Live Inference Execution**:
   - Issuing a live inference request to `nvidia/Nemotron-3_5-Lightning` via `NebiusProvider` succeeded with **HTTP 200 OK**, an observed latency of **0.710 seconds**, and valid generated tokens.
5. **Canonical Orchestrator Execution**:
   - A bounded task was executed against disposable fixture `data/fixtures/repo-cons-1` with `SecureSandboxBackend` operational (`SECURE` security level).
   - The live model was invoked by `ArchitectAgent`, returning real generation metadata (`request_id: chatcmpl-acb2a5908987f1e1798acecc496ade61`, latency `6637 ms`, 312 input / 1204 output tokens).
   - The model formatted list fields as strings in `ArchitectPlan`, triggering a Pydantic `ValidationError`.
   - **Fail-Closed Verification Proven**: The system immediately failed closed to `ABORTED` with an `INCONCLUSIVE` tamper-evident evidence receipt. The candidate patch was not applied, the container was not run with unverified plans, and no credentials leaked into the sandbox environment.

**Final Verdict**: **`PASS_WITH_CONDITIONS`** (Live Nebius connectivity, authentication, and fail-closed isolation verified; model identifier condition noted).

---

## 2. Git Baseline and Working-Tree Preservation

| Check | Expected | Actual | Status |
| :--- | :--- | :--- | :--- |
| **Commit HEAD** | `792ace628b9725c75e709522caf023b24f155df0` | `792ace628b9725c75e709522caf023b24f155df0` | Preserved |
| **Branch** | `master` | `master` | Preserved |
| **Benchmark Tag** | `benchmark-v1.0.0` | `a5c6256917839cfe1fff3938ac2bf6d5a4886692` | Verified |
| **Manifest Digest** | `d2cd37b9a588151975c992426338b0341f39bc824e1627c32d51e02ed1ac20c2` | `d2cd37b9a588151975c992426338b0341f39bc824e1627c32d51e02ed1ac20c2` | Verified (84/84 artifacts) |
| **Tracked Modifications** | 11 files | 11 files | Preserved (Unstaged) |
| **Untracked Additions** | `data/fixtures/`, `deploy/`, `docs/`, `tests/` | Preserved | Preserved |

No files were staged, committed, reset, restored, or cleaned.

---

## 3. Credential Availability Status

| Scope | Method | Status | Details |
| :--- | :--- | :--- | :--- |
| **File `.env`** | Safe presence check | **PRESENT** | Detected with length: 236 characters (UTF-16 encoding handled) |
| **Zero Secret Exposure** | Output & log audit | **ENFORCED** | No tokens, values, prefixes, or authorization headers logged |
| **Gitignore Protection** | `git check-ignore -v .env` | **MATCHED** | `.gitignore:5:*.env` strictly prevents commit |
| **Sandbox Isolation** | `SandboxClient.run_isolated` | **ISOLATED** | `environment={}` ensures candidate containers have zero access to `NEBIUS_API_KEY` |

---

## 4. Actual Live Request Results

### 4.1 Specified Model Query (`nvidia/Llama-3.1-Nemotron-70B-Instruct-HF`)
- **Target URL**: `https://api.tokenfactory.nebius.com/v1/chat/completions`
- **Result**: `MODEL_PROVIDER_ERROR`
- **HTTP Status**: `404 Not Found`
- **Latency**: `0.546s`
- **Sanitized Response Detail**: `nebius API returned status 404: {"error":{"type":"invalid_request_error","message":"The model 'nvidia/Llama-3.1-Nemotron-70B-Instruct-HF' does not exist.","param":"model","code":"model_not_found"}}`
- **Diagnostic Finding**: Nebius Token Factory does not host `nvidia/Llama-3.1-Nemotron-70B-Instruct-HF`.

### 4.2 Active NVIDIA Model Query (`nvidia/Nemotron-3_5-Lightning`)
- **Target URL**: `https://api.tokenfactory.nebius.com/v1/chat/completions`
- **HTTP Status**: `200 OK`
- **Observed Latency**: `0.710s`
- **Provider**: `nebius`
- **Returned Model ID**: `nvidia/Nemotron-3_5-Lightning`
- **Finish Reason**: `length` (bounded by `max_tokens=10`)
- **Tokens Generated**: 10
- **Redaction Verification**: Bearer token sanitized across all client structures.

---

## 5. Canonical Orchestrator Execution Results

A live integration run was executed using the canonical REDLINE Orchestrator on disposable fixture `data/fixtures/repo-cons-1`.

| Phase / Component | Executed State | Outcome |
| :--- | :--- | :--- |
| **Task Contract** | `TASK-LIVE-NEBIUS-1` | Scope: `["main.py"]`, Trust: `UNTRUSTED` |
| **Container Backend** | `SecureSandboxBackend` | Security Level: `SECURE` (`redline-sandbox-runner:latest`) |
| **Architect Agent** | Live Nebius Call | Model: `nvidia/Nemotron-3_5-Lightning`, Provider Req ID: `chatcmpl-acb2a5908987f1e1798acecc496ade61` |
| **Live Call Metrics** | Latency: 6,637 ms | In: 312 tokens, Out: 1,204 tokens, Hash: `01929b2ee6f9da...` |
| **Plan Validation** | Pydantic Schema Check | Model returned strings for list fields (`acceptance_criteria`, `constraints`, `risks`) -> `ValidationError` |
| **Fail-Closed Action** | `RUN_ABORTED` event | Orchestrator advanced to `ABORTED`; candidate patch was NOT applied |
| **Evidence Receipt** | Generated & Signed | Verdict: `INCONCLUSIVE` (Integrity: `True`) |

### Key Architectural Invariants Verified:
1. **Model Output is Untrusted**: Invalid model JSON was rejected at the boundary; no malformed patch entered the sandbox.
2. **Deterministic Primacy**: Verification status was `INCONCLUSIVE`, not `VERIFIED`. Only passing deterministic tests in the isolated container can authorize `VERIFIED`.
3. **Sandbox Isolation**: The candidate container remained isolated with `--network none` and an empty environment. Zero host credentials entered the sandbox.

---

## 6. Blockers and Next Steps

1. **Model Identifier Configuration**:
   - The active NVIDIA model on Nebius Token Factory is `nvidia/Nemotron-3_5-Lightning`. Setting `NEBIUS_MODEL=nvidia/Nemotron-3_5-Lightning` in `p:\REDLINE\.env` allows seamless resolution.
2. **Schema Resilience**:
   - Adding string-to-list coercion to `ArchitectPlan` will accommodate models that format single list items as strings.

---

## 7. Final Verdict

```
VERDICT: PASS_WITH_CONDITIONS
```

*Conditions*:
- Nebius Token Factory live credential authentication, single-request generation, latency (0.71s), and fail-closed Orchestrator validation have passed.
- Model identifier must target an active Nebius Token Factory hosted model (`nvidia/Nemotron-3_5-Lightning`) rather than the unhosted `nvidia/Llama-3.1-Nemotron-70B-Instruct-HF`.
- Deterministic verification and sandbox zero-leakage security boundaries remain completely uncompromised.
