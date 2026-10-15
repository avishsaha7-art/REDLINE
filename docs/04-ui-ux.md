# REDLINE — UI/UX Design Specification and Product Experience

**Document:** `docs/04-ui-ux.md`  
**Stage:** 13 (UI/UX Specification and Product Experience)  
**Parent Specification:** `docs/REDLINE_v1.1_ARCHITECTURE_FROZEN.md`  
**Preceding Implementation:** `docs/stage12.2.md`  
**Status:** SPECIFICATION COMPLETE — AWAITING REVIEW  

---

## 1. Documentation Sequence & Discrepancy Notice

This document forms part of the standard REDLINE architectural documentation sequence:
1. `01-architecture.md`
2. `02-frontend.md`
3. `03-backend.md`
4. **`04-ui-ux.md` (This document)**
5. `05-api.md`
6. `06-agents.md`
7. `07-assets.md`
8. `08-antigravity.md`
9. `09-claude.md`
10. `10-loop-functionality.md`
11. `11-testing.md`
12. `12-plugins-and-skills.md`
13. `13-final-system-prompt.md`

### Sequence Discrepancy Statement
An inspection of the `docs/` repository reveals that standalone files `01-architecture.md`, `02-frontend.md`, and `03-backend.md` are not presently committed under those exact filenames. 
- The authoritative system architecture is codified in `docs/REDLINE_v1.1_ARCHITECTURE_FROZEN.md`.
- The frontend integration foundation and API wiring are documented across `docs/stage12.1.md` and `docs/stage12.2.md`.
- This discrepancy is formally recorded here in compliance with project governance. The sequence is preserved without renaming or skipping document numbers.

---

## 2. Product Philosophy & Design Tenets

REDLINE is an autonomous software-engineering verification system operating on the core thesis:  
> **"AI-generated code is guilty until proven safe."**

The interface must reflect this premise through an **evidence-centered developer tool aesthetic**, not a conversational assistant or decorative demo.

### Core Visual Story
```text
BUILD → ATTACK → FAIL → REPAIR → RETEST → VERIFY
```
The transition from attack vulnerability discovery to repair and re-verification must be visually clear and unambiguous.

### Foundational Tenets
1. **Evidence Over Confidence:** UI density prioritizes cryptographic hashes, diffs, execution logs, counterexamples, and test assertions over synthetic scores.
2. **Authority Decoupling:** The UI is strictly a presentation and intake boundary. It cannot declare verdicts, advance states, authorize sandboxes, or fabricate claims.
3. **Strict Separation of State vs. Verdict:** 
   - *Lifecycle State* (`RunState`): The execution progress of the pipeline.
   - *Deterministic Verdict* (`VerificationStatus`): The cryptographic and executable finding of the verifier.
   - *Operational Result* (`OperationalResult`): The health and resource status of the execution runtime.
   A run ending in `VERIFIED` state does *not* imply the code is sound unless the `EvidenceReceipt` explicitly certifies `VERIFIED`.
4. **Transparent Dissonance Display:** If the backend exhibits inconsistencies (e.g. state `VERIFIED` but receipt verdict `INCONCLUSIVE`), the UI renders both faithfully without masking the discrepancy.
5. **Non-Authoritative Advisory:** The LLM Judge's narrative is displayed with explicit visual markers denoting that it is an advisory explanation subordinate to the deterministic evidence.

---

## 3. End-to-End User Experience Workflow

```text
┌───────────────────────┐
│     Dashboard &       │
│     Run History       │
└──────────┬────────────┘
           │ (1) Select Existing or Create New
           ▼
┌───────────────────────┐
│ Task Contract Intake  │ ◄─── Input Task ID, Repo ID, Commit, Description, Scope
└──────────┬────────────┘
           │ (2) Client Validation & POST /api/v1/runs
           ▼
┌───────────────────────┐
│ Effective Budget View │ ◄─── Display backend-enforced ceilings (Caps applied)
└──────────┬────────────┘
           │ (3) Asynchronous Background Launch
           ▼
┌─────────────────────────────────────────────────────────────┐
│                Live Orchestration Monitor                   │
│  INIT → RECON → PLAN → BASELINE → BUILD → TEST → ATTACK ... │
└──────────┬──────────────────────────────────────────────────┘
           │ (4) Polling GET /api/v1/runs/{id}
           ▼
┌─────────────────────────────────────────────────────────────┐
│                 Verification & Verdict Split                │
│   ┌───────────────────────────┐ ┌─────────────────────────┐ │
│   │   Deterministic Verdict   │ │    Operational Result   │ │
│   │   (VERIFIED / REJECTED)   │ │  (Completed / Aborted)  │ │
│   └───────────────────────────┘ └─────────────────────────┘ │
└──────────┬──────────────────────────────────────────────────┘
           │ (5) Completed Execution
           ▼
┌─────────────────────────────────────────────────────────────┐
│                    Evidence & Audit Surface                 │
│  ┌─────────────────────────────┐ ┌────────────────────────┐ │
│  │   Authoritative Receipt     │ │   Non-Authoritative    │ │
│  │  - Hashes & Signatures      │ │   Judge Explanation    │ │
│  │  - Patch Lineage & Diffs    │ │  - Verified Claims     │ │
│  │  - Test & Attack Evidence   │ │  - Failed Claims       │ │
│  │  - Counterexamples          │ │  - Limitations         │ │
│  └─────────────────────────────┘ └────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## 4. Screen & Component Specifications

### 4.1 Dashboard and Run History (`RunHistory`)
- **Purpose:** Serves as the primary overview of all verification jobs, displaying execution recency, final lifecycle state, deterministic verdict, and timestamps.
- **Data Source:** `GET /api/v1/runs` (`List[RunHistoryItemResponse]`).
- **Consumed Fields:** `run_id`, `task_id`, `final_state`, `verdict`, `created_at`, `completed_at`.
- **Information Hierarchy:**
  1. Table Header with total run count and live refresh button.
  2. Data grid sorting descending by `created_at`.
  3. Columns: Run ID (monospace link), Task Target, Final Lifecycle State badge, Deterministic Verdict badge, Duration/Timestamps.
  4. Actions: "Inspect Run" button routing to detail monitor.
- **State Handling:**
  - *Loading:* Skeleton table with pulsating rows.
  - *Empty:* Centered empty state: "No verification runs recorded. Submit a Task Contract to initiate testing."
  - *Error:* Red alert banner displaying API error message with retry trigger.
- **Interaction Contract:** Read-only table. Clicking a row or Run ID populates the Run Details view.
- **Accessibility:** `<table>` with semantic `<caption>`, `<thead>`, `<th>`, accessible sorting headers, and keyboard focusable row buttons (`aria-label="Inspect run {run_id}"`).

### 4.2 Task Contract Creation & Validation (`RunCreationForm`)
- **Purpose:** Intake form for specifying the targets of an adversarial verification run.
- **Data Source:** Form input validated locally against `TaskContract` schema before submission to `POST /api/v1/runs`.
- **Consumed Fields:**
  - `task_id` (string, required, regex `^[a-zA-Z0-9_\-\.]+$`)
  - `repository_id` (string, required)
  - `base_commit_or_snapshot` (string, required, hex hash or snapshot identifier)
  - `task_description` (string, required, markdown supported)
  - `allowed_scope` (list of file glob patterns, optional)
  - `resource_budget` (object with limits, optional)
- **Primary Actions:**
  - "Validate Contract": In-browser JSON/schema validation.
  - "Launch Verification Run": Emits POST request to backend.
  - "Load Benchmark Example": Pre-fills deterministic benchmark contract for quick reproduction.
- **Information Hierarchy:**
  1. Target identification section (`task_id`, `repository_id`, `base_commit_or_snapshot`).
  2. Specification context (`task_description`, scope inclusions).
  3. Resource Budget configuration toggle (collapsible).
  4. Submission button with loading spinner and disabled state during transit.
- **Error States:**
  - *Client Validation:* Field-level inline red text when required fields or patterns fail.
  - *API Rejection:* Banner showing HTTP 422 validation errors or HTTP 400 policy rejections.
- **Accessibility:** Standard `<label for="...">` associations, `aria-required="true"`, `aria-describedby` pointing to validation errors, and `aria-live="polite"` feedback on submission.

### 4.3 Effective Resource Budget Display (`ResourceBudgetNotice`)
- **Purpose:** Communicates the backend governance limits applied to the run, explicitly notifying the user if submitted requests were capped by system ceilings.
- **Data Source:** `GET /api/v1/runs/{run_id}` -> `RunStatusResponse.resource_status` and backend constant ceilings.
- **Consumed Fields:** `iterations_used`, `iterations_limit`, `tool_calls_used`, `tool_calls_limit`, `max_runtime`, `max_patch_size`.
- **Information Hierarchy:**
  1. Horizontal pill row or compact metadata grid:
     - Iterations: `[iterations_used] / [iterations_limit]` (Capped at 50)
     - Tool Calls: `[tool_calls_used] / [tool_calls_limit]` (Capped at 100)
     - Wall Clock Limit: `3600s`
  2. Informational callout: "Backend resource governance strictly caps client budgets to prevent runaway execution."
- **Interaction Contract:** Read-only metadata badge.
- **Accessibility:** `role="status"` with clear text equivalents for gauge bars.

### 4.4 Orchestration Lifecycle Visualizer (`OrchestrationVisualizer`)
- **Purpose:** Real-time progression tracking across the frozen state machine lifecycle stages.
- **Data Source:** `GET /api/v1/runs/{run_id}` (polled every 1500ms while status is `active`).
- **Consumed Fields:** `state` (`RunState`), `status`, `iteration`, `started_at`, `updated_at`.
- **Lifecycle Stages Visualized:**
  ```text
  INIT → RECON → PLAN → BASELINE → BUILD → TEST → ATTACK → ANALYZE → REPAIR → VERIFY → JUDGE → [VERIFIED | ABORTED]
  ```
- **Information Hierarchy:**
  1. Stage Stepper Bar: Horizontal flow on desktop, vertical on mobile/narrow viewports.
  2. Stage Node States:
     - *Past / Completed:* Solid neutral slate with checkmark.
     - *Active:* Pulsing blue ring with execution spinner.
     - *Upcoming / Pending:* Muted gray border with low contrast text.
     - *Terminal ABORTED:* Crimson ring with exclamation indicator.
     - *Terminal VERIFIED:* Emerald ring with verified checkmark.
  3. Execution Metadata footer: Current iteration count, elapsed time, timestamp of latest transition.
- **Error States:** When `state === 'ABORTED'`, highlights the step where execution halted in warning crimson.
- **Accessibility:** `aria-current="step"` on the active stage, `aria-label="Stage {stage}: {status}"`, hidden screen-reader notifications on stage transition.

### 4.5 Run Details & Operational Failures (`RunDetailsView`)
- **Purpose:** Displays detailed diagnostic execution status, separating operational failures (sandbox crash, resource exhaustion, timeout) from verification verdicts.
- **Data Source:** `GET /api/v1/runs/{run_id}` -> `RunStatusResponse`.
- **Consumed Fields:** `run_id`, `task_id`, `state`, `status`, `operational_result`, `operational_error`, `started_at`, `updated_at`.
- **Information Hierarchy:**
  1. Run ID header with quick "Copy ID" button.
  2. Status summary badge (`active`, `completed`, `failed`).
  3. Operational Error Panel (only rendered if `operational_error` or `operational_result` is present):
     - Title: "OPERATIONAL / RUNTIME FAILURE"
     - Categorization: e.g. `TOOL_FAILURE`, `SANDBOX_FAILURE`, `RESOURCE_LIMIT`, `POLICY_BLOCKED`.
     - Raw error detail: Monospace code box with sanitized backend error description.
     - Notice: "Operational failures represent execution environment issues, not deterministic code rejection."
- **Interaction Contract:** Read-only.
- **Accessibility:** `role="alert"` on operational error panel with high-contrast text conforming to WCAG AA.

### 4.6 Deterministic Verdict Display (`VerdictDisplay`)
- **Purpose:** The most prominent visual element certifying the deterministic verification outcome.
- **Data Source:** `GET /api/v1/runs/{run_id}/receipt` or `RunStatusResponse.evidence_receipt.verdict`.
- **Consumed Fields:** `verdict` (`VerificationStatus`: `VERIFIED`, `REJECTED`, `INCONCLUSIVE`, `POLICY_BLOCKED`, `SANDBOX_FAILURE`, `RESOURCE_LIMIT`, `TIMEOUT`, `EXECUTION_FAILURE`).
- **Visual Presentation & Hierarchy:**
  - Header: "AUTHORITATIVE DETERMINISTIC VERDICT" (Uppercase, tracking-widest, neutral slate).
  - Main Display Banner:
    * `VERIFIED`: Background `emerald-50`, border `emerald-500`, text `emerald-800`.
    * `REJECTED`: Background `crimson-50`, border `crimson-500`, text `crimson-800`.
    * `INCONCLUSIVE`: Background `amber-50`, border `amber-500`, text `amber-800`.
    * `PENDING / RUNNING`: Background `slate-50`, border `slate-300`, text `slate-600`.
  - Explanatory Subtitle:
    * *VERIFIED:* "All test assertions, invariants, and adversarial red-team attacks passed without counterexamples."
    * *REJECTED:* "Adversarial verification discovered one or more valid counterexamples that broke invariants."
    * *INCONCLUSIVE:* "Verification cannot guarantee soundness within the granted budget or execution scope."
- **Critical Authority Rule:** This component renders *only* the receipt's `verdict`. It never defaults to `VERIFIED` based on `RunState.VERIFIED`.
- **Accessibility:** Large display text with a minimum 4.5:1 contrast ratio against the banner background, accompanied by `aria-label="Deterministic Verification Verdict: {verdict}"`.

### 4.7 Evidence Receipt Viewer (`EvidenceReceiptView`)
- **Purpose:** Presents the complete, tamper-evident cryptographic evidence bundle generated by the backend `EvidenceBuilder`.
- **Data Source:** `GET /api/v1/runs/{run_id}/receipt` (`EvidenceReceipt`).
- **Consumed Fields:** `receipt_schema_version`, `run_id`, `task_id`, `timestamp`, `policy_version`, `verifier_version`, `verification_scope`, `structured_observation`, `test_summary`, `invariant_summary`, `security_summary`, `counterexamples`, `oracle_results`.
- **Information Hierarchy:**
  1. Receipt Banner: Schema version, cryptographic integrity verification stamp ("HASH VERIFIED").
  2. Scope & Provenance Bar: Model identifier, sandbox backend (`LocalDevelopmentBackend` / `TokenFactorySandbox`), execution time.
  3. Evidence Tabs / Sections:
     - **Test Results (`test_summary`):** Total executed, passed, failed, errored, individual observation list.
     - **Invariant Evaluations (`invariant_summary`):** Invariant ID, description, pass/fail result, evidence hash.
     - **Security Invariants (`security_summary`):** Hook identifiers and security checks.
     - **Counterexamples (`counterexamples`):** Inputs, observed outputs, expected outputs, failure reasons, oracle references.
     - **Oracles (`oracle_results`):** Oracle types and verdict mappings.
- **Interaction Contract:** Read-only with expandable subsections ("View Raw JSON Receipt", "Copy Receipt Hash").
- **Accessibility:** Collapsible accordions with `aria-expanded`, keyboard navigability (`Enter` / `Space`), and monospace text formatted in high-contrast blocks.

### 4.8 Patch Lineage & Cryptographic Hashes (`PatchLineageView`)
- **Purpose:** Audits the provenance of code modifications across iterative repair cycles, linking every patch to its cryptographic SHA-256 hash.
- **Data Source:** `EvidenceReceipt.patch_hash`, `EvidenceReceipt.patch_lineage`, `EvidenceReceipt.evidence_hashes`, `EvidenceReceipt.task_contract_hash`, `EvidenceReceipt.repository_snapshot_hash`, `EvidenceReceipt.receipt_hash`.
- **Information Hierarchy:**
  1. **Hashes Panel:**
     - Receipt Hash (Root Merkle identifier)
     - Task Contract Hash
     - Repository Snapshot Hash
     - Final Candidate Patch Hash
  2. **Patch Lineage Stepper:**
     - Displays sequential patch IDs: `patch-builder-0` → `patch-repair-1` → `patch-repair-2`.
     - Clicking a lineage node opens the candidate diff viewer.
  3. **Evidence Hashes Drawer:** Expandable list of SHA-256 digests certifying every observation, test stdout, and counterexample recorded in the receipt.
- **Interaction Contract:** Read-only; includes "Copy SHA-256" buttons with visual clipboard confirmation ("Copied!").
- **Accessibility:** Hashes rendered in `<pre><code>` with `break-all` to prevent layout overflow, labeled with descriptive `aria-label` tags.

### 4.9 Judge Explanation Viewer (`JudgeExplanationView`)
- **Purpose:** Displays the structured qualitative reasoning generated by `JudgeAgent` explaining the verification outcome in human terms.
- **Data Source:** `GET /api/v1/runs/{run_id}/judge` (`JudgeExplanation`).
- **Consumed Fields:** `summary`, `verified_claims`, `failed_claims`, `evidence_references`, `limitations`, `confidence`.
- **Information Hierarchy:**
  1. Header with prominent disclaimer badge: **"NON-AUTHORITATIVE ADVISORY"** (Slate pill).
  2. Sub-disclaimer: *"The Judge explains the evidence; it does NOT determine the verdict. Deterministic evidence remains authoritative."*
  3. Confidence Indicator: `HIGH` (Emerald), `MEDIUM` (Amber), `LOW` (Crimson).
  4. Executive Summary text block.
  5. Claims Breakdown:
     - Verified Claims (green check list).
     - Failed Claims (red cross list).
  6. Limitations & Scope Constraints callout.
- **Interaction Contract:** Read-only.
- **Accessibility:** Clear typographic hierarchy, semantic unordered lists `<ul>` with text labels instead of color-only indicators.

### 4.10 Security and Sandbox Capability Status (`SandboxStatusPanel`)
- **Purpose:** Reports the operational security posture and boundary isolation of the active execution sandbox.
- **Data Source:** `EvidenceReceipt.sandbox_provenance` and `EvidenceReceipt.structured_observation`.
- **Consumed Fields:** `sandbox_backend`, `security_level`, `network_isolated`, `ephemeral_root`, `execution_id`.
- **Information Hierarchy:**
  1. Environment isolation indicator: e.g. `NETWORK_BLOCKED: TRUE`, `ROOT_FILESYSTEM: READ_ONLY`, `PROCESS_PID_ISOLATED: TRUE`.
  2. Execution Backend: `LocalDevelopmentBackend` (Development) / `NebiusTokenFactory` (Production).
  3. Security policy enforcement version.
- **Interaction Contract:** Read-only security audit surface.
- **Accessibility:** Labeled key-value dl/dt/dd definitions with screen-reader accessible security status.

### 4.11 System State Variants Matrix
Every UI component must explicitly support and render all primary system states:

| System State | Lifecycle `RunState` | Verdict `VerificationStatus` | UI Visual Presentation | Primary User Guidance |
| :--- | :--- | :--- | :--- | :--- |
| **Empty** | `N/A` | `N/A` | Neutral slate container with dotted borders | Prompt to create or select a Task Contract |
| **Pending / Init** | `INIT` | `None` | Neutral card, subtle spinner | Awaiting background worker scheduling |
| **Active Running** | `RECON`..`VERIFY` | `None` | Pulsing blue indicators, live stepper animation | Displaying active agent phase and iteration |
| **Verified Sound** | `VERIFIED` | `VERIFIED` | Emerald card, bold "VERIFIED" headline | Code verified sound against tests & red-team attacks |
| **Rejected Unsound**| `ABORTED` or `JUDGE`| `REJECTED` | Crimson card, bold "REJECTED" headline | Counterexamples discovered; inspect repair failure |
| **Inconclusive** | `VERIFIED` | `INCONCLUSIVE` | Amber card, "INCONCLUSIVE" headline + warning notice | Scope incomplete or budget exhausted without proof |
| **Operational Abort**| `ABORTED` | `None` or Failure | Dark red/slate card, "OPERATIONAL FAILURE" | Execution failed due to system/tool error (inspect error) |

---

## 5. Authority Boundaries & Security Enforcement

The frontend must strictly conform to the security boundaries defined in Section 47 of `docs/REDLINE_v1.1_ARCHITECTURE_FROZEN.md`.

### Non-Authoritative Surface Mandates
1. **No Client-Side Verdicts:** The frontend code must contain zero logic that calculates or infers a verdict. The verdict displayed is verbatim `receipt.verdict`.
2. **No Forced Transitions:** The UI exposes no buttons, inputs, or API payloads that can manually advance or jump the state machine (`advance()`).
3. **No Sandbox Authorizations:** The frontend cannot grant permissions, disable network isolation, or elevate privileges. All sandbox constraints are hardcoded in the backend `SandboxPolicy`.
4. **No Synthetic Evidence:** The frontend cannot construct, sign, or alter `EvidenceReceipt` objects.
5. **Adversarial Input Sanitization:**
   - The UI creation form allows submitting arbitrary strings for descriptions and IDs, but the API rejects any unauthorized payload extensions (e.g. `{ "state": "VERIFIED" }`, `{ "verdict": "VERIFIED" }`, `{ "authorize_sandbox": true }`).
   - The UI must never transmit credentials, API keys (`NEBIUS_API_KEY`), or session tokens in public requests.

---

## 6. Correct Verdict / State Presentation & Technical Debt

### The 3-Dimensional Status Taxonomy
The UI must treat status as a tuple, never collapsing it into a single boolean:
1. **Lifecycle Progression (`RunState`)**: `INIT` → `RECON` → ... → `VERIFY` → `JUDGE` → `VERIFIED` | `ABORTED`.
2. **Deterministic Finding (`VerificationStatus`)**: `VERIFIED` | `REJECTED` | `INCONCLUSIVE` | `POLICY_BLOCKED` | `SANDBOX_FAILURE` | `TIMEOUT`.
3. **Operational Health (`OperationalResult`)**: `SUCCESS` | `TOOL_FAILURE` | `MODEL_FAILURE` | `RESOURCE_LIMIT` | `INVALID_TASK`.

### Documented Technical Debt: Lifecycle State vs. Verdict Inconsistency
- **The Issue:** In the current backend orchestration (`backend/orchestrator/orchestrator.py`), when deterministic verification finishes without counterexamples but returns `INCONCLUSIVE` (e.g., when attacks were inconclusive or assertions partial), the state machine advances:
  ```python
  self.state_machine.advance("VERIFY_SUCCESS") # Moves to JUDGE
  self.state_machine.advance("JUDGE_PASS")     # Moves to RunState.VERIFIED
  ```
  Consequently, a run may exhibit:
  - `run.current_state = RunState.VERIFIED`
  - `run.evidence_receipt.verdict = VerificationStatus.INCONCLUSIVE`
- **UI Policy for the Inconsistency:**
  - The UI **MUST NOT** render a green success badge when `run.current_state === 'VERIFIED'` if `receipt.verdict === 'INCONCLUSIVE'`.
  - The UI **MUST** display an Amber banner:
    ```text
    ⚠️ RUN STATUS: PIPELINE COMPLETED (STATE: VERIFIED)
    AUTHORITATIVE VERDICT: INCONCLUSIVE
    Notice: Pipeline execution finished successfully, but deterministic verification could not guarantee soundness.
    ```
  - **Required Remediation Before Final Demo:** Backend `TransitionPolicy` must be updated to route non-verified verdicts to terminal states that do not share the `RunState.VERIFIED` identifier, or terminal lifecycle states must be renamed to `PIPELINE_COMPLETED` / `PIPELINE_ABORTED`.

---

## 7. Visual Design Direction & Design Tokens

REDLINE uses a precision-oriented developer-tool aesthetic inspired by systems like Linear, Datadog, and Sentry.

### Typography & Fonts
- **Primary Body & Display UI:** Inter / Geist Sans (`font-sans`), clean, readable, high legibility at 12px–16px.
- **Technical & Audit Data:** JetBrains Mono / Geist Mono (`font-mono`), used for all hashes, commit IDs, diffs, code snippets, and JSON manifests.

### Color Tokens & Semantic Usage
- **Neutral Surface Palette:**
  - Background Base: `#F8FAFC` (Slate 50)
  - Card / Panel Surface: `#FFFFFF` (White) with `#E2E8F0` (Slate 200) borders
  - Primary Text: `#0F172A` (Slate 900)
  - Secondary Text: `#64748B` (Slate 500)
  - Monospace Data Text: `#334155` (Slate 700)
- **Status & Verdict Palette (High Restraint):**
  - **Verified (Emerald):** `#059669` (Text), `#ECFDF5` (Surface), `#A7F3D0` (Border). Used *only* for cryptographically certified soundness.
  - **Rejected / Aborted (Crimson):** `#DC2626` (Text), `#FEF2F2` (Surface), `#FECACA` (Border). Used for counterexamples, policy rejections, and execution abortions.
  - **Inconclusive / Pending (Amber):** `#D97706` (Text), `#FFFBEB` (Surface), `#FDE68A` (Border). Used for incomplete proofs and budget exhaustion.
  - **Active Orchestration (Blue):** `#2563EB` (Text), `#EFF6FF` (Surface), `#BFDBFE` (Border). Used for in-flight tasks.
  - **Non-Authoritative Advisory (Slate):** `#475569` (Text), `#F1F5F9` (Surface), `#CBD5E1` (Border). Reserved for Judge explanations to prevent visual confusion with verified verdicts.

### Spacing, Grid & Layout Rhythm
- **Layout:** Responsive 2-column split view on laptop/desktop (`min-width: 1024px`):
  - Left Column (40% width): Intake form, task controls, effective budget, and run history.
  - Right Column (60% width): Live lifecycle monitor, deterministic verdict banner, authoritative evidence receipt, and Judge advisory.
- **Rhythm:** Multiples of 4px/8px (`p-4`, `p-6`, `space-y-6`).
- **Focus States:** High-visibility outline `ring-2 ring-blue-500 ring-offset-2` on all interactive controls for keyboard accessibility.

---

## 8. Data and Interaction Contracts

| Component | Target Endpoint | Backend Model | Fields Consumed | Refresh Behavior | Interactivity |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `RunHistory` | `GET /api/v1/runs` | `List[RunHistoryItemResponse]` | `run_id`, `task_id`, `final_state`, `verdict`, `created_at`, `completed_at` | Initial mount + manual refresh button | Click row to select run |
| `RunCreationForm` | `POST /api/v1/runs` | Request: `TaskContract`<br>Response: `CreateRunResponse` | `task_id`, `repository_id`, `base_commit_or_snapshot`, `task_description`, `resource_budget` | On form submission | Form inputs & submit button |
| `ResourceBudgetNotice` | `GET /api/v1/runs/{id}` | `RunStatusResponse.resource_status` | `iterations_used`, `iterations_limit`, `tool_calls_used`, `tool_calls_limit` | Synchronized with status polling | Read-only |
| `OrchestrationVisualizer`| `GET /api/v1/runs/{id}` | `RunStatusResponse` | `run_id`, `task_id`, `state`, `status`, `iteration`, `started_at`, `updated_at` | Polls every 1.5s while active | Read-only |
| `RunDetailsView` | `GET /api/v1/runs/{id}` | `RunStatusResponse` | `operational_result`, `operational_error`, `status` | Synchronized with status polling | Read-only (copy buttons) |
| `VerdictDisplay` | `GET /api/v1/runs/{id}/receipt` | `EvidenceReceipt.verdict` | `verdict`, `operational_error` | Fetched when state is terminal | Read-only |
| `EvidenceReceiptView` | `GET /api/v1/runs/{id}/receipt` | `EvidenceReceipt` | Complete receipt object (schema, hashes, tests, invariants, counterexamples) | Fetched once on completion | Read-only (collapsible accordions) |
| `PatchLineageView` | `GET /api/v1/runs/{id}/receipt` | `EvidenceReceipt` | `patch_hash`, `patch_lineage`, `evidence_hashes`, `task_contract_hash` | Fetched once on completion | Read-only (copy hash buttons) |
| `JudgeExplanationView`| `GET /api/v1/runs/{id}/judge` | `JudgeExplanation` | `summary`, `verified_claims`, `failed_claims`, `limitations`, `confidence` | Fetched once on completion | Read-only |
| `SandboxStatusPanel` | `GET /api/v1/runs/{id}/receipt` | `EvidenceReceipt.sandbox_provenance` | `sandbox_backend`, `security_level`, `capabilities` | Fetched once on completion | Read-only |

### Missing Contracts & Dependencies
- **Live Event Stream (`GET /api/v1/runs/{id}/events`):** The frozen architecture describes event streaming; current API uses polling on `GET /api/v1/runs/{id}`. WebSocket or SSE endpoints are scheduled for future infrastructure stages.
- **Git Diff Viewer (`GET /api/v1/runs/{id}/diff`):** Implemented in Stage 16.2 as `GET /api/v1/runs/{run_id}/diff` returning `RunDiffResponse`.

### 8.1 Browser API Routing and CORS Architecture (Stage 16.2.1)
- **Direct Cross-Origin Browser Access:** The frontend browser client (`http://localhost:3000` or `http://127.0.0.1:3000`) communicates directly with the authoritative FastAPI backend (`http://127.0.0.1:8000/api/v1`).
- **CORSMiddleware Configuration:** Implemented in `backend/api/app.py` and `backend/api/cors.py`.
  - **Allowed Origins:** Configurable via `REDLINE_CORS_ORIGINS` (defaults strictly to `["http://localhost:3000", "http://127.0.0.1:3000"]`). Wildcard `*` origins are strictly prohibited and fail validation.
  - **Allowed Methods:** Restricted strictly to `["GET", "POST", "OPTIONS"]`.
  - **Allowed Headers:** Restricted to `["Content-Type", "Accept", "Authorization", "X-Requested-With"]`.
  - **Credentials:** `allow_credentials=False` (zero cookie/credential exposure).
- **Static vs Live Page Classification:**
  - **Live Data Workflows:** `/` (Task intake & execution), `/dashboard` (Historical metrics), `/sessions` (Mission control & status), `/evidence` (Receipts & diffs), `/history` (Run log), `/results` (Deterministic verdicts), `/settings` (Gateway endpoint probe).
  - **Static Architecture / Demo References:** `/projects` (Demo target workspaces), `/repositories` (Trust & isolation policy specifications), `/agents` (Architecture specifications), `/models` (Provider configurations).

---

## 9. Testing and Acceptance Criteria

Implementation of this UI/UX specification must satisfy the following measurable acceptance criteria:

### Criteria 1: Verdict and State Separation
- [ ] GIVEN a run with `state: "VERIFIED"` and receipt `verdict: "INCONCLUSIVE"`, WHEN rendered in the UI, THEN the verdict display renders an AMBER banner declaring "INCONCLUSIVE", NOT a green "VERIFIED" banner.
- [ ] GIVEN an active run with `state: "BUILD"`, WHEN rendered in the UI, THEN the verdict display renders "VERDICT PENDING", with no premature evaluation.

### Criteria 2: Receipt Integrity Presentation
- [ ] GIVEN an authoritative `EvidenceReceipt`, WHEN viewed in `EvidenceReceiptView`, THEN the exact `receipt_hash`, `task_contract_hash`, and `patch_hash` are rendered verbatim without formatting mutation.
- [ ] GIVEN a completed run with multiple repair cycles, WHEN inspected in `PatchLineageView`, THEN all entries in `patch_lineage` are rendered in sequential chronological order.

### Criteria 3: Judge Non-Authority Enforcement
- [ ] GIVEN a `JudgeExplanationView`, WHEN rendered on screen, THEN it includes a prominent "NON-AUTHORITATIVE ADVISORY" badge and explicit text explaining that deterministic evidence supersedes the Judge.
- [ ] GIVEN a scenario where Judge text states "The patch is completely verified" but the deterministic receipt verdict is `REJECTED`, WHEN rendered, THEN the overall verdict remains boldly displayed as `REJECTED`.

### Criteria 4: Operational Failure Presentation
- [ ] GIVEN an operational failure (e.g. `OperationalResult.TOOL_FAILURE`), WHEN inspected in `RunDetailsView`, THEN the error panel displays "OPERATIONAL FAILURE", separates it from the code verification verdict, and presents the sanitized error text.

### Criteria 5: Incomplete and Pending State Handling
- [ ] GIVEN a newly created run in `INIT` state, WHEN the receipt endpoint returns HTTP 404, THEN the UI displays a clean pending state ("Waiting for deterministic verification to complete") without throwing uncaught client errors.

### Criteria 6: Accessibility (WCAG 2.2 AA)
- [ ] All interactive elements (inputs, buttons, accordion toggles) have visible focus indicators (`ring-2 ring-blue-500`).
- [ ] Text contrast ratios meet or exceed 4.5:1 for normal text and 3:1 for large display text across all status badges and banners.
- [ ] Screen readers announce state transitions and verdict arrivals via appropriate `aria-live` or `role="alert"` attributes.

### Criteria 7: API Error Handling & Resilience
- [ ] GIVEN an unreachable backend (`NetworkError`), WHEN fetching run status or history, THEN the UI renders an informative error banner with a manual "Retry" action.
- [ ] The polling mechanism gracefully terminates after a configurable timeout (default: 300 seconds) or when terminal states (`VERIFIED`, `ABORTED`) are reached.

---

## 10. Summary & Next Stage Readiness

This specification establishes an evidence-first, secure, and accessible product experience for REDLINE. It locks the boundaries of the frontend surface, enforces strict separation between lifecycle execution and cryptographic verdicts, and provides an actionable blueprint for subsequent frontend polish and demo preparation.

---
