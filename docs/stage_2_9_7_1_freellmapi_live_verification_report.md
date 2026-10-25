# Stage 2.9.7.1: Live FreeLLMAPI Verification, Security Audit & Provider Regression Report

**Date**: 2026-10-25  
**Stage**: 2.9.7.1 — Live Verification, Security Audit & Cross-Provider Regression  
**Authoritative Verdict**: Complete & Verified (Gateway Offline $\rightarrow$ Live Calls BLOCKED, Security Audited, Provider Isolation PASS, Regressions PASS)  

---

## 1. Executive Summary & Verification Matrix

In Stage 2.9.7, FreeLLMAPI was integrated as an optional, secondary LLM provider. In Stage 2.9.7.1, we audited endpoint and network security, probed live gateway reachability, executed cross-provider isolation regression suites, and verified benchmark anchors.

Because the FreeLLMAPI service is not running on the host and no live gateway was reachable on port 3001, **live network inference was not fabricated**. The offline fail-closed behavior was verified.

### Criteria Verification Matrix

| Criterion | Evaluation Status | Mechanism / Evidence |
| :--- | :--- | :--- |
| **Default Provider Remains Nebius** | **PASS** | `test_default_provider_precedence_nebius` verifies `NebiusProvider` when provider is unset or default. |
| **Independent FreeLLMAPI Selection** | **PASS** | `test_explicit_selection_strictness` verifies explicit selection via `REDLINE_MODEL_PROVIDER=freellmapi`. |
| **Gateway Reachability** | **BLOCKED** | `Test-NetConnection -ComputerName 127.0.0.1 -Port 3001` $\rightarrow$ `TcpTestSucceeded: False`. Service not running. |
| **Gateway Authentication** | **BLOCKED** | Gateway unreachable on local port 3001; no live auth handshake could be performed. |
| **Real Live Inference** | **BLOCKED** | Local gateway unreachable; live inference was not executed (no simulated live claims). |
| **Response Schema Validation** | **MOCKED / PASS** | Validated via `test_freellmapi_chat_completion_mock_success`; live request **BLOCKED**. |
| **End-to-End Workflow** | **MOCKED / PASS** | Validated via `test_orchestrator_records_freellmapi_provenance`; live run **BLOCKED**. |
| **Deterministic Verification Supremacy** | **PASS** | `test_provider_failure_does_not_bypass_state_transitions` confirms deterministic gate strictly aborts. |
| **Evidence Receipt & Provenance** | **PASS** | `test_evidence_provenance_records_distinct_provider_and_model` confirms truthful provenance without secrets. |
| **Sandbox & Credential Isolation** | **PASS** | `test_candidate_container_never_receives_any_provider_credentials` confirms zero secrets enter container. |
| **Nebius Regression Tests** | **PASS** | All Nebius unit, integration, and structured-output tests passed (160 backend tests total). |
| **Benchmark Integrity** | **PASS** | Commit `6e476bccaba2187055254d1cd71b539d7903b34f`, manifest SHA-256 `d2cd...20c2` (**84/84 verified**). |

---

## 2. Baseline Repository State

- **Branch**: `master`
- **HEAD Commit**: `792ace628b9725c75e709522caf023b24f155df0`
- **Working Tree**: Preserved all uncommitted modifications, reports, fixtures, and untracked files.
- **Frozen Benchmark**: Anchored at `benchmark-v1.0.0`, verified with `verify_dataset_anchor()`.
- **Files Staged / Committed**: **Zero** (no git stage or commit operations performed).

---

## 3. FreeLLMAPI Availability Probe

### 1. Port & Network Probe
- **Target**: `127.0.0.1:3001`
- **Command**: `Test-NetConnection -ComputerName 127.0.0.1 -Port 3001`
- **Result**: `TcpTestSucceeded: False`
- **Process Check**: `Get-NetTCPConnection -LocalPort 3001` returned empty (no listening process).
- **Container Check**: `docker ps -a` returned 0 running or stopped FreeLLMAPI containers.

### 2. Credential Configuration Check
- `.env` inspection confirmed that `FREELLMAPI_API_KEY` is currently unset (placeholder).
- `os.environ` inspection confirmed `FREELLMAPI_API_KEY` is not present in the runtime process environment.

### 3. Conclusion on Availability
The local FreeLLMAPI service is neither installed nor active on this machine. In accordance with the non-negotiable rules ("Do not fabricate a live inference result; do not install software without explicit approval"), live inference was halted at this boundary.

---

## 4. Endpoint & Network Security Audit

A thorough code audit of `backend/models/freellmapi_provider.py` and `backend/models/openai_compatible_provider.py` evaluated the following vectors:

### 1. Loopback & Host Allowlist Validation
- `FreeLLMAPIProvider` restricts base URLs to:
  `["localhost", "127.0.0.1", "::1", "host.docker.internal"]` (+ optional `FREELLMAPI_APPROVED_HOSTS`).
- **IPv4 Loopback**: `http://127.0.0.1:3001/v1` $\rightarrow$ PASS.
- **IPv6 Loopback**: `http://[::1]:3001/v1` $\rightarrow$ `parsed.hostname == '::1'` $\rightarrow$ PASS.
- **Ambiguous Formats Rejected**:
  - Raw integer IPs (`http://2130706433:3001/v1`) $\rightarrow$ Rejected (`raw_hostname.isdigit()`).
  - Hex IPs (`http://0x7f000001:3001/v1`) $\rightarrow$ Rejected (`^0x[0-9a-fA-F]+$`).
  - Octal IPs (`http://0177.0.0.1:3001/v1`) $\rightarrow$ Rejected (leading zero in octets).
  - Short-form IPs (`http://127.1:3001/v1`) $\rightarrow$ Rejected (less than 4 dotted parts).
  - Deceptive trailing/leading dots (`http://localhost.:3001/v1`) $\rightarrow$ Rejected.
  - Backslash host deception (`http://localhost\attacker.com/v1`) $\rightarrow$ Rejected.

### 2. Docker vs. Host Topology Analysis
- **Host Execution (Standard)**: Backend runs on host workstation $\rightarrow$ connects to FreeLLMAPI on `127.0.0.1:3001`.
- **Containerized Backend**: If REDLINE's backend is executed inside a Docker container, `127.0.0.1` refers to the container itself. The host gateway must be addressed via `host.docker.internal:3001`.
- **Constraint**: `host.docker.internal` is allowed solely for local gateway connectivity and cannot route out to public internet addresses.

### 3. HTTP Redirect (SSRF) Protection
- `requests.post(..., allow_redirects=False)` is explicitly enforced.
- Responses with HTTP 301, 302, 303, 307, or 308 immediately raise `MODEL_PROVIDER_ERROR` and close the connection without following redirects.
- This prevents a compromised or malicious local gateway from redirecting requests (with `Authorization: Bearer <key>`) to external servers.

### 4. Credential Sanitization
- `OpenAICompatibleProvider._redact_secrets()` sanitizes exception strings and error bodies, replacing any occurrence of the API key with `[REDACTED_API_KEY]`.

### 5. Isolation from Token Factory Allowlist
- `NebiusProvider` enforces `allowed_hostnames = ["api.tokenfactory.nebius.com"]`, `allowed_schemes = ["https"]`, and `allowed_ports = [443]`.
- Verified that `NebiusProvider` rejects `localhost`, `127.0.0.1`, `host.docker.internal`, and HTTP schemes. The Token Factory allowlist was NOT broadened.

---

## 5. Cross-Provider Isolation Verification

Dedicated cross-provider isolation tests were implemented in [`tests/test_provider_cross_isolation.py`](file:///p:/REDLINE/tests/test_provider_cross_isolation.py):

1. **Precedence & Default**: When `REDLINE_MODEL_PROVIDER` is unset and both API keys are present, `NebiusProvider` is returned by default.
2. **Explicit Selection**: `REDLINE_MODEL_PROVIDER=freellmapi` returns `FreeLLMAPIProvider`; `REDLINE_MODEL_PROVIDER=nebius` returns `NebiusProvider`.
3. **No Silent Cross-Provider Fallback**:
   - `test_freellmapi_failure_never_calls_nebius`: When FreeLLMAPI fails with `MODEL_UNAVAILABLE`, the Orchestrator transitions to `RunState.ABORTED` without touching Nebius.
   - `test_nebius_failure_never_calls_freellmapi`: When Nebius fails with `MODEL_UNAVAILABLE`, the Orchestrator transitions to `RunState.ABORTED` without touching FreeLLMAPI.
4. **Model Identifier Separation**:
   - `NEBIUS_MODEL` controls only `NebiusProvider` (default: `nvidia/Nemotron-3_5-Lightning`).
   - `FREELLMAPI_MODEL` controls only `FreeLLMAPIProvider` (default: `auto`).
   - Modifying one does not affect the other.
5. **Authoritative Evidence Provenance**:
   - `EvidenceReceipt.model_provenance` records `{"provider": "freellmapi", "model": ...}` or `{"provider": "nebius", "model": ...}`.
6. **Container Environment Confinement**:
   - When both `NEBIUS_API_KEY` and `FREELLMAPI_API_KEY` are present in the host environment, container arguments generated by `SecureSandboxBackend.build_container_args()` contain zero provider credentials and enforce `--network none`.

---

## 6. Regression Testing Evidence

### 1. Model Providers & Cross-Isolation Suites
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_model_providers.py tests/test_provider_cross_isolation.py
```
- **Result**: **64 passed in 1.48s** (56 in `test_model_providers.py` + 8 in `test_provider_cross_isolation.py`).

### 2. Full Backend Regression Suite
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_architect_structured_output.py tests/test_judge_failure_diagnosis.py tests/test_model_providers.py tests/test_provider_cross_isolation.py tests/test_stage4.py tests/test_stage5.py tests/test_stage11.py tests/test_stage16_4_orchestrator_execution.py tests/test_secure_sandbox_backend.py
```
- **Result**: **160 passed, 1 skipped, 0 failed in 13.97s**  
  *(Note: 1 skipped test is `test_cgroups_memory_limit_enforced` due to Windows WSL2 cgroups v2 controller configuration differences.)*

### 3. Frontend Acceptance Suite
```powershell
cd frontend; npm test
```
- **Result**: **111 passed, 0 failed in 1.45s**

### 4. Benchmark Integrity Anchor
```powershell
.\venv\Scripts\python.exe -c "from backend.benchmark.integrity import verify_dataset_anchor; res = verify_dataset_anchor(); print(res.status, res.manifest_sha256, res.artifacts_verified)"
```
- **Result**: `VERIFIED d2cd37b9a588151975c992426338b0341f39bc824e1627c32d51e02ed1ac20c2 84`

---

## 7. Instructions for Enabling Live FreeLLMAPI (User Action Required)

To execute live requests through FreeLLMAPI when ready:

1. **Install FreeLLMAPI via Docker** (Official instructions):
   ```bash
   curl -fsSL https://freellmapi.co/install.sh | bash
   ```
   Or via source clone:
   ```bash
   git clone https://github.com/tashfeenahmed/freellmapi.git
   cd freellmapi
   docker compose up -d
   ```
2. **Retrieve Unified API Key**:
   - Access the FreeLLMAPI dashboard at `http://localhost:3001`.
   - Copy your unified API key (`freellmapi-...`).
3. **Configure REDLINE**:
   In `p:\REDLINE\.env`:
   ```env
   REDLINE_MODEL_PROVIDER=freellmapi
   FREELLMAPI_API_KEY=your-freellmapi-unified-key
   FREELLMAPI_BASE_URL=http://127.0.0.1:3001/v1
   FREELLMAPI_MODEL=groq/llama-3.3-70b-versatile
   ```
4. **Run Live Smoke Test**:
   ```powershell
   .\venv\Scripts\python.exe -c "from backend.models.registry import get_model_provider; p = get_model_provider('freellmapi'); res = p.generate([{'role': 'user', 'content': 'ping'}]); print('Live Response:', res.response_text)"
   ```
5. **Switch Back to Token Factory**:
   ```env
   REDLINE_MODEL_PROVIDER=nebius
   ```

---

## 8. Final Conclusion

Stage 2.9.7.1 audit and verification is **COMPLETE**:
- Token Factory remains the default, unaltered primary provider.
- FreeLLMAPI integration is fully isolated, secure, and fail-closed.
- Network and SSRF security controls are verified.
- Cross-provider non-interference is covered by passing automated regression tests.
- All 160 backend tests and 111 frontend tests pass.
- Frozen benchmark remains 100% verified.
- Working tree is clean of staged changes.
