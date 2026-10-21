import pytest
import datetime
from backend.sandbox.trust import (
    resolve_repository_trust,
    get_authorized_trusted_repositories,
    is_local_backend_enabled,
    set_local_backend_override,
)
from backend.sandbox.capabilities import RepositoryTrust
from backend.sandbox.factory import get_sandbox_backend
from backend.sandbox.backend import LocalDevelopmentBackend
from backend.sandbox.secure_backend import SecureSandboxBackend, ContainerRuntimeProbe
from backend.sandbox.models import SandboxPolicy, ExecutionRequest
from backend.verification.security_executor import SecurityTestExecutor
from backend.verification.security_models import (
    SecurityTestSpec,
    SecurityTestCategory,
    SecurityTestSeverity,
    SecurityTestStatus,
    AttackExecutionContext,
    SecurityResultClassification,
)
from backend.evidence.builder import EvidenceAggregator
from backend.models.evidence import EvidenceReceipt
from backend.models.schemas import TaskContract, RunState, ResourceBudget
from backend.orchestrator.orchestrator import Orchestrator


def test_generic_and_spoofed_repository_ids_resolve_to_untrusted():
    """Generic, numerical, or spoofed repository IDs must strictly resolve to UNTRUSTED."""
    disallowed_ids = [
        "1", "r1", "R1", "repo-1", "repo-2", "repo1", "repo2",
        "task-repo", "test-repo", "test_repo", "TEST-REPO",
        "admin", "system", "root", "production",
        "", "   ", None
    ]
    for repo_id in disallowed_ids:
        trust = resolve_repository_trust(repo_id)
        assert trust == RepositoryTrust.UNTRUSTED, f"Expected UNTRUSTED for '{repo_id}', got {trust}"


def test_client_supplied_trust_cannot_grant_privileges_on_unauthorized_repo():
    """Client-supplied trust strings cannot elevate an unauthorized repository."""
    unauthorized_ids = ["repo-1", "repo-2", "untrusted-external-repo", "my-repo", "1"]
    for repo_id in unauthorized_ids:
        assert resolve_repository_trust(repo_id, "TRUSTED_DEVELOPMENT") == RepositoryTrust.UNTRUSTED
        assert resolve_repository_trust(repo_id, RepositoryTrust.TRUSTED_DEVELOPMENT) == RepositoryTrust.UNTRUSTED
        assert resolve_repository_trust(repo_id, "trusted_development") == RepositoryTrust.UNTRUSTED


def test_client_supplied_untrusted_downgrades_authorized_repo():
    """If a client specifies UNTRUSTED even on an authorized repo, trust is downgraded."""
    assert resolve_repository_trust("repo-int-1", "UNTRUSTED") == RepositoryTrust.UNTRUSTED
    assert resolve_repository_trust("repo-int-1", RepositoryTrust.UNTRUSTED) == RepositoryTrust.UNTRUSTED


def test_trusted_repo_without_opt_in_does_not_select_local_backend(monkeypatch):
    """
    Authorized repositories require an explicit local backend opt-in (REDLINE_ENABLE_LOCAL_BACKEND=1).
    Without it, get_sandbox_backend must route to SecureSandboxBackend (fail-closed host protection).
    """
    monkeypatch.delenv("REDLINE_ENABLE_LOCAL_BACKEND", raising=False)
    set_local_backend_override(None)
    policy = SandboxPolicy(allowed_commands=["python"])

    backend = get_sandbox_backend(policy, repository_trust=RepositoryTrust.TRUSTED_DEVELOPMENT)
    assert isinstance(backend, SecureSandboxBackend), "Must route to SecureSandboxBackend when opt-in is absent"
    assert not isinstance(backend, LocalDevelopmentBackend)


def test_trusted_repo_with_opt_in_selects_local_backend(monkeypatch):
    """With explicit local backend opt-in, authorized trusted-dev workloads use LocalDevelopmentBackend."""
    monkeypatch.setenv("REDLINE_ENABLE_LOCAL_BACKEND", "1")
    set_local_backend_override(None)
    policy = SandboxPolicy(allowed_commands=["python"])

    backend = get_sandbox_backend(policy, repository_trust=RepositoryTrust.TRUSTED_DEVELOPMENT)
    assert isinstance(backend, LocalDevelopmentBackend)


def test_untrusted_workload_never_receives_local_backend_even_with_opt_in(monkeypatch):
    """
    CRITICAL INVARIANT: Untrusted workloads must NEVER receive LocalDevelopmentBackend,
    even if REDLINE_ENABLE_LOCAL_BACKEND=1 is enabled.
    """
    monkeypatch.setenv("REDLINE_ENABLE_LOCAL_BACKEND", "1")
    set_local_backend_override(None)
    policy = SandboxPolicy(allowed_commands=["python"])

    backend = get_sandbox_backend(policy, repository_trust=RepositoryTrust.UNTRUSTED)
    assert isinstance(backend, SecureSandboxBackend), "Untrusted workload received non-secure backend!"
    assert not isinstance(backend, LocalDevelopmentBackend), "Untrusted workload received LocalDevelopmentBackend!"


def test_runtime_unavailability_fails_closed_without_host_execution():
    """
    When the secure container runtime is unavailable, execution must fail closed
    with an operational error, and must NEVER fall back to host execution.
    """
    policy = SandboxPolicy(allowed_commands=["python"])
    class MockUnavailableProbe:
        def detect_runtime(self):
            return False, "NONE", {"error": "Neither podman nor docker CLI is available in PATH"}

    backend = SecureSandboxBackend(policy=policy, runtime_probe=MockUnavailableProbe())
    req = ExecutionRequest(
        command=["python", "-c", "print('should not run')"],
        working_directory=".",
        repository_trust="UNTRUSTED"
    )

    result = backend.execute(req, "test-run-unavailable")
    assert result.exit_code != 0
    assert "unavailable" in result.stderr.lower() or "not available" in result.stderr.lower()
    assert result.stdout == ""


def test_security_test_executor_defaults_to_untrusted(tmp_path):
    """
    SecurityTestExecutor must default to repository_trust="UNTRUSTED".
    When directed at LocalDevelopmentBackend, untrusted execution requests are blocked.
    """
    policy = SandboxPolicy(allowed_commands=["python"])
    backend = LocalDevelopmentBackend(policy)
    executor = SecurityTestExecutor(backend)
    assert executor.repository_trust == "UNTRUSTED"

    with open(tmp_path / "attack.py", "w") as f:
        f.write("print('attack')\n")

    spec = SecurityTestSpec(
        attack_id="ATTACK_DEF_UNTRUSTED",
        name="Test",
        category=SecurityTestCategory.ISOLATION_ESCAPE,
        description="Verify default untrusted setting",
        severity=SecurityTestSeverity.HIGH,
        preconditions=[],
        input_fixture="attack.py",
        expected_security_invariant="ISO",
        resource_budget=1000,
        clean_state_required=True,
        deterministic=True,
        version="1.0",
        status=SecurityTestStatus.IMPLEMENTED
    )
    ctx = AttackExecutionContext(
        attack_id="ATTACK_DEF_UNTRUSTED",
        run_id="run-def",
        base_snapshot="snap",
        patch_hash="patch",
        execution_id="e-def"
    )

    obs = executor.execute_test(spec, ctx, str(tmp_path))
    assert obs.status == SecurityResultClassification.BLOCKED


def test_security_test_executor_forces_untrusted_for_untrusted_execution_category(tmp_path):
    """UNTRUSTED_EXECUTION attack category must always force trust_level='UNTRUSTED'."""
    policy = SandboxPolicy(allowed_commands=["python"])
    backend = LocalDevelopmentBackend(policy)
    # Even if executor was initialized with TRUSTED_DEVELOPMENT
    executor = SecurityTestExecutor(backend, repository_trust="TRUSTED_DEVELOPMENT")

    with open(tmp_path / "probe.py", "w") as f:
        f.write("print('probe')\n")

    spec = SecurityTestSpec(
        attack_id="UNTRUSTED_EXECUTION",
        name="Category Probe",
        category=SecurityTestCategory.ISOLATION_ESCAPE,
        description="Verify attack ID forces untrusted",
        severity=SecurityTestSeverity.HIGH,
        preconditions=[],
        input_fixture="probe.py",
        expected_security_invariant="ISO",
        resource_budget=1000,
        clean_state_required=True,
        deterministic=True,
        version="1.0",
        status=SecurityTestStatus.IMPLEMENTED
    )
    ctx = AttackExecutionContext(
        attack_id="UNTRUSTED_EXECUTION",
        run_id="run-cat",
        base_snapshot="snap",
        patch_hash="patch",
        execution_id="e-cat"
    )

    obs = executor.execute_test(spec, ctx, str(tmp_path))
    # Must be BLOCKED by LocalDevelopmentBackend because UNTRUSTED_EXECUTION forces UNTRUSTED
    assert obs.status == SecurityResultClassification.BLOCKED


def test_timezone_aware_utc_timestamps_in_evidence_builder():
    """
    Evidence builder must produce timezone-aware ISO 8601 UTC timestamps,
    and must not use deprecated datetime.datetime.utcnow().
    """
    from backend.models.schemas import PatchCandidate
    from backend.verification.models import VerificationResult, VerificationStatus, TestResultSummary, RegressionSummary
    from backend.models.evidence import verify_receipt_integrity

    contract = TaskContract(
        task_id="T-TZ",
        repository_id="repo-int-1",
        base_commit_or_snapshot="COMMIT1",
        task_description="Test Task",
        allowed_scope=["main.py"],
    )
    patch = PatchCandidate(
        patch_id="P1",
        task_id="T-TZ",
        base_commit_or_snapshot="COMMIT1",
        diff="--- a/main.py\n+++ b/main.py\n+print('hello')"
    )
    result = VerificationResult(
        verification_id="V1",
        verifier_version="1.0",
        verified_scope="test_scope",
        status=VerificationStatus.VERIFIED,
        policy_version="1.0",
        repository_snapshot_hash="HASH1",
        patch_hash="HASH2",
        test_summary=TestResultSummary(executed=1, passed=1),
        regression_summary=RegressionSummary(),
        security_aggregation=None,
        invariants=[],
        oracle_results=[],
        counterexamples=[]
    )

    agg = EvidenceAggregator(contract)
    receipt = agg.build_receipt(
        run_id="run-tz-test",
        patch=patch,
        verification_result=result,
        attacks=[],
        model_provenance={"model": "test"},
        sandbox_provenance={"backend": "local"}
    )

    assert isinstance(receipt, EvidenceReceipt)
    ts = receipt.timestamp
    assert ts is not None

    # Parse timestamp - must have valid UTC timezone
    parsed_dt = datetime.datetime.fromisoformat(ts)
    assert parsed_dt.tzinfo is not None, "Timestamp must be timezone-aware"
    assert parsed_dt.utcoffset() == datetime.timedelta(0), "Timestamp must be UTC (+00:00)"
    assert verify_receipt_integrity(receipt) is True
