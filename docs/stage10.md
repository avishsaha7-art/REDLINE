# Stage 10: Autonomous Repairer & Closed-Loop

## Overview
Stage 10 implements the **Repairer** agent and establishes the autonomous closed loop of REDLINE:
`BUILD → ATTACK → REPAIR → VERIFY`.

This stage integrates the Repairer into the orchestrator while adhering to the core security principle: "The Repairer proposes changes but never establishes correctness." All repair proposals flow back through the existing deterministic verification pipeline.

## Implementation Details & Security Constraints

### 1. Repairer Integration
The Repairer is an autonomous agent implemented in `backend/agents/repairer.py`. It uses the `ModelProvider` pattern (same as the Architect and Builder) and strictly returns a `RepairCandidate` JSON. 

### 2. Orchestrator Loop (BUILD -> ATTACK -> REPAIR -> VERIFY)
The Orchestrator's state machine now connects the `VERIFY` step to the `REPAIR` step when a counterexample is found. It routes `ANALYZE -> NEEDS_REPAIR` (if budget allows) or `ANALYZE -> ABORTED/UNREPAIRABLE` (if exhausted).

### 3. Repair Limits and Budgeting
The orchestrator maintains `repair_attempts` based on the `resource_budget.max_failed_attempts`. If the repairer reaches the budget, the state machine advances to `UNREPAIRABLE`. Infinite loops are avoided by keeping a hash-set of `seen_repairs`; if the exact same repair is generated again, it fails with `OperationalResult.TOOL_FAILURE`.

### 4. Deterministic Verification and PatchValidation Security
The repair output is passed as a `PatchCandidate` into the `TEST` -> `VERIFY` pipeline. This inherently guarantees that the repair is validated with `validate_patch` (Stage 4/7 architecture), which performs strict path traversal, scope, and protected-file checks.

### 5. Counterexample Consumption
When a patch fails the `VERIFY` step (i.e. `ExecutionStatus.FAILED` or `InvariantResultStatus.FAIL`), a `Counterexample` is populated. In the `REPAIR` step, the Repairer uses this counterexample to generate a fix, maintaining precise feedback loops.

### 6. Untrusted Context Handling
If the sandbox execution fails due to backend limitations (e.g. `POLICY_BLOCKED`), the result is `INCONCLUSIVE` (handled correctly as it does not generate a counterexample that can be repaired).

### 7. Isolation (Zero-Trust Output)
The Repairer outputs a constrained Pydantic model (`RepairCandidate` with `extra="forbid"`). It cannot mutate `verdict`, `sandbox_backend`, `trust_level`, `authorized`, or any security flags. The orchestrator explicitly translates the proposed changes into a fresh `PatchCandidate`, preserving separation of duties.

## Adversarial Testing

Adversarial testing was introduced in `tests/test_stage10.py` to ensure that standard path validation applies equally to the Repairer output. The test cases specifically prove rejection of:
- **Path Traversal / Absolute Paths:** The patch validation securely blocks attempts to write to `/etc/passwd` or `../outside.txt`.
- **Protected File Access:** Attempts to modify `.env` or other out-of-scope files are rejected by the deterministic boundary.
- **Duplicate Fix Loop Prevention:** The hash-based state checking aborts execution if the Repairer falls into a repetitive cycle.
- **State Machine Isolation:** Tests confirm the output models do not include any capability to bypass the deterministic policy gate.

## Regression Guarantee
The full `pytest` suite was run (161 tests passed), confirming zero regressions in Stages 8, 9, 9.1, and 9.2. The security invariants established in the prior stages remain entirely intact.
