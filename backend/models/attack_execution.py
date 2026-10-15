from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import List, Dict, Optional, Any
from backend.models.attack import AttackType, OracleType, AttackResourceBudget
import hashlib
import json

class AttackExecutionRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    task_id: str
    snapshot_hash: str
    patch_hash: str
    attack_fingerprint: str
    attack_type: AttackType
    target: str = Field(..., max_length=500)
    input: str = Field(..., max_length=10000)
    strategy: str = Field(..., max_length=1000)
    oracle: OracleType
    resource_policy: AttackResourceBudget
    isolation_policy: List[str] = Field(default_factory=list, max_length=10)
    execution_policy_version: str = "1.0"

    @property
    def execution_id(self) -> str:
        # Deterministic identity derived from canonical representations
        normalized = {
            "version": "REDLINE_ATTACK_EXECUTION_V1",
            "snapshot_hash": self.snapshot_hash,
            "patch_hash": self.patch_hash,
            "attack_fingerprint": self.attack_fingerprint,
            "input": self.input,
            "execution_policy_version": self.execution_policy_version
        }
        encoded = json.dumps(normalized, sort_keys=True).encode('utf-8')
        return hashlib.sha256(encoded).hexdigest()

