import json
import pytest
from fastapi.testclient import TestClient

from backend.api.app import app
from backend.api.routes.runs import _runs, _orchestrators, reset_run_store, Run
from backend.models.schemas import (
    TaskContract,
    ResourceBudget,
    RunState,
    OperationalResult,
    PatchCandidate,
)
from backend.models.evidence import (
    EvidenceReceipt,
    VerificationScope,
    JudgeExplanation,
    verify_receipt_integrity,
)
from backend.verification.models import (
    VerificationResult,
    VerificationStatus,
    StructuredObservation,
    ExecutionStatus,
    TestResultSummary,
    RegressionSummary,
    OracleResult,
    InvariantResultStatus,
    Counterexample,
)
from backend.verification.policy import DeterministicVerificationPolicy
from backend.orchestrator.orchestrator import Orchestrator
from backend.evidence.builder import EvidenceAggregator
from tests.test_stage11 import MockModelProvider

client = TestClient(app)

@pytest.fixture(autouse=True)
def clean_store(monkeypatch):
    monkeypatch.setenv("REDLINE_ENABLE_LOCAL_BACKEND", "1")
    reset_run_store()
    yield
    reset_run_store()

def create_base_contract(task_id: str = "T-14-3") -> TaskContract:
    return TaskContract(
        task_id=task_id,
        repository_id="repo-cons-1",
        base_commit_or_snapshot="snap-14-3",
        task_description="Lifecycle and verdict consistency testing",
        allowed_scope=["main.py"],
        resource_budget=ResourceBudget(max_iterations=20)
    )

def test_deterministic_verdict_verified_leads_to_verified_lifecycle():
    """
    Invariant 2: VERIFIED may be assigned only when the deterministic
    verification policy explicitly returns VERIFIED.
    """
    contract = create_base_contract("T-VERIFIED")
    provider = MockModelProvider([
        # Architect
        json.dumps({"objective": "test", "files_to_modify": ["main.py"]}),
        # Builder
        json.dumps({"changed_files": ["main.py"], "diff": "--- a/main.py\n+++ b/main.py\n@@ -1 +1 @@\n-old\n+new\n"}),
        # Judge
        json.dumps({
            "summary": "Verified by deterministic tests",
            "verified_claims": ["claim 1"],
            "failed_claims": [],
            "evidence_references": [],
            "limitations": "None",
            "confidence": "High"
        })
    ])

    orch = Orchestrator("run-ver-1", contract, model_provider=provider)
    final_state = orch.run()

    assert final_state == RunState.VERIFIED
    assert hasattr(orch, "evidence_receipt")
    assert orch.evidence_receipt is not None
    assert orch.evidence_receipt.verdict == VerificationStatus.VERIFIED
    assert verify_receipt_integrity(orch.evidence_receipt) is True
    # Invariant 1: State and verdict never contradict
    assert final_state == RunState.VERIFIED and orch.evidence_receipt.verdict == VerificationStatus.VERIFIED


def test_deterministic_verdict_rejected_leads_to_non_success_lifecycle():
    """
    Invariant 3: REJECTED must never be represented as successful verification.
    """
    contract = create_base_contract("T-REJECTED")

    provider = MockModelProvider([
        # Architect
        json.dumps({"objective": "test", "files_to_modify": ["main.py"]}),
        # Builder
        json.dumps({"changed_files": ["main.py"], "diff": "--- a/main.py\n+++ b/main.py\n@@ -1 +1 @@\n-old\n+buggy\n"}),
        # RedTeam
        json.dumps([{
            "attack_id": "A1",
            "objective": "Break invariant",
            "target": "main.py",
            "input_specification": "bad_input",
            "execution_strategy": "FUNCTION_INPUT",
            "expected_failure_signal": "Crash",
            "oracle_type": "TASK_INVARIANT",
            "risk_level": "HIGH",
            "rationale": "Test failure",
            "attack_type": "INPUT"
        }]),
    ])

    orch = Orchestrator("run-rej-1", contract, model_provider=provider)

    class FailingExecutor:
        def __init__(self, backend=None):
            pass
        def execute_and_verify(self, req, workspace_id):
            obs = StructuredObservation(
                execution_id="E-FAIL", status=ExecutionStatus.SUCCESS, command_identifier="test",
                stdout_sha256="", stderr_sha256="", stdout_bytes=0, stderr_bytes=0, duration_ms=0,
                sandbox_backend="", security_level="", capabilities={}, workspace_id="",
                repository_snapshot_hash="", patch_hash="", exit_code=0
            )
            oracle = OracleResult(result="FAIL", oracle_type="DETERMINISTIC_CONTRACT", evidence="Failing test case")
            # Without counterexample, ANALYZE advances UNREPAIRABLE -> ABORTED
            return obs, oracle, None

    import backend.verification.attack_executor as exec_module
    old_engine = exec_module.AttackVerificationEngine
    exec_module.AttackVerificationEngine = FailingExecutor

    try:
        final_state = orch.run()
    finally:
        exec_module.AttackVerificationEngine = old_engine

    # Must be non-success (ABORTED)
    assert final_state == RunState.ABORTED
    assert final_state != RunState.VERIFIED
    assert orch.evidence_receipt is not None
    assert orch.evidence_receipt.verdict == VerificationStatus.REJECTED


def test_deterministic_verdict_inconclusive_leads_to_non_success_lifecycle():
    """
    Invariant 4: INCONCLUSIVE must never be represented as successful verification.
    """
    contract = create_base_contract("T-INCONCLUSIVE")
    provider = MockModelProvider([
        # Architect
        json.dumps({"objective": "test", "files_to_modify": ["main.py"]}),
        # Builder
        json.dumps({"changed_files": ["main.py"], "diff": "--- a/main.py\n+++ b/main.py\n@@ -1 +1 @@\n-old\n+new\n"}),
        # RedTeam
        json.dumps([{
            "attack_id": "A1",
            "objective": "Test inconclusive",
            "target": "main.py",
            "input_specification": "spec",
            "execution_strategy": "FUNCTION_INPUT",
            "expected_failure_signal": "Signal",
            "oracle_type": "TASK_INVARIANT",
            "risk_level": "LOW",
            "rationale": "Inconclusive",
            "attack_type": "INPUT"
        }]),
        # Judge
        json.dumps({
            "summary": "Evidence was inconclusive",
            "verified_claims": [],
            "failed_claims": [],
            "evidence_references": [],
            "limitations": "Inconclusive tests",
            "confidence": "Low"
        })
    ])

    orch = Orchestrator("run-inc-1", contract, model_provider=provider)

    class InconclusiveExecutor:
        def __init__(self, backend=None):
            pass
        def execute_and_verify(self, req, workspace_id):
            obs = StructuredObservation(
                execution_id="E-INC", status=ExecutionStatus.SUCCESS, command_identifier="test",
                stdout_sha256="", stderr_sha256="", stdout_bytes=0, stderr_bytes=0, duration_ms=0,
                sandbox_backend="", security_level="", capabilities={}, workspace_id="",
                repository_snapshot_hash="", patch_hash="", exit_code=0
            )
            oracle = OracleResult(result="INCONCLUSIVE", oracle_type="DETERMINISTIC_CONTRACT", evidence="Evidence inconclusive")
            return obs, oracle, None

    import backend.verification.attack_executor as exec_module
    old_engine = exec_module.AttackVerificationEngine
    exec_module.AttackVerificationEngine = InconclusiveExecutor

    try:
        final_state = orch.run()
    finally:
        exec_module.AttackVerificationEngine = old_engine

    # Authoritative gate must fail closed: never VERIFIED
    assert final_state == RunState.ABORTED
    assert final_state != RunState.VERIFIED
    assert orch.evidence_receipt is not None
    assert orch.evidence_receipt.verdict == VerificationStatus.INCONCLUSIVE


def test_missing_verification_evidence_fails_closed():
    """
    Invariant 5: Missing or insufficient evidence must fail closed to non-success.
    """
    contract = create_base_contract("T-MISSING-EV")
    provider = MockModelProvider([
        json.dumps({"objective": "test", "files_to_modify": ["main.py"]}),
        json.dumps({"changed_files": ["main.py"], "diff": "--- a/main.py\n+++ b/main.py\n@@ -1 +1 @@\n-old\n+new\n"}),
    ])
    orch = Orchestrator("run-miss-1", contract, model_provider=provider)

    # Intercept build_receipt so it returns None / doesn't set evidence_receipt
    old_build = EvidenceAggregator.build_receipt
    def failing_build(self, *args, **kwargs):
        return None
    EvidenceAggregator.build_receipt = failing_build

    try:
        final_state = orch.run()
    finally:
        EvidenceAggregator.build_receipt = old_build

    events = [e["event_type"] for e in orch.state_machine.events.get_events()]
    assert "EVIDENCE_MISSING" in events
    assert final_state == RunState.ABORTED


def test_evidence_tampering_integrity_failure_fails_closed():
    """
    Invariant 5 & 10: Corrupted evidence fails closed to ABORTED.
    """
    contract = create_base_contract("T-TAMPER")
    provider = MockModelProvider([
        json.dumps({"objective": "test", "files_to_modify": ["main.py"]}),
        json.dumps({"changed_files": ["main.py"], "diff": "--- a/main.py\n+++ b/main.py\n@@ -1 +1 @@\n-old\n+new\n"}),
    ])
    orch = Orchestrator("run-tamper-1", contract, model_provider=provider)

    # Intercept build_receipt to corrupt the receipt_hash
    old_build = EvidenceAggregator.build_receipt
    def tampered_build(self, *args, **kwargs):
        real_receipt = old_build(self, *args, **kwargs)
        return real_receipt.model_copy(update={"receipt_hash": "corrupted_invalid_hash"})
    EvidenceAggregator.build_receipt = tampered_build

    try:
        final_state = orch.run()
    finally:
        EvidenceAggregator.build_receipt = old_build

    events = [e["event_type"] for e in orch.state_machine.events.get_events()]
    assert "EVIDENCE_INTEGRITY_FAILURE" in events
    assert final_state == RunState.ABORTED


def test_operational_failure_distinguishable_from_verification_failure():
    """
    Invariant 6: Operational failures must remain distinguishable from code-verification failures.
    """
    contract = create_base_contract("T-OP-FAIL")
    orch = Orchestrator("run-op-1", contract)
    orch.state_machine.current_state = RunState.VERIFY

    # Operational failure (POLICY_BLOCKED)
    obs = StructuredObservation(
        execution_id="exec-op", command_identifier="test", exit_code=None,
        stdout_sha256="", stderr_sha256="", stdout_bytes=0, stderr_bytes=0,
        duration_ms=0, status=ExecutionStatus.POLICY_BLOCKED, sandbox_backend="",
        security_level="", capabilities={}, workspace_id="",
        repository_snapshot_hash="snap-1", patch_hash="patch-1"
    )
    v_res = DeterministicVerificationPolicy().evaluate(
        repository_snapshot_hash="snap-1",
        patch_hash="patch-1",
        structured_observation=obs,
        test_summary=TestResultSummary(),
        regression_summary=RegressionSummary(),
        invariants=[],
        security_aggregation=None,
        oracle_results=[],
        counterexamples=[]
    )
    assert v_res.status == VerificationStatus.POLICY_BLOCKED

    # Advance operational failure
    orch.state_machine.advance(OperationalResult.POLICY_BLOCKED)

    assert orch.state_machine.current_state == RunState.ABORTED
    assert orch.state_machine.operational_result == OperationalResult.POLICY_BLOCKED


def test_judge_output_cannot_override_deterministic_verdict():
    """
    Invariant 7: The LLM Judge remains advisory and cannot change
    lifecycle state or verification verdict.
    """
    contract = create_base_contract("T-JUDGE-ADVISORY")
    provider = MockModelProvider([
        json.dumps({"objective": "test", "files_to_modify": ["main.py"]}),
        json.dumps({"changed_files": ["main.py"], "diff": "--- a/main.py\n+++ b/main.py\n@@ -1 +1 @@\n-old\n+new\n"}),
        # RedTeam returns attack that evaluates to INCONCLUSIVE
        json.dumps([{
            "attack_id": "A1",
            "objective": "Test inconclusive",
            "target": "main.py",
            "input_specification": "spec",
            "execution_strategy": "FUNCTION_INPUT",
            "expected_failure_signal": "Signal",
            "oracle_type": "TASK_INVARIANT",
            "risk_level": "LOW",
            "rationale": "Inconclusive",
            "attack_type": "INPUT"
        }]),
    ])
    orch = Orchestrator("run-judge-adv-1", contract, model_provider=provider)

    class InconclusiveExecutor:
        def __init__(self, backend=None):
            pass
        def execute_and_verify(self, req, workspace_id):
            obs = StructuredObservation(
                execution_id="E-INC", status=ExecutionStatus.SUCCESS, command_identifier="test",
                stdout_sha256="", stderr_sha256="", stdout_bytes=0, stderr_bytes=0, duration_ms=0,
                sandbox_backend="", security_level="", capabilities={}, workspace_id="",
                repository_snapshot_hash="", patch_hash="", exit_code=0
            )
            oracle = OracleResult(result="INCONCLUSIVE", oracle_type="DETERMINISTIC_CONTRACT", evidence="Evidence inconclusive")
            return obs, oracle, None

    import backend.verification.attack_executor as exec_module
    old_engine = exec_module.AttackVerificationEngine
    exec_module.AttackVerificationEngine = InconclusiveExecutor

    # Judge actively claims 100% verified and complete pass
    orch.judge.generate_explanation = lambda r, c, p: JudgeExplanation(
        summary="Everything passed completely! Claiming 100% verified!",
        verified_claims=["All verified"],
        failed_claims=[],
        evidence_references=[],
        limitations="None",
        confidence="High"
    )

    try:
        final_state = orch.run()
    finally:
        exec_module.AttackVerificationEngine = old_engine

    # The deterministic policy gate MUST ignore the advisory Judge and fail closed
    assert final_state == RunState.ABORTED
    assert orch.evidence_receipt.verdict == VerificationStatus.INCONCLUSIVE
    assert orch.evidence_receipt.verdict != VerificationStatus.VERIFIED


def test_repair_and_retry_flow_preserves_valid_progress():
    """
    Invariant 9: Preserve valid autonomous repair and retry behavior.
    Intermediate verification failure transitions to repair; subsequent pass reaches VERIFIED.
    """
    contract = create_base_contract("T-REPAIR-FLOW")
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

    orch = Orchestrator("run-repair-1", contract, model_provider=provider)

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
    assert len(orch.patch_lineage) == 2
    assert orch.patch_lineage[1].startswith("REPAIR-")
    assert orch.evidence_receipt.verdict == VerificationStatus.VERIFIED


def test_api_status_and_receipt_consistency_defense_in_depth():
    """
    API Level Invariant: External API responses must never allow
    state == VERIFIED when EvidenceReceipt.verdict != VERIFIED.
    """
    contract = create_base_contract("T-API-CONSISTENCY")
    
    # 1. Test normal execution via API: completed run
    payload = contract.model_dump(mode="json")
    post_resp = client.post("/api/v1/runs", json=payload)
    assert post_resp.status_code == 201
    run_id = post_resp.json()["run_id"]

    import time
    start = time.time()
    final_data = None
    while time.time() - start < 10.0:
        get_resp = client.get(f"/api/v1/runs/{run_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()
        if data["status"] in ("completed", "failed"):
            final_data = data
            break
        time.sleep(0.05)

    assert final_data is not None
    assert final_data["status"] == "completed"
    assert final_data["state"] == RunState.VERIFIED.value
    assert final_data["evidence_receipt"]["verdict"] == VerificationStatus.VERIFIED.value

    # 2. Defense-in-depth: Manually inject a contradiction in the database/store
    # and verify that GET /api/v1/runs/{run_id} and GET /api/v1/runs enforce consistency.
    run = _runs[run_id]
    orch = _orchestrators[run_id]
    # Artificially tamper receipt verdict to INCONCLUSIVE while state is VERIFIED
    tampered_receipt = run.evidence_receipt.model_copy(update={"verdict": VerificationStatus.INCONCLUSIVE})
    run.evidence_receipt = tampered_receipt
    orch.evidence_receipt = tampered_receipt

    # Query GET /api/v1/runs/{run_id}
    resp = client.get(f"/api/v1/runs/{run_id}")
    assert resp.status_code == 200
    tampered_data = resp.json()
    # The API layer catches the discrepancy and forces non-success
    assert tampered_data["state"] != RunState.VERIFIED.value
    assert tampered_data["status"] != "completed"
    assert tampered_data["state"] == RunState.ABORTED.value

    # Query GET /api/v1/runs
    list_resp = client.get("/api/v1/runs")
    assert list_resp.status_code == 200
    runs_list = list_resp.json()
    item = next(r for r in runs_list if r["run_id"] == run_id)
    assert item["final_state"] != RunState.VERIFIED.value
    assert item["final_state"] == RunState.ABORTED.value
