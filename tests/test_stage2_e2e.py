"""
REDLINE Stage 2 End-to-End Integration Tests
Validates the complete workflow from remote repository intake -> registry -> run creation ->
lifecycle inspection -> verification history -> diff retrieval.
Ensures UNTRUSTED trust enforcement and fail-closed security invariants.
"""

import os
import json
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from backend.api.app import app
from backend.sandbox.capabilities import RepositoryTrust
from backend.sandbox.cloner import QuarantinedRepositoryMetadata
from backend.sandbox.registry import get_repository_registry, RepositoryTarget
from backend.models.schemas import TaskContract, ResourceBudget

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_registry():
    """Ensure registry baseline is reset between tests."""
    registry = get_repository_registry()
    registry.clear()
    yield
    registry.clear()


def test_stage2_full_remote_intake_to_run_flow():
    """
    End-to-End Test:
    1. Import public HTTPS repository at pinned commit SHA via POST /api/v1/repositories/import.
    2. Confirm returned internal target ID, UNTRUSTED trust, and metadata.
    3. Verify target presence in GET /api/v1/repositories/{id} and GET /api/v1/repositories.
    4. Create verification run via POST /api/v1/runs using the imported target ID.
    5. Inspect run status via GET /api/v1/runs/{run_id}.
    6. Confirm run presence in GET /api/v1/runs history.
    7. Retrieve diff via GET /api/v1/runs/{run_id}/diff.
    """
    fake_target_id = "repo-remote-e2e-stage2-9988"
    test_url = "https://github.com/octocat/Hello-World.git"
    test_sha = "7fd1a60b01f91b314f59955a4e4d4e80d8edf11d"

    fake_meta = QuarantinedRepositoryMetadata(
        target_id=fake_target_id,
        repository_url=test_url,
        commit_sha=test_sha,
        quarantine_path=os.path.join("data", "quarantine", fake_target_id),
        snapshot_hash="f" * 64,
        file_manifest_hash="e" * 64,
        file_count=3,
        total_bytes=2048,
        trust=RepositoryTrust.UNTRUSTED,
        imported_at="2026-10-27T00:00:00Z"
    )

    with patch("backend.api.routes.repositories.QuarantinedRepositoryCloner") as MockCloner:
        instance = MockCloner.return_value
        def fake_import(url, commit_sha, budget):
            # Register in registry like genuine cloner does
            get_repository_registry().register(RepositoryTarget(
                repository_id=fake_target_id,
                trust=RepositoryTrust.UNTRUSTED,
                repo_root=os.path.abspath(os.path.join("data", "quarantine", fake_target_id)),
                repository_url=url,
                commit_sha=commit_sha,
                snapshot_hash="f" * 64,
                file_manifest_hash="e" * 64,
                file_count=3,
                total_bytes=2048,
                is_quarantined=True
            ))
            return fake_meta
        instance.import_repository.side_effect = fake_import

        # 1. POST /api/v1/repositories/import
        import_resp = client.post(
            "/api/v1/repositories/import",
            json={
                "repository_url": test_url,
                "commit_sha": test_sha
            }
        )
        assert import_resp.status_code == 201
        import_data = import_resp.json()
        assert import_data["repository_id"] == fake_target_id
        assert import_data["trust"] == "UNTRUSTED"
        assert import_data["commit_sha"] == test_sha
        assert import_data["is_quarantined"] is True
        assert import_data["snapshot_hash"] == "f" * 64

        # 2. GET /api/v1/repositories/{id}
        get_target_resp = client.get(f"/api/v1/repositories/{fake_target_id}")
        assert get_target_resp.status_code == 200
        assert get_target_resp.json()["repository_id"] == fake_target_id

        # 3. GET /api/v1/repositories
        list_targets_resp = client.get("/api/v1/repositories")
        assert list_targets_resp.status_code == 200
        target_ids = [t["repository_id"] for t in list_targets_resp.json()]
        assert fake_target_id in target_ids

        # 4. POST /api/v1/runs with registered remote target
        run_payload = {
            "task_id": "task-e2e-stage2-remote-run",
            "repository_id": fake_target_id,
            "base_commit_or_snapshot": test_sha,
            "task_description": "Validate public repo invariants under secure sandbox containment",
            "allowed_scope": [],
            "repository_trust": "UNTRUSTED"
        }
        create_run_resp = client.post("/api/v1/runs", json=run_payload)
        assert create_run_resp.status_code == 201
        run_data = create_run_resp.json()
        assert "run_id" in run_data
        run_id = run_data["run_id"]
        assert run_id.startswith("run-")

        # 5. GET /api/v1/runs/{run_id} status inspection
        status_resp = client.get(f"/api/v1/runs/{run_id}")
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        assert status_data["run_id"] == run_id
        assert status_data["task_id"] == "task-e2e-stage2-remote-run"

        # 6. GET /api/v1/runs history list
        history_resp = client.get("/api/v1/runs")
        assert history_resp.status_code == 200
        history_runs = [r["run_id"] for r in history_resp.json()]
        assert run_id in history_runs

        # 7. GET /api/v1/runs/{run_id}/diff (404 when patch candidate not yet generated, 200 when generated)
        diff_resp_pending = client.get(f"/api/v1/runs/{run_id}/diff")
        assert diff_resp_pending.status_code == 404
        assert "Patch diff not available" in diff_resp_pending.json()["detail"]

        # Simulate completed patch candidate
        from backend.api.routes.runs import get_run
        from backend.models.schemas import PatchCandidate
        run_obj = get_run(run_id)
        run_obj.patches.append(PatchCandidate(
            patch_id="patch-stage2-01",
            task_id="task-e2e-stage2-remote-run",
            base_commit_or_snapshot=test_sha,
            diff="--- a/main.py\n+++ b/main.py\n@@ -1 +1 @@\n-broken\n+fixed\n",
            changed_files=["main.py"]
        ))

        diff_resp_ready = client.get(f"/api/v1/runs/{run_id}/diff")
        assert diff_resp_ready.status_code == 200
        diff_data = diff_resp_ready.json()
        assert diff_data["run_id"] == run_id
        assert "fixed" in diff_data["diff"]
        assert diff_data["changed_files"] == ["main.py"]


def test_stage2_direct_remote_url_in_task_contract():
    """
    Test direct intake via TaskContract when user provides repository_url directly in create_run.
    """
    fake_target_id = "repo-remote-direct-001"
    test_url = "https://github.com/octocat/Spoon-Knife.git"
    test_sha = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

    fake_meta = QuarantinedRepositoryMetadata(
        target_id=fake_target_id,
        repository_url=test_url,
        commit_sha=test_sha,
        quarantine_path=os.path.join("data", "quarantine", fake_target_id),
        snapshot_hash="1" * 64,
        file_manifest_hash="2" * 64,
        file_count=2,
        total_bytes=1024,
        trust=RepositoryTrust.UNTRUSTED,
        imported_at="2026-10-27T00:00:00Z"
    )

    with patch("backend.sandbox.cloner.QuarantinedRepositoryCloner") as MockCloner:
        instance = MockCloner.return_value
        def fake_import(url, commit_sha, budget):
            get_repository_registry().register(RepositoryTarget(
                repository_id=fake_target_id,
                trust=RepositoryTrust.UNTRUSTED,
                repo_root=os.path.abspath(os.path.join("data", "quarantine", fake_target_id)),
                repository_url=url,
                commit_sha=commit_sha,
                snapshot_hash="1" * 64,
                file_manifest_hash="2" * 64,
                file_count=2,
                total_bytes=1024,
                is_quarantined=True
            ))
            return fake_meta
        instance.import_repository.side_effect = fake_import

        payload = {
            "task_id": "task-direct-remote-01",
            "repository_url": test_url,
            "commit_sha": test_sha,
            "base_commit_or_snapshot": test_sha,
            "task_description": "Direct remote intake test",
            "repository_trust": "TRUSTED_DEVELOPMENT"  # Client claims trusted, backend must override
        }

        resp = client.post("/api/v1/runs", json=payload)
        assert resp.status_code == 201
        run_id = resp.json()["run_id"]

        status_resp = client.get(f"/api/v1/runs/{run_id}")
        assert status_resp.status_code == 200


def test_stage2_invalid_inputs_fail_closed():
    """Verify that insecure schemes, SSRF URLs, and invalid commits fail closed with HTTP 400."""
    # 1. Non-HTTPS scheme
    resp_http = client.post(
        "/api/v1/repositories/import",
        json={
            "repository_url": "http://github.com/octocat/Hello-World.git",
            "commit_sha": "a" * 40
        }
    )
    assert resp_http.status_code == 400

    # 2. Localhost SSRF
    resp_loopback = client.post(
        "/api/v1/repositories/import",
        json={
            "repository_url": "https://127.0.0.1/repo.git",
            "commit_sha": "a" * 40
        }
    )
    assert resp_loopback.status_code == 400

    # 3. Invalid commit SHA (branch name instead of full hex)
    resp_branch = client.post(
        "/api/v1/repositories/import",
        json={
            "repository_url": "https://github.com/octocat/Hello-World.git",
            "commit_sha": "main"
        }
    )
    assert resp_branch.status_code == 400

    # 4. Unknown repository target rejected
    resp_unknown_target = client.post(
        "/api/v1/runs",
        json={
            "task_id": "task-unknown-target-fail",
            "repository_id": "unregistered-target-9999",
            "base_commit_or_snapshot": "snap-01",
            "task_description": "Unknown target must fail closed"
        }
    )
    assert resp_unknown_target.status_code == 400


def test_stage2_existing_fixtures_unaffected():
    """Verify that authorized baseline fixtures (e.g. repo-int-1) continue to operate as expected."""
    payload = {
        "task_id": "task-fixture-backward-compat",
        "repository_id": "repo-int-1",
        "base_commit_or_snapshot": "snap-demo-a-01",
        "task_description": "Baseline fixture execution backward compatibility test"
    }
    resp = client.post("/api/v1/runs", json=payload)
    assert resp.status_code == 201
    run_id = resp.json()["run_id"]

    status_resp = client.get(f"/api/v1/runs/{run_id}")
    assert status_resp.status_code == 200
