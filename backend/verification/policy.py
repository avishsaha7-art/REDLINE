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
        counterexamples: List[Counterexample]
    ) -> VerificationResult:
        
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
                
        if status == VerificationStatus.INCONCLUSIVE:
            # 2. Logic failures
            if regression_summary.regression_detected:
                status = VerificationStatus.REJECTED
            elif test_summary.failed > 0 or test_summary.errored > 0:
                status = VerificationStatus.REJECTED
            elif any(inv.result == "FAIL" for inv in invariants):
                status = VerificationStatus.REJECTED
            elif security_aggregation and security_aggregation.overall_status == SecurityResultClassification.FAIL:
                status = VerificationStatus.REJECTED
            elif any(o.result == "FAIL" for o in oracle_results):
                status = VerificationStatus.REJECTED
                
                
            # 3. Missing/Inconclusive evidence
            elif test_summary.inconclusive > 0:
                status = VerificationStatus.INCONCLUSIVE
            elif any(inv.result == "INCONCLUSIVE" for inv in invariants):
                status = VerificationStatus.INCONCLUSIVE
            elif security_aggregation and security_aggregation.overall_status == SecurityResultClassification.INCONCLUSIVE:
                status = VerificationStatus.INCONCLUSIVE
            elif security_aggregation and security_aggregation.overall_status == SecurityResultClassification.NOT_EVALUATED:
                status = VerificationStatus.INCONCLUSIVE
            elif security_aggregation and security_aggregation.overall_status == SecurityResultClassification.BLOCKED:
                # If execution itself was not blocked, but security was blocked, it's INCONCLUSIVE 
                # (or POLICY_BLOCKED depending on interpretation, but the prompt says INCONCLUSIVE or POLICY_BLOCKED)
                status = VerificationStatus.INCONCLUSIVE
            elif any(o.result == "INCONCLUSIVE" for o in oracle_results):
                status = VerificationStatus.INCONCLUSIVE
            else:
                # Need at least SOME positive oracle passing to say VERIFIED
                # If there are NO tests run, that's INCONCLUSIVE
                has_passing_test = test_summary.passed > 0
                has_passing_invariant = any(inv.result == "PASS" for inv in invariants)
                has_passing_oracle = any(o.result == "PASS" for o in oracle_results)
                
                if test_summary.executed == 0 and len(invariants) == 0 and len(oracle_results) == 0:
                    status = VerificationStatus.INCONCLUSIVE
                elif not (has_passing_test or has_passing_invariant or has_passing_oracle):
                    status = VerificationStatus.INCONCLUSIVE
                else:
                    status = VerificationStatus.VERIFIED
                
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
            
        scopes = ["EXECUTION", "TESTS", "INVARIANTS"]
        if security_aggregation and security_aggregation.overall_status == SecurityResultClassification.PASS:
            scopes.append("SECURITY")
            
        # Also include the old security_summary list to satisfy existing models
        # but we use the new security_aggregation to set it.
        legacy_security_summary = []
            
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
            verified_scope=", ".join(scopes)
        )
        return res

