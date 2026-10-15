# REDLINE — STAGE UI-A7 IMPLEMENTATION PLAN
## Final UI Acceptance, Integration, Responsiveness & Polish

**Stage:** UI-A7 (Final UI Stabilization & Acceptance)  
**Authorized Scope:** UI-A7 only  
**Frozen Baseline:** UI-A1 through UI-A6 complete; backend frozen (`docs/REDLINE_v1.1_ARCHITECTURE_FROZEN.md`)  

---

### 1. Mandatory Preflight & Baseline Status

Prior to any modifications or fixes, the system was inspected and tested to establish a baseline:
- **Git Working Tree:** Clean, no uncommitted changes outside untracked workspace artifacts.
- **Frontend Test Suite (`npm test`):** 102/102 tests passing (0 failures, 0 skipped, runtime ~1.4s).
- **TypeScript Type Check (`npx tsc --noEmit`):** Clean (exit code 0).
- **Production Build (`npm run build`):** Clean compilation across all 17 App Router routes (12 static routes, 3 dynamic redirect routes).
- **Backend Regression Suite (`pytest tests/`):** 256 passed, 1 skipped (Docker e2e test correctly skipped), 0 failures.

---

### 2. Frozen Architecture & Invariant Constraints

Non-negotiable architectural boundaries:
- **No Orchestrator or Verifier Edits:** The central Orchestrator loop, deterministic verification engine, and state machine transitions remain frozen.
- **Verdict Authority:** The deterministic test runner and invariant evaluators are sole authorities for verdicts (`VERIFIED`, `REJECTED`, `INCONCLUSIVE`). Operational failures (timeouts, container aborts) remain distinct from code verdicts.
- **Subordinate Judge Advisory:** The Judge Agent synthesizes natural language evidence summaries but cannot overturn verdicts, manufacture passes, or dictate execution state.
- **Zero Client Credential Leakage:** No API keys or tokens in the UI, `localStorage`, `sessionStorage`, or client logs. `NEBIUS_API_KEY` is isolated server-side.
- **Sandbox Security Profile:** Execution occurs exclusively inside Docker containers with `CAP_DROP_ALL`, `--net none`, read-only roots, and path traversal guards.
- **Truthful Status Policy:** No fabricated online agent swarms, fake GPU latencies, simulated model pings, or artificial success toasts.

---

### 3. Route Audit Matrix (All 12 Navigation Destinations + Dynamic Routes)

| Route | Expected Role | Layout & Components | Acceptance Verification |
|-------|---------------|---------------------|--------------------------|
| `/` | Task Intake & Contract Submission | Bento split: Intake form (left), System Telemetry & Recent Pipeline (right) | Validates task submission, repo selection, input bounds, and redirect to sessions. |
| `/dashboard` | Executive Operational Overview | Fleet metrics, Stage breakdown, Active runs table, Quick intake CTA | Truthful stats from `getRunHistory()`, empty/loading states, verified sound counters. |
| `/projects` | Workspace & Benchmark Catalog | 3 Target Repositories (Express, Python, FastAPI) | Discloses static demo workspaces, no fake CRUD, links to Task Intake. |
| `/sessions` | Mission Control & Run Monitoring | Left run selector, Center execution timeline, Right inspector panel | Live polling (5000ms), 5-failure threshold, race-condition guard, terminal state stop. |
| `/sessions/[id]` | Dynamic Run Deep-Link | Redirects to `/sessions?runId={id}` | URL query sync, deep-link restoration, direct entry. |
| `/runs/[id]` | Legacy Dynamic Deep-Link | Redirects to `/results?runId={id}` | Backward-compatible URL preservation. |
| `/repositories` | Monitored Repositories & Security Profile | Repository cards, Security policy gates | Discloses architectural reference, zero fake GitHub URLs, links to Intake. |
| `/agents` | Autonomous Agent Architecture Specification | 5 Agent roles, Input/Output contracts, Invariants | Discloses frozen static specification, least-authority matrix, Judge subordination. |
| `/playground` | Sandbox Workbench & Terminal Observer | File tree, Diff inspector, Read-only terminal | Enforces read-only observation, path traversal rejection, no host-shell bypass. |
| `/evidence` | Cryptographic Evidence & Proofs | 7-col inspector, 5-col ledger, Multi-tab matrix | Truthful unverified client hash status, JSON receipt download, hash copying. |
| `/evidence/[id]` | Dynamic Evidence Deep-Link | Redirects to `/evidence?runId={id}` | URL query sync and instant receipt loading. |
| `/models` | Model Providers & Infrastructure | 3 Providers (Nebius, NVIDIA, Mock) | Discloses server-side credential isolation, 0 client keys, provenance tracking. |
| `/settings` | Platform Governance & Ceilings | 4 Horizontal tabs: Gateway, Ceilings, Sandbox, Prefs | Live Gateway probe with latency, read-only system ceilings from `limits.py`. |
| `/history` | Verification History & Audit Ledger | Filter tabs, Real-time search, Ledger table | Distinguishes empty DB vs empty search, clipboard copying, multi-destination links. |
| `/results` | Run Verification Results & Findings | `VerdictDisplay`, Proof highlights, Judge, Diff | Separates operational failure from verdict, links to Evidence/Sessions. |

---

### 4. Responsive Viewport Acceptance Plan

Inspect and verify layouts at three mandatory viewports:
1. **Desktop (1440px):**
   - Full 64-width persistent sidebar.
   - Multi-column bento grids (e.g. 7-col / 5-col splits on `/evidence`, 2-col splits on `/`, 3-col on `/models`).
   - Sticky top operational status header with full telemetry ribbons.
2. **Tablet (768px):**
   - Collapsible mobile drawer or fluid flex-wrapping.
   - Grid reflow: 2-column or single-column responsive collapse.
   - Tables scroll horizontally with `overflow-x-auto` without overflowing the viewport.
3. **Mobile (390px):**
   - Top navbar with hamburger trigger and accessible slide-out modal drawer (`role="dialog"`).
   - Single-column card stacks.
   - Long strings (Run IDs, SHA-256 hashes, model identifiers) wrap cleanly (`break-all`, `truncate`, or horizontal scroll).
   - Touch targets meet minimum accessible dimensions (44x44px).
   - Zero horizontal overflow at document/body level.

---

### 5. Cross-Page Workflow Acceptance Flow

Verify the end-to-end user journey across the frontend:
1. **Intake Flow:** Submit a task contract from `/` → verify navigation to `/sessions?runId=...`.
2. **Monitoring Flow:** Observe lifecycle progression on `/sessions` → verify stage visuals and event logs.
3. **Verdict & Analysis Flow:** Navigate to `/results?runId=...` → verify deterministic verdict display, judge advisory, and patch diff.
4. **Audit & Cryptographic Proof Flow:** Navigate to `/evidence?runId=...` → verify receipt digest, sandbox security profile, and JSON receipt download.
5. **Ledger Auditing:** Navigate to `/history` → verify run appearance in ledger table, test search/filtering.
6. **Platform Inspection:** Traverse `/agents`, `/models`, and `/settings` → verify architecture disclosures, zero credential inputs, and live Gateway probe.
7. **Negative & Error Flows:** Navigate to non-existent run ID (`/sessions?runId=invalid-id-999`) → verify truthful 404 alert without UI crashing.

---

### 6. Accessibility, Consistency & Code Quality Audit

- Single semantic `<h1>` on every page.
- Accessible heading hierarchy (`<h1>` → `<h2>` → `<h3>`).
- Semantic buttons and links (`<button>` for actions, `<Link>` for navigation).
- Keyboard navigation: Visible crimson focus rings (`focus-visible:ring-2 focus-visible:ring-[#ef4444]`), skip-link to `#main-content`, `Escape` key closes mobile drawer.
- Motion safety: All CSS animations wrapped in `motion-safe:` or respecting `prefers-reduced-motion`.
- Consistent color tokens from `DESIGN.md` (`#09090b` canvas, `#0d0e12` cards, `#13141b` elevated elements, `#222430` borders, `#ef4444` crimson accents).

---

### 7. Regression Verification Gate

1. `npm test` — Run all frontend unit and acceptance tests.
2. `npx tsc --noEmit` — Confirm clean TypeScript compilation.
3. `npx eslint` — Confirm zero lint errors or warnings on all pages.
4. `npm run build` — Confirm clean production Turbopack build.
5. `pytest tests/` — Confirm full backend suite passes with zero regressions.
6. Write `docs/stage_ui_a7_completion_report.md` documenting all audit results, viewport inspections, and gate verification.
