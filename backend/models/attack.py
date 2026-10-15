from enum import Enum
from pydantic import BaseModel, Field, field_validator
from typing import List, Dict, Optional, Any
import hashlib
import json

class AttackScore(BaseModel):
    total_score: float = Field(ge=0.0, le=1.0)
    relevance_score: float = Field(ge=0.0, le=1.0)
    novelty_score: float = Field(ge=0.0, le=1.0)
    oracle_strength_score: float = Field(ge=0.0, le=1.0)
    boundary_score: float = Field(ge=0.0, le=1.0)
    security_score: float = Field(ge=0.0, le=1.0)
    redundancy_penalty: float = Field(ge=0.0, le=1.0)
    cost_penalty: float = Field(ge=0.0, le=1.0)
    reasons: List[str] = Field(default_factory=list)

class AttackType(str, Enum):
    BOUNDARY = "BOUNDARY"
    INPUT = "INPUT"
    STATE = "STATE"
    REGRESSION = "REGRESSION"
    SECURITY = "SECURITY"
    RESOURCE = "RESOURCE"
    INVARIANT = "INVARIANT"
    MUTATION_DERIVED = "MUTATION_DERIVED"

class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

class OracleType(str, Enum):
    TASK_INVARIANT = "TASK_INVARIANT"
    TRUSTED_ACCEPTANCE_TEST = "TRUSTED_ACCEPTANCE_TEST"
    REGRESSION_TEST = "REGRESSION_TEST"
    REFERENCE_IMPLEMENTATION = "REFERENCE_IMPLEMENTATION"
    METAMORPHIC_RELATION = "METAMORPHIC_RELATION"
    DIFFERENTIAL_EXECUTION = "DIFFERENTIAL_EXECUTION"
    MODEL_GENERATED = "MODEL_GENERATED"

class AttackResourceBudget(BaseModel):
    max_runtime_ms: int = Field(default=5000, le=60000)
    max_memory_mb: int = Field(default=256, le=1024)
    max_output_bytes: int = Field(default=10240, le=102400)

class AttackMetadata(BaseModel):
    relevance: float = Field(default=0.5, ge=0.0, le=1.0)
    novelty: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    @field_validator('relevance', 'novelty', mode='before')
    def validate_hints(cls, v):
        if v is None:
            return 0.5
        try:
            val = float(v)
            import math
            if not math.isfinite(val):
                return 0.5
            if val < 0.0: return 0.0
            if val > 1.0: return 1.0
            return val
        except (ValueError, TypeError):
            return 0.5
            
    @field_validator('confidence', mode='before')
    def validate_confidence(cls, v):
        if v is None:
            return None
        try:
            val = float(v)
            import math
            if not math.isfinite(val):
                return None
            if val < 0.0: return 0.0
            if val > 1.0: return 1.0
            return val
        except (ValueError, TypeError):
            return None

class AttackCandidate(BaseModel):
    attack_id: str
    attack_type: AttackType
    objective: str = Field(..., max_length=1000)
    target: str = Field(..., max_length=500)
    preconditions: List[str] = Field(default_factory=list, max_length=20)
    input_specification: str = Field(..., max_length=10000)
    execution_strategy: str = Field(..., max_length=1000)
    expected_failure_signal: str = Field(..., max_length=1000)
    oracle_type: OracleType
    risk_level: RiskLevel
    resource_budget: AttackResourceBudget = Field(default_factory=AttackResourceBudget)
    isolation_requirements: List[str] = Field(default_factory=list, max_length=10)
    rationale: str = Field(..., max_length=2000)
    metadata: AttackMetadata = Field(default_factory=AttackMetadata)
    provenance: Dict[str, Any] = Field(default_factory=dict)

    @field_validator('preconditions')
    def validate_preconditions(cls, v):
        for p in v:
            if len(p) > 500:
                raise ValueError("Precondition string too long")
        return v
        
    @field_validator('isolation_requirements')
    def validate_isolation(cls, v):
        for p in v:
            if len(p) > 100:
                raise ValueError("Isolation requirement string too long")
        return v
    
    # Must NOT contain arbitrary fields such as success or verdicts. Model dumps reject unknown fields by default in pydantic (extra="forbid") 
    model_config = {
        "extra": "forbid"
    }
    
    @property
    def deterministic_fingerprint(self) -> str:
        # A fingerprint must be deterministic and hash equivalent attacks equally.
        normalized = {
            "attack_type": self.attack_type.value,
            "target": self.target,
            "input_specification": self.input_specification,
            "execution_strategy": self.execution_strategy
        }
        encoded = json.dumps(normalized, sort_keys=True).encode('utf-8')
        return hashlib.sha256(encoded).hexdigest()

class SelectedAttack(BaseModel):
    attack_fingerprint: str
    rank: int
    score: float
    category: AttackType
    redundancy_group: str
    estimated_cost: float
    selection_reason: str
    score_breakdown: AttackScore

