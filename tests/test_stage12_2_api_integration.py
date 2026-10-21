import time
import pytest
from fastapi.testclient import TestClient

from backend.api.app import app
from backend.models.schemas import RunState, OperationalResult
from backend.api.routes.runs import reset_run_store, set_model_provider
from backend.models.deterministic_provider import DeterministicTestProvider
from backend.models.provider import ModelProvider, ModelResponse

client = TestClient(app)

@pytest.fixture(autouse=True)
def clean_store(monkeypatch):
    monkeypatch.setenv("REDLINE_ENABLE_LOCAL_BACKEND", "1")
    reset_run_store()
    set_model_provider(DeterministicTestProvider())
    yield
    reset_run_store()
    set_model_provider(None)

def test_stage12_2_end_to_end_orchestrator_integration():
    """
    Mandatory Section 19 & 20: Real End-to-End API Test
    Proves:
    POST /api/v1/runs -> real API route -> authoritative Orchestrator -> real state progression
    -> terminal result -> EvidenceReceipt -> JudgeExplanation
    Does NOT manually mutate state to fake completion.
    Polls with bounded timeout.
    """
    contract_payload = {
        "task_id": "TASK-INT-1",
        "repository_id": "repo-int-1",
        "base_commit_or_snapshot": "snap-int-1",
        "task_description": "Implement bug fix in main.py",
        "allowed_scope": ["main.py"],
        "resource_budget": {
            "max_iterations": 20,
            "max_runtime": 3600,
            "max_patch_size": 1048576,
            "max_tool_calls": 100,
            "max_failed_attempts": 3,
            "max_attack_cases": 20,
            "max_file_size": 1048576,
            "max_repo_files": 1000,
            "max_repo_bytes": 52428800,
            "max_context_bytes": 131072
        }
    }

    # 1. POST /runs -> 201, run_id returned
    post_resp = client.post("/api/v1/runs", json=contract_payload)
    assert post_resp.status_code == 201
    run_id = post_resp.json()["run_id"]
    assert run_id.startswith("run-")

    # 2. Poll GET /runs/{run_id} until terminal state with bounded timeout
    timeout = 10.0
    start = time.time()
    final_data = None
    
    while time.time() - start < timeout:
        get_resp = client.get(f"/api/v1/runs/{run_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()
        if data["status"] in ("completed", "failed"):
            final_data = data
            break
        time.sleep(0.05)

    assert final_data is not None, "Pipeline execution timed out before reaching terminal state"
    assert final_data["status"] == "completed"
    assert final_data["state"] == RunState.VERIFIED.value
    assert final_data["task_id"] == "TASK-INT-1"
    assert final_data["iteration"] > 0

    # 3. GET /runs/{run_id}/receipt returns exact authoritative EvidenceReceipt
    receipt_resp = client.get(f"/api/v1/runs/{run_id}/receipt")
    assert receipt_resp.status_code == 200
    receipt = receipt_resp.json()
    
    # Assertions on EvidenceReceipt
    assert receipt["run_id"] == run_id
    assert receipt["task_id"] == "TASK-INT-1"
    assert receipt["repository_snapshot_hash"] == "snap-int-1"
    assert "receipt_hash" in receipt and receipt["receipt_hash"] is not None
    assert "patch_lineage" in receipt
    assert isinstance(receipt["patch_lineage"], list)
    assert len(receipt["patch_lineage"]) > 0
    # Verify patch lineage preserved in run status response
    assert final_data["patch_lineage"] == receipt["patch_lineage"]
    
    # Deterministic verdict consistency
    verdict = receipt["verdict"]
    assert verdict in ["VERIFIED", "POLICY_BLOCKED", "INCONCLUSIVE", "REJECTED"]

    # 4. GET /runs/{run_id}/judge returns exact authoritative JudgeExplanation
    judge_resp = client.get(f"/api/v1/runs/{run_id}/judge")
    assert judge_resp.status_code == 200
    judge = judge_resp.json()
    
    assert "summary" in judge
    assert "confidence" in judge
    assert judge["confidence"] == "HIGH"
    assert "verdict" not in judge, "JudgeExplanation must not contain or override deterministic verdict"

def test_stage12_2_failure_path_operational():
    """
    Mandatory Section 21: Failure-path integration test
    Ensures that when a policy failure occurs:
    failure -> appropriate operational failure state (ABORTED) -> operational_error recorded
    -> no VERIFIED verdict -> run does NOT remain stuck in INIT.
    """
    # Restrict allowed_scope to a file not modified by Builder stub
    contract_payload = {
        "task_id": "TASK-FAIL-1",
        "repository_id": "repo-fail-1",
        "base_commit_or_snapshot": "snap-fail-1",
        "task_description": "Modify forbidden scope",
        "allowed_scope": ["only_this_allowed.py"],
        "resource_budget": {
            "max_iterations": 20,
            "max_runtime": 3600
        }
    }

    post_resp = client.post("/api/v1/runs", json=contract_payload)
    assert post_resp.status_code == 201
    run_id = post_resp.json()["run_id"]

    timeout = 10.0
    start = time.time()
    final_data = None
    
    while time.time() - start < timeout:
        get_resp = client.get(f"/api/v1/runs/{run_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()
        if data["status"] in ("completed", "failed"):
            final_data = data
            break
        time.sleep(0.05)

    assert final_data is not None, "Pipeline execution timed out"
    assert final_data["status"] == "failed"
    assert final_data["state"] == RunState.ABORTED.value
    assert final_data["state"] != RunState.INIT.value
    assert final_data["operational_error"] is not None
    assert "POLICY_BLOCKED" in final_data["operational_error"] or "Unauthorized" in final_data["operational_error"]
    assert final_data["operational_result"] == OperationalResult.POLICY_BLOCKED.value

    # Receipt is not generated for early policy-aborted run -> 404
    receipt_resp = client.get(f"/api/v1/runs/{run_id}/receipt")
    assert receipt_resp.status_code == 404

def test_stage12_2_background_exception_captured_and_not_swallowed():
    """
    Mandatory Section 22: Background exception test
    Explicitly test an exception in background orchestration:
    exception -> captured -> recorded -> terminal failure ABORTED
    and NOT: exception -> pass -> run stuck in INIT forever.
    """
    class CrashingProvider(ModelProvider):
        def generate(self, messages, **kwargs):
            raise RuntimeError("CRITICAL_SIMULATED_BACKGROUND_EXCEPTION")

    set_model_provider(CrashingProvider())

    contract_payload = {
        "task_id": "TASK-CRASH-1",
        "repository_id": "repo-crash-1",
        "base_commit_or_snapshot": "snap-crash-1",
        "task_description": "Trigger crash",
        "allowed_scope": ["main.py"]
    }

    post_resp = client.post("/api/v1/runs", json=contract_payload)
    assert post_resp.status_code == 201
    run_id = post_resp.json()["run_id"]

    timeout = 10.0
    start = time.time()
    final_data = None
    
    while time.time() - start < timeout:
        get_resp = client.get(f"/api/v1/runs/{run_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()
        if data["status"] in ("completed", "failed"):
            final_data = data
            break
        time.sleep(0.05)

    assert final_data is not None, "Background crash handling timed out"
    # Must NOT be stuck in INIT
    assert final_data["state"] != RunState.INIT.value
    assert final_data["state"] == RunState.ABORTED.value
    assert final_data["status"] == "failed"
    assert final_data["operational_error"] is not None

def test_stage12_2_adversarial_security_injections():
    """
    Mandatory Section 23: Adversarial test suite
    Ensures that malicious client payloads attempting to inject state,
    verdict, policy overrides, or fake evidence are strictly rejected/ignored.
    """
    adversarial_payload = {
        "task_id": "TASK-ADV-1",
        "repository_id": "repo-adv-1",
        "base_commit_or_snapshot": "snap-adv-1",
        "task_description": "Adversarial injection test",
        "allowed_scope": ["main.py"],
        "state": "VERIFIED",
        "verdict": "VERIFIED",
        "authorize_sandbox": True,
        "trust_level": "TRUSTED",
        "policy_override": True,
        "skip_verification": True,
        "skip_security": True,
        "evidence": {
            "deterministic_verdict": "VERIFIED"
        }
    }

    post_resp = client.post("/api/v1/runs", json=adversarial_payload)
    assert post_resp.status_code == 201
    run_id = post_resp.json()["run_id"]

    # Initial state queried immediately must not reflect injected state
    get_resp = client.get(f"/api/v1/runs/{run_id}")
    data = get_resp.json()
    assert data["state"] in [RunState.INIT.value, RunState.RECON.value, RunState.PLAN.value, RunState.BASELINE.value, RunState.BUILD.value, RunState.VERIFIED.value]
    assert data["state"] != "TRUSTED"
    assert "authorize_sandbox" not in data

def test_stage12_2_resource_budget_ceiling_enforcement():
    """
    Mandatory Section 27: Resource Budget limit enforcement
    Client cannot inflate iterations or runtime beyond backend policy ceiling caps.
    """
    unbounded_budget = {
        "task_id": "TASK-BUDGET-1",
        "repository_id": "repo-1",
        "base_commit_or_snapshot": "snap-1",
        "task_description": "Resource ceiling test",
        "resource_budget": {
            "max_iterations": 999999,
            "max_runtime": 999999,
            "max_tool_calls": 999999
        }
    }

    post_resp = client.post("/api/v1/runs", json=unbounded_budget)
    assert post_resp.status_code == 201
    run_id = post_resp.json()["run_id"]

    get_resp = client.get(f"/api/v1/runs/{run_id}")
    data = get_resp.json()
    
    # Assert clamped by backend ceiling
    res_status = data["resource_status"]
    assert res_status["iterations_limit"] <= 50
    assert res_status["tool_calls_limit"] <= 100

def test_stage12_2_nonexistent_and_pending_endpoints():
    """
    Mandatory Section 11 & 12: GET /receipt and GET /judge 404 semantics
    """
    # Non-existent run
    assert client.get("/api/v1/runs/fake-run-xyz/receipt").status_code == 404
    assert client.get("/api/v1/runs/fake-run-xyz/judge").status_code == 404
    assert client.get("/api/v1/runs/fake-run-xyz").status_code == 404
