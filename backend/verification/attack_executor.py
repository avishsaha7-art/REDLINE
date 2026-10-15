from typing import List, Optional
from backend.sandbox.backend import SandboxBackend, LocalDevelopmentBackend
from backend.sandbox.models import ExecutionRequest, ExecutionResult
from backend.models.attack_execution import AttackExecutionRequest
from backend.verification.observer import DeterministicVerificationObserver
from backend.verification.models import (
    StructuredObservation, ExecutionStatus, OracleResult, InvariantResultStatus, Counterexample,
    OracleType as VerificationOracleType
)
import hashlib

def _map_oracle_type(attack_oracle_type) -> VerificationOracleType:
    mapping = {
        "TASK_INVARIANT": VerificationOracleType.DETERMINISTIC_CONTRACT,
        "MODEL_GENERATED": VerificationOracleType.MODEL_EXPECTATION,
    }
    # For others like REGRESSION_TEST etc., they should match
    try:
        return VerificationOracleType(mapping.get(attack_oracle_type.value, attack_oracle_type.value))
    except ValueError:
        return VerificationOracleType.MODEL_EXPECTATION

class AttackVerificationEngine:
    def __init__(self, backend: SandboxBackend, repository_trust: str = "UNTRUSTED"):
        self.backend = backend
        self.repository_trust = repository_trust
        self.observer = DeterministicVerificationObserver()

    def execute_and_verify(self, req: AttackExecutionRequest, workspace_id: str) -> tuple[StructuredObservation, OracleResult, Optional[Counterexample]]:
        # 1. Policy Gate / Sandbox Capability Check
        # If repository is untrusted, we require a secure sandbox.
        # LocalDevelopmentBackend returns secure_untrusted_execution=False
        
        caps = self.backend.capabilities()
        
        if self.repository_trust != "TRUSTED_DEVELOPMENT" and not caps.secure_untrusted_execution:
            # We fail closed!
            msg = f"POLICY_BLOCKED: Secure sandbox unavailable for untrusted repository (trust='{self.repository_trust}')."
            # Construct a blocked observation directly
            obs = StructuredObservation(
                execution_id=req.execution_id,
                command_identifier=req.strategy,
                exit_code=None,
                stdout_sha256=hashlib.sha256(b"").hexdigest(),
                stderr_sha256=hashlib.sha256(msg.encode()).hexdigest(),
                stdout_bytes=0,
                stderr_bytes=len(msg),
                duration_ms=0,
                status=ExecutionStatus.POLICY_BLOCKED,
                sandbox_backend=caps.model_dump().get("name", "LocalDevelopmentBackend"),
                security_level="DEVELOPMENT_ONLY",
                capabilities=caps.model_dump(),
                workspace_id=workspace_id,
                repository_snapshot_hash=req.snapshot_hash,
                patch_hash=req.patch_hash
            )
            oracle_res = OracleResult(
                oracle_type=_map_oracle_type(req.oracle),
                result=InvariantResultStatus.INCONCLUSIVE,
                evidence="Blocked by policy gate: secure sandbox required."
            )
            return obs, oracle_res, None

        # 2. Map strategy to actual execution command
        # For this stage, we assume a structured mapping, but we don't have a real framework yet.
        # We will mock the command for now based on strategy
        command = ["python", "-c", f"print('Executing {req.strategy}')"]
        
        # 3. Create Backend Request
        # If workspace_id is an abstract identifier rather than an existing directory path,
        # provision an ephemeral isolated workspace for this execution step.
        import os
        import tempfile
        import shutil
        cleanup_temp = False
        exec_dir = workspace_id
        if not (workspace_id and os.path.isdir(workspace_id)):
            exec_dir = tempfile.mkdtemp(prefix="redline_verify_ws_")
            cleanup_temp = True
            
        try:
            backend_req = ExecutionRequest(
                command=command,
                working_directory=exec_dir,
                repository_trust=self.repository_trust,
                timeout_seconds=min(30, req.resource_policy.max_runtime_ms // 1000)
            )
            
            # 4. Execute
            res = self.backend.execute(backend_req, req.run_id)
        finally:
            if cleanup_temp and exec_dir:
                shutil.rmtree(exec_dir, ignore_errors=True)
        
        # 5. Observe
        obs = self.observer.observe_execution(res, workspace_id, req.snapshot_hash, req.patch_hash)
        
        # 6. Oracle evaluation
        if obs.status == ExecutionStatus.SUCCESS or obs.status == ExecutionStatus.NONZERO:
            # Deterministic oracle based on observation
            # Since this is a test, let's say NONZERO means the attack broke something -> counterexample
            if obs.status == ExecutionStatus.NONZERO:
                oracle_res = OracleResult(
                    oracle_type=_map_oracle_type(req.oracle),
                    result=InvariantResultStatus.FAIL,
                    evidence=f"Execution resulted in NONZERO exit code: {res.exit_code}"
                )
                evidence_hash = hashlib.sha256(oracle_res.evidence.encode()).hexdigest()
                ce = Counterexample(
                    counterexample_id=f"ce_{req.execution_id}",
                    invariant_id=req.target,
                    test_id=None,
                    input_data=req.input,
                    observed_output=res.stderr or res.stdout,
                    expected_output="Exit code 0",
                    failure_reason="Attack caused nonzero exit code",
                    oracle_type=_map_oracle_type(req.oracle),
                    execution_id=req.execution_id,
                    evidence_hash=evidence_hash
                )
            else:
                oracle_res = OracleResult(
                    oracle_type=_map_oracle_type(req.oracle),
                    result=InvariantResultStatus.PASS,
                    evidence="Execution resulted in SUCCESS exit code 0"
                )
                ce = None
        else:
            oracle_res = OracleResult(
                oracle_type=_map_oracle_type(req.oracle),
                result=InvariantResultStatus.INCONCLUSIVE,
                evidence=f"Execution did not complete normally. Status: {obs.status}"
            )
            ce = None
            
        return obs, oracle_res, ce
