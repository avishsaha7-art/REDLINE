# Stage 11: Evidence Receipt, Deterministic Verdict Binding & Judge Explanation

## Overview
Stage 11 implements the final output and reporting stage of REDLINE. It establishes a tamper-evident, reproducible **Evidence Receipt** and introduces the **Judge** agent, adhering to the foundational security principle: 

> "The LLM may explain evidence. It may never create, strengthen, weaken, or override the evidence-based verdict."

## Implementation Details & Security Constraints

### 1. EvidenceReceipt & Integrity Hashing
The `EvidenceReceipt` model aggregates outputs from REDLINE's pipeline:
- `VerificationScope`: Defines the boundaries of the test (contract, commit, patch hash).
- `VerificationResult`: The raw output from Stage 8B/8C deterministic verifications.
- `verdict`: The final enum state (`VERIFIED`, `REJECTED`, etc.) bound to the policy evaluation.
- `integrity_hash`: A SHA-256 hash using domain separation (`REDLINE_EVIDENCE_RECEIPT_V1`) and canonical JSON representation of all fields except the hash itself.

Using Pydantic (`frozen=True`, `extra="forbid"`), the models prevent attribute modification post-instantiation, preventing tampering. `EvidenceAggregator` strictly requires a `VerificationResult` and prevents manual injection of arbitrary verdicts.

### 2. The Judge Agent
The `JudgeAgent` consumes the `EvidenceReceipt`, `TaskContract`, and `PatchCandidate` to produce a human-readable `JudgeExplanation`. It is constrained strictly to reporting:
- `summary`: A high-level explanation of why the patch passed or failed.
- `verified_claims` & `failed_claims`: Lists mapping evidence findings to human-readable explanations.
- `limitations` & `confidence`.

The Judge's output is purely informational and NEVER feeds back into a decision gate, completely isolating model hallucination or prompt injection from altering the outcome.

### 3. Orchestrator Integration
The `Orchestrator` introduces new state transitions for this stage:
- **VERIFY**: The results of the test pipeline and deterministic observer are aggregated by the `EvidenceAggregator` to produce the `EvidenceReceipt`.
- **JUDGE**: If the receipt is successfully generated, the orchestrator invokes the `JudgeAgent` to generate a `JudgeExplanation`.
- Both `VERIFIED` and `UNREPAIRABLE` terminal states successfully yield a receipt and explanation.

### 4. E2E and Integrity Testing
Comprehensive unit and end-to-end tests guarantee:
- Generating the exact same receipt multiple times yields identical `integrity_hash` values.
- Modifying any attribute of a receipt strictly invalidates its `integrity_hash`.
- The `JudgeAgent` fails and raises validation errors if it attempts to include out-of-schema attributes (e.g., trying to invent an `override_verdict` field).
