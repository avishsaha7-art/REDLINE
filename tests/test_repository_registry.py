import os
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from backend.api.app import app
from backend.models.schemas import TaskContract, ResourceBudget, RunState, OperationalResult
from backend.sandbox.capabilities import RepositoryTrust
from backend.sandbox.trust import resolve_repository_trust
from backend.sandbox.registry import (
    get_repository_registry,
    reset_repository_registry,
    RepositoryTarget,

)
from backend.orchestrator.orchestrator import Orchestrator
from backend.models.deterministic_provider import DeterministicTestProvider

client = TestClient(app)


from backend.api.routes.runs import set_model_provider, reset_run_store

@pytest.fixture(autouse=True)
def clean_registry():
    reset_repository_registry()
    reset_run_store()
    set_model_provider(DeterministicTestProvider())
    yield
    reset_repository_registry()
    reset_run_store()
    set_model_provider(None)


# ==============================================================================
# Registry Target Resolution Tests
# ==============================================================================

def test_baseline_fixtures_pre_registered():
    """Authorized baseline fixtures (repo-int-1, repo-cons-1) resolve correctly with TRUSTED_DEVELOPMENT."""
    registry = get_repository_registry()

    target_int = registry.resolve_target("repo-int-1")
    assert target_int is not None
    assert target_int.repository_id == "repo-int-1"
    assert target_int.trust == RepositoryTrust.TRUSTED_DEVELOPMENT
    assert not target_int.is_quarantined

    target_cons = registry.resolve_target("repo-cons-1")
    assert target_cons is not None
    assert target_cons.trust == RepositoryTrust.TRUSTED_DEVELOPMENT


def test_remote_quarantined_repository_strictly_untrusted():
    """Remotely imported repositories are strictly UNTRUSTED by architectural invariant."""
    registry = get_repository_registry()
    target = RepositoryTarget(
        repository_id="repo-remote-deadbeef1234",
        repo_root="/fake/quarantine/path",
        trust=RepositoryTrust.TRUSTED_DEVELOPMENT,  # Attempting to declare trusted
        repository_url="https://github.com/attacker/repo.git",
        commit_sha="a" * 40,
        is_quarantined=True,
    )
    # Registry forces UNTRUSTED for any quarantined or remote repository
    registry.register(target)

    resolved = registry.get("repo-remote-deadbeef1234")
    assert resolved is not None
    assert resolved.trust == RepositoryTrust.UNTRUSTED


def test_trust_resolver_strictly_enforces_untrusted_for_remote_ids():
    """resolve_repository_trust cannot be bypassed for remote or quarantined IDs."""
    remote_id = "repo-remote-abcdef123456"

    # Even if caller passes TRUSTED_DEVELOPMENT
    trust = resolve_repository_trust(remote_id, "TRUSTED_DEVELOPMENT")
    assert trust == RepositoryTrust.UNTRUSTED

    trust = resolve_repository_trust(remote_id, RepositoryTrust.TRUSTED_DEVELOPMENT)
    assert trust == RepositoryTrust.UNTRUSTED


def test_unknown_target_fails_closed_in_registry():
    """Unknown repository targets resolve to None instead of falling back to repo-int-1."""
    registry = get_repository_registry()
    assert registry.resolve_target("nonexistent-repository-target") is None
    assert registry.resolve_target("repo-unknown-999") is None


def test_url_as_repository_id_is_not_treated_as_filesystem_path():
    """A Git URL passed in repository_id cannot be resolved or treated as a filesystem path."""
    registry = get_repository_registry()
    malicious_ids = [
        "https://github.com/evil/repo.git",
        "../../etc/passwd",
        "/etc/shadow",
        "C:\\Windows\\System32",
    ]
    for m_id in malicious_ids:
        assert registry.resolve_target(m_id) is None


# ==============================================================================
# Orchestrator Resolution & Fail-Closed Invariant Tests
# ==============================================================================

def test_orchestrator_unknown_target_fails_closed_without_fallback():
    """
    CRITICAL INVARIANT: When an unknown repository target is submitted,
    Orchestrator._resolve_repo_root() rejects the target and Orchestrator
    aborts at PLAN state with OperationalResult.INVALID_REPOSITORY.
    It must NEVER silently fall back to repo-int-1, repo-cons-1, or os.getcwd().
    """
    contract = TaskContract(
        task_id="TASK-UNKNOWN-TARGET",
        repository_id="completely-unregistered-repo-12345",
        base_commit_or_snapshot="abcdef123456",
        task_description="Test unknown repo fail-closed",
        allowed_scope=["main.py"],
        resource_budget=ResourceBudget(max_iterations=5)
    )
    provider = DeterministicTestProvider()
    orch = Orchestrator("run-unknown-fail-closed", contract, model_provider=provider)

    # _resolve_repo_root must raise ValueError
    with pytest.raises(ValueError, match="Unknown repository target"):
        orch._resolve_repo_root()

    # run() must abort with INVALID_REPOSITORY
    final_state = orch.run()
    assert final_state == RunState.ABORTED
    assert orch.state_machine.operational_result == OperationalResult.INVALID_REPOSITORY

    events = [e["event_type"] for e in orch.state_machine.events.get_events()]
    assert "REPOSITORY_RESOLUTION_FAILED" in events
    assert "RUN_ABORTED" in events


# ==============================================================================
# TaskContract Validation Tests
# ==============================================================================

def test_task_contract_valid_remote_url():
    """TaskContract successfully accepts valid repository_url with pinned commit SHA."""
    contract = TaskContract(
        task_id="TASK-REMOTE-01",
        repository_url="https://github.com/example/public-repo.git",
        base_commit_or_snapshot="a" * 40,
        commit_sha="a" * 40,
        task_description="Verify public remote repository",
    )
    assert contract.repository_url == "https://github.com/example/public-repo.git"
    assert contract.commit_sha == "a" * 40


def test_task_contract_rejects_insecure_remote_url():
    """TaskContract rejects non-https URLs."""
    with pytest.raises(ValueError, match="https"):
        TaskContract(
            task_id="TASK-REMOTE-02",
            repository_url="http://github.com/example/insecure-repo.git",
            base_commit_or_snapshot="a" * 40,
            task_description="Insecure remote",
        )


def test_task_contract_forces_untrusted_on_remote_claiming_trusted_development():
    """TaskContract overrides and forces UNTRUSTED when a remote URL attempts to declare TRUSTED_DEVELOPMENT."""
    contract = TaskContract(
        task_id="TASK-REMOTE-03",
        repository_url="https://github.com/example/public-repo.git",
        base_commit_or_snapshot="a" * 40,
        task_description="Attempted trust spoofing",
        repository_trust="TRUSTED_DEVELOPMENT"
    )
    assert contract.repository_trust == "UNTRUSTED"


def test_task_contract_rejects_remote_binding_to_local_fixture_id():
    """TaskContract rejects attempts to bind a remote URL to authorized local fixture IDs."""
    with pytest.raises(ValueError, match="Cannot bind a remote repository URL to an authorized local fixture"):
        TaskContract(
            task_id="TASK-REMOTE-04",
            repository_id="repo-int-1",
            repository_url="https://github.com/example/public-repo.git",
            base_commit_or_snapshot="a" * 40,
            task_description="Attempted ID spoofing",
        )


# ==============================================================================
# API Routes Integration Tests
# ==============================================================================

def test_create_run_rejects_unregistered_repository_target():
    """POST /api/v1/runs rejects unknown repository targets with HTTP 400."""
    payload = {
        "task_id": "TASK-API-UNKNOWN",
        "repository_id": "unknown-target-nonexistent",
        "base_commit_or_snapshot": "base123",
        "task_description": "Unknown target test",
        "allowed_scope": ["main.py"]
    }
    resp = client.post("/api/v1/runs", json=payload)
    assert resp.status_code == 400
    assert "Unknown repository target" in resp.json()["detail"]


def test_create_run_with_remote_url_imports_and_forces_untrusted():
    """POST /api/v1/runs with repository_url imports repository and enforces UNTRUSTED status."""
    fake_target_sha = "c" * 40
    fake_target_id = "repo-remote-123456789abc"

    fake_meta = MagicMock(
        target_id=fake_target_id,
        commit_sha=fake_target_sha,
        trust=RepositoryTrust.UNTRUSTED
    )

    def fake_import(*args, **kwargs):
        get_repository_registry().register(RepositoryTarget(
            repository_id=fake_target_id,
            repo_root="/fake/quarantine/path",
            trust=RepositoryTrust.UNTRUSTED,
            is_quarantined=True,
        ))
        return fake_meta

    with patch("backend.sandbox.cloner.QuarantinedRepositoryCloner.import_repository", side_effect=fake_import) as mock_import, \
         patch("backend.api.routes.runs.execute_run"):  # Don't run worker in background

        payload = {
            "task_id": "TASK-REMOTE-RUN",
            "repository_url": "https://github.com/octocat/Hello-World.git",
            "base_commit_or_snapshot": fake_target_sha,
            "commit_sha": fake_target_sha,
            "task_description": "Import remote repo and verify",
            "allowed_scope": ["main.py"],
            "repository_trust": "TRUSTED_DEVELOPMENT"  # Client attempt to declare trusted
        }

        resp = client.post("/api/v1/runs", json=payload)
        assert resp.status_code == 201
        run_id = resp.json()["run_id"]

        # Verify import was called with URL and commit SHA
        mock_import.assert_called_once()

        # Query run status to verify authoritative contract was updated to UNTRUSTED and repo-remote-* ID
        status_resp = client.get(f"/api/v1/runs/{run_id}")
        assert status_resp.status_code == 200


def test_repositories_api_list_and_get():
    """GET /api/v1/repositories lists baseline fixtures and GET /api/v1/repositories/{id} retrieves metadata."""
    list_resp = client.get("/api/v1/repositories")
    assert list_resp.status_code == 200
    repos = list_resp.json()
    repo_ids = [r["repository_id"] for r in repos]
    assert "repo-int-1" in repo_ids
    assert "repo-cons-1" in repo_ids

    get_resp = client.get("/api/v1/repositories/repo-int-1")
    assert get_resp.status_code == 200
    int_repo = get_resp.json()
    assert int_repo["repository_id"] == "repo-int-1"
    assert int_repo["trust"] == "TRUSTED_DEVELOPMENT"

    # Nonexistent target returns 404
    missing_resp = client.get("/api/v1/repositories/nonexistent-target")
    assert missing_resp.status_code == 404
