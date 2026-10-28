"""
REDLINE Stage 8 / Phase 1: Sandbox Correctness & Policy Enforcement Tests.

Validates that:
1. Untrusted imported code uses SecureSandboxBackend when secure sandbox execution is required.
2. Missing or unavailable Docker produces an explicit blocked or failed state (RUNTIME_UNAVAILABLE / POLICY_BLOCKED).
3. Untrusted workloads NEVER silently fall back to LocalDevelopmentBackend, even if REDLINE_ENABLE_LOCAL_BACKEND=1.
4. Trusted local-development tasks can use LocalDevelopmentBackend ONLY when policy and environment permit.
5. Evidence receipts accurately identify the runtime backend and observed security capabilities.
6. UI labels / receipt validators cannot claim secure execution unless the actual execution record supports that claim.
"""

import os
import pytest
from unittest.mock import MagicMock

from backend.sandbox.models import SandboxPolicy, ExecutionRequest, ExecutionResult
from backend.sandbox.capabilities import RepositoryTrust, SecurityLevel, SandboxCapabilities
from backend.sandbox.backend import LocalDevelopmentBackend
from backend.sandbox.secure_backend import SecureSandboxBackend, ContainerRuntimeProbe
from backend.sandbox.factory import get_sandbox_backend
from backend.sandbox.trust import resolve_repository_trust, is_local_backend_enabled, set_local_backend_override
from backend.sandbox.client import SandboxClient
from backend.models.schemas import PatchCandidate, TaskContract
from backend.models.evidence import EvidenceReceipt, VerificationScope, verify_receipt_integrity
from backend.verification.models import VerificationResult, VerificationStatus, StructuredObservation, TestResultSummary


class ControlledUnavailableProbe(ContainerRuntimeProbe):
    """Probe simulating host where Docker/Podman is completely absent."""
    def detect_runtime(self):
        return False, "NONE", {"error": "Docker daemon not running"}

    def inspect_image(self, engine, image_name):
        return False, None, None, "Runtime unavailable"


class ControlledOperationalProbe(ContainerRuntimeProbe):
    """Probe simulating host with fully operational container runtime."""
    def detect_runtime(self):
        return True, "docker", {"executable": "/usr/bin/docker", "server_version": "26.1.0"}

    def inspect_image(self, engine, image_name):
        return True, "sha256:mockimageid", "mockimage@sha256:mockimageid", None


# 1. Untrusted imported code uses SecureSandboxBackend
def test_untrusted_imported_code_uses_secure_sandbox_backend():
    policy = SandboxPolicy()

    # Imported project ID format
    backend = get_sandbox_backend(policy, repository_trust=RepositoryTrust.UNTRUSTED)
    assert isinstance(backend, SecureSandboxBackend)
    assert backend.capabilities().security_level in (SecurityLevel.SECURE, SecurityLevel.UNAVAILABLE)

    # Remote clone ID format
    trust = resolve_repository_trust("repo-remote-123456789abc")
    assert trust == RepositoryTrust.UNTRUSTED
    backend_remote = get_sandbox_backend(policy, repository_trust=trust)
    assert isinstance(backend_remote, SecureSandboxBackend)


# 2. Missing or unavailable Docker produces an explicit blocked state
def test_missing_docker_produces_explicit_blocked_state():
    probe = ControlledUnavailableProbe()
    backend = SecureSandboxBackend(policy=SandboxPolicy(), runtime_probe=probe)

    caps = backend.capabilities()
    assert caps.security_level == SecurityLevel.UNAVAILABLE
    assert caps.secure_untrusted_execution is False

    req = ExecutionRequest(
        command=["python", "-m", "pytest"],
        working_directory=os.path.abspath("."),
        repository_trust=RepositoryTrust.UNTRUSTED.value
    )
    result = backend.execute(req, run_id="run-unavailable-test")

    assert result.policy_blocked is True
    assert result.exit_code == -1
    assert "OPERATIONAL_FAILURE" in result.stderr
    assert "UNAVAILABLE" in result.stderr
    assert result.backend_provenance["status"] == "OPERATIONAL_FAILURE"
    assert result.backend_provenance["reason"] == "RUNTIME_UNAVAILABLE"


# 3. Untrusted workloads NEVER silently fall back to LocalDevelopmentBackend
def test_untrusted_workload_never_falls_back_to_local_backend(monkeypatch):
    monkeypatch.setenv("REDLINE_ENABLE_LOCAL_BACKEND", "1")
    set_local_backend_override(True)
    try:
        policy = SandboxPolicy()

        # Even with local backend enabled, untrusted repo MUST get SecureSandboxBackend
        backend = get_sandbox_backend(policy, repository_trust=RepositoryTrust.UNTRUSTED)
        assert isinstance(backend, SecureSandboxBackend)
        assert not isinstance(backend, LocalDevelopmentBackend)

        # Directly invoking LocalDevelopmentBackend on UNTRUSTED request must fail closed
        local_backend = LocalDevelopmentBackend(policy=policy)
        req = ExecutionRequest(
            command=["python", "-m", "pytest"],
            working_directory=os.path.abspath("."),
            repository_trust=RepositoryTrust.UNTRUSTED.value
        )
        res = local_backend.execute(req, run_id="run-illegal-local")
        assert res.policy_blocked is True
        assert "UNSAFE FOR UNTRUSTED PRODUCTION WORKLOADS" in res.stderr
    finally:
        set_local_backend_override(None)


# 4. Trusted local-development tasks can use local backend ONLY when policy permits
def test_trusted_development_uses_local_backend_only_when_enabled(monkeypatch):
    policy = SandboxPolicy()

    # When REDLINE_ENABLE_LOCAL_BACKEND is NOT enabled, trusted tasks route to SecureSandboxBackend
    monkeypatch.delenv("REDLINE_ENABLE_LOCAL_BACKEND", raising=False)
    set_local_backend_override(False)
    backend_disabled = get_sandbox_backend(policy, repository_trust=RepositoryTrust.TRUSTED_DEVELOPMENT)
    assert isinstance(backend_disabled, SecureSandboxBackend)

    # When explicitly enabled, trusted development receives LocalDevelopmentBackend
    monkeypatch.setenv("REDLINE_ENABLE_LOCAL_BACKEND", "1")
    set_local_backend_override(True)
    try:
        backend_enabled = get_sandbox_backend(policy, repository_trust=RepositoryTrust.TRUSTED_DEVELOPMENT)
        assert isinstance(backend_enabled, LocalDevelopmentBackend)
        assert backend_enabled.capabilities().security_level == SecurityLevel.DEVELOPMENT_ONLY
    finally:
        set_local_backend_override(None)


# 5. Receipts accurately identify runtime backend and capabilities
def test_receipt_accurately_identifies_runtime_backend():
    receipt = EvidenceReceipt(
        run_id="run-backend-prov-01",
        task_id="task-prov-01",
        repository_snapshot_hash="snap-01",
        task_contract_hash="contract-01",
        patch_hash="patch-01",
        patch_id="PATCH-01",
        patch_digest="a" * 64,
        policy_version="1.0.0",
        verifier_version="1.0.0",
        timestamp="2026-10-28T12:00:00Z",
        verdict=VerificationStatus.VERIFIED,
        verification_scope=VerificationScope(execution="VERIFIED", tests="VERIFIED"),
        test_summary=TestResultSummary(discovered=2, executed=2, passed=2, failed=0),
        sandbox_provenance={
            "backend": "LocalDevelopmentBackend",
            "security_level": "DEVELOPMENT_ONLY",
            "trust": "TRUSTED_DEVELOPMENT"
        },
        structured_observation=StructuredObservation(
            execution_id="exec-01",
            command_identifier="pytest",
            exit_code=0,
            stdout_sha256="b" * 64,
            stderr_sha256="c" * 64,
            stdout_bytes=10,
            stderr_bytes=0,
            duration_ms=50,
            status="SUCCESS",
            sandbox_backend="LocalDevelopmentBackend",
            security_level="DEVELOPMENT_ONLY",
            capabilities={"network": True, "filesystem_isolation": "PROCESS_ONLY"},
            workspace_id="ws-1",
            repository_snapshot_hash="snap-01",
            patch_hash="a" * 64
        )
    )
    receipt = receipt.model_copy(update={"receipt_hash": receipt.calculate_integrity_hash()})

    assert receipt.sandbox_provenance["backend"] == "LocalDevelopmentBackend"
    assert receipt.structured_observation.sandbox_backend == "LocalDevelopmentBackend"
    assert verify_receipt_integrity(receipt) is True


# 6. UI / receipt validator rejects falsely claimed secure execution
def test_receipt_validator_rejects_falsely_claimed_security():
    # Attempt to claim VERIFIED with UNKNOWN sandbox backend
    receipt_unknown = EvidenceReceipt(
        run_id="run-fake-sec-01",
        task_id="task-fake-01",
        repository_snapshot_hash="snap-01",
        task_contract_hash="contract-01",
        patch_hash="patch-01",
        policy_version="1.0.0",
        verifier_version="1.0.0",
        timestamp="2026-10-28T12:00:00Z",
        verdict=VerificationStatus.VERIFIED,
        verification_scope=VerificationScope(execution="VERIFIED", tests="VERIFIED"),
        test_summary=TestResultSummary(discovered=2, executed=2, passed=2, failed=0),
        sandbox_provenance={"backend": "UNKNOWN"},
        structured_observation=StructuredObservation(
            execution_id="exec-01",
            command_identifier="pytest",
            exit_code=0,
            stdout_sha256="b" * 64,
            stderr_sha256="c" * 64,
            stdout_bytes=10,
            stderr_bytes=0,
            duration_ms=50,
            status="SUCCESS",
            sandbox_backend="UNKNOWN",
            security_level="DEVELOPMENT_ONLY",
            capabilities={},
            workspace_id="ws-1",
            repository_snapshot_hash="snap-01",
            patch_hash="a" * 64
        )
    )
    receipt_unknown = receipt_unknown.model_copy(update={"receipt_hash": receipt_unknown.calculate_integrity_hash()})
    # Integrity check must detect the UNKNOWN backend
    assert verify_receipt_integrity(receipt_unknown) is False
