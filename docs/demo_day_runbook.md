# REDLINE — Demo-Day Operational Runbook

**Document Target**: Operational execution guide for presentation day and technical evaluator review  
**Platform**: REDLINE — Autonomous Vulnerability Remediation & Deterministic Verification Platform  
**Target Environment**: Windows 11 (PowerShell) / Linux & macOS (Bash)  
**Security Policy**: Zero secret exposure, strict container isolation, fail-closed verification  

---

## 1. System Prerequisites & Environment Verification

Before starting services or executing demonstrations, verify the local host environment:

### Required Software Components
| Component | Minimum Version | Verification Command | Expected Output |
| :--- | :--- | :--- | :--- |
| **Python** | 3.11+ (Active: 3.14.8) | `python --version` | `Python 3.11+` |
| **Node.js** | 18+ (Active: 22.18.0) | `node --version` | `v18.0.0+` |
| **npm** | 9+ (Active: 10.9.2) | `npm --version` | `9.0.0+` |
| **Docker Engine** | 24+ (WSL2 / Linux) | `docker --version` | `Docker version 24+` |
| **Git** | 2.40+ | `git --version` | `git version 2.40+` |

---

## 2. Docker Daemon & Sandbox Health Checks

REDLINE executes candidate code inside the hardened `redline-sandbox-runner:latest` container.

### Step 2.1: Verify Docker Daemon Reachability
Run the following check to verify the Docker socket is responsive:
```powershell
docker info --format '{{.ServerVersion}}'
```
- **Success Indicator**: Emits Docker version string (e.g. `27.5.1` or `24.x.x`).
- **Failure Indicator**: `error during connect: This error may indicate that the docker daemon is not running.`
- **Recovery Action**: Launch Docker Desktop, ensure the engine finishes initializing, and verify context is set to `desktop-linux`:
  ```powershell
  docker context use desktop-linux
  ```

### Step 2.2: Verify Sandbox Runner Image
Confirm the pre-built sandbox runner image exists locally:
```powershell
docker images redline-sandbox-runner:latest
```
- **Success Indicator**:
  ```text
  REPOSITORY               TAG       IMAGE ID       CREATED        SIZE
  redline-sandbox-runner   latest    939c871d41a8   ...            560MB
  ```
- **If Missing**: Build the runner image (takes ~30 seconds, no host modifications):
  ```powershell
  docker build -t redline-sandbox-runner:latest -f deploy/sandbox/Dockerfile deploy/sandbox/
  ```

---

## 3. Environment Configuration by Mode

REDLINE reads configuration from shell environment variables or the local gitignored `.env` file via `backend/config.py`.

> [!IMPORTANT]
> Never copy, paste, or commit real API keys into repository files or command logs.

### Mode A: Offline Deterministic Demonstration (Zero External Dependencies)
```powershell
# Set deterministic mock provider explicitly
$env:REDLINE_MODEL_PROVIDER="deterministic"
```

### Mode B: Live Nebius Token Factory Demonstration
```powershell
# Set Nebius as active provider
$env:REDLINE_MODEL_PROVIDER="nebius"
# Configure your personal token in .env or active session only:
$env:NEBIUS_API_KEY="your-nebius-token-factory-key"
$env:NEBIUS_MODEL="nvidia/Nemotron-3_5-Lightning"
```

### Mode C: Optional Self-Hosted FreeLLMAPI Demonstration
```powershell
# Set FreeLLMAPI as active provider
$env:REDLINE_MODEL_PROVIDER="freellmapi"
$env:FREELLMAPI_API_KEY="your-freellmapi-unified-key"
$env:FREELLMAPI_BASE_URL="http://127.0.0.1:3001/v1"
$env:FREELLMAPI_MODEL="auto"
```

---

## 4. Exact Demonstration Execution Commands

### Demonstration Path 1: Fast Deterministic Rehearsal Runner (Recommended)
This command runs the complete Orchestrator workflow, real Docker sandbox container, deterministic test execution, and tamper-evident receipt builder in ~10 seconds:

```powershell
.\venv\Scripts\python.exe scratch/demo_rehearsal.py
```

#### Expected Output Indicators:
```text
================================================================================
  REDLINE — Autonomous Vulnerability Remediation & Deterministic Verification
  Demo Execution Mode: MOCK
================================================================================
[MODEL ATTRIBUTION]
  Execution Engine: Deterministic Rehearsal Engine (deterministic-demo-engine-v1)
  Live Network Calls: Disabled (Deterministic Mock Flow)

[SANDBOX ISOLATION CONTROLS]
  Backend: SecureSandboxBackend
  Security Level: SECURE
  Network Isolation: --network none (strictly enforced)
  Host Filesystem: Read-only mount / temporary isolated copy

================================================================================
  WORKFLOW EXECUTION RESULTS
================================================================================
  Total Duration: ~10.6 seconds
  Final Orchestrator State: VERIFIED

[PATCH CANDIDATE & LINEAGE]
  Patch ID: PATCH-XXXXXXXX
  Changed Files: ['main.py']
  Diff Preview:
--- a/main.py
+++ b/main.py
@@ -1,1 +1,2 @@
-old
+def calculate():
+    return 0

[SANDBOX TEST EXECUTION]
  Exit Code: 0 (0 indicates test suite passed)
  Stdout: 1 passed

[CRYPTOGRAPHIC EVIDENCE RECEIPT]
  Receipt Hash: <64-character-sha256-hex>
  Verdict: VERIFIED
  Tamper-Evident Integrity: VALID
```

---

### Demonstration Path 2: Full Web Platform (Backend API + Next.js UI)

#### Step 4.2.1: Launch Backend API Server
In Terminal 1:
```powershell
Set-Location p:\REDLINE
.\venv\Scripts\python.exe -m uvicorn backend.api.app:app --host 127.0.0.1 --port 8000
```
- **Health Probe**: `http://127.0.0.1:8000/docs` (Interactive OpenAPI Swagger UI)
- **Localhost Boundary Notice**: The API enforces `LocalhostOnlyMiddleware`. Requests from non-loopback addresses are rejected with HTTP 403 Forbidden.

#### Step 4.2.2: Launch Frontend Dashboard
In Terminal 2:
```powershell
Set-Location p:\REDLINE\frontend
npm run dev
```
- **Dashboard URL**: `http://localhost:3000`
- **Primary Routes**:
  - Mission Control & Run Intake: `http://localhost:3000/`
  - Cryptographic Evidence Receipts: `http://localhost:3000/receipts`
  - Active Runs & Telemetry: `http://localhost:3000/sessions`
  - Sandboxed Playground Workbench: `http://localhost:3000/playground`

---

### Demonstration Path 3: Live Nebius Smoke Test (When Configured)
To execute a genuine outbound inference call to Nebius Token Factory:

```powershell
$env:REDLINE_MODEL_PROVIDER="nebius"
.\venv\Scripts\python.exe scratch/demo_rehearsal.py --live
```
- **Expected Duration**: 45–75 seconds (due to `nvidia/Nemotron-3_5-Lightning` generating 1,200+ reasoning tokens).
- **Success Criteria**: Terminal reports `Inference Provider: Nebius Token Factory`, passes schema gate, creates patch, runs Docker container, and records `Final Orchestrator State: VERIFIED`.

---

### Demonstration Path 4: 5-Scenario Deterministic Test Engine
To execute all 5 canonical scenarios (Clean Fix, Autonomous Repair, Scope Rejection, Policy Blocking, Tampered Evidence Detection):

```powershell
$env:REDLINE_ENABLE_LOCAL_BACKEND="1"
$env:REDLINE_MODEL_PROVIDER="deterministic"
.\venv\Scripts\python.exe -m backend.demo.run_demo all
```
- **Expected Outcome**: All 5 scenarios report `PASSED (100%)`.

---

## 5. Troubleshooting & Recovery Procedures

| Issue | Symptom | Root Cause | Immediate Recovery Action |
| :--- | :--- | :--- | :--- |
| **Docker daemon offline** | `Cannot connect to the Docker daemon at unix:///var/run/docker.sock` | Docker Desktop process not running or starting | Start Docker Desktop; wait for system tray icon to turn solid green; re-run `docker info`. |
| **ModelProviderError on Run Creation** | HTTP 400: `No live model provider is configured` | Neither Nebius nor FreeLLMAPI credentials are set and mock mode was not explicitly requested | Set `$env:REDLINE_MODEL_PROVIDER="deterministic"` in shell before triggering demo. |
| **HTTP 403 Forbidden on API** | `{"detail": "Forbidden: REDLINE API is restricted to loopback connections"}` | Accessing API via non-loopback IP (e.g. LAN IP or public hostname) | Connect strictly via `http://127.0.0.1:8000` or `http://localhost:8000`. |
| **FreeLLMAPI Gateway 503 / 502** | `no_providers_configured` or connection refused | FreeLLMAPI container stopped or upstream API keys unconfigured in gateway | Fall back to primary Nebius provider or deterministic mode: `$env:REDLINE_MODEL_PROVIDER="deterministic"`. |
| **Nebius Outbound Latency > 60s** | Presentation script waiting on model output | High network load on public Nebius API endpoint | Terminate live run with `Ctrl+C` and instantly launch: `.\venv\Scripts\python.exe scratch/demo_rehearsal.py`. |
| **Windows File Lock on Cleanup** | `PermissionError: [WinError 5] Access is denied: ... .git` | Windows file locks on git repository directories | REDLINE automatically invokes `_rmtree_readonly` to clear read-only attributes. If manually cleaning temp dirs, close any open Explorer windows. |

---

## 6. Pre-Submission Cleanliness Check

Before concluding the demonstration or packaging for submission:
1. **Confirm No Residual Containers**:
   ```powershell
   docker ps -a --filter "name=redline-"
   ```
   *(Must return 0 containers)*
2. **Confirm Zero Git Staged Files**:
   ```powershell
   git status --short
   ```
   *(Zero lines prefixed with `M `, `A `, or `D ` in index column)*
3. **Verify Frozen Benchmark Anchor**:
   ```powershell
   .\venv\Scripts\python.exe -c "from backend.benchmark.integrity import verify_dataset_anchor; res = verify_dataset_anchor(); assert res.status == 'VERIFIED'"
   ```
