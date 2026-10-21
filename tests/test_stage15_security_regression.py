import time
import pytest
from fastapi.testclient import TestClient

from backend.api.app import app
from backend.api.routes.runs import reset_run_store, set_model_provider
from backend.models.schemas import TaskContract, RunState, OperationalResult, ResourceBudget
from backend.models.deterministic_provider import DeterministicTestProvider
from backend.sandbox.backend import LocalDevelopmentBackend
from backend.sandbox.models import ExecutionRequest, SandboxPolicy
from backend.sandbox.capabilities import RepositoryTrust
from backend.sandbox.trust import resolve_repository_trust, get_authorized_trusted_repositories
from backend.verification.models import VerificationStatus, ExecutionStatus
from backend.verification.attack_executor import AttackVerificationEngine
from backend.models.attack_execution import AttackExecutionRequest
from backend.models.attack import AttackType, OracleType, AttackResourceBudget

client = TestClient(app)

@pytest.fixture(autouse=True)
def clean_store():
    reset_run_store()
    set_model_provider(DeterministicTestProvider())
    yield
    reset_run_store()
    set_model_provider(None)


def test_untrusted_repo_via_api_reaches_policy_blocked():
    """
    Production boundary test:
    An UNTRUSTED repository submitted through POST /api/v1/runs executed
    via LocalDevelopmentBackend must be blocked with POLICY_BLOCKED.
    The run must abort cleanly without executing untrusted code on host.
    """
    payload = {
        "task_id": "TASK-UNTRUSTED-01",
        "repository_id": "untrusted-external-repo-xyz",
        "base_commit_or_snapshot": "snap-untrusted-01",
        "task_description": "Attempt to verify untrusted external code",
        "allowed_scope": ["main.py"],
        "repository_trust": "UNTRUSTED",
        "resource_budget": {
            "max_iterations": 10
        }
    }

    resp = client.post("/api/v1/runs", json=payload)
    assert resp.status_code == 201
    run_id = resp.json()["run_id"]

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
    assert final_data["status"] == "failed"
    assert final_data["state"] == RunState.ABORTED.value
    assert final_data["operational_result"] == OperationalResult.POLICY_BLOCKED.value
    assert "POLICY_BLOCKED" in (final_data.get("operational_error") or "")

    receipt_resp = client.get(f"/api/v1/runs/{run_id}/receipt")
    assert receipt_resp.status_code == 200
    receipt = receipt_resp.json()
    assert receipt["verdict"] == VerificationStatus.POLICY_BLOCKED.value


def test_caller_self_promotion_attempt_blocked_at_api_boundary():
    """
    Production boundary test:
    A caller or repository must NOT be able to promote itself to trusted
    merely by supplying a request field (e.g. repository_trust='TRUSTED_DEVELOPMENT').
    """
    payload = {
        "task_id": "TASK-SELF-PROMOTE-02",
        "repository_id": "malicious-unauthorized-repo",
        "base_commit_or_snapshot": "snap-malicious",
        "task_description": "Attempted self-promotion to trusted development",
        "allowed_scope": ["main.py"],
        # Malicious caller attempts self-promotion:
        "repository_trust": "TRUSTED_DEVELOPMENT",
        "resource_budget": {
            "max_iterations": 10
        }
    }

    resp = client.post("/api/v1/runs", json=payload)
    assert resp.status_code == 201
    run_id = resp.json()["run_id"]

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
    assert final_data["status"] == "failed"
    assert final_data["state"] == RunState.ABORTED.value
    # Self-promotion was denied; execution was policy-blocked
    assert final_data["operational_result"] == OperationalResult.POLICY_BLOCKED.value
    assert final_data["evidence_receipt"]["verdict"] == VerificationStatus.POLICY_BLOCKED.value


def test_missing_trust_classification_fails_closed_to_untrusted():
    """
    Production boundary test:
    Missing trust classifications must not silently authorize execution.
    An unauthorized repo without repository_trust defaults to UNTRUSTED and blocks.
    """
    payload = {
        "task_id": "TASK-MISSING-TRUST-03",
        "repository_id": "unknown-external-repo",
        "base_commit_or_snapshot": "snap-unknown",
        "task_description": "Missing trust classification test",
        "allowed_scope": ["main.py"],
        # repository_trust omitted
        "resource_budget": {
            "max_iterations": 10
        }
    }

    resp = client.post("/api/v1/runs", json=payload)
    assert resp.status_code == 201
    run_id = resp.json()["run_id"]

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
    assert final_data["status"] == "failed"
    assert final_data["state"] == RunState.ABORTED.value
    assert final_data["operational_result"] == OperationalResult.POLICY_BLOCKED.value
    assert final_data["evidence_receipt"]["verdict"] == VerificationStatus.POLICY_BLOCKED.value


def test_malformed_trust_classification_fails_closed():
    """
    Production boundary test:
    Malformed or unexpected trust classifications (e.g. 'SUPERUSER', empty string, numbers)
    must NOT silently authorize execution.
    """
    malformed_values = ["SUPERUSER", "ADMIN", "ELEVATED", "", "INVALID_TRUST"]

    for val in malformed_values:
        # Test unit resolver directly
        resolved = resolve_repository_trust("repo-int-1", val)
        assert resolved == RepositoryTrust.UNTRUSTED, f"Malformed trust '{val}' was not rejected"

        # Test at production API boundary
        payload = {
            "task_id": f"TASK-MALFORMED-{val[:4]}",
            "repository_id": "repo-int-1",
            "base_commit_or_snapshot": "snap-malformed",
            "task_description": "Malformed trust test",
            "allowed_scope": ["main.py"],
            "repository_trust": val
        }
        resp = client.post("/api/v1/runs", json=payload)
        assert resp.status_code == 201
        run_id = resp.json()["run_id"]

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


def test_local_development_backend_direct_execution_fail_closed():
    """
    Direct sandbox backend boundary:
    LocalDevelopmentBackend must NEVER execute host commands for any
    trust level other than explicitly authorized TRUSTED_DEVELOPMENT.
    """
    backend = LocalDevelopmentBackend(SandboxPolicy())

    test_trusts = ["UNTRUSTED", "", "MALFORMED", "SECURE", None, "ADMIN"]
    for trust in test_trusts:
        req = ExecutionRequest(
            command=["python", "-c", "import sys; sys.exit(0)"],
            working_directory=".",
            repository_trust=str(trust) if trust is not None else ""
        )
        res = backend.execute(req, "test-direct-run")
        assert res.policy_blocked is True
        assert res.exit_code == -1
        assert "POLICY_BLOCKED" in res.stderr
        assert res.stdout == ""


def test_attack_verification_engine_boundary_fail_closed():
    """
    Direct attack executor boundary:
    AttackVerificationEngine must fail closed when repository_trust is not TRUSTED_DEVELOPMENT
    and secure_untrusted_execution is False.
    """
    backend = LocalDevelopmentBackend(SandboxPolicy())
    untrusted_engine = AttackVerificationEngine(backend, repository_trust="UNTRUSTED")

    req = AttackExecutionRequest(
        run_id="run-atk-01",
        task_id="task-atk-01",
        snapshot_hash="snap-01",
        patch_hash="patch-01",
        attack_fingerprint="fp-atk-01",
        attack_type=AttackType.BOUNDARY,
        target="main.py",
        strategy="boundary_overflow",
        input="overflow_data",
        oracle=OracleType.TASK_INVARIANT,
        resource_policy=AttackResourceBudget(max_runtime_ms=1000)
    )

    obs, oracle, ce = untrusted_engine.execute_and_verify(req, "workspace-01")
    assert obs.status == ExecutionStatus.POLICY_BLOCKED
    assert "POLICY_BLOCKED" in obs.stderr_sha256 or obs.stderr_bytes > 0
    assert oracle.result == "INCONCLUSIVE"
    assert ce is None


def test_authorized_trusted_development_repo_executes_successfully(monkeypatch):
    """
    Verifies that explicitly authorized local repositories (e.g. repo-int-1)
    preserve trusted-development execution mode and can reach completion.
    """
    monkeypatch.setenv("REDLINE_ENABLE_LOCAL_BACKEND", "1")
    payload = {
        "task_id": "TASK-TRUSTED-DEV-01",
        "repository_id": "repo-int-1",
        "base_commit_or_snapshot": "snap-trusted-01",
        "task_description": "Legitimate development task in trusted repo",
        "allowed_scope": ["main.py"],
        "repository_trust": "TRUSTED_DEVELOPMENT"
    }

    resp = client.post("/api/v1/runs", json=payload)
    assert resp.status_code == 201
    run_id = resp.json()["run_id"]

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
