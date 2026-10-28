from typing import List, Optional
import hashlib
import uuid
from backend.verification.models import (
    VerificationResult,
    VerificationStatus,
    StructuredObservation,
    TestResultSummary,
    RegressionSummary,
    InvariantEvaluation,
    ExecutionStatus,
    Counterexample,
    OracleResult,
)
from backend.verification.security_models import SecurityResultAggregation, SecurityResultClassification

class DeterministicVerificationPolicy:
    def __init__(self, policy_version: str = "v1.0"):
        self.policy_version = policy_version

    def evaluate(
        self,
        repository_snapshot_hash: str,
        patch_hash: str,
        structured_observation: Optional[StructuredObservation],
        test_summary: TestResultSummary,
        regression_summary: RegressionSummary,
        invariants: List[InvariantEvaluation],
        security_aggregation: Optional[SecurityResultAggregation],
        oracle_results: List[OracleResult],
        counterexamples: List[Counterexample],
        required_checks: Optional[List[str]] = None,
        task_contract: Optional[Any] = None
    ) -> VerificationResult:
        """
        Deterministic Verification Policy:
        - VERIFIED is permitted ONLY when all required verification conditions are satisfied by valid evidence.
        - Required checks: by default 'execution' and 'tests'; plus 'security' and/or 'invariants' if specified
          in required_checks, task contract constraints/criteria, or untrusted repository policy.
        - Any failed check (required or optional) prevents VERIFIED and produces REJECTED.
        - Any counterexample for the candidate patch prevents VERIFIED and produces REJECTED.
        - A required check that was not executed prevents VERIFIED and produces INCONCLUSIVE.
        - Optional checks may remain unexecuted when the policy/contract permits.
        - Unknown sandbox provenance prevents VERIFIED and produces SANDBOX_FAILURE.
        """
        status = VerificationStatus.INCONCLUSIVE

        # 1. Operational failures override everything
        if structured_observation:
            if structured_observation.status == ExecutionStatus.POLICY_BLOCKED:
                status = VerificationStatus.POLICY_BLOCKED
            elif structured_observation.status == ExecutionStatus.SANDBOX_FAILURE:
                status = VerificationStatus.SANDBOX_FAILURE
            elif structured_observation.status == ExecutionStatus.RESOURCE_LIMIT:
                status = VerificationStatus.RESOURCE_LIMIT
            elif structured_observation.status == ExecutionStatus.TIMEOUT:
                status = VerificationStatus.TIMEOUT
            elif structured_observation.status == ExecutionStatus.EXECUTION_FAILURE:
                status = VerificationStatus.EXECUTION_FAILURE
            elif structured_observation.status == ExecutionStatus.NONZERO:
                status = VerificationStatus.REJECTED

        # 2. Active counterexamples for this patch prevent verification immediately
        active_ces = [
            ce for ce in (counterexamples or [])
            if (ce.patch_id and ce.patch_id == patch_hash) or (ce.invariant_id == "PATCH_APPLICATION")
        ]
        if active_ces and status == VerificationStatus.INCONCLUSIVE:
            status = VerificationStatus.REJECTED

        if status == VerificationStatus.INCONCLUSIVE:
            # 3. Logic failures across all executed checks (required or optional)
            is_sec_agg = isinstance(security_aggregation, SecurityResultAggregation)
            if regression_summary.regression_detected:
                status = VerificationStatus.REJECTED
            elif test_summary.failed > 0 or test_summary.errored > 0:
                status = VerificationStatus.REJECTED
            elif any(inv.result == "FAIL" for inv in invariants):
                status = VerificationStatus.REJECTED
            elif is_sec_agg and security_aggregation.overall_status == SecurityResultClassification.FAIL:
                status = VerificationStatus.REJECTED
            elif any(o.result == "FAIL" for o in oracle_results):
                status = VerificationStatus.REJECTED

            # 4. Unknown sandbox provenance fails closed when tests ran/passed
            elif structured_observation and structured_observation.sandbox_backend == "UNKNOWN" and test_summary.executed > 0 and test_summary.passed > 0:
                status = VerificationStatus.SANDBOX_FAILURE

            # 5. Inconclusive observations on executed checks
            elif test_summary.inconclusive > 0:
                status = VerificationStatus.INCONCLUSIVE
            elif any(inv.result == "INCONCLUSIVE" for inv in invariants):
                status = VerificationStatus.INCONCLUSIVE
            elif is_sec_agg and security_aggregation.overall_status in (
                SecurityResultClassification.INCONCLUSIVE,
                SecurityResultClassification.NOT_EVALUATED,
                SecurityResultClassification.BLOCKED
            ):
                status = VerificationStatus.INCONCLUSIVE
            elif any(o.result == "INCONCLUSIVE" for o in oracle_results):
                status = VerificationStatus.INCONCLUSIVE
            else:
                # 6. Evaluate required verification scope
                effective_required = set()
                if required_checks is not None:
                    effective_required = set(c.lower() for c in required_checks)
                else:
                    effective_required.add("execution")
                    effective_required.add("tests")
                    if task_contract:
                        is_untrusted = getattr(task_contract, "repository_trust", None) == "UNTRUSTED"
                        desc = (getattr(task_contract, "task_description", "") or "").lower()
                        constraints = " ".join(getattr(task_contract, "constraints", []) or []).lower()
                        criteria = " ".join(getattr(task_contract, "acceptance_criteria", []) or []).lower()
                        combined = f"{desc} {constraints} {criteria}"
                        if is_untrusted or any(term in combined for term in ("security", "vuln", "cve", "sanitize", "safe", "injection")):
                            effective_required.add("security")
                        if any(term in combined for term in ("invariant", "contract", "precondition")):
                            effective_required.add("invariants")

                # Check execution requirement
                exec_ok = (
                    structured_observation is not None
                    and structured_observation.status == ExecutionStatus.SUCCESS
                    and structured_observation.sandbox_backend != "UNKNOWN"
                    and structured_observation.exit_code == 0
                )
                if "execution" in effective_required and not exec_ok:
                    status = VerificationStatus.INCONCLUSIVE

                # Check tests requirement
                tests_ok = (
                    test_summary.executed > 0
                    and test_summary.passed > 0
                    and test_summary.failed == 0
                    and test_summary.errored == 0
                    and test_summary.inconclusive == 0
                )
                if "tests" in effective_required and not tests_ok:
                    status = VerificationStatus.INCONCLUSIVE

                # Check invariants requirement
                inv_ok = (
                    len(invariants) > 0
                    and all(inv.result == "PASS" for inv in invariants)
                )
                if "invariants" in effective_required and not inv_ok:
                    status = VerificationStatus.INCONCLUSIVE

                # Check security requirement
                sec_ok = (
                    is_sec_agg
                    and security_aggregation.overall_status == SecurityResultClassification.PASS
                )
                if "security" in effective_required and not sec_ok:
                    status = VerificationStatus.INCONCLUSIVE

                # If all required checks are satisfied and there is positive evidence
                if status == VerificationStatus.INCONCLUSIVE:
                    has_positive_evidence = (
                        (exec_ok and "execution" in effective_required) or
                        (tests_ok and "tests" in effective_required) or
                        (inv_ok and "invariants" in effective_required) or
                        (sec_ok and "security" in effective_required)
                    )
                    all_req_satisfied = True
                    for req in effective_required:
                        if req == "execution" and not exec_ok:
                            all_req_satisfied = False
                        elif req == "tests" and not tests_ok:
                            all_req_satisfied = False
                        elif req == "invariants" and not inv_ok:
                            all_req_satisfied = False
                        elif req == "security" and not sec_ok:
                            all_req_satisfied = False

                    if all_req_satisfied and has_positive_evidence:
                        if structured_observation and structured_observation.sandbox_backend == "UNKNOWN":
                            status = VerificationStatus.SANDBOX_FAILURE
                        else:
                            status = VerificationStatus.VERIFIED
                    else:
                        status = VerificationStatus.INCONCLUSIVE

        execution_ids = []
        if structured_observation:
            execution_ids.append(structured_observation.execution_id)
        evidence_hashes = []
        for inv in invariants:
            if inv.evidence_hash:
                evidence_hashes.append(inv.evidence_hash)
        for ce in counterexamples:
            evidence_hashes.append(ce.evidence_hash)

        if security_aggregation:
            for obs in security_aggregation.observations:
                evidence_hashes.append(obs.evidence_hash)
                if obs.execution_id not in execution_ids:
                    execution_ids.append(obs.execution_id)

        scopes = []
        if structured_observation and structured_observation.status == ExecutionStatus.SUCCESS:
            scopes.append("EXECUTION")
        if test_summary.executed > 0 and test_summary.passed > 0 and test_summary.failed == 0 and test_summary.errored == 0:
            scopes.append("TESTS")
        if invariants and all(inv.result == "PASS" for inv in invariants):
            scopes.append("INVARIANTS")
        if security_aggregation and security_aggregation.overall_status == SecurityResultClassification.PASS:
            scopes.append("SECURITY")

        # Build structured security summary list
        from backend.verification.models import SecurityObservation, InvariantResultStatus
        legacy_security_summary = []
        if security_aggregation and security_aggregation.observations:
            for obs in security_aggregation.observations:
                st = InvariantResultStatus.PASS if getattr(obs, "status", None) in ("PASS", InvariantResultStatus.PASS) else (
                    InvariantResultStatus.FAIL if getattr(obs, "status", None) in ("FAIL", InvariantResultStatus.FAIL) else InvariantResultStatus.INCONCLUSIVE
                )
                legacy_security_summary.append(
                    SecurityObservation(
                        hook_id=getattr(obs, "attack_id", getattr(obs, "hook_id", "security_hook")),
                        status=st,
                        evidence=getattr(obs, "evidence", "")
                    )
                )
        elif oracle_results:
            for idx, o in enumerate(oracle_results):
                legacy_security_summary.append(
                    SecurityObservation(
                        hook_id=f"oracle_{idx+1}",
                        status=o.result if isinstance(o.result, InvariantResultStatus) else InvariantResultStatus(o.result),
                        evidence=o.evidence
                    )
                )

        res = VerificationResult(
            verification_id=str(uuid.uuid4()),
            status=status,
            structured_observation=structured_observation,
            test_summary=test_summary,
            invariant_summary=invariants,
            regression_summary=regression_summary,
            security_summary=legacy_security_summary,
            counterexamples=counterexamples,
            oracle_results=oracle_results,
            execution_ids=execution_ids,
            evidence_hashes=evidence_hashes,
            policy_version=self.policy_version,
            verifier_version="REDLINE_v1.1",
            repository_snapshot_hash=repository_snapshot_hash,
            patch_hash=patch_hash,
            verified_scope=", ".join(scopes) if scopes else "NONE"
        )
        return res
