# REDLINE Stage 9.2: Real Attack Execution Integration

## 1. Objective
Implement the execution bridge for autonomous software-engineering verification system, connecting selected Red Team attacks to the existing deterministic verification and sandbox layers without bypassing security boundaries.

## 2. Architecture
The architecture maps `AttackCandidate` into a trusted `AttackExecutionRequest`. This request is subjected to policy and capability checking. It flows through the `SandboxBackend`, into the `DeterministicVerificationObserver`, and finally is evaluated by an `Oracle` which determines if a `Counterexample` was produced. 

## 3. AttackExecutionRequest
This model is immutable (`frozen=True`) and structured strictly to prevent arbitrary control flow modifications. It hashes its inputs (snapshot hash, patch hash, attack fingerprint, and input) to derive a deterministic `execution_id`.

## 4. Validation
Before execution, `validate_attack_for_execution` ensures that the attack's execution strategy is within a recognized bounded list of strategies and complies with expected shapes, mapping untrusted model parameters into trusted policy structures.

## 5. Authorization
The model cannot authorize its own execution. The orchestrator acts as the policy gate. The execution request strips out any arbitrary model-provided `authorized` flags or backend selections.

## 6. Sandbox Capability Enforcement
Before executing an attack on an untrusted repository, the engine verifies the capabilities of the current backend. If `secure_untrusted_execution` is False, execution is blocked.

## 7. Execution Strategies
Strategies are strictly mapped (e.g., `TEST_CASE`, `FUNCTION_INPUT`, `INVARIANT_CHECK`). The engine does not provide a generic shell executor.

## 8. Resource Governance
Resource limits (time, memory, output bytes) strictly adhere to policy limits encoded in `AttackResourceBudget`. The engine provides these as constraints to the `SandboxBackend`.

## 9. Observer Integration
Execution results pass into the `DeterministicVerificationObserver`, which converts OS-level process data (exit code, output size, timeouts) into a semantic `StructuredObservation`.

## 10. Oracle Integration
The oracle interprets the `StructuredObservation` using deterministic policies (e.g. exit code heuristics) to produce an `OracleResult`. The LLM's expectation is not authoritative for declaring "SUCCESS" or "FAIL".

## 11. Counterexamples
If the oracle evaluation results in an invariant failure (`FAIL`), a `Counterexample` is generated bridging the `execution_id`, observed output, and input data, bound deterministically.

## 12. Evidence/Provenance
Every execution generates observation evidence, oracle evidence, and counterexample evidence hashes. These preserve a chain of custody tracing back to the snapshot and patch hashes.

## 13. Failure Handling
Errors, resource exhaustion, and sandbox denials produce explicit operational outcomes (`POLICY_BLOCKED`, `TIMEOUT`, `RESOURCE_LIMIT`, `EXECUTION_FAILURE`) rather than silent passes or false positives.

## 14. Security Guarantees
- No arbitrary shell access.
- Local execution of untrusted repository code is explicitly prohibited.
- The Red Team model cannot independently declare an attack successful.
- The Red Team model cannot manipulate the state machine to bypass the orchestrator.

## 15. Current Sandbox Limitation
> REDLINE currently fails closed for untrusted repository execution when a secure sandbox backend is unavailable.

## 16. Test Results
- 157 Tests collected.
- 156 Passed, 1 Skipped.
- Stage 9.2 specific tests prove identity consistency, validation rules, adversarial blocking, and `POLICY_BLOCKED` behavior.

## 17. Known Limitations
- The system defaults to failing closed on the Windows host since full process/network/filesystem isolation for untrusted repositories is unavailable in the LocalDevelopmentBackend.
- Mapped oracle types treat some attack types as generic model expectations until concrete strategy hooks are expanded.

## 18. Future Secure Sandbox Integration
Subsequent stages (e.g., Stage 10+) will introduce remote secure sandboxes capable of safely orchestrating arbitrary repository code execution. The current execution bridge is designed to integrate cleanly with this future capability simply by changing the `SandboxBackend` provisioned by the Orchestrator.
