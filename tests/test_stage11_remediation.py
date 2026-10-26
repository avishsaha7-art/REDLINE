import pytest
import json
import hashlib
from backend.models.schemas import TaskContract, PatchCandidate, ResourceBudget, RunState
from backend.models.evidence import EvidenceReceipt, VerificationScope, verify_receipt_integrity
from backend.verification.models import VerificationStatus, StructuredObservation, ExecutionStatus, OracleResult, Counterexample
from backend.evidence.builder import EvidenceAggregator
from backend.orchestrator.orchestrator import Orchestrator
from backend.orchestrator.limits import GovernanceController
from tests.test_stage11 import MockModelProvider
from backend.models.evidence import JudgeExplanation

@pytest.fixture(autouse=True)
def enable_local_backend(monkeypatch):
    monkeypatch.setenv("REDLINE_ENABLE_LOCAL_BACKEND", "1")
    yield

def test_finding_1_task_contract_hash_determinism():
    contract1 = TaskContract(
        task_id="T1",
        repository_id="R1",
        base_commit_or_snapshot="C1",
        task_description="test1",
        allowed_scope=["main.py"],
        resource_budget=ResourceBudget(max_iterations=20)
    )
    
    contract2 = TaskContract(
        task_id="T1",
        repository_id="R1",
        base_commit_or_snapshot="C1",
        task_description="test1",
        allowed_scope=["main.py"],
        resource_budget=ResourceBudget(max_iterations=20)
    )
    
    # We want to prove that EvidenceAggregator produces the exact same hash for equivalent contracts
    agg1 = EvidenceAggregator(contract1)
    agg2 = EvidenceAggregator(contract2)
    
    patch = PatchCandidate(patch_id="P1", task_id="T1", base_commit_or_snapshot="C1", diff="diff1")
    
    from backend.verification.models import VerificationResult, TestResultSummary, RegressionSummary
    v_res = VerificationResult(
        repository_snapshot_hash="C1",
        patch_hash="h1",
        status=VerificationStatus.VERIFIED,
        structured_observation=None,
        test_summary=TestResultSummary(executed=1, passed=1),
        regression_summary=RegressionSummary(),
        invariant_summary=[],
        security_summary=[],
        oracle_results=[],
        counterexamples=[],
        verification_id="V1",
        policy_version="1.0",
        verifier_version="1.0",
        verified_scope="main.py"
    )
    
    rec1 = agg1.build_receipt("run1", patch, v_res, [], {}, {})
    rec2 = agg2.build_receipt("run1", patch, v_res, [], {}, {})
    
    # The task_contract_hash MUST be identical, and MUST NOT be using the default python hash (which produces a short int string usually)
    assert rec1.task_contract_hash == rec2.task_contract_hash
    # Ensure it's a 64 char hex string (SHA-256)
    assert len(rec1.task_contract_hash) == 64
    
    # Different contract
    contract3 = TaskContract(
        task_id="T2",
        repository_id="R1",
        base_commit_or_snapshot="C1",
        task_description="test1",
        allowed_scope=["main.py"],
    )
    agg3 = EvidenceAggregator(contract3)
    rec3 = agg3.build_receipt("run1", patch, v_res, [], {}, {})
    
    assert rec1.task_contract_hash != rec3.task_contract_hash

def test_finding_2_receipt_hash_timestamp_independence():
    contract = TaskContract(
        task_id="T1",
        repository_id="R1",
        base_commit_or_snapshot="C1",
        task_description="test1",
    )
    
    patch = PatchCandidate(patch_id="P1", task_id="T1", base_commit_or_snapshot="C1", diff="diff1")
    from backend.verification.models import VerificationResult, TestResultSummary, RegressionSummary
    v_res = VerificationResult(
        repository_snapshot_hash="C1",
        patch_hash="h1",
        status=VerificationStatus.VERIFIED,
        structured_observation=None,
        test_summary=TestResultSummary(executed=1, passed=1),
        regression_summary=RegressionSummary(),
        invariant_summary=[],
        security_summary=[],
        oracle_results=[],
        counterexamples=[],
        verification_id="V1",
        policy_version="1.0",
        verifier_version="1.0",
        verified_scope="main.py"
    )
    
    agg = EvidenceAggregator(contract)
    rec1 = agg.build_receipt("run1", patch, v_res, [], {}, {})
    
    # Simulate same evidence but different timestamp
    rec2 = rec1.model_copy(update={"timestamp": "different_timestamp"})
    rec2 = rec2.model_copy(update={"receipt_hash": rec2.calculate_integrity_hash()})
    
    # Hash MUST be exactly the same
    assert rec1.receipt_hash == rec2.receipt_hash
    assert verify_receipt_integrity(rec1)
    assert verify_receipt_integrity(rec2)
    
    # Changing authoritative evidence MUST change the hash
    rec3 = rec1.model_copy(update={"patch_hash": "different_patch_hash"})
    # Since we can't manually set receipt_hash of rec3 easily, we just check calculate_integrity_hash
    assert rec3.calculate_integrity_hash() != rec1.receipt_hash

def test_finding_3_patch_lineage():
    contract = TaskContract(
        task_id="T1",
        repository_id="repo-cons-1",
        base_commit_or_snapshot="COMMIT1",
        task_description="Test Task",
        allowed_scope=["main.py"],
        resource_budget=ResourceBudget(max_iterations=20)
    )
    provider = MockModelProvider([
        # Architect
        json.dumps({"objective": "test", "files_to_modify": ["main.py"]}),
        # Builder (Initial buggy patch)
        json.dumps({"changed_files": ["main.py"], "diff": "--- a/main.py\n+++ b/main.py\n@@ -1 +1 @@\n-old\n+v1\n"}),
        # RedTeam
        json.dumps([{
            "attack_id": "A1",
            "objective": "Trigger bug",
            "target": "main.py",
            "input_specification": "edge_case",
            "execution_strategy": "FUNCTION_INPUT",
            "expected_failure_signal": "Crash",
            "oracle_type": "TASK_INVARIANT",
            "risk_level": "HIGH",
            "rationale": "Edge case test",
            "attack_type": "INPUT"
        }]),
        # Repairer (Repaired patch)
        json.dumps({
            "diff": "--- a/main.py\n+++ b/main.py\n@@ -1 +1 @@\n-old\n+repaired\n",
            "changed_files": ["main.py"],
            "target_failure": "edge_case",
            "reasoning_summary": "Fixed edge case"
        })
    ])

    orch = Orchestrator("RUN1", contract, model_provider=provider)

    call_count = 0
    class RepairExecutor:
        def __init__(self, backend=None):
            pass
        def execute_and_verify(self, req, workspace_id):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First attempt fails -> triggers repair
                obs = StructuredObservation(
                    execution_id="E-1", status=ExecutionStatus.SUCCESS, command_identifier="test",
                    stdout_sha256="", stderr_sha256="", stdout_bytes=0, stderr_bytes=0, duration_ms=0,
                    sandbox_backend="", security_level="", capabilities={}, workspace_id="",
                    repository_snapshot_hash="", patch_hash="", exit_code=0
                )
                oracle = OracleResult(result="FAIL", oracle_type="DETERMINISTIC_CONTRACT", evidence="Failing initial test")
                ce = Counterexample(
                    counterexample_id="CE-1", invariant_id="INV-1", test_id="T-1",
                    input_data="edge_case", observed_output="crash", expected_output="pass",
                    failure_reason="Unhandled edge case", oracle_type="DETERMINISTIC_CONTRACT",
                    execution_id="E-1", evidence_hash=""
                )
                return obs, oracle, ce
            else:
                # Repaired attempt passes -> reaches VERIFIED
                obs = StructuredObservation(
                    execution_id="E-2", status=ExecutionStatus.SUCCESS, command_identifier="test",
                    stdout_sha256="", stderr_sha256="", stdout_bytes=0, stderr_bytes=0, duration_ms=0,
                    sandbox_backend="", security_level="", capabilities={}, workspace_id="",
                    repository_snapshot_hash="", patch_hash="", exit_code=0
                )
                oracle = OracleResult(result="PASS", oracle_type="DETERMINISTIC_CONTRACT", evidence="Edge case handled cleanly")
                return obs, oracle, None

    import backend.verification.attack_executor as exec_module
    old_engine = exec_module.AttackVerificationEngine
    exec_module.AttackVerificationEngine = RepairExecutor

    # Supply deterministic judge explanation
    orch.judge.generate_explanation = lambda r, c, p: JudgeExplanation(
        summary="Verified repaired candidate",
        verified_claims=[],
        failed_claims=[],
        evidence_references=[],
        limitations="None",
        confidence="High"
    )

    try:
        final_state = orch.run()
    finally:
        exec_module.AttackVerificationEngine = old_engine

    assert final_state == RunState.VERIFIED

    # Check lineage
    print([e["event_type"] for e in orch.state_machine.events.get_events()])
    assert len(orch.patch_lineage) == 2
    assert orch.patch_lineage[1].startswith("REPAIR-")
    assert orch.evidence_receipt.patch_lineage == orch.patch_lineage
    # final patch identity used by EvidenceReceipt
    assert orch.evidence_receipt.patch_hash == orch.patch_candidate.patch_id
    assert orch.patch_candidate.patch_id.startswith("REPAIR-")

def test_finding_4_resource_budget_defaults_and_enforcement():
    # Production default should be 20
    budget = ResourceBudget()
    assert budget.max_iterations == 20
    
    gov = GovernanceController(budget)
    
    # Prove that iteration 1 to 20 is allowed
    for _ in range(20):
        assert not gov.is_exhausted()
        gov.increment_iteration()
        
    # Prove that next iteration is rejected
    assert gov.is_exhausted()
    
    # Test iteration bounds limit in orchestrator
    contract = TaskContract(
        task_id="T1",
        repository_id="R1",
        base_commit_or_snapshot="COMMIT1",
        task_description="Test Task",
        allowed_scope=["main.py"],
        # Use a small budget for this test to show exhaustion
        resource_budget=ResourceBudget(max_iterations=1)
    )
    provider = MockModelProvider([
        # Architect
        json.dumps({"objective": "...", "rationale": "...", "files_to_modify": ["main.py"], "instructions": "..."}),
    ])
    orch = Orchestrator("RUN_EXHAUST", contract, model_provider=provider)
    final_state = orch.run()
    
    # Should abort due to RESOURCE_LIMIT
    assert final_state == RunState.ABORTED
    assert orch.state_machine.events.get_events()[-1]["details"].get("result") == "RESOURCE_LIMIT"

