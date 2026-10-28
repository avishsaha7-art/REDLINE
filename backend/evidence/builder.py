import datetime
from typing import Dict, Any, List
import json
import hashlib

from backend.models.schemas import TaskContract, PatchCandidate
from backend.models.attack import AttackCandidate
from backend.verification.models import VerificationResult, VerificationStatus
from backend.models.evidence import EvidenceReceipt, VerificationScope

class EvidenceAggregator:
    def __init__(self, task_contract: TaskContract, patch_lineage: List[str] = None):
        self.task_contract = task_contract
        self.patch_lineage = patch_lineage or []

    def determine_scope(self, verification_result: VerificationResult) -> VerificationScope:
        # Check what parts of verification were actually executed and successful
        execution = "NOT EXECUTED"
        if verification_result.structured_observation:
            execution = "VERIFIED" if verification_result.structured_observation.status == "SUCCESS" else "FAILED"
        elif verification_result.status == VerificationStatus.VERIFIED:
            execution = "VERIFIED"
        elif verification_result.status == VerificationStatus.POLICY_BLOCKED:
            execution = "POLICY_BLOCKED"
        elif verification_result.status == VerificationStatus.SANDBOX_FAILURE:
            execution = "SANDBOX_FAILURE"
        elif verification_result.status == VerificationStatus.RESOURCE_LIMIT:
            execution = "RESOURCE_LIMIT"
        elif verification_result.status == VerificationStatus.TIMEOUT:
            execution = "TIMEOUT"

        tests = "NOT EXECUTED"
        if verification_result.test_summary:
            if verification_result.test_summary.executed > 0:
                if verification_result.test_summary.failed > 0 or verification_result.test_summary.errored > 0:
                    tests = "FAILED"
                elif verification_result.test_summary.inconclusive > 0:
                    tests = "INCONCLUSIVE"
                elif verification_result.test_summary.passed > 0:
                    tests = "VERIFIED"
                else:
                    tests = "INCONCLUSIVE"

        invariants = "NOT EXECUTED"
        if verification_result.invariant_summary:
            if any(getattr(i, "result", None) == "FAIL" for i in verification_result.invariant_summary):
                invariants = "FAILED"
            elif any(getattr(i, "result", None) in ("INCONCLUSIVE", "NOT_EVALUATED") for i in verification_result.invariant_summary):
                invariants = "INCONCLUSIVE"
            elif all(getattr(i, "result", None) == "PASS" for i in verification_result.invariant_summary) and len(verification_result.invariant_summary) > 0:
                invariants = "VERIFIED"
            else:
                invariants = "EVALUATED"

        security = "NOT EXECUTED"
        if verification_result.security_summary:
            if any(getattr(s, "status", None) == "FAIL" for s in verification_result.security_summary):
                security = "FAILED"
            elif any(getattr(s, "status", None) == "INCONCLUSIVE" for s in verification_result.security_summary):
                security = "INCONCLUSIVE"
            elif all(getattr(s, "status", None) == "PASS" for s in verification_result.security_summary) and len(verification_result.security_summary) > 0:
                security = "VERIFIED"
            else:
                security = "EVALUATED"

        return VerificationScope(
            execution=execution,
            tests=tests,
            invariants=invariants,
            security=security
        )

    def build_receipt(
        self,
        run_id: str,
        patch: PatchCandidate,
        verification_result: VerificationResult,
        attacks: List[AttackCandidate],
        model_provenance: Dict[str, str],
        sandbox_provenance: Dict[str, str],
        snapshot_hash: Optional[str] = None
    ) -> EvidenceReceipt:
        scope = self.determine_scope(verification_result)

        attack_fingerprints = [a.attack_id for a in attacks]
        resolved_snapshot_hash = snapshot_hash or getattr(self, "snapshot_hash", None) or self.task_contract.base_commit_or_snapshot

        # Scoped counterexamples: only retain counterexamples belonging to this active patch candidate
        active_counterexamples = [
            ce for ce in (verification_result.counterexamples or [])
            if ce.patch_id is None or ce.patch_id == patch.patch_id
        ]

        digest = getattr(patch, "diff_sha256", None) or hashlib.sha256(getattr(patch, "diff", "").encode("utf-8")).hexdigest()

        receipt_dict = dict(
            run_id=run_id,
            task_id=self.task_contract.task_id,
            repository_snapshot_hash=resolved_snapshot_hash,
            task_contract_hash=hashlib.sha256(json.dumps(self.task_contract.model_dump(mode="json"), sort_keys=True, separators=(',', ':')).encode("utf-8")).hexdigest(),
            patch_hash=getattr(patch, "patch_id", None) or getattr(patch, "diff_sha256", None) or "none",
            patch_id=patch.patch_id,
            patch_digest=digest,
            patch_lineage=self.patch_lineage,
            execution_ids=verification_result.execution_ids,
            attack_fingerprints=attack_fingerprints,
            verdict=verification_result.status,
            verification_scope=scope,
            structured_observation=verification_result.structured_observation,
            test_summary=verification_result.test_summary,
            invariant_summary=verification_result.invariant_summary,
            security_summary=verification_result.security_summary,
            counterexamples=active_counterexamples,
            oracle_results=verification_result.oracle_results,
            policy_version=verification_result.policy_version,
            verifier_version=verification_result.verifier_version,
            sandbox_provenance=sandbox_provenance,
            model_provenance=model_provenance,
            evidence_hashes=verification_result.evidence_hashes,
            timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat()
        )

        # We create the receipt without the hash, then compute it
        receipt = EvidenceReceipt(**receipt_dict)
        integrity_hash = receipt.calculate_integrity_hash()

        # Since it's frozen, we must recreate or use model_copy
        receipt = receipt.model_copy(update={"receipt_hash": integrity_hash})
        return receipt
