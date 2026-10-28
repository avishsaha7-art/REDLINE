from enum import Enum
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
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
    repository_id: str = ""
    base_commit_or_snapshot: str
    task_description: str
    constraints: List[str] = Field(default_factory=list)
    acceptance_criteria: List[str] = Field(default_factory=list)
    allowed_scope: List[str] = Field(default_factory=list)
    resource_budget: ResourceBudget = Field(default_factory=ResourceBudget)
    repository_trust: Optional[str] = None
    repository_url: Optional[str] = None
    commit_sha: Optional[str] = None

    @model_validator(mode="after")
    def _validate_repository_fields(self) -> "TaskContract":
        if not self.repository_id and not self.repository_url:
            raise ValueError("Either repository_id or repository_url must be provided.")
        if self.repository_url:
            url = self.repository_url.strip()
            if not url.startswith("https://"):
                raise ValueError("repository_url must use the 'https://' scheme.")
            # Remote repositories are strictly UNTRUSTED by default; client cannot override
            self.repository_trust = "UNTRUSTED"
            if self.repository_id in ("repo-int-1", "repo-cons-1"):
                raise ValueError("Cannot bind a remote repository URL to an authorized local fixture repository ID.")
        elif self.repository_id:
            rid = self.repository_id.strip()
            if rid.startswith("http://") or rid.startswith("https://"):
                raise ValueError("Repository URL must be provided in the 'repository_url' field, not 'repository_id'.")
            if any(c in rid for c in ("..", "/", "\\")):
                raise ValueError("Repository ID contains invalid or path traversal characters.")
        return self

class ArchitectPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective: str
    files_to_inspect: List[str] = Field(default_factory=list)
    files_to_modify: List[str] = Field(default_factory=list)
    implementation_steps: List[str] = Field(default_factory=list)
    acceptance_criteria: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    expected_tests: List[str] = Field(default_factory=list)

    @field_validator("objective", mode="before")
    @classmethod
    def _normalize_objective(cls, v: Any) -> Any:
        if isinstance(v, list):
            return " ".join(str(item) for item in v if item).strip()
        return v

    @field_validator(
        "acceptance_criteria",
        "constraints",
        "risks",
        "implementation_steps",
        "expected_tests",
        "files_to_inspect",
        "files_to_modify",
        mode="before",
    )
    @classmethod
    def _normalize_string_collection(cls, v: Any, info) -> Any:
        if isinstance(v, str):
            v_stripped = v.strip()
            if not v_stripped:
                return []
            if len(v_stripped) > 4096:
                raise ValueError(f"{info.field_name} string exceeds maximum allowed length of 4096 characters.")
            return [v_stripped]
        return v

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
