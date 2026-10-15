from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from enum import Enum
import hashlib

class SecurityTestCategory(str, Enum):
    PATH_TRAVERSAL = "PATH_TRAVERSAL"
    RESOURCE_EXHAUSTION = "RESOURCE_EXHAUSTION"
    PROMPT_INJECTION = "PROMPT_INJECTION"
    ISOLATION_ESCAPE = "ISOLATION_ESCAPE"
    EVIDENCE_TAMPERING = "EVIDENCE_TAMPERING"

class SecurityTestSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

class SecurityTestStatus(str, Enum):
    IMPLEMENTED = "IMPLEMENTED"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    NOT_AVAILABLE = "NOT_AVAILABLE"
    BLOCKED = "BLOCKED"

class SecurityTestSpec(BaseModel):
    attack_id: str
    name: str
    category: SecurityTestCategory
    description: str
    severity: SecurityTestSeverity
    preconditions: List[str]
    input_fixture: str
    expected_security_invariant: str
    resource_budget: int
    clean_state_required: bool
    deterministic: bool
    version: str
    status: SecurityTestStatus

class AttackExecutionContext(BaseModel):
    attack_id: str
    run_id: str
    base_snapshot: str
    patch_hash: str
    execution_id: str

class SecurityResultClassification(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"
    NOT_EVALUATED = "NOT_EVALUATED"
    BLOCKED = "BLOCKED"
    ERROR = "ERROR"

class SecurityObservation(BaseModel):
    attack_id: str
    execution_id: str
    status: SecurityResultClassification
    exit_code: Optional[int]
    stdout_hash: str
    stderr_hash: str
    output_size: int
    duration: int
    resource_status: str
    expected_condition: str
    observed_condition: str
    invariant_results: List[str] = Field(default_factory=list)
    counterexample_ids: List[str] = Field(default_factory=list)
    evidence_hash: str

class SecurityInvariant(BaseModel):
    invariant_id: str
    version: str
    description: str
    expected_condition: str
    evaluation_method: str

class MutationOperator(str, Enum):
    REMOVE_CONDITION = "REMOVE_CONDITION"
    FLIP_BOOLEAN = "FLIP_BOOLEAN"
    CHANGE_CONSTANT = "CHANGE_CONSTANT"
    REMOVE_RETURN = "REMOVE_RETURN"
    ALTER_COMPARISON = "ALTER_COMPARISON"

class MutationSpec(BaseModel):
    mutation_id: str
    operator: MutationOperator
    target_file: str
    target_line: int
    original_code: str
    mutated_code: str

class MutationResult(BaseModel):
    mutation_id: str
    status: SecurityResultClassification
    detected: bool
    evidence_hash: str

class MetamorphicRelation(BaseModel):
    relation_id: str
    input_transform: str
    expected_relation: str
    version: str

class MetamorphicTestResult(BaseModel):
    relation_id: str
    status: SecurityResultClassification
    evidence_hash: str

class SecurityRegressionSummary(BaseModel):
    newly_failing: List[str] = Field(default_factory=list)
    newly_passing: List[str] = Field(default_factory=list)
    regression_detected: bool = False

class SecurityResultAggregation(BaseModel):
    observations: List[SecurityObservation] = Field(default_factory=list)
    invariants: List[SecurityInvariant] = Field(default_factory=list)
    mutations: List[MutationResult] = Field(default_factory=list)
    metamorphic: List[MetamorphicTestResult] = Field(default_factory=list)
    regression: Optional[SecurityRegressionSummary] = None
    overall_status: SecurityResultClassification

    def hash(self) -> str:
        s = f"{self.overall_status.value}:{len(self.observations)}:{len(self.invariants)}"
        return hashlib.sha256(s.encode()).hexdigest()
