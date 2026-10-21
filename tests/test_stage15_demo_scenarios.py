import time
import json
import pytest
from fastapi.testclient import TestClient

from backend.api.app import app
from backend.api.routes.runs import reset_run_store, set_model_provider, _runs, _orchestrators
from backend.models.schemas import TaskContract, RunState, OperationalResult, ResourceBudget
from backend.models.deterministic_provider import DeterministicTestProvider
from backend.models.evidence import verify_receipt_integrity
from backend.verification.models import (
    VerificationStatus,
    ExecutionStatus,
    StructuredObservation,
    OracleResult,
    Counterexample,
    OracleType,
)
from backend.sandbox.capabilities import RepositoryTrust

client = TestClient(app)

@pytest.fixture(autouse=True)
def clean_store(monkeypatch):
    monkeypatch.setenv("REDLINE_ENABLE_LOCAL_BACKEND", "1")
    reset_run_store()
    set_model_provider(DeterministicTestProvider())
    yield
    reset_run_store()
    set_model_provider(None)


def test_scenario_a_successful_verification():
    """
    Scenario A — Successful verification:
    A controlled task produces a valid patch, deterministic tests pass,
    and the system produces a consistent VERIFIED lifecycle state,
    evidence receipt, and advisory judge explanation.
    """
    contract_payload = {
        "task_id": "DEMO-TASK-A",
        "repository_id": "repo-int-1",
        "base_commit_or_snapshot": "snap-demo-a",
        "task_description": "Implement bug fix in main.py",
        "allowed_scope": ["main.py"],
        "repository_trust": "TRUSTED_DEVELOPMENT",
        "resource_budget": {
            "max_iterations": 20
        }
    }

    # 1. Task submission -> 201
    post_resp = client.post("/api/v1/runs", json=contract_payload)
    assert post_resp.status_code == 201
    run_id = post_resp.json()["run_id"]
    assert run_id.startswith("run-")

    # 2. Poll until terminal state
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

    assert final_data is not None, "Execution timed out"
    # Authoritative lifecycle state must be VERIFIED
    assert final_data["status"] == "completed"
    assert final_data["state"] == RunState.VERIFIED.value

    # Evidence receipt consistency
    receipt = final_data["evidence_receipt"]
    assert receipt is not None
    assert receipt["verdict"] == VerificationStatus.VERIFIED.value
    assert len(receipt["patch_lineage"]) >= 1

    # Cryptographic integrity
    receipt_resp = client.get(f"/api/v1/runs/{run_id}/receipt")
    assert receipt_resp.status_code == 200
    authoritative_receipt = _runs[run_id].evidence_receipt
    assert verify_receipt_integrity(authoritative_receipt) is True

    # Judge explanation advisory
    judge_resp = client.get(f"/api/v1/runs/{run_id}/judge")
    assert judge_resp.status_code == 200
    judge_data = judge_resp.json()
    assert "summary" in judge_data
    assert judge_data["confidence"] == "HIGH"

    # Patch diff endpoint
    diff_resp = client.get(f"/api/v1/runs/{run_id}/diff")
    assert diff_resp.status_code == 200
    diff_data = diff_resp.json()
    assert diff_data["run_id"] == run_id
    assert diff_data["patch_id"] is not None
    assert "--- a/main.py" in diff_data["diff"]
    assert diff_data["changed_files"] == ["main.py"]


def test_scenario_b_failed_candidate_and_autonomous_repair():
    """
    Scenario B — Failed candidate and autonomous repair:
    An initial candidate fails a deterministic check. REDLINE records
    the failure, invokes repair within its budget, reruns verification,
    and preserves patch lineage.
    """
    import backend.verification.attack_executor as exec_module
    old_engine = exec_module.AttackVerificationEngine

    call_count = 0
    class RepairMockExecutor:
        def __init__(self, backend=None, repository_trust="TRUSTED_DEVELOPMENT"):
            self.backend = backend
            self.repository_trust = repository_trust

        def execute_and_verify(self, req, workspace_id):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # 1st attempt: fails deterministic invariant -> counterexample
                obs = StructuredObservation(
                    execution_id="E-REPAIR-1", status=ExecutionStatus.SUCCESS, command_identifier="test",
                    stdout_sha256="", stderr_sha256="", stdout_bytes=0, stderr_bytes=0, duration_ms=0,
                    sandbox_backend="LocalDevelopmentBackend", security_level="DEVELOPMENT_ONLY",
                    capabilities={"secure_untrusted_execution": False}, workspace_id=workspace_id,
                    repository_snapshot_hash="snap-b", patch_hash="patch-initial", exit_code=0
                )
                oracle = OracleResult(result="FAIL", oracle_type="DETERMINISTIC_CONTRACT", evidence="Edge case failure")
                ce = Counterexample(
                    counterexample_id="CE-DEMO-1", invariant_id="INV-BOUNDARY-1", test_id="T-1",
                    input_data="boundary_input", observed_output="crash", expected_output="handled",
                    failure_reason="Unhandled boundary input", oracle_type="DETERMINISTIC_CONTRACT",
                    execution_id="E-REPAIR-1", evidence_hash=""
                )
                return obs, oracle, ce
            else:
                # 2nd attempt: repaired candidate passes
                obs = StructuredObservation(
                    execution_id="E-REPAIR-2", status=ExecutionStatus.SUCCESS, command_identifier="test",
                    stdout_sha256="", stderr_sha256="", stdout_bytes=0, stderr_bytes=0, duration_ms=0,
                    sandbox_backend="LocalDevelopmentBackend", security_level="DEVELOPMENT_ONLY",
                    capabilities={"secure_untrusted_execution": False}, workspace_id=workspace_id,
                    repository_snapshot_hash="snap-b", patch_hash="patch-repaired", exit_code=0
                )
                oracle = OracleResult(result="PASS", oracle_type="DETERMINISTIC_CONTRACT", evidence="All invariants verified")
                return obs, oracle, None

    exec_module.AttackVerificationEngine = RepairMockExecutor

    try:
        contract_payload = {
            "task_id": "DEMO-TASK-B",
            "repository_id": "repo-int-1",
            "base_commit_or_snapshot": "snap-demo-b",
            "task_description": "Boundary repair verification",
            "allowed_scope": ["main.py"],
            "repository_trust": "TRUSTED_DEVELOPMENT",
            "resource_budget": {
                "max_iterations": 20,
                "max_failed_attempts": 3
            }
        }

        post_resp = client.post("/api/v1/runs", json=contract_payload)
        assert post_resp.status_code == 201
        run_id = post_resp.json()["run_id"]

        start = time.time()
        final_data = None
        while time.time() - start < 10.0:
            get_resp = client.get(f"/api/v1/runs/{run_id}")
            data = get_resp.json()
            if data["status"] in ("completed", "failed"):
                final_data = data
                break
            time.sleep(0.05)

        assert final_data is not None
        assert final_data["status"] == "completed"
        assert final_data["state"] == RunState.VERIFIED.value

        # Patch lineage preserves both initial candidate and repair candidate
        assert len(final_data["patch_lineage"]) == 2
        assert final_data["patch_lineage"][1].startswith("REPAIR-")

        # Repaired receipt verdict is VERIFIED
        assert final_data["evidence_receipt"]["verdict"] == VerificationStatus.VERIFIED.value

        # Diff endpoint returns the repaired patch
        diff_resp = client.get(f"/api/v1/runs/{run_id}/diff")
        assert diff_resp.status_code == 200
        assert diff_resp.json()["patch_id"] == final_data["patch_lineage"][1]
    finally:
        exec_module.AttackVerificationEngine = old_engine


def test_scenario_c_rejected_or_inconclusive_candidate():
    """
    Scenario C — Rejected or inconclusive candidate:
    A deliberately failing or insufficiently verified candidate must NOT
    be reported as successful. The receipt, lifecycle state, and UI must agree.
    """
    import backend.verification.attack_executor as exec_module
    old_engine = exec_module.AttackVerificationEngine

    class RejectMockExecutor:
        def __init__(self, backend=None, repository_trust="TRUSTED_DEVELOPMENT"):
            self.backend = backend
            self.repository_trust = repository_trust

        def execute_and_verify(self, req, workspace_id):
            obs = StructuredObservation(
                execution_id="E-REJECT-1", status=ExecutionStatus.NONZERO, command_identifier="test",
                stdout_sha256="", stderr_sha256="", stdout_bytes=0, stderr_bytes=0, duration_ms=0,
                sandbox_backend="LocalDevelopmentBackend", security_level="DEVELOPMENT_ONLY",
                capabilities={"secure_untrusted_execution": False}, workspace_id=workspace_id,
                repository_snapshot_hash="snap-c", patch_hash="patch-c", exit_code=1
            )
            oracle = OracleResult(result="FAIL", oracle_type="DETERMINISTIC_CONTRACT", evidence="Persistent failure")
            ce = Counterexample(
                counterexample_id="CE-DEMO-C", invariant_id="INV-C", test_id="T-C",
                input_data="fail_input", observed_output="error", expected_output="pass",
                failure_reason="Persistent invariant failure", oracle_type="DETERMINISTIC_CONTRACT",
                execution_id="E-REJECT-1", evidence_hash=""
            )
            return obs, oracle, ce

    exec_module.AttackVerificationEngine = RejectMockExecutor

    try:
        contract_payload = {
            "task_id": "DEMO-TASK-C",
            "repository_id": "repo-int-1",
            "base_commit_or_snapshot": "snap-demo-c",
            "task_description": "Unrepairable candidate verification",
            "allowed_scope": ["main.py"],
            "repository_trust": "TRUSTED_DEVELOPMENT",
            "resource_budget": {
                "max_iterations": 20,
                "max_failed_attempts": 1
            }
        }

        post_resp = client.post("/api/v1/runs", json=contract_payload)
        assert post_resp.status_code == 201
        run_id = post_resp.json()["run_id"]

        start = time.time()
        final_data = None
        while time.time() - start < 10.0:
            get_resp = client.get(f"/api/v1/runs/{run_id}")
            data = get_resp.json()
            if data["status"] in ("completed", "failed"):
                final_data = data
                break
            time.sleep(0.05)

        assert final_data is not None
        # Must fail closed: never completed, never VERIFIED
        assert final_data["status"] == "failed"
        assert final_data["state"] == RunState.ABORTED.value
        assert final_data["state"] != RunState.VERIFIED.value

        receipt = final_data["evidence_receipt"]
        assert receipt is not None
        assert receipt["verdict"] in (VerificationStatus.REJECTED.value, VerificationStatus.INCONCLUSIVE.value)
        assert receipt["verdict"] != VerificationStatus.VERIFIED.value

        # List runs consistency
        list_resp = client.get("/api/v1/runs")
        item = next(r for r in list_resp.json() if r["run_id"] == run_id)
        assert item["final_state"] == RunState.ABORTED.value
        assert item["verdict"] != VerificationStatus.VERIFIED.value
    finally:
        exec_module.AttackVerificationEngine = old_engine


def test_scenario_d_sandbox_security_boundary():
    """
    Scenario D — Sandbox security boundary:
    An untrusted repository must be blocked by the development backend.
    The system must not silently fall back to unsafe execution.
    """
    contract_payload = {
        "task_id": "DEMO-TASK-D",
        "repository_id": "untrusted-external-repo-demo",
        "base_commit_or_snapshot": "snap-demo-d",
        "task_description": "Untrusted external repository execution attempt",
        "allowed_scope": ["main.py"],
        "repository_trust": "UNTRUSTED",
        "resource_budget": {
            "max_iterations": 10
        }
    }

    post_resp = client.post("/api/v1/runs", json=contract_payload)
    assert post_resp.status_code == 201
    run_id = post_resp.json()["run_id"]

    start = time.time()
    final_data = None
    while time.time() - start < 10.0:
        get_resp = client.get(f"/api/v1/runs/{run_id}")
        data = get_resp.json()
        if data["status"] in ("completed", "failed"):
            final_data = data
            break
        time.sleep(0.05)

    assert final_data is not None
    assert final_data["status"] == "failed"
    assert final_data["state"] == RunState.ABORTED.value
    assert final_data["operational_result"] == OperationalResult.POLICY_BLOCKED.value
    assert final_data["evidence_receipt"]["verdict"] == VerificationStatus.POLICY_BLOCKED.value


def test_scenario_e_missing_or_tampered_evidence():
    """
    Scenario E — Missing or tampered evidence:
    The system must fail closed and clearly communicate that successful
    verification was not established when receipt integrity fails.
    """
    from backend.orchestrator.orchestrator import Orchestrator
    from backend.evidence.builder import EvidenceAggregator

    contract = TaskContract(
        task_id="DEMO-TASK-E",
        repository_id="repo-int-1",
        base_commit_or_snapshot="snap-e",
        task_description="Tampered receipt fail-closed test",
        allowed_scope=["main.py"],
        repository_trust="TRUSTED_DEVELOPMENT",
        resource_budget=ResourceBudget(max_iterations=20)
    )

    provider = DeterministicTestProvider()
    orch = Orchestrator("run-demo-e", contract, model_provider=provider)

    # Intercept build_receipt to corrupt receipt_hash before JUDGE phase
    old_build = EvidenceAggregator.build_receipt
    def tampered_build(self, *args, **kwargs):
        real_receipt = old_build(self, *args, **kwargs)
        return real_receipt.model_copy(update={"receipt_hash": "corrupted_invalid_hash_xyz"})
    EvidenceAggregator.build_receipt = tampered_build

    try:
        final_state = orch.run()
    finally:
        EvidenceAggregator.build_receipt = old_build

    # System must fail closed to ABORTED
    assert final_state == RunState.ABORTED
    events = [e["event_type"] for e in orch.state_machine.events.get_events()]
    assert "EVIDENCE_INTEGRITY_FAILURE" in events
    assert final_state != RunState.VERIFIED


def test_diff_endpoint_error_handling():
    """
    Validates diff endpoint error cases (404 for unknown run, etc.)
    """
    resp = client.get("/api/v1/runs/nonexistent-run-id-999/diff")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Run not found"
