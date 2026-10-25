from pydantic import BaseModel, Field, field_validator
from typing import List, Dict, Optional, Any
import math
import hashlib

class SandboxPolicy(BaseModel):
    max_runtime_seconds: int = 60
    max_output_bytes: int = 1024 * 1024  # 1 MB
    max_memory_bytes: int = 512 * 1024 * 1024  # 512 MB default
    # max_disk_bytes: Reactive post-execution workspace measurement limit.
    # IMPORTANT SECURITY LIMITATION (Findings F-01 / F-02):
    # This check is strictly REACTIVE and occurs AFTER container execution finishes.
    # Because host bind mounts (-v) write directly to the host filesystem, this check
    # CANNOT proactively prevent host disk exhaustion during execution. It must NOT
    # be represented as a hard or proactive disk quota. Proactive quota enforcement
    # (e.g. dedicated loopback or tmpfs volumes) remains future work.
    max_disk_bytes: Optional[int] = None
    cpu_limit: float = 1.0  # 1.0 core default
    pids_limit: int = 64  # 64 processes default
    network_enabled: bool = False
    allowed_commands: List[str] = Field(default_factory=lambda: ["python", "pytest"])
    allowed_workspaces: Optional[List[str]] = None
    sandbox_root: Optional[str] = None
    require_absolute_paths: bool = False

    @field_validator("max_runtime_seconds", mode="before")
    @classmethod
    def validate_runtime_seconds(cls, v: Any) -> int:
        if isinstance(v, bool) or not isinstance(v, int):
            raise ValueError("max_runtime_seconds must be an integer")
        if v < 1 or v > 600:
            raise ValueError(f"max_runtime_seconds must be between 1 and 600 seconds, got {v}")
        return v

    @field_validator("max_output_bytes", mode="before")
    @classmethod
    def validate_output_bytes(cls, v: Any) -> int:
        if isinstance(v, bool) or not isinstance(v, int):
            raise ValueError("max_output_bytes must be an integer")
        if v < 1 or v > 100 * 1024 * 1024:
            raise ValueError(f"max_output_bytes must be between 1 and 100MB, got {v}")
        return v

    @field_validator("max_memory_bytes", mode="before")
    @classmethod
    def validate_memory_bytes(cls, v: Any) -> int:
        if isinstance(v, bool) or not isinstance(v, int):
            raise ValueError("max_memory_bytes must be an integer")
        if v < 4 * 1024 * 1024 or v > 8 * 1024 * 1024 * 1024:
            raise ValueError(f"max_memory_bytes must be between 4MB and 8GB, got {v}")
        return v

    @field_validator("cpu_limit", mode="before")
    @classmethod
    def validate_cpu_limit(cls, v: Any) -> float:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError("cpu_limit must be a numeric value")
        float_v = float(v)
        if math.isnan(float_v) or math.isinf(float_v):
            raise ValueError("cpu_limit must be a finite number")
        if float_v < 0.1 or float_v > 16.0:
            raise ValueError(f"cpu_limit must be between 0.1 and 16.0 cores, got {v}")
        return float_v

    @field_validator("pids_limit", mode="before")
    @classmethod
    def validate_pids_limit(cls, v: Any) -> int:
        if isinstance(v, bool) or not isinstance(v, int):
            raise ValueError("pids_limit must be an integer")
        if v < 4 or v > 1024:
            raise ValueError(f"pids_limit must be between 4 and 1024 processes, got {v}")
        return v

    @field_validator("max_disk_bytes", mode="before")
    @classmethod
    def validate_disk_bytes(cls, v: Any) -> Optional[int]:
        if v is None:
            return None
        if isinstance(v, bool) or not isinstance(v, int):
            raise ValueError("max_disk_bytes must be an integer")
        if v < 1024 * 1024 or v > 20 * 1024 * 1024 * 1024:
            raise ValueError(f"max_disk_bytes must be between 1MB and 20GB, got {v}")
        return v

class ExecutionRequest(BaseModel):
    command: List[str]
    working_directory: str
    environment: Dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=30, ge=1, le=600)
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
