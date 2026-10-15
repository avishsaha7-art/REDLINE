from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
import hashlib

class SandboxPolicy(BaseModel):
    max_runtime_seconds: int = 60
    max_output_bytes: int = 1024 * 1024  # 1 MB
    max_memory_bytes: Optional[int] = None
    max_disk_bytes: Optional[int] = None
    network_enabled: bool = False
    allowed_commands: List[str] = Field(default_factory=lambda: ["python", "pytest"])
    allowed_workspaces: Optional[List[str]] = None
    sandbox_root: Optional[str] = None
    require_absolute_paths: bool = False

class ExecutionRequest(BaseModel):
    command: List[str]
    working_directory: str
    environment: Dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int = 30
    repository_trust: str = "UNTRUSTED"
    
class ExecutionResult(BaseModel):
    run_id: str
    exit_code: Optional[int]
    stdout: str
    stderr: str
    stdout_sha256: str
    stderr_sha256: str
    timed_out: bool = False
    crashed: bool = False
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    policy_blocked: bool = False
    backend_provenance: Dict[str, Any] = Field(default_factory=dict)
    runtime_ms: int = 0
    resource_usage: Dict[str, Any] = Field(default_factory=dict)
    command_metadata: List[str] = Field(default_factory=list)
