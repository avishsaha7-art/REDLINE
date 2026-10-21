"""
API Integration Tests for Benchmark Endpoints.

Validates:
1. Benchmark run creation (POST /api/v1/benchmark/runs).
2. Run state querying (GET /api/v1/benchmark/runs/{run_id}).
3. Runner start endpoint (POST /api/v1/benchmark/runs/{run_id}/start).
4. Run cancellation endpoint (POST /api/v1/benchmark/runs/{run_id}/cancel).
5. Run report retrieval in JSON and Markdown formats.
6. Comparative analysis endpoint (POST /api/v1/benchmark/compare).
"""

import pytest
from fastapi.testclient import TestClient
from backend.api.app import app
from backend.benchmark.models import BenchmarkArmType, BenchmarkVerdict, TaskEvaluationResult
from backend.benchmark.storage import get_benchmark_repository


@pytest.fixture
def client():
    return TestClient(app)


def test_api_create_benchmark_run(client):
    """POST /api/v1/benchmark/runs creates a new benchmark run."""
    payload = {
        "arm_type": "SYNTHETIC",
        "tasks_selected": ["SEC-BENCH-001"],
        "strict_working_tree": True,
    }
    resp = client.post("/api/v1/benchmark/runs", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["run_id"].startswith("bench_")
    assert data["state"] == "CREATED"
    assert data["config"]["arm_type"] == "SYNTHETIC"
    assert data["config"]["tasks_selected"] == ["SEC-BENCH-001"]


def test_api_get_benchmark_run(client):
    """GET /api/v1/benchmark/runs/{run_id} retrieves run record."""
    create_resp = client.post("/api/v1/benchmark/runs", json={"arm_type": "SYNTHETIC"})
    run_id = create_resp.json()["run_id"]

    get_resp = client.get(f"/api/v1/benchmark/runs/{run_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["run_id"] == run_id


def test_api_cancel_benchmark_run(client):
    """POST /api/v1/benchmark/runs/{run_id}/cancel cancels an active run."""
    create_resp = client.post("/api/v1/benchmark/runs", json={"arm_type": "SYNTHETIC"})
    run_id = create_resp.json()["run_id"]

    cancel_resp = client.post(f"/api/v1/benchmark/runs/{run_id}/cancel")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["state"] == "CANCELLED"


def test_api_start_benchmark_run_fails_closed_without_container_runtime(client):
    """
    POST /api/v1/benchmark/runs/{run_id}/start on this host fails closed to
    OPERATIONAL_FAILURE because Docker/Podman is not running.
    """
    create_resp = client.post("/api/v1/benchmark/runs", json={"arm_type": "ARM_A_REDLINE"})
    run_id = create_resp.json()["run_id"]

    start_resp = client.post(f"/api/v1/benchmark/runs/{run_id}/start")
    assert start_resp.status_code == 200
    data = start_resp.json()
    # Must have failed closed at CAPABILITY_CHECK without running candidate code
    assert data["state"] == "OPERATIONAL_FAILURE"
    assert "CAPABILITY_GATE_FAILED" in (data["error_message"] or "")


def test_api_get_benchmark_report_json_and_markdown(client):
    """GET /api/v1/benchmark/runs/{run_id}/report returns valid JSON and Markdown."""
    create_resp = client.post("/api/v1/benchmark/runs", json={"arm_type": "SYNTHETIC"})
    run_id = create_resp.json()["run_id"]

    # Seed a task result
    repo = get_benchmark_repository()
    repo.record_task_result(
        run_id,
        TaskEvaluationResult(
            task_id="SEC-BENCH-001",
            arm="SYNTHETIC",
            verdict=BenchmarkVerdict.VERIFIED,
            vulnerability_neutralized=True,
            secure_acceptance_passed=True,
            regression_passed=True,
        )
    )

    # JSON report
    resp_json = client.get(f"/api/v1/benchmark/runs/{run_id}/report?format=json")
    assert resp_json.status_code == 200
    assert resp_json.json()["run_id"] == run_id
    assert resp_json.json()["dataset_name"] == "REDLINE-Held-Out-Security-Benchmark"

    # Markdown report
    resp_md = client.get(f"/api/v1/benchmark/runs/{run_id}/report?format=markdown")
    assert resp_md.status_code == 200
    assert resp_md.headers["content-type"].startswith("text/markdown")
    assert f"# REDLINE Benchmark Run Report: `{run_id}`" in resp_md.text


def test_api_compare_benchmark_runs(client):
    """POST /api/v1/benchmark/compare generates comparative summary."""
    r1 = client.post("/api/v1/benchmark/runs", json={"arm_type": "SYNTHETIC"}).json()["run_id"]
    r2 = client.post("/api/v1/benchmark/runs", json={"arm_type": "SYNTHETIC"}).json()["run_id"]

    resp = client.post("/api/v1/benchmark/compare", json={"run_ids": [r1, r2]})
    assert resp.status_code == 200
    data = resp.json()
    assert "arm_metrics" in data
    assert "head_to_head_tasks" in data
    assert "statistical_limitation_disclaimer" in data
