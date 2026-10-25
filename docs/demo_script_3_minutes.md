# REDLINE — 3-Minute Presentation Demo Script

**Platform**: REDLINE — Autonomous Vulnerability Remediation & Deterministic Verification Platform  
**Target Event**: Nebius Global AI Hackathon  
**Target Audience**: Hackathon Judges, Security Researchers, and AI Engineers  
**Presentation Duration**: Exactly 3 Minutes (180 Seconds)  
**Primary Demonstration Mode**: Fast Offline Deterministic Rehearsal (~10.6s execution) with Pre-Recorded Live Nebius Logs Available as Supporting Evidence

---

## Presentation Overview & Setup

Before speaking, ensure the presentation terminal is open at `p:\REDLINE` with the Python virtual environment activated:
```powershell
Set-Location p:\REDLINE
.\venv\Scripts\Activate.ps1
```

If demonstrating in **Deterministic Mock Mode** (Recommended for zero-network dependency and guaranteed 10-second response):
```powershell
$env:REDLINE_MODEL_PROVIDER="deterministic"
```

If demonstrating in **Live Nebius Mode** (Requires configured `NEBIUS_API_KEY`):
```powershell
$env:REDLINE_MODEL_PROVIDER="nebius"
```

---

## Timed Speaker Script & Screen Cues

### 0:00 – 0:20 | The Problem: The Self-Assessment Trap in AI Coding
- **Screen Cue**: Open `data/fixtures/repo-cons-1/main.py` in split view alongside terminal. Point to the broken `old` placeholder function failing `test_main.py`.
- **Spoken Script**:
  > *"Every software team wants autonomous AI agents to remediate vulnerabilities and patch bugs. But existing agents have a fatal flaw: **they evaluate themselves**. Asking an LLM whether its own code fix is secure creates a circular hallucination trap. Worse, many coding agents execute untrusted code directly on host workstations with ambient developer credentials. At REDLINE, we asked a fundamental question: **What if we treat generative models as strictly untrusted proposal generators, and let isolated deterministic sandboxes make all decisions?**"*

---

### 0:20 – 0:45 | REDLINE Architecture: Decoupling Generation from Verification
- **Screen Cue**: Show the REDLINE Architecture Flowchart (from `README.md` or slide):
  `[Untrusted LLM Proposes] -> [Isolated Docker Sandbox Executes] -> [Deterministic Policy Decides] -> [Evidence Receipts Prove]`
- **Spoken Script**:
  > *"REDLINE enforces strict separation of powers across four architectural tiers:
  > First, our **Architect and Builder agents** propose remediation plans and diffs through strict Pydantic schema gates.
  > Second, candidate patches enter an **ephemeral Docker container** stripped of network access, Linux capabilities, and host credentials.
  > Third, our **Deterministic Verification Policy** makes the authoritative verdict based purely on sandbox exit codes and contract oracles.
  > Fourth, every run produces a tamper-evident **Evidence Receipt** sealed with domain-separated SHA-256 canonical digests. Even our advisory Judge agent cannot alter or upgrade the verdict."*

---

### 0:45 – 1:30 | Live Workflow Execution
- **Screen Cue**: Clear terminal and launch the demo runner:
  ```powershell
  .\venv\Scripts\python.exe scratch/demo_rehearsal.py
  ```
- **Spoken Script**:
  > *(As terminal starts streaming)*  
  > *"Let's see this in action. We trigger an automated remediation for a broken calculation routine in an untrusted repository.
  > Notice the startup attribution: we are running our deterministic rehearsal engine in mock development mode—disclosing all execution provenance honestly without simulating live network latency.
  > In the background, REDLINE resolves authorized workspace boundaries using strict path containment, wipes all secret and `.env` files from candidate copies, and spins up our hardened container `redline-sandbox-runner`."*

---

### 1:30 – 2:10 | Sandbox Isolation & Deterministic Verdict
- **Screen Cue**: Terminal prints `[SANDBOX ISOLATION CONTROLS]`, `[PATCH CANDIDATE & LINEAGE]`, and `[SANDBOX TEST EXECUTION]`.
- **Spoken Script**:
  > *"Notice the isolation controls logged right here: `--network none` is strictly enforced; candidate code has zero external network access.
  > The Builder synthesized a clean patch: replacing the broken stub with `def calculate(): return 0`.
  > The test suite executed inside the isolated container: **Exit Code 0, 1 test passed in 835 milliseconds**.
  > Because the sandbox test genuinely passed and all invariant oracles succeeded, our deterministic orchestrator transitions the run to the authoritative **VERIFIED** state. The model didn't decide this—the deterministic test exit code did."*

---

### 2:10 – 2:40 | Cryptographic Evidence Receipt & Advisory Judge
- **Screen Cue**: Highlight `[CRYPTOGRAPHIC EVIDENCE RECEIPT]` and `[JUDGE EXPLANATION (ADVISORY ONLY)]` in terminal output.
- **Spoken Script**:
  > *"Now look at the evidence tier. REDLINE generates an `EvidenceReceipt` binding the canonical repository snapshot hash, the patch lineage, and execution telemetry into a domain-separated SHA-256 digest: `94051a3b...`.
  > Tamper-evident integrity is verified cryptographically: any bit-level modification to test results or diffs invalidates the receipt immediately.
  > Above it is our Judge agent's plain-text explanation. But observe our key design principle: the Judge is explicitly labeled **ADVISORY ONLY**. If a model claims a patch works but the test suite fails, REDLINE fails closed into `REJECTED`."*

---

### 2:40 – 3:00 | Hackathon Impact, Real-World Preflight & Conclusion
- **Screen Cue**: Show the Web Dashboard (`http://localhost:3000`) or screenshot of `session_detail_mission_control/screen.png` showing dark-theme telemetry and evidence receipt.
- **Spoken Script**:
  > *"In our submission preflight, we also verified live outbound inference against **Nebius Token Factory** using the open-source **NVIDIA Nemotron 3.5 Lightning** model, as well as secondary routing via self-hosted **FreeLLMAPI**.
  > REDLINE transforms autonomous vulnerability remediation from an uncontrolled risk into an auditable, verifiable engineering pipeline.
  > Generative models propose. The sandbox executes. Deterministic verification decides.
  > Thank you!"*

---

## Presentation Delivery Notes & Fallback Protocol

1. **Disclosure Rule**: If presenting using `scratch/demo_rehearsal.py` without live API keys, explicitly say: *"This rehearsal executes the full local Orchestrator state machine, real Docker sandbox container, and cryptographic receipt builder using deterministic test responses."*
2. **If presenting Live Nebius**: If live API keys and internet are stable, pass `--live`:
   ```powershell
   .\venv\Scripts\python.exe scratch/demo_rehearsal.py --live
   ```
   Execution will take ~45–70s due to NVIDIA Nemotron's 1,200+ reasoning tokens. Use that window to walk through the Next.js frontend UI (`http://localhost:3000`).
3. **If Live Nebius encounters a rate limit or network stall**: Instantly switch back to deterministic mode:
   ```powershell
   .\venv\Scripts\python.exe scratch/demo_rehearsal.py
   ```
   Do not pause or apologize; seamlessly disclose: *"We'll switch directly to our offline deterministic runner to inspect the exact same container sandbox isolation and receipt verification."*
