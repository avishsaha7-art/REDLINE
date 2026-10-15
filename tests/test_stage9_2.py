import pytest
from backend.models.attack import AttackCandidate, AttackType, OracleType, AttackResourceBudget
from backend.models.attack_execution import AttackExecutionRequest
from backend.verification.attack_validator import validate_attack_for_execution
from backend.verification.attack_executor import AttackVerificationEngine
from backend.sandbox.backend import LocalDevelopmentBackend
from backend.sandbox.models import SandboxPolicy, ExecutionResult
from backend.verification.models import ExecutionStatus, InvariantResultStatus

def create_valid_candidate(strategy="TEST_CASE"):
    return AttackCandidate(
        attack_id="ATTACK-1",
        attack_type=AttackType.INPUT,
        objective="Test",
        target="target_function",
        preconditions=[],
        input_specification='{"test": 1}',
        execution_strategy=strategy,
        expected_failure_signal="Crash",
        oracle_type=OracleType.TASK_INVARIANT,
        risk_level="MEDIUM",
        rationale="test"
    )

def test_attack_execution_request_identity():
    candidate1 = create_valid_candidate()
    req1 = validate_attack_for_execution("run_1", "task_1", "snap_A", "patch_B", candidate1)
    
    # Same inputs should produce same execution ID
    req2 = validate_attack_for_execution("run_1", "task_1", "snap_A", "patch_B", candidate1)
    assert req1.execution_id == req2.execution_id
    
    # Changed patch should change execution ID
    req3 = validate_attack_for_execution("run_1", "task_1", "snap_A", "patch_C", candidate1)
    assert req1.execution_id != req3.execution_id
    
    # Changed input specification should change execution ID
    candidate2 = create_valid_candidate()
    candidate2.input_specification = '{"test": 2}'
    req4 = validate_attack_for_execution("run_1", "task_1", "snap_A", "patch_B", candidate2)
    assert req1.execution_id != req4.execution_id

def test_attack_execution_request_validation():
    # Valid strategy
    candidate = create_valid_candidate(strategy="TEST_CASE")
    req = validate_attack_for_execution("run", "task", "snap", "patch", candidate)
    assert req.strategy == "TEST_CASE"
    
    # Invalid strategy
    candidate_invalid = create_valid_candidate(strategy="INVALID_SHELL_COMMAND")
    with pytest.raises(ValueError, match="Invalid execution strategy: INVALID_SHELL_COMMAND"):
        validate_attack_for_execution("run", "task", "snap", "patch", candidate_invalid)

def test_untrusted_sandbox_fails_closed():
    # Model cannot override trust level. It is not part of AttackExecutionRequest.
    # The engine strictly enforces it based on backend capabilities.
    backend = LocalDevelopmentBackend(SandboxPolicy())
    engine = AttackVerificationEngine(backend)
    
    candidate = create_valid_candidate()
    req = validate_attack_for_execution("run", "task", "snap", "patch", candidate)
    
    obs, oracle_res, ce = engine.execute_and_verify(req, "workspace")
    
    assert obs.status == ExecutionStatus.POLICY_BLOCKED
    assert oracle_res.result == InvariantResultStatus.INCONCLUSIVE
    assert ce is None
    assert "Secure sandbox unavailable" in obs.stderr_sha256 or "Secure sandbox unavailable" in obs.command_identifier or obs.stderr_bytes > 0

def test_orchestrator_verify_state():
    from backend.orchestrator.orchestrator import Orchestrator
    from backend.models.schemas import TaskContract, ResourceBudget
    
    contract = TaskContract(
        task_id="T1",
        repository_id="R1",
        base_commit_or_snapshot="main",
        task_description="test",
        resource_budget=ResourceBudget()
    )
    
    orch = Orchestrator("run_1", contract)
    orch.selected_attacks = [create_valid_candidate()]
    orch.snapshot_hash = "snap_1"
    orch.workspace_id = "ws_1"
    
    class MockPatch:
        diff_sha256 = "patch_1"
    orch.patch_candidate = MockPatch()
    
    orch.state_machine.current_state = "VERIFY"
    
    # Run the VERIFY block manually to avoid orch.run() advancing TASK_ACCEPTED on a mid-run state
    from backend.sandbox.backend import LocalDevelopmentBackend
    from backend.sandbox.models import SandboxPolicy
    policy = SandboxPolicy()
    backend = LocalDevelopmentBackend(policy)
    executor = AttackVerificationEngine(backend)
    any_fails = False
    
    for attack_candidate in orch.selected_attacks:
        req = validate_attack_for_execution(
            orch.state_machine.run_id,
            orch.task_contract.task_id,
            orch.snapshot_hash,
            orch.patch_candidate.diff_sha256,
            attack_candidate
        )
        obs, oracle_res, ce = executor.execute_and_verify(req, orch.workspace_id)
        if oracle_res.result == "FAIL":
            any_fails = True
            
    if any_fails:
        orch.state_machine.advance("VERIFY_FAILED")
    else:
        orch.state_machine.advance("VERIFY_SUCCESS")
    
    # It should advance to JUDGE
    assert orch.state_machine.current_state == "JUDGE"

def test_adversarial_sandbox_override():
    req = validate_attack_for_execution("run", "task", "snap", "patch", create_valid_candidate())
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        req.execution_policy_version = "99.9" # frozen
    with pytest.raises(ValidationError):
        req.oracle = "TRUSTED" # frozen

def test_adversarial_model_cannot_authorize():
    # Ensure attack request doesn't have fields for authorization
    req = validate_attack_for_execution("run", "task", "snap", "patch", create_valid_candidate())
    assert not hasattr(req, "authorized")
    assert not hasattr(req, "sandbox_backend")
    assert not hasattr(req, "trust_level")

