from pydantic import BaseModel, Field, model_validator
from typing import List, Dict, Optional, Any
from enum import Enum
import hashlib

class OracleType(str, Enum):
    DETERMINISTIC_CONTRACT = "DETERMINISTIC_CONTRACT"
    TRUSTED_ACCEPTANCE_TEST = "TRUSTED_ACCEPTANCE_TEST"
    REGRESSION_TEST = "REGRESSION_TEST"
    REFERENCE_IMPLEMENTATION = "REFERENCE_IMPLEMENTATION"
    METAMORPHIC_RELATION = "METAMORPHIC_RELATION"
    DIFFERENTIAL_EXECUTION = "DIFFERENTIAL_EXECUTION"
    MODEL_EXPECTATION = "MODEL_EXPECTATION"

class ExecutionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    NONZERO = "NONZERO"
    TIMEOUT = "TIMEOUT"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"
    SANDBOX_FAILURE = "SANDBOX_FAILURE"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    EXECUTION_FAILURE = "EXECUTION_FAILURE"

class TestStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"
    INCONCLUSIVE = "INCONCLUSIVE"

class InvariantResultStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"
    NOT_EVALUATED = "NOT_EVALUATED"

class VerificationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    INCONCLUSIVE = "INCONCLUSIVE"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    SANDBOX_FAILURE = "SANDBOX_FAILURE"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"
    TIMEOUT = "TIMEOUT"
    EXECUTION_FAILURE = "EXECUTION_FAILURE"

class StructuredObservation(BaseModel):
    execution_id: str
    command_identifier: str
    exit_code: Optional[int]
    stdout_sha256: str
    stderr_sha256: str
    stdout_bytes: int
    stderr_bytes: int
    duration_ms: int
    status: ExecutionStatus
    sandbox_backend: str
    security_level: str
    capabilities: Dict[str, Any]
    workspace_id: str
    repository_snapshot_hash: str
    patch_hash: str

class TestObservation(BaseModel):
    test_id: str
    status: TestStatus
    duration_ms: int
    framework: str
    output_summary: str

class TestResultSummary(BaseModel):
    discovered: int = 0
    executed: int = 0
    passed: int = 0
    failed: int = 0
    errored: int = 0
    skipped: int = 0
    inconclusive: int = 0
    observations: List[TestObservation] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_arithmetic_consistency(self):
        # Auto-adjust discovered if not explicitly set
        if "discovered" not in self.model_fields_set:
            self.discovered = self.executed + self.skipped
        elif self.discovered < self.executed + self.skipped:
            raise ValueError(
                f"Contradictory test counts: discovered ({self.discovered}) < executed ({self.executed}) + skipped ({self.skipped})"
            )

        expected_executed = self.passed + self.failed + self.errored + self.inconclusive
        if self.executed != expected_executed:
            raise ValueError(
                f"Inconsistent test counts: executed ({self.executed}) != passed ({self.passed}) + failed ({self.failed}) + errored ({self.errored}) + inconclusive ({self.inconclusive})"
            )
        return self

class RegressionSummary(BaseModel):
    newly_failing: List[str] = Field(default_factory=list)
    newly_passing: List[str] = Field(default_factory=list)
    changed_invariants: List[str] = Field(default_factory=list)
    regression_detected: bool = False

class InvariantEvaluation(BaseModel):
    invariant_id: str
    description: str
    result: InvariantResultStatus
    failure_reason: Optional[str]
    evidence_hash: str

class SecurityObservation(BaseModel):
    hook_id: str
    status: InvariantResultStatus
    evidence: str

class Counterexample(BaseModel):
    counterexample_id: str
    invariant_id: str
    test_id: Optional[str]
    input_data: str
    observed_output: str
    expected_output: str
    failure_reason: str
    oracle_type: OracleType
    execution_id: str
    evidence_hash: str
    patch_id: Optional[str] = None
    target_file: Optional[str] = None
    workspace_id: Optional[str] = None
    snapshot_hash: Optional[str] = None

    def hash(self) -> str:
        s = f"{self.counterexample_id}:{self.invariant_id}:{self.execution_id}:{self.input_data}:{self.observed_output}:{self.patch_id or ''}:{self.target_file or ''}"
        return hashlib.sha256(s.encode()).hexdigest()

class OracleResult(BaseModel):
    oracle_type: OracleType
    result: InvariantResultStatus
    evidence: str

class VerificationResult(BaseModel):
    verification_id: str
    status: VerificationStatus
    structured_observation: Optional[StructuredObservation] = None
    test_summary: Optional[TestResultSummary] = None
    invariant_summary: List[InvariantEvaluation] = Field(default_factory=list)
    regression_summary: Optional[RegressionSummary] = None
    security_summary: List[SecurityObservation] = Field(default_factory=list)
    counterexamples: List[Counterexample] = Field(default_factory=list)
    oracle_results: List[OracleResult] = Field(default_factory=list)
    execution_ids: List[str] = Field(default_factory=list)
    evidence_hashes: List[str] = Field(default_factory=list)
    policy_version: str
    verifier_version: str
    repository_snapshot_hash: str
    patch_hash: str
    verified_scope: str

    def hash(self) -> str:
        s = f"{self.status.value}:{self.repository_snapshot_hash}:{self.patch_hash}"
        return hashlib.sha256(s.encode()).hexdigest()
