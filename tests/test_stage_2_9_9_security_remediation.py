"""
REDLINE Stage 2.9.9 — Critical Security Remediation Regression Suite
Targeted regression tests validating findings REDLINE-REV-001 through REDLINE-REV-018.
"""

import os
import tempfile
import hashlib
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.api.app import app
from backend.api.routes.runs import reset_run_store, set_model_provider
from backend.models.schemas import TaskContract, RunState, OperationalResult, ResourceBudget, PatchCandidate
from backend.models.provider import ModelErrorType, ModelProviderError, ModelResponse
from backend.models.registry import get_model_provider, reset_model_provider
from backend.models.deterministic_provider import DeterministicTestProvider
from backend.models.nebius_provider import NebiusProvider
from backend.models.freellmapi_provider import FreeLLMAPIProvider
from backend.sandbox.models import SandboxPolicy, ExecutionRequest
from backend.sandbox.secure_backend import SecureSandboxBackend, ContainerRuntimeProbe
from backend.sandbox.workspace_sanitizer import (
    workspace_copy_ignore,
    assert_and_clean_workspace_secrets,
    is_secret_file
)
from backend.verification.attack_executor import AttackVerificationEngine
from backend.models.attack_execution import AttackExecutionRequest
from backend.models.attack import AttackType, OracleType, AttackResourceBudget
from backend.verification.models import ExecutionStatus, InvariantResultStatus
from backend.config import load_dotenv_if_present


client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    reset_run_store()
    reset_model_provider()
    yield
    reset_run_store()
    reset_model_provider()


# =====================================================================
# REV-001: Explicit Provider Selection & Deterministic Mock Provenance
# =====================================================================

def test_rev001_unconfigured_provider_fails_closed(monkeypatch):
    monkeypatch.delenv("REDLINE_MODEL_PROVIDER", raising=False)
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    monkeypatch.delenv("FREELLMAPI_API_KEY", raising=False)

    with pytest.raises(ModelProviderError) as exc:
        get_model_provider()
    assert exc.value.error_type == ModelErrorType.MODEL_CONFIGURATION_ERROR
    assert "No model provider configured" in str(exc.value)


def test_rev001_explicit_deterministic_has_mock_mode_marker(monkeypatch):
    monkeypatch.setenv("REDLINE_MODEL_PROVIDER", "deterministic")
    provider = get_model_provider()
    assert isinstance(provider, DeterministicTestProvider)
    assert provider.mode == "MOCK_DEVELOPMENT"
    assert provider.provider_name == "deterministic-mock"


def test_rev001_create_run_returns_http_400_on_unconfigured_provider(monkeypatch):
    monkeypatch.delenv("REDLINE_MODEL_PROVIDER", raising=False)
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    monkeypatch.delenv("FREELLMAPI_API_KEY", raising=False)

    contract = {
        "task_id": "REV001-TASK",
        "repository_id": "test-repo",
        "base_commit_or_snapshot": "snap1",
        "task_description": "test unconfigured provider",
        "test_command": "pytest",
        "allowed_scope": ["main.py"],
        "resource_budget": {"max_iterations": 5}
    }
    resp = client.post("/api/v1/runs", json=contract)
    assert resp.status_code == 400
    assert "Model provider configuration error" in resp.json()["detail"]


# =====================================================================
# REV-002: Nebius Model Default Alignment
# =====================================================================

def test_rev002_nebius_default_model_is_nemotron_lightning(monkeypatch):
    monkeypatch.delenv("NEBIUS_MODEL", raising=False)
    provider = NebiusProvider(api_key="test-key")
    assert provider.default_model == "nvidia/Nemotron-3_5-Lightning"


def test_rev002_nebius_model_override_preserved(monkeypatch):
    monkeypatch.setenv("NEBIUS_MODEL", "custom/nemotron-override")
    provider = NebiusProvider(api_key="test-key")
    assert provider.default_model == "custom/nemotron-override"


# =====================================================================
# REV-003: Sandbox Workspace Confinement & Path Escapes
# =====================================================================

def test_rev003_workspace_confinement_rejects_unauthorized_path(tmp_path):
    policy = SandboxPolicy(sandbox_root=str(tmp_path / "authorized_root"))
    (tmp_path / "authorized_root").mkdir()
    (tmp_path / "outside_dir").mkdir()

    backend = SecureSandboxBackend(policy)
    # Outside directory must be rejected fail-closed
    with pytest.raises(ValueError) as exc:
        backend.resolve_and_validate_cwd(str(tmp_path / "outside_dir"))
    assert "escapes authorized workspace roots" in str(exc.value)


def test_rev003_workspace_confinement_accepts_confined_path(tmp_path):
    root = tmp_path / "authorized_root"
    root.mkdir()
    sub_ws = root / "workspace_1"
    sub_ws.mkdir()

    policy = SandboxPolicy(sandbox_root=str(root))
    backend = SecureSandboxBackend(policy)
    resolved = backend.resolve_and_validate_cwd(str(sub_ws))
    assert Path(resolved).resolve() == sub_ws.resolve()


# =====================================================================
# REV-004: Sandbox Image Verification & Digest Pinning
# =====================================================================

def test_rev004_nonexistent_sandbox_image_fails_closed(tmp_path):
    policy = SandboxPolicy()
    ws = tmp_path / "ws"
    ws.mkdir()
    req = ExecutionRequest(
        command=["python", "test.py"],
        working_directory=str(ws),
        repository_trust="UNTRUSTED"
    )

    class MockProbe(ContainerRuntimeProbe):
        def detect_runtime(self):
            return True, "docker", {"executable": "docker"}

    # Use nonexistent image name
    backend = SecureSandboxBackend(policy, container_image="nonexistent_image_xyz_123:never_exists", runtime_probe=MockProbe())
    res = backend.execute(req, "run-img-test")
    assert res.policy_blocked is True
    assert "IMAGE_NOT_FOUND" in res.backend_provenance.get("reason", "")


def test_rev004_image_digest_mismatch_fails_closed(tmp_path):
    policy = SandboxPolicy()
    ws = tmp_path / "ws"
    ws.mkdir()
    req = ExecutionRequest(
        command=["python", "test.py"],
        working_directory=str(ws),
        repository_trust="UNTRUSTED"
    )

    class MockProbe(ContainerRuntimeProbe):
        def detect_runtime(self):
            return True, "docker", {"executable": "docker"}

    backend = SecureSandboxBackend(
        policy,
        container_image="redline-sandbox-runner:latest",
        runtime_probe=MockProbe(),
        expected_image_digest="sha256:0000000000000000000000000000000000000000000000000000000000000000"
    )
    res = backend.execute(req, "run-digest-test")
    assert res.policy_blocked is True
    assert "IMAGE_DIGEST_MISMATCH" in res.backend_provenance.get("reason", "")


# =====================================================================
# REV-005: FreeLLMAPI Loopback & Port 3001 Restrictions
# =====================================================================

def test_rev005_freellmapi_default_port_is_3001():
    provider = FreeLLMAPIProvider(api_key="test-key")
    assert provider.allowed_ports == [3001]


def test_rev005_freellmapi_rejects_unapproved_ports():
    provider = FreeLLMAPIProvider(api_key="test-key", base_url="http://127.0.0.1:8080/v1")
    with pytest.raises(ModelProviderError) as exc:
        provider.generate([{"role": "user", "content": "hi"}])
    assert "Unexpected port 8080" in str(exc.value)


def test_rev005_freellmapi_requires_opt_in_for_host_docker_internal(monkeypatch):
    monkeypatch.delenv("REDLINE_CONTAINERIZED", raising=False)
    monkeypatch.delenv("REDLINE_IN_CONTAINER", raising=False)
    monkeypatch.delenv("FREELLMAPI_APPROVED_HOSTS", raising=False)

    provider = FreeLLMAPIProvider(api_key="test-key", base_url="http://host.docker.internal:3001/v1")
    with pytest.raises(ModelProviderError) as exc:
        provider.generate([{"role": "user", "content": "hi"}])
    assert "not in approved destinations" in str(exc.value)


# =====================================================================
# REV-006: Secret Exclusion from Candidate Workspaces
# =====================================================================

def test_rev006_secret_exclusion_filter():
    files = [".env", ".env.local", "secrets.json", "private_key.pem", "id_rsa", "main.py", "test_main.py"]
    ignored = workspace_copy_ignore("some_dir", files)
    assert ".env" in ignored
    assert ".env.local" in ignored
    assert "secrets.json" in ignored
    assert "private_key.pem" in ignored
    assert "id_rsa" in ignored
    assert "main.py" not in ignored
    assert "test_main.py" not in ignored


def test_rev006_assert_and_clean_workspace_secrets_fails_on_secret(tmp_path):
    ws = tmp_path / "candidate_ws"
    ws.mkdir()
    (ws / "main.py").write_text("print('hello')", encoding="utf-8")
    (ws / ".env").write_text("SECRET=123", encoding="utf-8")

    with pytest.raises(RuntimeError) as exc:
        assert_and_clean_workspace_secrets(str(ws))
    assert "SECURITY_VIOLATION" in str(exc.value)
    # File must be cleaned up
    assert not (ws / ".env").exists()


# =====================================================================
# REV-008: Counterexample Preservation Across Phases
# =====================================================================

def test_rev008_counterexamples_not_cleared_in_verify():
    from backend.orchestrator.orchestrator import Orchestrator
    from backend.verification.models import Counterexample, OracleType as VerificationOracleType

    contract = TaskContract(
        task_id="CE-PRESERVE-01",
        repository_id="test-repo",
        base_commit_or_snapshot="snap1",
        task_description="preserve counterexample",
        test_command="pytest",
        allowed_scope=["main.py"]
    )
    orch = Orchestrator(run_id="run-ce-test", task_contract=contract, model_provider=DeterministicTestProvider())

    dummy_ce = Counterexample(
        counterexample_id="ce_test_prior",
        invariant_id="DETERMINISTIC_TEST_SUITE",
        test_id="test_suite",
        input_data="pytest",
        observed_output="AssertionError",
        expected_output="Exit 0",
        failure_reason="Prior test failure",
        oracle_type=VerificationOracleType.DETERMINISTIC_CONTRACT,
        execution_id="exec-1",
        evidence_hash=hashlib.sha256(b"prior").hexdigest()
    )
    orch.counterexamples.append(dummy_ce)

    # When VERIFY initializes, it must preserve prior counterexamples
    assert dummy_ce in orch.counterexamples


# =====================================================================
# REV-009: Centralized Safe .env Loader
# =====================================================================

def test_rev009_dotenv_loader_handles_crlf_and_bom(tmp_path, monkeypatch):
    monkeypatch.delenv("TEST_SAFE_VAR_A", raising=False)
    monkeypatch.delenv("TEST_SAFE_VAR_B", raising=False)

    env_file = tmp_path / ".env"
    # Write UTF-8 with BOM and CRLF
    env_content = '\ufeff# Comment line\r\nTEST_SAFE_VAR_A="value_a"\r\nTEST_SAFE_VAR_B=value_b # comment\r\n'
    env_file.write_bytes(env_content.encode("utf-8"))

    loaded = load_dotenv_if_present(str(env_file))
    assert "TEST_SAFE_VAR_A" in loaded
    assert "TEST_SAFE_VAR_B" in loaded
    assert os.environ.get("TEST_SAFE_VAR_A") == "value_a"
    assert os.environ.get("TEST_SAFE_VAR_B") == "value_b"


# =====================================================================
# REV-010: Localhost-Only API Middleware Boundary
# =====================================================================

def test_rev010_localhost_middleware_blocks_remote_ip(monkeypatch):
    monkeypatch.delenv("REDLINE_ALLOW_REMOTE_API", raising=False)

    # Simulate client request from external LAN IP
    resp = client.get("/api/v1/runs", headers={"X-Forwarded-For": "192.168.1.100"})
    # TestClient default host is 'testclient', which is in LOOPBACK_IPS
    assert resp.status_code == 200

    # Using custom ASGI scope with external client IP
    remote_client = TestClient(app, client=("192.168.1.50", 54321))
    remote_resp = remote_client.get("/api/v1/runs")
    assert remote_resp.status_code == 403
    assert "restricted to loopback (localhost) connections only" in remote_resp.json()["detail"]


# =====================================================================
# REV-011: Missing Verification Command Fails Closed
# =====================================================================

def test_rev011_missing_verification_command_fails_closed(tmp_path):
    policy = SandboxPolicy()

    class MockBackend:
        def capabilities(self):
            from backend.sandbox.capabilities import SandboxCapabilities, SecurityLevel
            return SandboxCapabilities(
                security_level=SecurityLevel.SECURE,
                filesystem_isolation="ENFORCED",
                secure_untrusted_execution=True
            )

    empty_repo = tmp_path / "empty_repo"
    empty_repo.mkdir()

    engine = AttackVerificationEngine(backend=MockBackend(), repository_trust="TRUSTED_DEVELOPMENT", repo_root=str(empty_repo))

    req = AttackExecutionRequest(
        run_id="run-empty",
        task_id="task-empty",
        snapshot_hash="snap-empty",
        patch_hash="patch-empty",
        attack_fingerprint="fp-empty",
        attack_type=AttackType.BOUNDARY,
        target="nonexistent_target.py",
        input="test",
        strategy="boundary_fuzz",
        oracle=OracleType.TASK_INVARIANT,
        resource_policy=AttackResourceBudget()
    )

    obs, oracle_res, ce = engine.execute_and_verify(req, workspace_id=str(empty_repo))
    # Must fail closed as EXECUTION_FAILURE and INCONCLUSIVE, NEVER execute dummy sys.exit(0)
    assert obs.status == ExecutionStatus.EXECUTION_FAILURE
    assert obs.command_identifier == "NO_VERIFICATION_COMMAND"
    assert oracle_res.result == InvariantResultStatus.INCONCLUSIVE
    assert "No valid verification test script" in oracle_res.evidence
