from pydantic import BaseModel, Field, ConfigDict
from typing import List, Dict, Optional, Any
from enum import Enum
import hashlib
import json

from backend.verification.models import (
    VerificationStatus,
    TestResultSummary,
    InvariantEvaluation,
    SecurityObservation,
    Counterexample,
    OracleResult,
    StructuredObservation
)

class VerificationScope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    execution: str = "NOT EXECUTED"
    tests: str = "NOT EXECUTED"
    invariants: str = "NOT EXECUTED"
    security: str = "NOT EXECUTED"

class EvidenceReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    receipt_schema_version: str = "1.0"
    run_id: str
    task_id: str
    repository_snapshot_hash: str
    task_contract_hash: str

    patch_hash: str
    patch_id: Optional[str] = None
    patch_digest: Optional[str] = None
    patch_lineage: List[str] = Field(default_factory=list)

    execution_ids: List[str] = Field(default_factory=list)
    attack_fingerprints: List[str] = Field(default_factory=list)

    verdict: VerificationStatus
    verification_scope: VerificationScope

    structured_observation: Optional[StructuredObservation] = None
    test_summary: Optional[TestResultSummary] = None
    invariant_summary: List[InvariantEvaluation] = Field(default_factory=list)
    security_summary: List[SecurityObservation] = Field(default_factory=list)
    counterexamples: List[Counterexample] = Field(default_factory=list)
    oracle_results: List[OracleResult] = Field(default_factory=list)

    policy_version: str
    verifier_version: str

    sandbox_provenance: Dict[str, str] = Field(default_factory=dict)
    model_provenance: Dict[str, str] = Field(default_factory=dict)

    evidence_hashes: List[str] = Field(default_factory=list)

    timestamp: str
    receipt_hash: Optional[str] = None

    def calculate_integrity_hash(self) -> str:
        exclude_fields = {"receipt_hash", "timestamp"}
        if self.patch_id is None:
            exclude_fields.add("patch_id")
        if self.patch_digest is None:
            exclude_fields.add("patch_digest")
        data = self.model_dump(exclude=exclude_fields, mode="json")
        for ce in data.get("counterexamples", []):
            for k in ("patch_id", "target_file", "workspace_id", "snapshot_hash"):
                if ce.get(k) is None:
                    ce.pop(k, None)
        canonical_str = json.dumps(data, sort_keys=True, separators=(',', ':'))
        # Using domain separation
        domain_separated = f"REDLINE_EVIDENCE_RECEIPT_V1:{canonical_str}"
        return hashlib.sha256(domain_separated.encode("utf-8")).hexdigest()

def verify_receipt_integrity(receipt: EvidenceReceipt) -> bool:
    if not receipt.receipt_hash:
        return False

    # 1. Cryptographic canonical hash verification
    if receipt.receipt_hash != receipt.calculate_integrity_hash():
        return False

    # 2. Field consistency and verdict soundness verification
    if receipt.verdict == VerificationStatus.VERIFIED:
        # A VERIFIED verdict cannot have failed or unexecuted required scopes
        if receipt.verification_scope.execution in ("FAILED", "POLICY_BLOCKED", "SANDBOX_FAILURE", "RESOURCE_LIMIT", "TIMEOUT", "EXECUTION_FAILURE", "NOT EXECUTED"):
            return False
        if receipt.verification_scope.tests in ("FAILED", "INCONCLUSIVE", "NOT EXECUTED"):
            return False
        if receipt.verification_scope.invariants == "FAILED":
            return False
        if receipt.verification_scope.security == "FAILED":
            return False

        # Cannot have active counterexamples for this patch
        if receipt.counterexamples:
            for ce in receipt.counterexamples:
                if ce.patch_id is None or ce.patch_id == receipt.patch_id or (receipt.patch_id is None and ce.invariant_id == "PATCH_APPLICATION"):
                    return False

        # If structured observation is present, enforce provenance and execution status
        if receipt.structured_observation:
            if receipt.structured_observation.sandbox_backend == "UNKNOWN":
                return False
            if receipt.structured_observation.exit_code != 0:
                return False
            if (
                receipt.repository_snapshot_hash
                and receipt.structured_observation.repository_snapshot_hash
                and len(receipt.repository_snapshot_hash) == 64
                and len(receipt.structured_observation.repository_snapshot_hash) == 64
                and receipt.structured_observation.repository_snapshot_hash != receipt.repository_snapshot_hash
            ):
                return False
            if (
                receipt.patch_digest
                and receipt.structured_observation.patch_hash
                and len(receipt.patch_digest) == 64
                and len(receipt.structured_observation.patch_hash) == 64
                and receipt.structured_observation.patch_hash != receipt.patch_digest
            ):
                return False

        # If test summary is present, enforce arithmetic and test passing
        if receipt.test_summary:
            if receipt.test_summary.failed > 0 or receipt.test_summary.errored > 0:
                return False
            if receipt.test_summary.executed != (
                receipt.test_summary.passed + receipt.test_summary.failed +
                receipt.test_summary.errored + receipt.test_summary.inconclusive
            ):
                return False
            if receipt.test_summary.discovered < (receipt.test_summary.executed + receipt.test_summary.skipped):
                return False

    return True

class JudgeExplanation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    summary: str
    verified_claims: List[str] = Field(default_factory=list)
    failed_claims: List[str] = Field(default_factory=list)
    evidence_references: List[str] = Field(default_factory=list)
    limitations: str
    confidence: str
