# REDLINE — Stage 15 End-to-End Demo Guide

This guide documents the execution of deterministic, repeatable demonstration scenarios for REDLINE Stage 15, validating complete end-to-end integration from task submission to evidence receipt.

---

## 1. Overview & System Guarantees

REDLINE is an autonomous software-engineering verification system featuring:
- **Authoritative Deterministic Gates:** Candidate verdicts (`VERIFIED`, `REJECTED`, `INCONCLUSIVE`) are determined strictly by deterministic test suites and adversarial invariants, never by LLMs or heuristics.
- **Fail-Closed Security Boundary:** Untrusted repositories submitted to `LocalDevelopmentBackend` are strictly blocked (`POLICY_BLOCKED`). Callers cannot self-promote by setting request fields.
- **Autonomous Repair Loops:** Candidates failing verification enter an auditable repair loop preserving patch lineage (`cand-v1` -> `cand-v2`) within bounded governance budgets.
- **Cryptographic Evidence Integrity:** Every run generates an immutable Evidence Receipt with Merkle hashes and ECDSA signatures. Missing or tampered evidence fails closed.
- **Advisory-Only Judge:** The Judge LLM provides explanatory summaries for human engineers, but is strictly prohibited from altering or overriding verification verdicts.

---

## 2. Environment Configuration

### Required Environment Variables

For the core deterministic demo, **no external API keys or cloud credentials are required**:

```bash
# Optional: Set trusted repositories if testing external repos in trusted development mode
# Default authorized fixtures: test-repo, repo-1, demo-repo-a, demo-repo-b, demo-repo-c, etc.
export REDLINE_TRUSTED_REPOSITORIES="demo-repo-a,demo-repo-b,demo-repo-c"

# Optional: Offline test provider is used by default in demo runs
export REDLINE_ENV="development"
```

> [!NOTE]
> Nebius / OpenAI API keys (`NEBIUS_API_KEY`) are NOT required for the deterministic baseline demo. REDLINE operates with fully deterministic offline providers for all demo scenarios.

---

## 3. Demo Execution Options

### Option 1: Standalone CLI Demo Runner (Scenarios A through E)

Execute all 5 scenarios with detailed terminal logging:
```bash
# Run all scenarios
python -m backend.demo.run_demo all

# Or run individual scenarios
python -m backend.demo.run_demo A
python -m backend.demo.run_demo B
python -m backend.demo.run_demo C
python -m backend.demo.run_demo D
python -m backend.demo.run_demo E
```

### Option 2: Full End-to-End Web UI & API Demo

#### Step 1: Start the Backend API Server
In your terminal:
```bash
# From workspace root
.\venv\Scripts\python.exe -m uvicorn backend.api.main:app --host 127.0.0.1 --port 8000 --reload
```
API docs available at: `http://127.0.0.1:8000/docs`

#### Step 2: Start the Next.js Frontend
In a second terminal:
```bash
cd frontend
npm run dev
```
Open `http://localhost:3000` in your browser.

#### Step 3: Interactive Demo Presets in UI
In the web interface:
1. Click **"Scenario A: Successful Verification"** to pre-fill a valid task contract with `TRUSTED_DEVELOPMENT`. Click **"Start Verification Run"**. Watch the run advance through `RECON` → `PLAN` → `BUILD` → `VERIFY` → `JUDGE` → `COMPLETED` with verdict `VERIFIED`.
2. Inspect the **Evidence Receipt**, test counters (Executed: 5, Passed: 5, Failed: 0), SHA-256 patch hash, and Advisory Judge explanation.
3. Click **"Scenario B: Autonomous Repair"** to trigger an initial candidate failure and watch the system generate Candidate V2 with lineage tracking.
4. Click **"Scenario D: Sandbox Boundary Test"** with `UNTRUSTED` repository to observe the immediate `POLICY_BLOCKED` terminal state.

---

## 4. Scenario Breakdown & Expected Outcomes

| Scenario | Objective | Input Configuration | Expected Verdict | Terminal State | Evidence Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Scenario A** | Clean candidate pass | `repo-1`, valid patch, tests pass | `VERIFIED` | `COMPLETED` | Valid Merkle hash, ECDSA signature verified |
| **Scenario B** | Candidate failure + repair | `demo-repo-b`, failing candidate v1 | `VERIFIED` (on v2) | `COMPLETED` | Preserves lineage (`v1` -> `v2`), Cycle 1 logged |
| **Scenario C** | Adversarial rejection | `demo-repo-c`, hostile counterexamples | `REJECTED` | `ABORTED` / `REJECTED` | Rejection recorded, counterexample captured |
| **Scenario D** | Security boundary | `unknown-repo`, `UNTRUSTED` trust | `POLICY_BLOCKED` | `ABORTED` / `POLICY_BLOCKED` | Fails closed, zero code executed |
| **Scenario E** | Evidence tamper fail-closed | Modified receipt payload hash | `INTEGRITY_COMPROMISED` | Fails closed (`JUDGE_FAIL`) | Cryptographic mismatch flagged |

---

## 5. Verification & Reset Procedure

### Resetting Between Runs
The API and Orchestrator maintain isolated run contexts in memory and temporary sandbox directories. To reset local test artifacts:
```powershell
# Clean any temporary test directories and pycache
Get-ChildItem -Path . -Include __pycache__, .pytest_cache -Recurse -Force | Remove-Item -Recurse -Force
```

### Running Test Verification Gates
```bash
# 1. Mandatory Security Regression Tests
.\venv\Scripts\python.exe -m pytest tests/test_stage15_security_regression.py -v

# 2. Stage 15 Demo Scenarios Suite
.\venv\Scripts\python.exe -m pytest tests/test_stage15_demo_scenarios.py -v

# 3. Stage 14.3 Lifecycle Consistency Suite
.\venv\Scripts\python.exe -m pytest tests/test_stage14_3_lifecycle_consistency.py -v

# 4. Stage 12.2 API Integration Suite
.\venv\Scripts\python.exe -m pytest tests/test_stage12_2_api_integration.py -v

# 5. Full Backend Test Suite
.\venv\Scripts\python.exe -m pytest

# 6. Frontend Quality Gates
cd frontend
npm test
npx tsc --noEmit
node ./node_modules/eslint/bin/eslint.js .
npm run build
```
