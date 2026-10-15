import pytest
from fastapi.testclient import TestClient
from backend.api.app import app
from backend.models.schemas import RunState

client = TestClient(app)

valid_task_contract = {
    "task_id": "test-task",
    "repository_id": "test-repo",
    "base_commit_or_snapshot": "test-hash",
    "task_description": "Fix bug",
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

def test_api_create_run_and_get():
    # Test A: POST valid TaskContract -> creates a run
    response = client.post("/api/v1/runs", json=valid_task_contract)
    assert response.status_code == 201
    run_id = response.json()["run_id"]

    # Test D: GET existing run -> backend state returned
    get_response = client.get(f"/api/v1/runs/{run_id}")
    assert get_response.status_code == 200
    data = get_response.json()
    assert data["run_id"] == run_id
    assert data["state"] in [s.value for s in RunState]

def test_api_malformed_task_contract():
    # Test B: POST malformed TaskContract -> rejected
    response = client.post("/api/v1/runs", json={"invalid": "payload"})
    assert response.status_code == 422

def test_api_unknown_run():
    # Test C: GET unknown run -> 404
    response = client.get("/api/v1/runs/fake-run")
    assert response.status_code == 404

def test_adversarial_state_injection():
    # Test G, H, I, J, K: Frontend cannot submit authoritative fields
    adversarial_contract = valid_task_contract.copy()
    adversarial_contract["state"] = "VERIFIED"
    adversarial_contract["verdict"] = "VERIFIED"
    adversarial_contract["authorize_sandbox"] = True
    adversarial_contract["trust_level"] = "TRUSTED"
    adversarial_contract["policy_override"] = True
    adversarial_contract["skip_verification"] = True
    adversarial_contract["skip_security"] = True
    
    # POST ignores these fields and creates run with INIT state
    response = client.post("/api/v1/runs", json=adversarial_contract)
    assert response.status_code == 201
    run_id = response.json()["run_id"]

    get_response = client.get(f"/api/v1/runs/{run_id}")
    data = get_response.json()
    # It must NOT be VERIFIED. It must be strictly controlled by backend.
    assert data["state"] != "VERIFIED"
    assert data["state"] in [s.value for s in RunState]


def test_api_judge_evidence_endpoints():
    response = client.post("/api/v1/runs", json=valid_task_contract)
    run_id = response.json()["run_id"]
    
    # Run doesn't have receipt or judge explanation yet
    receipt_resp = client.get(f"/api/v1/runs/{run_id}/receipt")
    assert receipt_resp.status_code == 404
    
    judge_resp = client.get(f"/api/v1/runs/{run_id}/judge")
    assert judge_resp.status_code == 404

def test_api_credentials_leak():
    # Test L: API does not expose credentials
    response = client.get("/api/v1/runs")
    data = response.json()
    assert isinstance(data, list)
    content = str(data).lower()
    assert "nebius_api_key" not in content
    assert "password" not in content

def test_api_integration():
    # Integration Test
    response = client.post("/api/v1/runs", json=valid_task_contract)
    assert response.status_code == 201
    run_id = response.json()["run_id"]
    
    response = client.get(f"/api/v1/runs/{run_id}")
    assert response.status_code == 200
