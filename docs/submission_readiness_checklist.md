# REDLINE — Hackathon Submission Readiness Checklist & Evidence Inventory

**Competition**: Nebius Global AI Hackathon  
**Project Name**: REDLINE — Autonomous Vulnerability Remediation & Deterministic Verification Platform  
**One-Sentence Tagline**: *AI proposes. The sandbox executes. Deterministic verification decides. Evidence explains why.*  
**Document Target**: Comprehensive Submission Package & Audit Inventory  
**Date**: 2026-10-25  

---

## 1. Submission Requirements Checklist

| Requirement Field | Project Information & Status | Evidence / Location | Status |
| :--- | :--- | :--- | :---: |
| **Project Name** | **REDLINE** (Autonomous Vulnerability Remediation & Deterministic Verification Platform) | `README.md:1` | **COMPLETE** |
| **One-Sentence Description** | Treating generative AI models as untrusted proposal generators whose candidate patches are executed inside isolated sandboxes and evaluated exclusively by deterministic verification oracles and tamper-evident evidence receipts. | `README.md:3-5` | **COMPLETE** |
| **Problem Statement** | Autonomous AI coding assistants suffer from self-assessment hallucination (models declaring their own broken code verified), uncontrolled host execution, and lack of tamper-evident proof. | `README.md:9-16` | **COMPLETE** |
| **Target Users** | Security engineers, DevSecOps teams, repository maintainers, automated vulnerability remediation pipelines, and mission-critical software teams. | `docs/04-ui-ux.md` | **COMPLETE** |
| **Core Differentiator** | Complete decoupling of generation from verification authority: LLMs have zero authority over state transitions or verdicts; sandbox exit code alone governs verification; receipts are cryptographically sealed. | `README.md:26-36` | **COMPLETE** |
| **Architecture & Stack** | - **Backend**: Python 3.11+ / FastAPI / Pydantic v2 / SQLite / Docker SDK<br/>- **Frontend**: Next.js 16 (App Router) / React 19 / TypeScript / Tailwind CSS / Vanilla CSS dark-theme<br/>- **Sandbox**: Docker Engine (`--network none`, `--cap-drop ALL`, unprivileged `UID 1000`, read-only root)<br/>- **Models**: Nebius Token Factory (`nvidia/Nemotron-3_5-Lightning`) / FreeLLMAPI | `backend/`, `frontend/`, `deploy/sandbox/` | **COMPLETE** |
| **Nebius Integration** | Outbound inference routes to **Nebius Token Factory** (`https://api.tokenfactory.nebius.com/v1/chat/completions`) using the open-source foundation model `nvidia/Nemotron-3_5-Lightning`. Structured Pydantic schema validation (`extra="forbid"`). | `backend/models/nebius_provider.py` | **COMPLETE** |
| **Installation & Setup** | Clear, reproducible step-by-step instructions for Windows (PowerShell) and Linux/macOS (Bash). | `README.md:200-297`, `docs/demo_day_runbook.md` | **COMPLETE** |
| **Security & Threat Model** | Comprehensive disclosures: reactive disk measurement, Windows WSL2 memory constraints, domain-separated receipt hashing vs PKI digital signatures, and localhost-only API boundary (`LocalhostOnlyMiddleware`). | `README.md:413-427` | **COMPLETE** |
| **Demo & Script** | - 3-Minute timed script (`docs/demo_script_3_minutes.md`)<br/>- Fast offline deterministic rehearsal runner (~10.6s)<br/>- 5-Scenario deterministic regression suite | `scratch/demo_rehearsal.py`, `docs/demo_script_3_minutes.md` | **COMPLETE** |
| **Frozen Benchmark** | Held-Out Security Benchmark anchor frozen at tag `benchmark-v1.0.0` (commit `6e476bcc...`, manifest SHA-256 `d2cd...20c2`, 84/84 artifacts verified clean). | `backend/benchmark/dataset/` | **COMPLETE** |
| **Repository Integrity** | Branch `master`, HEAD `792ace62...`, **0 staged files, zero commits**, all baseline changes preserved. | `git status` | **COMPLETE** |

---

## 2. Honest Demo Evidence Inventory

This inventory distinguishes between directly verified live outputs, deterministic offline demonstrations, and pre-recorded preflight artifacts:

### 2.1 Direct Verified Executions (Conducted During Audit)
| Execution Type | Command | Duration | Final State | Verification Verdict | Audit Reference |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Offline Deterministic Demonstration** | `.\venv\Scripts\python.exe scratch/demo_rehearsal.py` | **10.61s** | `VERIFIED` | `VALID` (SHA-256 `94051a3b...`) | Stage 2.9.10 (§4.1) |
| **Targeted Security Remediation Suite** | `pytest tests/test_stage_2_9_9_security_remediation.py` | **2.01s** | N/A | **18 passed, 0 failed** | Stage 2.9.10 (§3.1) |
| **Core Production Regression Suite** | `pytest <10 canonical test files>` | **13.19s** | N/A | **179 passed, 1 skipped, 0 failed** | Stage 2.9.10 (§3.2) |
| **Provider Unit & Cross-Isolation Suites** | `pytest tests/test_model_providers.py tests/test_provider_cross_isolation.py` | **1.10s** | N/A | **65 passed, 0 failed** | Stage 2.9.10 (§3.3) |
| **Frontend Acceptance Suite** | `npm test -- --watchAll=false` | **1.00s** | N/A | **111 passed, 0 failed** | Stage 2.9.10 (§3.4) |
| **Benchmark Anchor Verification** | `backend/benchmark/integrity.py` | **0.50s** | `VERIFIED` | **4/4 checks passed (84 artifacts)** | Stage 2.9.10 (§1) |

---

### 2.2 Live Provider Smoke Tests & Status Disclosure
| Provider | Model Identifier | Active Shell Status | Historical Preflight Evidence | Current Audit Status |
| :--- | :--- | :---: | :--- | :---: |
| **Nebius Token Factory** | `nvidia/Nemotron-3_5-Lightning` | Key unconfigured in shell | Step 2.9.6.4 / 2.9.6.5 end-to-end run completed in 72.89s; valid receipt generated (`scratch/live_e2e_results.json`). | **NOT VERIFIED IN THIS RUN** (Deferred to demo preflight per zero-credentials rule) |
| **FreeLLMAPI Gateway** | `llama-3.3-70b` | Daemon running (HTTP 200); Key unconfigured | Stage 2.9.7.3 live run completed in 18.18s; valid receipt generated (`3b370038...`). | **NOT VERIFIED IN THIS RUN** (Deferred to demo preflight per zero-credentials rule) |

---

### 2.3 Existing UI Screenshots & Media Inventory
The repository contains 9 authentic UI screenshots located in `Degine.md/stitch_poject_redline/`:
1. `dashboard_overview/screen.png`: Main dashboard showing system ceiling metrics, active runs, and lifecycle states.
2. `session_detail_mission_control/screen.png`: Live run telemetry view with lifecycle stage stepper and container status.
3. `evidence_cryptographic_receipts/screen.png`: Cryptographic evidence receipts ledger with SHA-256 hashes and tamper checks.
4. `agent_llm_configuration/screen.png`: Agent trust boundary settings (Architect, Builder, advisory Judge).
5. `models_configuration/screen.png`: Foundation model routing (Nebius Token Factory / FreeLLMAPI).
6. `playground_sandbox_deep_dive/screen.png`: Sandboxed execution workbench and container isolation telemetry.
7. `projects/screen.png`: Managed repository projects and trust levels.
8. `repositories/screen.png`: Repository catalog and security gate policies.
9. `settings/screen.png`: Platform ceilings, network boundaries, and environment disclosures.

---

### 2.4 Pre-Recorded Evidence Files & Logs
- `scratch/live_e2e_results.json`: Record of verified live run against Nebius Token Factory (`nvidia/Nemotron-3_5-Lightning`, 72.89s, receipt verified).
- `docs/stage_2_9_6_5_final_integration_and_demo_readiness_report.md`: Complete audit of successful live run and judge diagnosis.
- `docs/stage_2_9_7_3_upstream_provider_live_verification_report.md`: Complete audit of successful FreeLLMAPI gateway inference.
- `docs/stage_2_9_9_critical_security_remediation_report.md`: Remediation report covering REV-001 through REV-018.
- `docs/stage_2_9_10_final_release_gate_report.md`: Final release-engineering gate and independent audit report.

---

## 3. Submission Packaging Verification

- [x] All secret keys (`.env`, `*.key`, `*.pem`) are strictly gitignored and excluded from candidate workspaces.
- [x] Benchmark anchor is frozen at `benchmark-v1.0.0` (84 artifacts, SHA-256 `d2cd...20c2`).
- [x] All 10 backend regression suites pass cleanly (179 passed, 1 skipped, 0 failed).
- [x] Frontend test suite passes cleanly (111 passed, 0 failed).
- [x] Fast deterministic demonstration executes in ~10.6 seconds with exit code 0.
- [x] README is fully synchronized with test counts, gateway policies, and demo steps.
- [x] Three-minute presentation demo script is finalized (`docs/demo_script_3_minutes.md`).
- [x] Demo-day runbook and failure recovery plan are established (`docs/demo_day_runbook.md`).
- [x] Zero files are staged or committed in the git repository.
