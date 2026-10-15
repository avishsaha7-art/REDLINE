# REDLINE — STAGE P2-1 IMPLEMENTATION PLAN: FULL-REPOSITORY LINT CLEANUP

**Date:** 2026-10-15  
**Stage:** Stage P2-1 Full-Repository Lint Cleanup  
**Baseline Commit:** `d791120fb69efb71309b2073118d42d0dc499592`  
**Working Tree State:** Branch `master`, baseline checkpoint preserved, untracked `docs/stage_p2_0_git_baseline_report.md` preserved.

---

### 1. Objective & Context

Following the creation and verification of the initial Git baseline checkpoint (Stage P2-0), full-repository lint analysis (`npm run lint` executing `eslint` across `frontend/`) revealed **17 problems (12 errors, 5 warnings)**.

The objective of Stage P2-1 is to resolve all underlying code issues cleanly without disabling ESLint rules, adding blanket suppressions, using `any` casts, or modifying package dependencies, while preserving all existing behaviors, API contracts, deterministic verification invariants, and tests.

---

### 2. Baseline Diagnostic Inventory

The full-repository lint baseline produced the following 17 reproducible diagnostics:

| # | File Path | Line:Col | Severity | ESLint Rule | Description |
|---|-----------|:--------:|:--------:|-------------|-------------|
| 1 | `frontend/src/app/evidence/page.tsx` | 58:5 | Error | `react-hooks/set-state-in-effect` | Synchronous `setIsLoading(true)` in `useEffect` |
| 2 | `frontend/src/app/evidence/page.tsx` | 166:21 | Error | `react/jsx-no-comment-textnodes` | Unescaped `//` in breadcrumb `<span>` |
| 3 | `frontend/src/app/evidence/page.tsx` | 168:21 | Error | `react/jsx-no-comment-textnodes` | Unescaped `//` in breadcrumb `<span>` |
| 4 | `frontend/src/app/history/page.tsx` | 89:21 | Error | `react/jsx-no-comment-textnodes` | Unescaped `//` in breadcrumb `<span>` |
| 5 | `frontend/src/app/history/page.tsx` | 91:21 | Error | `react/jsx-no-comment-textnodes` | Unescaped `//` in breadcrumb `<span>` |
| 6 | `frontend/src/app/playground/page.tsx` | 210:21 | Error | `react/jsx-no-comment-textnodes` | Unescaped `//` in breadcrumb `<span>` |
| 7 | `frontend/src/app/playground/page.tsx` | 212:21 | Error | `react/jsx-no-comment-textnodes` | Unescaped `//` in breadcrumb `<span>` |
| 8 | `frontend/src/app/projects/page.tsx` | 95:5 | Error | `react-hooks/set-state-in-effect` | Synchronous `fetchRuns()` calling `setState` inside `useEffect` |
| 9 | `frontend/src/app/results/page.tsx` | 45:5 | Error | `react-hooks/set-state-in-effect` | Synchronous `setIsLoading(true)` in `useEffect` |
| 10 | `frontend/src/app/results/page.tsx` | 91:21 | Error | `react/jsx-no-comment-textnodes` | Unescaped `//` in breadcrumb `<span>` |
| 11 | `frontend/src/app/results/page.tsx` | 93:21 | Error | `react/jsx-no-comment-textnodes` | Unescaped `//` in breadcrumb `<span>` |
| 12 | `frontend/src/app/sessions/page.tsx` | 7:37 | Warning | `@typescript-eslint/no-unused-vars` | Unused import `RunState` |
| 13 | `frontend/src/app/sessions/page.tsx` | 60:7 | Error | `react-hooks/set-state-in-effect` | Synchronous `setStatus(null)` in `useEffect` |
| 14 | `frontend/src/lib/anime.ts` | 6:67 | Warning | `@typescript-eslint/no-unused-vars` | Unused type import `Timeline` |
| 15 | `frontend/src/tests/anime_motion.test.ts` | 9:3 | Warning | `@typescript-eslint/no-unused-vars` | Unused import `animateTableRows` |
| 16 | `frontend/src/tests/dashboard_ui_a2.test.ts` | 5:26 | Warning | `@typescript-eslint/no-unused-vars` | Unused import `TaskContract` |
| 17 | `frontend/src/tests/sessions_playground_ui_a4.test.ts` | 8:56 | Warning | `@typescript-eslint/no-unused-vars` | Unused import `isRequestCurrent` |

---

### 3. Concrete Fix Strategy

#### 3.1 `react-hooks/set-state-in-effect` Fixes
The React 19 compiler and ESLint rule flag synchronous `setState` invocations inside the root body of `useEffect` because they cause cascading re-renders before any asynchronous operation begins.

1. **`frontend/src/app/projects/page.tsx`:**
   - `isLoading` is already initialized to `true`.
   - Remove the synchronous wrapper `fetchRuns()` call in `useEffect`. Instead, call `apiClient.getRunHistory()` directly with an `ignore` cancellation flag. Update state only when the promise resolves or rejects asynchronously.
2. **`frontend/src/app/results/page.tsx`:**
   - Loading state is already managed at initial render via `useState<boolean>(Boolean(initialRunId))` and during run selection in `handleSelectRun`.
   - Remove the redundant synchronous `setIsLoading(true)` on line 45. The asynchronous promise handles updating data and resetting `setIsLoading(false)` upon completion.
3. **`frontend/src/app/sessions/page.tsx`:**
   - Remove unused import `RunState` from line 7.
   - On line 60, remove synchronous `setStatus(null)` in the effect body. If `selectedRunId` is empty, return early.
   - Update `handleSelectRun` to manage clearing status and setting loading when the run selection changes via user interaction.
   - Let the async `getRunStatus` promise update `status`, `error`, and `isLoading` exclusively within `.then()` and `.catch()`.
4. **`frontend/src/app/evidence/page.tsx`:**
   - Loading state is already managed at initial render and in `handleSelectRun`.
   - Remove redundant synchronous `setIsLoading(true)` on line 58. State updates are confined to the settled promise handlers.

#### 3.2 `react/jsx-no-comment-textnodes` Fixes
Breadcrumbs rendered as `<span>//</span>` are flagged because JSX parses raw `//` as potentially ambiguous comment text nodes.
- Replace bare `<span>//</span>` with `<span>{'//'}</span>` in:
  - `frontend/src/app/history/page.tsx` (lines 89, 91)
  - `frontend/src/app/playground/page.tsx` (lines 210, 212)
  - `frontend/src/app/results/page.tsx` (lines 91, 93)
  - `frontend/src/app/evidence/page.tsx` (lines 166, 168)
- Displays identical visual breadcrumb separator `//` without altering text or layout.

#### 3.3 `@typescript-eslint/no-unused-vars` Fixes
- `frontend/src/lib/anime.ts`: Remove unused `type Timeline` from the `animejs` import.
- `frontend/src/tests/anime_motion.test.ts`: Remove unused `animateTableRows` import.
- `frontend/src/tests/dashboard_ui_a2.test.ts`: Remove unused `TaskContract` import.
- `frontend/src/tests/sessions_playground_ui_a4.test.ts`: Remove unused `isRequestCurrent` import.

---

### 4. Implementation Steps & Verification Gates

1. **Step 1:** Apply fixes to `src/app/projects/page.tsx`.
2. **Step 2:** Apply fixes to `src/app/results/page.tsx` and `src/app/evidence/page.tsx`.
3. **Step 3:** Apply fixes to `src/app/sessions/page.tsx`.
4. **Step 4:** Apply fixes to `src/app/history/page.tsx` and `src/app/playground/page.tsx`.
5. **Step 5:** Apply unused import cleanups in `src/lib/anime.ts` and test files.
6. **Step 6: Comprehensive Verification:**
   - `npm test` in `frontend/` (all 111 tests must pass).
   - `npx tsc --noEmit` in `frontend/` (0 errors).
   - `npm run lint` in `frontend/` (0 errors, 0 warnings).
   - `npm run build` in `frontend/` (production Turbopack build succeeds).
   - `pytest tests/` in workspace root (256 passed, 1 skipped).
7. **Step 7:** Author `docs/stage_p2_1_completion_report.md` and present for user review.
