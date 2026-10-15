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
        data = self.model_dump(exclude={"receipt_hash", "timestamp"}, mode="json")
        canonical_str = json.dumps(data, sort_keys=True, separators=(',', ':'))
        # Using domain separation
        domain_separated = f"REDLINE_EVIDENCE_RECEIPT_V1:{canonical_str}"
        return hashlib.sha256(domain_separated.encode("utf-8")).hexdigest()

def verify_receipt_integrity(receipt: EvidenceReceipt) -> bool:
    if not receipt.receipt_hash:
        return False
    return receipt.receipt_hash == receipt.calculate_integrity_hash()

class JudgeExplanation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    summary: str
    verified_claims: List[str] = Field(default_factory=list)
    failed_claims: List[str] = Field(default_factory=list)
    evidence_references: List[str] = Field(default_factory=list)
    limitations: str
    confidence: str
