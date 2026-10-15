from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from backend.sandbox.models import ExecutionResult

class Observation(BaseModel):
    process_status: str
    exit_code: Optional[int]
    timeout: bool
    crash: bool
    stdout_hash: str
    stderr_hash: str
    test_observations: Dict[str, Any] = Field(default_factory=dict)
    runtime_ms: int
    resource_observations: Dict[str, Any] = Field(default_factory=dict)
    provenance: Dict[str, Any] = Field(default_factory=dict)

class DeterministicObserver:
    def observe(self, result: ExecutionResult, patch_hash: str = "") -> Observation:
        status = "SUCCESSFUL_EXECUTION"
        if getattr(result, "policy_blocked", False):
            status = "POLICY_BLOCKED"
        elif result.timed_out:
            status = "TIMEOUT"
        elif result.crashed or (result.exit_code is not None and result.exit_code < 0):
            status = "CRASH"
        elif result.exit_code != 0:
            status = "CODE_FAILURE"

        return Observation(
            process_status=status,
            exit_code=result.exit_code,
            timeout=result.timed_out,
            crash=result.crashed,
            stdout_hash=result.stdout_sha256,
            stderr_hash=result.stderr_sha256,
            test_observations={},
            runtime_ms=result.runtime_ms,
            resource_observations=result.resource_usage,
            provenance={
                "run_id": result.run_id,
                "command": result.command_metadata,
                "patch_hash": patch_hash,
                "sandbox_backend": getattr(result, "backend_provenance", {})
            }
        )
