# STAGE UI-A6 IMPLEMENTATION PLAN
## Agents, Models & Settings UI Redesign

**Project:** REDLINE — Autonomous Software Engineering & Verification Platform  
**Stage:** UI-A6 (The ONLY authorized stage)  
**Date:** 2026-10-15  
**Design Reference:** `Degine.md/stitch_poject_redline/redline_engineering_ops/DESIGN.md`

---

### 1. Routes & Design Prototype Mapping

| Route | Page Name | Stitch Prototype Folder | Key Reference Files |
|-------|-----------|-------------------------|---------------------|
| `/agents` | Agent Configuration & Architecture Overview | `Degine.md/stitch_poject_redline/agent_llm_configuration/` | `code.html`, `screen.png` |
| `/models` | Model Providers & Provenance Reference | `Degine.md/stitch_poject_redline/models_configuration/` | `code.html`, `screen.png` |
| `/settings` | Platform Governance, Ceilings & Security Policies | `Degine.md/stitch_poject_redline/settings/` | `code.html`, `screen.png` |

---

### 2. Architectural Truthfulness & Safety Boundaries

1. **Frozen Architecture Preserved:**
   - The canonical Orchestrator, state machine transitions, deterministic verifier, database schemas, and Python implementation are strictly frozen and will not be edited.
   - The frontend remains purely a presentation surface: verifier measures, judge explains (non-authoritative), frontend displays.
2. **Backend API Reality:**
   - The backend exposes REST routes under `/api/v1/runs` only.
   - There are no separate `/api/v1/agents`, `/api/v1/models`, or `/api/v1/settings` CRUD endpoints.
   - All architecture specifications, provider definitions, and system ceilings on `/agents`, `/models`, and `/settings` must be truthfully labeled as:
     - `STATIC SPECIFICATION` / `CONFIGURED ARCHITECTURE` (for the 5 logical agents and providers)
     - `STATIC POLICY` / `READ-ONLY CEILINGS` (for system governance limits)
     - `LIVE PROBE` (strictly for the gateway connectivity test `GET /api/v1/runs`)
   - Zero simulated toggles, fake "Save Changes" operations, or fictitious online agent swarm telemetry.
3. **Zero Credential Exposure Mandate:**
   - No API keys (e.g. `NEBIUS_API_KEY`) are ever rendered in plain text, stored in localStorage/sessionStorage, or repopulated into form values.
   - Any credential inputs must be strictly masked (`type="password"`), accompanied by warnings that credentials belong in server environment variables.
4. **Judge Subordination:**
   - The Judge Agent is prominently marked as `Non-Authoritative Advisory`. Its purpose is strictly to explain evidence; it can never overturn deterministic verifier outcomes or change verdicts.

---

### 3. Detailed Redesign Plan by Route

#### Route A: `/agents` (`frontend/src/app/agents/page.tsx`)
- **Visual Aesthetic:** Adopt the Stitch Agent LLM Configuration layout with dark obsidian canvas (`#09090b`), elevated cards (`#0d0e12`), border tokens (`#222430`), and crimson accents (`#ef4444`).
- **Header & Telemetry Ribbon:**
  - Breadcrumbs: `CORE // 04. AGENTS // ARCHITECTURE_SPECIFICATION`.
  - Heading: `04. Agents & Architecture Specification` with `v2.4-deterministic` tag.
  - Subtitle: *Frozen architectural specification of the five logical agents, authorized toolsets, least-privilege boundaries, and prompt-injection guardrails.*
  - Top Telemetry Ribbon (Truthful):
    - Configured Logical Agents: `5 / 5 Configured` (Architect, Builder, Red Team, Repairer, Judge).
    - Architecture Model: `Orchestrator-Centric (Shared Agent Interface)`.
    - Verification Authority: `Deterministic Verifier (Non-Agent Policy Gate)`.
    - Runtime Privilege: `Least Authority (Clean Sandbox Separation)`.
- **The Five Logical Agent Matrix:**
  1. **Architect Agent:**
     - Module: `backend/agents/architect.py:ArchitectAgent`
     - Authority: `READ_ONLY_PLANNER`
     - Tools: `list_files`, `read_file`, `search_code`
     - Contract: Input `TaskContract` → Output `ArchitectPlan`
     - Invariant: Zero write permissions. Forbidden from executing shell commands or altering repository snapshots.
  2. **Builder Agent:**
     - Module: `backend/agents/builder.py:BuilderAgent`
     - Authority: `CODE_SYNTHESIZER`
     - Tools: `synthesize_diff`, `inspect_plan`
     - Contract: Input `ArchitectPlan, TaskContract` → Output `PatchCandidate`
     - Invariant: Strictly scoped by `allowed_scope`. Forbidden from modifying protected paths (`.github`, `Dockerfile`, `venv`).
  3. **Red Team Agent:**
     - Module: `backend/agents/red_team.py:RedTeamAgent`
     - Authority: `ADVERSARIAL_ATTACKER`
     - Tools: `boundary_fuzzer`, `invariant_violator`, `counterexample_search`
     - Contract: Input `PatchCandidate, RepositorySnapshot` → Output `AttackCandidate, MutationSpec`
     - Invariant: Cannot declare verdicts. Evaluated strictly in isolated clean-state sandbox. Prompt injections discarding `VERIFIED` claims.
  4. **Repairer Agent:**
     - Module: `backend/agents/repairer.py:RepairerAgent`
     - Authority: `TARGETED_REPAIRER`
     - Tools: `targeted_diff_repair`
     - Contract: Input `Counterexample, BasePatchHash` → Output `RepairCandidate`
     - Invariant: Bounded by iteration budget. Must link fixes to specific counterexample evidence hashes in patch lineage.
  5. **Judge Agent:**
     - Module: `backend/agents/judge.py:JudgeAgent`
     - Authority: `NON_AUTHORITATIVE_ADVISORY`
     - Tools: `evidence_synthesizer`
     - Contract: Input `EvidenceReceipt, StructuredObservation` → Output `JudgeExplanation`
     - Invariant: Strictly subordinate to deterministic verifier. Opinions cannot overturn counterexamples or falsify verdicts.
- **Global Orchestration Policy Panel:**
  - Clear explanation of the frozen state machine and why dynamic agent modification is prohibited.

#### Route B: `/models` (`frontend/src/app/models/page.tsx`)
- **Visual Aesthetic:** Adopt the Stitch Models Configuration layout with 3 provider cards (NVIDIA Nemotron, Nebius Token Factory, Deterministic Offline Mock).
- **Header & Telemetry Ribbon:**
  - Breadcrumbs: `CORE // 09. MODELS // INFRASTRUCTURE`.
  - Heading: `09. Models & Provider Infrastructure` with `v2.4-deterministic` tag.
  - Subtitle: *Supported model providers, server-side credential isolation, and model provenance tracking.*
  - Quick action: `+ New Task Contract` linking to `/`.
- **Top Telemetry Ribbon (Truthful):**
  - Supported Providers: `2 Configured (Nebius Token Factory + Deterministic Mock)`.
  - Credential Storage: `Server-Side Environment (NEBIUS_API_KEY)`.
  - Frontend Exposure: `Zero Keys In Browser`.
  - Default Model: `meta-llama/Meta-Llama-3.1-70B-Instruct` (or configured `NEBIUS_MODEL`).
- **Provider Infrastructure Cards:**
  1. **Nebius Token Factory Provider:**
     - Backend: `backend/models/nebius_provider.py:NebiusProvider`
     - Models: `deepseek-ai/DeepSeek-R1`, `meta-llama/Meta-Llama-3.1-70B-Instruct`, `Qwen/Qwen2.5-Coder-32B-Instruct`
     - Status: `SERVER_CONFIGURED`
     - Credential Security: Server-side environment variable `NEBIUS_API_KEY`. Zero browser storage.
     - Provenance: Captured in `EvidenceReceipt.model_provenance`.
  2. **NVIDIA Nemotron / Cloud Provider:**
     - Status: `ARCHITECTURE_REFERENCE` (Supported via Nebius Token Factory gateway).
     - Models: `nvidia/nemotron-4-340b-instruct`, `nvidia/nemotron-70b-instruct`
     - Note: Clearly disclosed as routing through Token Factory endpoint.
  3. **Deterministic Test Mock Provider:**
     - Backend: `backend/models/deterministic_provider.py:DeterministicTestProvider`
     - Models: `deterministic-mock-v1`
     - Status: `OFFLINE_AVAILABLE` (Zero external network dependencies, guaranteed CI/CD test reproducibility).
- **Zero Frontend Credential Mandate Notice:**
  - Explains that the browser never handles API secrets or token values.

#### Route C: `/settings` (`frontend/src/app/settings/page.tsx`)
- **Visual Aesthetic:** Adopt the Stitch Settings engineering console layout with dark obsidian panels, horizontal section tabs, and system governance indicators.
- **Header & Telemetry:**
  - Breadcrumbs: `CORE // 10. SETTINGS // GOVERNANCE_POLICY`.
  - Heading: `10. Platform Governance & Settings` with `v2.4-deterministic` badge.
  - Subtitle: *Platform governance parameters, system ceilings, sandbox security policies, and gateway connectivity verification.*
- **Section Tabs:**
  1. **Gateway & Connectivity (Live Probe):**
     - Base URL display (`NEXT_PUBLIC_API_BASE_URL` or default `http://127.0.0.1:8000/api/v1`).
     - "Test Backend Connection" button sending live probe to `GET /api/v1/runs` and measuring roundtrip latency.
     - Explicit disclosure that this probe verifies HTTP route reachability only and does not test sandbox daemons or model provider quotas.
  2. **System Ceilings (Static Policy / Read-Only):**
     - Hardcoded governance limits from `backend/orchestrator/limits.py`:
       - `MAX_ITERATIONS: 50`
       - `MAX_TOOL_CALLS: 100`
       - `MAX_RUNTIME: 3600s`
       - `MAX_PATCH_SIZE: 1,048,576 B (1MB)`
       - `MAX_REPO_FILES: 1,000 files`
       - `MAX_CONTEXT_BYTES: 131,072 B (128KB)`
     - Clarifies that these ceilings are fail-closed invariants enforced by the backend Orchestrator.
  3. **Sandbox Isolation & Safety Policies (Read-Only):**
     - Tier 2 / Tier 3 Ephemeral Docker / MicroVM isolation.
     - Capabilities dropped: `CAP_DROP ALL`.
     - Host networking: Disabled (`--net none`).
     - Root filesystem: Read-only.
     - Working directory isolation: Stage 16.1 defense-in-depth against directory traversal escapes.
  4. **Interface Preferences (Local Storage / Safe):**
     - High-contrast obsidian theme indicator.
     - Reduced motion support indicator (`prefers-reduced-motion`).

---

### 4. Reusable Components & Primitives

- `AppShell`: Persistent navigation and layout shell.
- Monospace breadcrumbs, dark obsidian surface tokens (`#09090b`, `#0d0e12`, `#13141b`, `#222430`, `#ef4444`).
- Inline SVG icons with zero external CDN dependencies.
- Visible focus rings (`focus-visible:ring-2 focus-visible:ring-[#ef4444]`) and semantic heading hierarchy (exactly one `<h1>` per page).

---

### 5. Files Expected to Change

1. `frontend/src/app/agents/page.tsx` — Complete redesign using Stitch Agent LLM Configuration aesthetic.
2. `frontend/src/app/models/page.tsx` — Complete redesign using Stitch Models Configuration aesthetic.
3. `frontend/src/app/settings/page.tsx` — Complete redesign using Stitch Settings layout.
4. `frontend/src/tests/agents_models_settings_ui_a6.test.ts` — **New Test Suite** verifying single H1 hierarchy, truthful status distinctions, zero secret leakage, read-only policy enforcement, gateway probe safety, and keyboard accessibility.
5. `docs/stage_ui_a6_completion_report.md` — Authoritative completion report for Stage UI-A6.

---

### 6. Testing & Acceptance Criteria

- Execute `npm test` across all frontend test suites (ensure 100% pass rate).
- Execute `npm run build` (Next.js Turbopack build, verify all 17 routes compile and 0 type errors).
- Execute `pytest tests/` (verify 256 backend tests continue to pass without regressions).
- Inspect Git diff for scope discipline.
