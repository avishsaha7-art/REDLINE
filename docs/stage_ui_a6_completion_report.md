# REDLINE UI REDESIGN — STAGE UI-A6 COMPLETION REPORT
## Agents, Models & Settings

**Stage:** UI-A6  
**Status:** COMPLETE & VERIFIED  
**Reference Assets:**
- Agents Prototype: `Degine.md/stitch_poject_redline/agent_llm_configuration/code.html`, `screen.png`
- Models Prototype: `Degine.md/stitch_poject_redline/models_configuration/code.html`, `screen.png`
- Settings Prototype: `Degine.md/stitch_poject_redline/settings/code.html`, `screen.png`
- Design Tokens: `Degine.md/stitch_poject_redline/redline_engineering_ops/DESIGN.md`  
**Target Routes:** `/agents` (Autonomous Agent Architecture Specification), `/models` (Model Providers & Infrastructure), and `/settings` (Platform Governance & Verification Ceilings)

---

### 1. Summary of Redesigns

#### Autonomous Agent Architecture Specification (`/agents`)
The `/agents` page has been redesigned using the Stitch Agent LLM Configuration aesthetic with Obsidian-dark tokens (`#09090b` canvas, `#0d0e12` cards, `#13141b` inputs/panels, `#222430` borders, `#ef4444` crimson accents, and role-specific authority badges):
1. **Header & Context:**
   - Monospace cyber breadcrumbs: `CORE // 04. AGENTS // ARCHITECTURE_SPECIFICATION`.
   - Title: `04. Agent Fleet & Architecture Specification` with `v2.4-deterministic` badge.
   - Action cluster: `+ New Task Contract` linking to `/`.
2. **Truthful Architecture Disclosure Banner:**
   - Clear disclosure indicating that the agent fleet is an architectural specification governed by `docs/REDLINE_v1.1_ARCHITECTURE_FROZEN.md`.
   - Agents operate behind a centralized Orchestrator loop; arbitrary runtime process spawning or frontend agent execution is strictly prohibited.
3. **Truthful Telemetry Ribbon:**
   - Configured Agents: `5 / 5 Configured` (Architect, Builder, Red Team, Repairer, Judge).
   - Orchestration Mode: `Central Orchestrator` with fail-closed bounds.
   - Synthesis Temperature: `0.0 Deterministic` (strict repeatability).
   - Verifier Precedence: `Deterministic Verifier Absolute`.
   - Shell Execution: `0 Host Shells (Sandbox Isolated)`.
4. **Agent Roles & Authority Inspector:**
   - **Architect Agent** (`backend/agents/architect.py`): `READ_ONLY_PLANNER`. AST generation, dependency graph resolution, vulnerability attack surface mapping. Authorized tools: `list_files`, `read_file`, `search_code`. Output: `ArchitectPlan`. Invariant: Zero write permissions.
   - **Builder Agent** (`backend/agents/builder.py`): `CODE_SYNTHESIZER`. Synthesizes unified diffs strictly within allowed scopes. Prohibited from editing protected paths (`.github`, `Dockerfile`, `venv`). Cannot declare its patch verified.
   - **Red Team Agent** (`backend/agents/red_team.py`): `ADVERSARIAL_ATTACKER`. Generates attack vectors, boundary fuzzer inputs, and invariant counterexamples. Forbidden from declaring verdicts; prompt injections attempting to output `VERIFIED` are discarded.
   - **Repairer Agent** (`backend/agents/repairer.py`): `TARGETED_REPAIRER`. Converts counterexample failures into targeted patches while preserving passing tests. Historical evidence records cannot be deleted.
   - **Judge Agent** (`backend/agents/judge.py`): `NON_AUTHORITATIVE_ADVISORY`. Explains evidence receipts in human-readable prose. Subordinate to deterministic verifier; cannot overturn verdicts or manufacture test passes.
5. **Sidebar Governance & Invariants:**
   - Least-Authority Matrix detailing non-negotiable runtime boundaries for each agent role.
   - Orchestration state progression visualization: `Recon & Plan` → `Synthesize Patch` → `Execute Attacks` → `Targeted Repair` → `Deterministic Verification` → `Explain Evidence`.
   - Cross-navigation links to `/models`, `/settings`, and `/playground`.

#### Models & Provider Infrastructure (`/models`)
Redesigned following the Stitch Models Configuration layout:
1. **Header & Context:**
   - Monospace cyber breadcrumbs: `CORE // 09. MODELS // INFRASTRUCTURE`.
   - Title: `09. Models & Provider Infrastructure` with `Configuration Reference` and `v2.4-deterministic` badges.
   - Action cluster: `+ New Task Contract` linking to `/`.
2. **Zero-Credential Security Disclosure Banner:**
   - Explicitly documents server-side credential isolation. API keys reside exclusively in backend environment variables (`NEBIUS_API_KEY`).
   - Zero credential inputs or browser secret caching (`localStorage` / `sessionStorage`) are permitted.
3. **Telemetry Ribbon:**
   - Configured Providers: `2 Active` (Nebius Token Factory + Offline Mock).
   - Credential Storage: `Server Environment (NEBIUS_API_KEY)`.
   - Browser Secret Leakage: `0 Keys in UI` (verified zero client storage).
   - Provenance Tracking: `Evidence Receipts` (exact model identifiers, temperature 0.0, token ceilings).
4. **Provider Infrastructure Grid:**
   - **Nebius Token Factory Provider** (`backend/models/nebius_provider.py`): Primary inference runtime on Nebius Cloud. Supported models: `deepseek-ai/DeepSeek-R1`, `meta-llama/Meta-Llama-3.1-70B-Instruct`, `Qwen/Qwen2.5-Coder-32B-Instruct`. Endpoint: `https://api.tokenfactory.nebius.com/v1/chat/completions`. Guardrails: Server-side API key isolation and Pydantic validation.
   - **NVIDIA Nemotron / Cloud Gateway**: High-parameter reasoning models (`nvidia/nemotron-4-340b-instruct`, `nvidia/nemotron-70b-instruct`) routed via server-dispatched Token Factory infrastructure. Temperature 0.0 enforcement and automated output truncation on response limit breach.
   - **Deterministic Test Mock Provider** (`backend/models/deterministic_provider.py`): Hermetic offline mock provider for local verification, CI/CD regression suites, and offline benchmark testing (`deterministic-mock-v1`). Zero external network calls; in-memory fixtures.
5. **Cross-Navigation Notice Box:**
   - Quick links to `/agents` and `/settings`.

#### Platform Governance & Settings (`/settings`)
Redesigned following the Stitch Settings layout with horizontal tabbed navigation:
1. **Header & Context:**
   - Monospace cyber breadcrumbs: `CORE // 10. SETTINGS // GOVERNANCE_POLICY`.
   - Title: `10. Platform Governance & Settings` with `v2.4-deterministic` badge.
   - Action cluster: `+ New Task Contract` linking to `/`.
2. **Horizontal Tabs Navigation:**
   - Tab 1: `API Gateway Probe`
   - Tab 2: `System Ceilings (Policy)`
   - Tab 3: `Sandbox Isolation Rules`
   - Tab 4: `Interface Preferences`
3. **Tab 1 — API Gateway Probe (Live Measured Network Check):**
   - Displays configured `NEXT_PUBLIC_API_BASE_URL` (defaults to `http://127.0.0.1:8000/api/v1`).
   - Button: `Test Backend Connection`. Sends real HTTP `GET /api/v1/runs` via `apiClient.getRunHistory()`.
   - Measures exact roundtrip latency in milliseconds (`performance.now()`).
   - Diagnostic scope disclosure: "Verifies HTTP route reachability only; does not evaluate sandbox daemon or model provider health."
4. **Tab 2 — Enforced System Ceilings (Static Policy / Read-Only):**
   - Authoritative constants from `backend/orchestrator/limits.py`:
     - `MAX_ITERATIONS: 50` (Per-task repair loop)
     - `MAX_TOOL_CALLS: 100` (Total invocation budget)
     - `MAX_RUNTIME: 3600s` (1 hour wall-clock limit)
     - `MAX_PATCH_SIZE: 1 MB` (1,048,576 bytes)
     - `MAX_REPO_FILES: 1,000` (Max files per snapshot)
     - `MAX_CONTEXT_BYTES: 128 KB` (131,072 bytes)
     - `MAX_FAILED_ATTEMPTS: 5` (Consecutive failure threshold)
     - `MAX_ATTACK_CASES: 20` (Red team attack budget)
   - Labeled `STATIC POLICY` and explicitly notes that dynamic client-side editing is not supported to protect compute infrastructure against denial-of-service.
5. **Tab 3 — Sandbox Isolation Rules (Read-Only Security Specification):**
   - Container execution profile: Network `DISABLED (--net none)`, Capabilities `DROP_ALL`, Filesystem `READ_ONLY_ROOT`, Lifecycle `EPHEMERAL TEARDOWN`.
   - Working directory path sanitization (`../` traversal blocks).
   - Deterministic verifier authority and subordinate Judge advisory guarantees.
6. **Tab 4 — Interface Preferences:**
   - WCAG 2.2 AA Obsidian color palette documentation.
   - Motion safety (`prefers-reduced-motion`) compliance.
   - Visible keyboard navigation focus rings.
7. **Cross-Navigation Footer:**
   - Direct links to `/agents`, `/models`, and `/sessions`.

---

### 2. Exact Files Modified and Added

| File | Type | Description |
|------|------|-------------|
| `docs/stage_ui_a6_plan.md` | Added | Implementation plan mapping prototypes, API contracts, truthfulness boundaries, and test criteria. |
| `frontend/src/app/agents/page.tsx` | Modified | Redesigned agent architecture specification, 5 REDLINE agent roles, input/output contracts, authorized tools, least-privilege matrix, and cross-navigation links. |
| `frontend/src/app/models/page.tsx` | Modified | Redesigned model provider infrastructure, zero client-side credentials disclosure, Nebius / NVIDIA / Mock providers, supported models, and provenance tracking. |
| `frontend/src/app/settings/page.tsx` | Modified | Redesigned platform governance screen with 4 horizontal tabs: Gateway Probe, System Ceilings, Sandbox Isolation Rules, and Interface Preferences. |
| `frontend/src/tests/agents_models_settings_ui_a6.test.ts` | Added | Comprehensive acceptance test suite with 8 focused tests covering single H1, truthfulness, zero secrets, read-only ceilings, 5 agents, model providers, probe reachability, and cross-navigation. |
| `docs/stage_ui_a6_completion_report.md` | Added | Authoritative completion report for Stage UI-A6. |

---

### 3. Actual API Endpoints and Schemas Used

| Route | Endpoint / Data Source | Method | Data Contract / Schema | Usage in UI-A6 |
|-------|------------------------|--------|------------------------|----------------|
| `/settings` | `/api/v1/runs` | `GET` | `RunSummary[]` via `apiClient.getRunHistory()` | Evaluates gateway route reachability and measures real HTTP roundtrip latency in ms. |
| `/agents` | `backend/agents/*.py` | N/A | `AgentRole` architectural metadata | Static architectural specification representing the frozen multi-agent system. |
| `/models` | `backend/models/*.py` | N/A | `ModelProviderSpec` metadata | Static provider configuration reference reflecting server-side model infrastructure. |
| `/settings` | `backend/orchestrator/limits.py` | N/A | Hardcoded governance constants | Read-only system ceiling limits displayed in governance tab. |

---

### 4. Categorization of Statuses (Live vs. Static vs. Unavailable)

| Component / Item | Displayed Status | Classification | Grounded Evidence / Rationale |
|------------------|------------------|----------------|--------------------------------|
| Gateway Probe | `ONLINE: Gateway responded` or `OFFLINE: Connection failed` | **Live Measured** | Grounded in actual HTTP GET call to `/api/v1/runs` with real timing measurement. |
| Gateway Latency | `${pingLatency}ms` | **Live Measured** | Measured client-side using `performance.now()` across the real fetch duration. |
| Agent Fleet Roles | `5 / 5 Configured` | **Static Architecture** | Reflects the 5 backend agents defined in `docs/REDLINE_v1.1_ARCHITECTURE_FROZEN.md`. |
| Active Agent Swarm | Not Displayed | **Unavailable / Prohibited** | Omitted completely. No fake online indicators or simulated agent threads. |
| Model Providers | `Configured Reference` | **Static Reference** | Reflects real server-side provider implementations (`NebiusProvider`, `DeterministicTestProvider`). |
| Model Latency / Ping | Not Displayed | **Unavailable / Prohibited** | Omitted completely. No fake model ping telemetry without an authoritative backend probe endpoint. |
| System Ceilings | `STATIC POLICY (Read-Only)` | **Static Policy** | Directly matches hardcoded limits in `backend/orchestrator/limits.py`. |
| Dynamic Settings Modification | Disabled / Read-Only | **Unavailable / Prohibited** | Omitted completely. No fake toggle buttons or simulated "Save Settings" mutations. |
| Container Security Rules | `POLICY SPECIFICATION (Read-Only)` | **Static Security** | Documents Docker sandbox flags (`--net none`, `DROP_ALL`, read-only root). |

---

### 5. Frontend Test, Type Check, Lint, and Build Results

#### 1. Frontend Test Suite (`npm test`)
```
npm test
> frontend@0.1.0 test
> tsx --test src/tests/**/*.test.ts

✔ UI-A6 Agents, Models & Settings Acceptance Tests (19.4ms)
  ✔ Criterion 1: Agents, Models, and Settings maintain single H1 semantic hierarchy
  ✔ Criterion 2: Truthful distinction between configured, unavailable, and measured statuses
  ✔ Criterion 3: Zero credential leakage & API keys never displayed or accepted in UI
  ✔ Criterion 4: Read-only security policy and system ceilings cannot be toggled client-side
  ✔ Criterion 5: Five logical REDLINE agents faithfully represented with Judge subordinate advisory
  ✔ Criterion 6: Models page truthfully presents providers and supported architectures
  ✔ Criterion 7: Settings page implements truthful Gateway Probe with route reachability
  ✔ Criterion 8: Seamless cross-navigation destinations are preserved across all pages

ℹ tests 102
ℹ suites 0
ℹ pass 102
ℹ fail 0
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 1343.05ms
```

#### 2. TypeScript Type Check (`npx tsc --noEmit`)
```
npx tsc --noEmit
Exit code: 0 (Clean, 0 errors)
```

#### 3. ESLint Audit (`npx eslint`)
```
npx eslint src/app/agents/page.tsx src/app/models/page.tsx src/app/settings/page.tsx src/tests/agents_models_settings_ui_a6.test.ts
Exit code: 0 (Clean, 0 errors, 0 warnings)
```

#### 4. Production Next.js Build (`npm run build`)
```
npm run build
> frontend@0.1.0 build
> next build

▲ Next.js 16.4.0 (Turbopack)
✓ Running next.config.ts took 149ms
- Cache Components enabled
- Partial Prefetching enabled

  Creating an optimized production build ...
✓ Compiled successfully in 4.8s
  Running TypeScript ...
  Finished TypeScript in 3.7s ...
  Collecting page data using 11 workers ...
  Generating static pages using 11 workers (0/17) ...
  Generating static pages using 11 workers (4/17) 
  Generating static pages using 11 workers (8/17) 
  Generating static pages using 11 workers (12/17) 
✓ Generating static pages using 11 workers (17/17) in 1780ms
  Finalizing page optimization ...

Route (app)
┌ ○ /
├ ○ /_not-found
├ ○ /agents
├ ○ /dashboard
├ ○ /evidence
├   /evidence/[id]
│ └ ◐ /evidence/[id]
├ ○ /history
├ ○ /models
├ ○ /playground
├ ○ /projects
├ ○ /repositories
├ ○ /results
├   /runs/[id]
│ └ ◐ /runs/[id]
├ ○ /sessions
├   /sessions/[id]
│ └ ◐ /sessions/[id]
└ ○ /settings

○  (Static)             prerendered as static content
◐  (Partial Prerender)  prerendered as static HTML with dynamic server-streamed content

Exit code: 0
```

---

### 6. Backend Regression Test Verification

Executed full backend test suite with `PYTHONPATH='.'`:
```
$env:PYTHONPATH='.'; .\venv\Scripts\pytest tests/
============================= test session starts =============================
platform win32 -- Python 3.14.8, pytest-9.1.1, pluggy-1.6.0
rootdir: P:\REDLINE
collected 257 items

tests\test_orchestrator.py .......                                       [  2%]
tests\test_stage10.py .....                                              [  4%]
tests\test_stage11.py ......                                             [  7%]
tests\test_stage11_remediation.py ....                                   [  8%]
tests\test_stage12_1_api.py .......                                      [ 11%]
tests\test_stage12_2_api_integration.py ......                           [ 13%]
tests\test_stage14_3_lifecycle_consistency.py .........                  [ 17%]
tests\test_stage15_demo_scenarios.py ......                              [ 19%]
tests\test_stage15_security_regression.py .......                        [ 22%]
tests\test_stage16_1_working_dir_hardening.py ...........                [ 26%]
tests\test_stage16_2_1_cors.py ...........                               [ 30%]
tests\test_stage16_3_1_persistence.py .............                      [ 35%]
tests\test_stage16_3_2_artifact_storage.py ...............               [ 41%]
tests\test_stage4.py .....................                               [ 49%]
tests\test_stage5.py ............                                        [ 54%]
tests\test_stage5_1.py ..........                                        [ 58%]
tests\test_stage6.py ........                                            [ 61%]
tests\test_stage7.py ................                                    [ 67%]
tests\test_stage7_e2e.py .s                                              [ 68%]
tests\test_stage8a.py ........                                           [ 71%]
tests\test_stage8a_security.py .........                                 [ 75%]
tests\test_stage8b.py .............                                      [ 80%]
tests\test_stage8b_e2e.py .                                              [ 80%]
tests\test_stage8c.py .............                                      [ 85%]
tests\test_stage9.py ...............                                     [ 91%]
tests\test_stage9_1.py ...........                                       [ 95%]
tests\test_stage9_1_r.py .....                                           [ 97%]
tests\test_stage9_2.py ......                                            [100%]

================ 256 passed, 1 skipped, 53 warnings in 27.37s =================
```
Result: **256 passed, 1 skipped (test_stage7_e2e Docker skip). Zero failures or regressions.**

---

### 7. Security Invariants, Least-Privilege, and Credential Isolation Verification

1. **Zero Credential Exposure:**
   - Zero `<input type="password">` or API key inputs exist on `/agents`, `/models`, or `/settings`.
   - `NEBIUS_API_KEY` is documented and isolated strictly to the server environment.
   - Zero storage of secrets in `localStorage`, `sessionStorage`, or cookies.
2. **Read-Only System Ceilings:**
   - The platform governance limits (`MAX_ITERATIONS`, `MAX_TOOL_CALLS`, `MAX_RUNTIME`, `MAX_PATCH_SIZE`) are displayed as read-only constants from `backend/orchestrator/limits.py`.
   - No mock forms or simulated mutations were introduced.
3. **Subordinate Judge Advisory:**
   - The Judge Agent is explicitly documented as `NON_AUTHORITATIVE_ADVISORY`.
   - Both in `/agents` specifications and runtime components, deterministic verdicts take absolute precedence over natural-language commentary.
4. **No Host-Shell Execution or Sandbox Bypass:**
   - No host-shell execution mechanisms or arbitrary process spawning controls were created.
   - Sandbox profile specifies `CAP_DROP_ALL`, `--net none`, and ephemeral container teardown.

---

### 8. Accessibility (WCAG 2.2 AA) and Semantic HTML Auditing

1. **Heading Hierarchy:**
   - Exactly one semantic `<h1>` element per page across `/agents`, `/models`, and `/settings`.
   - Subsections use semantic `<h2>` and `<h3>` tags with logical structure.
2. **Keyboard Navigation & ARIA Support:**
   - Tab list on `/settings` uses `role="tablist"`, `role="tab"`, and `aria-selected` attributes.
   - Tab panels use `role="tabpanel"`.
   - Status messages use `role="status"` for screen-reader announcement.
   - Interactive buttons have visible focus rings (`focus:ring-2 focus:ring-[#ef4444]`).
3. **Contrast & Color Semantics:**
   - High contrast text (`text-white`, `text-slate-200`, `text-slate-300`, `text-slate-400`) against obsidian backgrounds (`#09090b`, `#0d0e12`, `#13141b`).
   - Every colored status badge is paired with non-color icons or clear text labels (e.g. `✓`, `0 Keys in UI`, `STATIC POLICY`, `OFFLINE_AVAILABLE`).

---

### 9. Known Limitations, Read-Only Policies, and Future Scope

1. **Read-Only Administrative View:**
   - Because the backend architecture does not provide write/mutation endpoints for model configurations or system limits (`/api/v1/runs` is the sole registered route), settings and model specifications are presented as truthful, read-only platform governance records.
2. **Gateway Route Probe Scope:**
   - The `/settings` connectivity probe tests HTTP route reachability to `/api/v1/runs`. It explicitly discloses that it does not evaluate container daemon health, GPU availability, or LLM token balances.

---

### 10. Confirmation of UI-A1–UI-A5 Preservation and Frozen Architecture Fidelity

- All 12 primary navigation destinations (`/`, `/dashboard`, `/projects`, `/sessions`, `/repositories`, `/agents`, `/playground`, `/evidence`, `/models`, `/settings`, `/history`, `/results`) remain intact and functional.
- All 17 App Router routes (including dynamic routes `/evidence/[id]`, `/runs/[id]`, and `/sessions/[id]`) build without warnings or regressions.
- All 102 frontend tests pass cleanly.
- All 256 backend regression tests pass cleanly.
- Canonical state machine, deterministic verifier, limits, and SQLite schemas remain completely unaltered.
- **UI-A6 is fully complete. Work is halted awaiting user instruction.**
