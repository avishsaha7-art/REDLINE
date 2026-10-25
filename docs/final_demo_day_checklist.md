# REDLINE — Final Demo-Day Checklist & Presentation Guide

**Target Event**: Nebius x NVIDIA Global AI Hackathon (Devpost)  
**Submission Deadline**: October 30, 2026, at 10:00 AM PDT  
**Track**: Coding and Agentic Engineering Track  
**Platform**: REDLINE — Autonomous Vulnerability Remediation & Deterministic Verification Platform  
**Document Purpose**: Rapid reference card for presenters and technical reviewers  

---

## 1. 5-Minute Preflight Checklist

Run these commands in order 5 minutes before your demo:

- [ ] **1. Docker Desktop Active**:
  ```powershell
  docker info --format '{{.ServerVersion}}'
  ```
  *Must return a valid version string (e.g. 24.x or 27.x).*

- [ ] **2. Sandbox Runner Image Present**:
  ```powershell
  docker images redline-sandbox-runner:latest
  ```
  *Must list `redline-sandbox-runner:latest`.*

- [ ] **3. Terminal Virtual Environment Activated**:
  ```powershell
  Set-Location p:\REDLINE
  .\venv\Scripts\Activate.ps1
  ```

- [ ] **4. Benchmark Anchor Intact**:
  ```powershell
  .\venv\Scripts\python.exe -c "from backend.benchmark.integrity import verify_dataset_anchor; assert verify_dataset_anchor().status == 'VERIFIED'"
  ```

- [ ] **5. Fast Rehearsal Preflight**:
  ```powershell
  $env:REDLINE_MODEL_PROVIDER="deterministic"
  .\venv\Scripts\python.exe scratch/demo_rehearsal.py
  ```
  *Must complete in ~10–12 seconds with `Final Orchestrator State: VERIFIED` and `Tamper-Evident Integrity: VALID`.*

---

## 2. 3-Minute Presentation Rehearsal Flow

| Time | Topic | Key Talking Point | Screen Cue |
| :--- | :--- | :--- | :--- |
| **0:00–0:20** | **The Problem** | Generative models evaluate themselves, creating a hallucination trap. Coding agents run on host workstations with ambient credentials. | Split view: `data/fixtures/repo-cons-1/main.py` failing `test_main.py`. |
| **0:20–0:45** | **Architecture** | Separation of powers: Generative models propose; ephemeral sandboxes execute; deterministic test suites decide; receipts explain. | Diagram from `README.md` (Untrusted -> Sandbox -> Verifier -> Evidence). |
| **0:45–1:30** | **Workflow Execution** | Trigger automated remediation. Disclose mock provenance honestly (deterministic rehearsal engine). | Run `.\venv\Scripts\python.exe scratch/demo_rehearsal.py`. |
| **1:30–2:10** | **Sandbox Isolation** | Strict `--network none`, dropped Linux capabilities, zero credentials in container. Exit code 0 alone governs VERIFIED. | Terminal shows `[SANDBOX ISOLATION CONTROLS]` and `1 passed` in ~800ms. |
| **2:10–2:40** | **Evidence Receipt** | Tamper-evident `EvidenceReceipt` bound via domain-separated SHA-256 canonical hash. Advisory Judge cannot alter verdict. | Terminal highlights `[CRYPTOGRAPHIC EVIDENCE RECEIPT]` and SHA-256 digest. |
| **2:40–3:00** | **Impact & Conclusion** | Tested live against Nebius Token Factory (`nvidia/Nemotron-3_5-Lightning`). Transforms AI coding into an auditable engineering pipeline. | Show UI dashboard at `http://localhost:3000` or stored screenshots. |

---

## 3. Emergency Recovery Matrix

| Scenario | Immediate Action | Spoken Disclosure |
| :--- | :--- | :--- |
| **Docker Desktop not started** | Launch Docker Desktop immediately. While starting, open `scratch/live_e2e_results.json` and web UI to walk through architecture and verified logs. | *"While Docker Desktop finishes initializing its container daemon, let's inspect the telemetry from our preflight live run against Nebius Token Factory."* |
| **Sandbox Image Missing** | Build image quickly (~30s): `docker build -t redline-sandbox-runner:latest -f deploy/sandbox/Dockerfile deploy/sandbox/`. | *"We're instantiating our minimal, non-root sandbox runner built on pinned Python 3.11 slim bookworm."* |
| **Nebius Live API Latency > 45s** | Interrupt with `Ctrl+C` and instantly launch: `.\venv\Scripts\python.exe scratch/demo_rehearsal.py`. | *"Public API latency is elevated; we'll switch immediately to our offline deterministic rehearsal runner, which executes the exact same state machine and Docker container with deterministic test responses."* |
| **FreeLLMAPI Gateway 503** | Switch to primary Nebius provider or deterministic mode. | *"FreeLLMAPI is an optional secondary provider; we'll switch to our primary path."* |
| **Frontend UI Not Running** | Present entirely from terminal output and interactive OpenAPI Swagger UI (`http://127.0.0.1:8000/docs`). | *"REDLINE is built API-first: every execution state, artifact diff, and evidence receipt is accessible via our OpenAPI contract."* |
| **Presentation Running Over Time** | Skip live code diff inspection and jump straight to the Evidence Receipt SHA-256 hash and verdict authority attestation. | *"In the interest of time, look at the final Evidence Receipt: domain-separated SHA-256 digest, cryptographically verified, zero model hallucination."* |
| **Receipt Tamper Question** | Run in-memory tamper check: changing a single bit in a receipt immediately invalidates `receipt_hash`. | *"Tamper evidence is mathematical: any bit-level change to test summaries or verdicts invalidates the domain-separated SHA-256 digest."* |

---

## 4. Submission Checklist for Devpost Upload

- [ ] **Title**: REDLINE — Autonomous Vulnerability Remediation & Deterministic Verification Platform
- [ ] **Tagline**: AI proposes. The sandbox executes. Deterministic verification decides. Evidence explains why.
- [ ] **Track**: Coding and Agentic Engineering Track
- [ ] **Required Model**: NVIDIA Nemotron family (`nvidia/Nemotron-3_5-Lightning`)
- [ ] **Required Platform**: Nebius Token Factory (`https://api.tokenfactory.nebius.com/v1`)
- [ ] **Repository Link**: Public GitHub repository with clean working tree
- [ ] **Demo Video**: 3-minute video following `docs/demo_script_3_minutes.md`
- [ ] **Screenshots**: 9 authentic UI screenshots from `Degine.md/stitch_poject_redline/`
- [ ] **Built With**: Python, FastAPI, Pydantic, Docker, Next.js 16, TypeScript, Tailwind CSS, Nebius Token Factory, NVIDIA Nemotron
