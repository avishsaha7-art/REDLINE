import pytest
from backend.models.schemas import TaskContract, ResourceBudget, RepairCandidate, PatchCandidate
from backend.models.provider import ModelProvider, ModelResponse
from backend.orchestrator.orchestrator import Orchestrator
from backend.verification.models import Counterexample, OracleType

class DeterministicTestProvider(ModelProvider):
    def __init__(self, responses=None):
        self.responses = responses or {}
        
    def generate(self, messages, temperature=1.0):
        content = messages[0]["content"]
        if "Architect" in content:
            return ModelResponse(response_text='{"objective": "test", "files_to_modify": [], "implementation_steps": [], "acceptance_criteria": [], "constraints": [], "risks": [], "expected_tests": []}', model="test", provider="test", input_tokens=10, output_tokens=10, timestamp=0.0)
        elif "Builder" in content:
            return ModelResponse(response_text='{"changed_files": ["test.py"], "diff": "--- a/test.py\\n+++ b/test.py\\n@@ -1 +1 @@\\n-a\\n+b"}', model="test", provider="test", input_tokens=10, output_tokens=10, timestamp=0.0)
        elif "Red Team" in content:
            return ModelResponse(response_text='''[{"attack_id": "A1", "attack_type": "INPUT", "objective": "break", "target": "f", "preconditions": [], "input_specification": "{}", "execution_strategy": "TEST_CASE", "expected_failure_signal": "Crash", "oracle_type": "TASK_INVARIANT", "risk_level": "LOW", "rationale": "test"}]''', model="test", provider="test", input_tokens=10, output_tokens=10, timestamp=0.0)
        elif "Repairer" in content:
            return ModelResponse(response_text='{"changed_files": ["test.py"], "diff": "--- a/test.py\\n+++ b/test.py\\n@@ -1 +1 @@\\n-b\\n+c", "target_failure": "fixed bug", "reasoning_summary": "fixed"}', model="test", provider="test", input_tokens=10, output_tokens=10, timestamp=0.0)
        
        return ModelResponse(response_text="{}", model="test", provider="test", input_tokens=10, output_tokens=10, timestamp=0.0)

def test_repairer_isolation():
    from backend.agents.repairer import RepairerAgent
    
    agent = RepairerAgent(tools=[], model_provider=DeterministicTestProvider())
    contract = TaskContract(task_id="T1", repository_id="R1", base_commit_or_snapshot="main", task_description="t")
    patch = PatchCandidate(patch_id="P1", task_id="T1", base_commit_or_snapshot="main", diff="--- a/test.py\n+++ b/test.py\n@@ -1 +1 @@\n-x\n+y")
    
    res = agent.repair(contract, patch, "counterexample text")
    assert isinstance(res, RepairCandidate)
    assert not hasattr(res, "verdict")
    assert not hasattr(res, "sandbox_backend")
    assert not hasattr(res, "trust_level")
    assert not hasattr(res, "authorized")

def test_e2e_closed_loop():
    contract = TaskContract(
        task_id="T1",
        repository_id="R1",
        base_commit_or_snapshot="main",
        task_description="test",
        resource_budget=ResourceBudget(max_iterations=10, max_failed_attempts=3)
    )
    orch = Orchestrator("run_1", contract, model_provider=DeterministicTestProvider())
    
    orch.state_machine.current_state = "ANALYZE"
    orch.counterexamples = [
        Counterexample(
            counterexample_id="ce1", invariant_id="inv1", test_id=None, input_data="a", 
            observed_output="b", expected_output="c", failure_reason="fail", 
            oracle_type=OracleType.DETERMINISTIC_CONTRACT, execution_id="ex1", evidence_hash="hash"
        )
    ]
    
    orch.patch_candidate = PatchCandidate(patch_id="P1", task_id="T1", base_commit_or_snapshot="main", diff="--- a/test.py\n+++ b/test.py\n@@ -1 +1 @@\n-a\n+b")
    orch.untrusted_context = "context"
    
    orch.state_machine.advance("NEEDS_REPAIR")
    assert orch.state_machine.current_state == "REPAIR"
    
    repair_candidate = orch.repairer.repair(
        orch.task_contract,
        orch.patch_candidate,
        "ce_text",
        orch.untrusted_context
    )
    
    from backend.verification.patch_validation import validate_patch
    new_patch = PatchCandidate(
        patch_id=repair_candidate.repair_id,
        task_id=orch.task_contract.task_id,
        base_commit_or_snapshot=orch.task_contract.base_commit_or_snapshot,
        diff=repair_candidate.diff,
        changed_files=repair_candidate.changed_files,
        patch_metadata={"parent_hash": repair_candidate.base_patch_hash},
        generation_provenance={}
    )
    validate_patch(new_patch, orch.task_contract)
    orch.state_machine.advance(new_patch)
    
    assert orch.state_machine.current_state == "TEST"

def test_infinite_loop_prevention():
    contract = TaskContract(
        task_id="T1",
        repository_id="R1",
        base_commit_or_snapshot="main",
        task_description="test",
        resource_budget=ResourceBudget(max_iterations=10, max_failed_attempts=2)
    )
    orch = Orchestrator("run_1", contract, model_provider=DeterministicTestProvider())
    orch.state_machine.current_state = "ANALYZE"
    orch.counterexamples = [
        Counterexample(
            counterexample_id="ce1", invariant_id="inv1", test_id=None, input_data="a", 
            observed_output="b", expected_output="c", failure_reason="fail", 
            oracle_type=OracleType.DETERMINISTIC_CONTRACT, execution_id="ex1", evidence_hash="hash"
        )
    ]
    
    orch.repair_attempts = 1
    if orch.repair_attempts >= orch.task_contract.resource_budget.max_failed_attempts:
        orch.state_machine.advance("UNREPAIRABLE")
    else:
        orch.state_machine.advance("NEEDS_REPAIR")
    assert orch.state_machine.current_state == "REPAIR"
    
    orch.state_machine.current_state = "ANALYZE"
    orch.repair_attempts = 2
    if orch.repair_attempts >= orch.task_contract.resource_budget.max_failed_attempts:
        orch.state_machine.advance("UNREPAIRABLE")
    else:
        orch.state_machine.advance("NEEDS_REPAIR")
        
    assert orch.state_machine.current_state == "ABORTED"

def test_adversarial_repair_patch():
    contract = TaskContract(
        task_id="T1",
        repository_id="R1",
        base_commit_or_snapshot="main",
        task_description="test"
    )
    from backend.verification.patch_validation import validate_patch
    
    # Path traversal
    p1 = PatchCandidate(patch_id="1", task_id="T1", base_commit_or_snapshot="main", changed_files=["../outside.txt"], diff="--- a/../outside.txt\n+++ b/../outside.txt\n@@ -1 +1 @@\n-a\n+b")
    with pytest.raises(ValueError, match="Path traversal or absolute path detected"):
        validate_patch(p1, contract)
        
    # Absolute path
    p2 = PatchCandidate(patch_id="2", task_id="T1", base_commit_or_snapshot="main", changed_files=["/etc/passwd"], diff="--- a//etc/passwd\n+++ b//etc/passwd\n@@ -1 +1 @@\n-a\n+b")
    with pytest.raises(ValueError, match="Path traversal or absolute path detected"):
        validate_patch(p2, contract)
        
    # Protected file
    p3 = PatchCandidate(patch_id="3", task_id="T1", base_commit_or_snapshot="main", changed_files=[".env"], diff="--- a/.env\n+++ b/.env\n@@ -1 +1 @@\n-a\n+b")
    with pytest.raises(ValueError, match="Protected-file modification attempted"):
        validate_patch(p3, contract)

def test_duplicate_repair_rejection():
    # If the repairer provides the same repair twice, it should abort to avoid infinite loop
    contract = TaskContract(
        task_id="T1",
        repository_id="R1",
        base_commit_or_snapshot="main",
        task_description="test"
    )
    orch = Orchestrator("run_1", contract, model_provider=DeterministicTestProvider())
    orch.state_machine.current_state = "REPAIR"
    orch.counterexamples = [
        Counterexample(
            counterexample_id="ce1", invariant_id="inv1", test_id=None, input_data="a", 
            observed_output="b", expected_output="c", failure_reason="fail", 
            oracle_type=OracleType.DETERMINISTIC_CONTRACT, execution_id="ex1", evidence_hash="hash"
        )
    ]
    orch.patch_candidate = PatchCandidate(patch_id="P1", task_id="T1", base_commit_or_snapshot="main", diff="--- a/test.py\n+++ b/test.py\n@@ -1 +1 @@\n-a\n+b")
    
    # First time
    orch.state_machine.advance("REPAIR") # Doesn't actually run orch loop, so we trigger manually:
    repair_candidate = orch.repairer.repair(orch.task_contract, orch.patch_candidate, "ce", "")
    orch.seen_repairs.add(repair_candidate.repair_hash)
    
    # Now simulate a second REPAIR loop with the same result
    # We call the REPAIR block manually
    if repair_candidate.repair_hash in orch.seen_repairs:
        orch.state_machine.advance("TOOL_FAILURE")
    
    assert orch.state_machine.current_state == "ABORTED"

