from enum import Enum
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
import hashlib

class RunState(str, Enum):
    INIT = "INIT"
    RECON = "RECON"
    PLAN = "PLAN"
    BASELINE = "BASELINE"
    BUILD = "BUILD"
    TEST = "TEST"
    ATTACK = "ATTACK"
    ANALYZE = "ANALYZE"
    REPAIR = "REPAIR"
    VERIFY = "VERIFY"
    JUDGE = "JUDGE"
    VERIFIED = "VERIFIED"
    ABORTED = "ABORTED"

class OperationalResult(str, Enum):
    SANDBOX_FAILURE = "SANDBOX_FAILURE"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    TIMEOUT = "TIMEOUT"
    INVALID_REPOSITORY = "INVALID_REPOSITORY"
    INVALID_TASK = "INVALID_TASK"
    MODEL_FAILURE = "MODEL_FAILURE"
    TOOL_FAILURE = "TOOL_FAILURE"

class ResourceBudget(BaseModel):
    max_iterations: int = 20
    max_runtime: int = 3600
    max_patch_size: int = 1024 * 1024
    max_tool_calls: int = 100
    max_failed_attempts: int = 3
    max_attack_cases: int = 20
    max_file_size: int = 1024 * 1024
    max_repo_files: int = 1000
    max_repo_bytes: int = 50 * 1024 * 1024
    max_context_bytes: int = 128 * 1024

class TaskContract(BaseModel):
    task_id: str
    repository_id: str
    base_commit_or_snapshot: str
    task_description: str
    constraints: List[str] = Field(default_factory=list)
    acceptance_criteria: List[str] = Field(default_factory=list)
    allowed_scope: List[str] = Field(default_factory=list)
    resource_budget: ResourceBudget = Field(default_factory=ResourceBudget)
    repository_trust: Optional[str] = None

class ArchitectPlan(BaseModel):
    objective: str
    files_to_inspect: List[str] = Field(default_factory=list)
    files_to_modify: List[str] = Field(default_factory=list)
    implementation_steps: List[str] = Field(default_factory=list)
    acceptance_criteria: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    expected_tests: List[str] = Field(default_factory=list)

class PatchCandidate(BaseModel):
    patch_id: str
    task_id: str
    base_commit_or_snapshot: str
    diff: str
    changed_files: List[str] = Field(default_factory=list)
    patch_metadata: Dict[str, Any] = Field(default_factory=dict)
    generation_provenance: Dict[str, Any] = Field(default_factory=dict)

    @property
    def diff_sha256(self) -> str:
        return hashlib.sha256(self.diff.encode('utf-8')).hexdigest()

class RepairCandidate(BaseModel, extra="forbid"):
    repair_id: str
    base_patch_hash: str
    diff: str
    changed_files: List[str] = Field(default_factory=list)
    target_failure: str
    reasoning_summary: str
    counterexample_reference: Optional[str] = None
    
    @property
    def diff_sha256(self) -> str:
        return hashlib.sha256(self.diff.encode('utf-8')).hexdigest()

    @property
    def repair_hash(self) -> str:
        s = f"{self.base_patch_hash}:{self.diff_sha256}:{self.target_failure}"
        return hashlib.sha256(s.encode('utf-8')).hexdigest()

class Run(BaseModel):
    run_id: str
    task_id: str
    task_contract: TaskContract
    current_state: RunState = RunState.INIT
    state_history: List[Dict[str, Any]] = Field(default_factory=list)
    events: List[Dict[str, Any]] = Field(default_factory=list)
    patches: List[PatchCandidate] = Field(default_factory=list)
    evidence_manifest: Dict[str, Any] = Field(default_factory=dict)
    operational_result: Optional[OperationalResult] = None
    operational_error: Optional[str] = None
    current_iteration: int = 0
    resource_status: Dict[str, Any] = Field(default_factory=dict)
    evidence_receipt: Optional[Any] = None
    judge_explanation: Optional[Any] = None
