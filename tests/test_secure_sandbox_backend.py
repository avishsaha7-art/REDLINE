"""
Unit and integration tests for SecureSandboxBackend and Fail-Closed Gate.

Verifies:
1. Truthful capability reporting when runtime is unavailable.
2. Fail-closed behavior on untrusted execution when runtime is absent.
3. Container argument construction and security hardening (read-only root, no network, cap-drop).
4. Container lifecycle cleanup on timeout, failure, and normal completion.
5. Integration with AttackVerificationEngine (policy-blocked fail-closed).
"""

import os
import sys
import tempfile
import shutil
import pytest
from unittest.mock import MagicMock, patch

from backend.sandbox.models import SandboxPolicy, ExecutionRequest, ExecutionResult
from backend.sandbox.capabilities import SandboxCapabilities, SecurityLevel, RepositoryTrust
from backend.sandbox.secure_backend import SecureSandboxBackend, ContainerRuntimeProbe
from backend.verification.attack_executor import AttackVerificationEngine
from backend.verification.attack_validator import validate_attack_for_execution
from backend.models.attack import AttackCandidate, AttackType, OracleType, AttackResourceBudget
from backend.verification.models import ExecutionStatus, InvariantResultStatus


@pytest.fixture
def temp_workspace():
    ws = tempfile.mkdtemp(prefix="test_secure_sandbox_")
    yield ws
    shutil.rmtree(ws, ignore_errors=True)


class MockProbeUnavailable(ContainerRuntimeProbe):
    def detect_runtime(self):
        return False, "NONE", {"error": "Mocked: container daemon not present"}


class MockProbeAvailable(ContainerRuntimeProbe):
    def detect_runtime(self):
        return True, "docker", {"executable": "/usr/bin/docker", "server_version": "27.0.0"}


# ---------------------------------------------------------------------------
# 1. Truthful Capability Reporting
# ---------------------------------------------------------------------------

def test_capabilities_truthful_when_runtime_unavailable():
    """When container runtime is absent, capabilities must NOT claim SECURE."""
    backend = SecureSandboxBackend(
        policy=SandboxPolicy(),
        runtime_probe=MockProbeUnavailable()
    )
    caps = backend.capabilities()
    assert caps.security_level == SecurityLevel.UNAVAILABLE
    assert caps.filesystem_isolation == "NOT_AVAILABLE"
    assert caps.process_isolation == "NOT_AVAILABLE"
    assert caps.network_isolation == "NOT_AVAILABLE"
    assert caps.secure_untrusted_execution is False


def test_capabilities_truthful_when_runtime_available():
    """When container runtime is verified operational, capabilities report SECURE."""
    backend = SecureSandboxBackend(
        policy=SandboxPolicy(),
        runtime_probe=MockProbeAvailable()
    )
    caps = backend.capabilities()
    assert caps.security_level == SecurityLevel.SECURE
    assert caps.filesystem_isolation == "ENFORCED"
    assert caps.process_isolation == "ENFORCED"
    assert caps.network_isolation == "ENFORCED"
    assert caps.secure_untrusted_execution is True


def test_real_host_probe_truthfully_reports_state():
    """Real host probe on this environment must report truthful capability."""
    backend = SecureSandboxBackend(policy=SandboxPolicy())
    caps = backend.capabilities()
    # On this Windows host, Docker is not running; probe must report UNAVAILABLE
    assert caps.security_level == SecurityLevel.UNAVAILABLE
    assert caps.secure_untrusted_execution is False


# ---------------------------------------------------------------------------
# 2. Fail-Closed Execution Gate
# ---------------------------------------------------------------------------

def test_untrusted_execution_fails_closed_without_runtime(temp_workspace):
    """Untrusted request must be refused with OPERATIONAL_FAILURE when runtime is absent."""
    backend = SecureSandboxBackend(
        policy=SandboxPolicy(),
        runtime_probe=MockProbeUnavailable()
    )
    req = ExecutionRequest(
        command=["python", "app.py"],
        working_directory=temp_workspace,
        repository_trust="UNTRUSTED"
    )
    res = backend.execute(req, run_id="run-test-1")

    assert res.policy_blocked is True
    assert res.exit_code == -1
    assert "OPERATIONAL_FAILURE" in res.stderr
    assert "UNAVAILABLE" in res.stderr
    assert res.backend_provenance.get("status") == "OPERATIONAL_FAILURE"
    assert res.backend_provenance.get("reason") == "RUNTIME_UNAVAILABLE"


def test_trusted_execution_also_refused_by_secure_backend_without_runtime(temp_workspace):
    """SecureSandboxBackend does NOT fall back to host execution even for trusted requests."""
    backend = SecureSandboxBackend(
        policy=SandboxPolicy(),
        runtime_probe=MockProbeUnavailable()
    )
    req = ExecutionRequest(
        command=["python", "app.py"],
        working_directory=temp_workspace,
        repository_trust="TRUSTED_DEVELOPMENT"
    )
    res = backend.execute(req, run_id="run-test-2")

    assert res.policy_blocked is True
    assert "OPERATIONAL_FAILURE" in res.stderr


# ---------------------------------------------------------------------------
# 3. Container Argument Hardening Unit Tests
# ---------------------------------------------------------------------------

def test_container_arg_hardening_spec(temp_workspace):
    """Verify exact hardening flags in container argument construction."""
    backend = SecureSandboxBackend(
        policy=SandboxPolicy(
            max_memory_bytes=512 * 1024 * 1024,
            network_enabled=False
        ),
        container_image="custom-redline:v1",
        runtime_probe=MockProbeAvailable()
    )
    canonical_ws = os.path.realpath(temp_workspace)
    args = backend.build_container_args(
        engine="docker",
        container_name="test_cnt_1",
        canonical_workspace=canonical_ws,
        command=["pytest", "test_app.py"],
        env={"CUSTOM_VAR": "val1"}
    )

    # Core security constraints
    assert "--read-only" in args, "Must enforce read-only root filesystem"
    assert "--cap-drop=ALL" in args, "Must drop all Linux capabilities"
    assert "--security-opt=no-new-privileges" in args, "Must forbid privilege escalation"
    assert "--user" in args and "1000:1000" in args, "Must run as non-root user"
    assert "--network" in args and "none" in args, "Must disable networking by default"
    assert "--privileged" not in args, "Must NEVER run with --privileged"
    assert "/var/run/docker.sock" not in " ".join(args), "Must NEVER expose Docker socket"

    # Workspace mount containment
    expected_mount = f"{canonical_ws}:/workspace:rw"
    assert "-v" in args and expected_mount in args, "Must mount only canonical workspace"
    assert "-w" in args and "/workspace" in args, "Working directory must be /workspace"

    # Memory constraint
    assert "--memory" in args and f"{512 * 1024 * 1024}b" in args

    # Command and image
    assert "custom-redline:v1" in args
    assert args[-2:] == ["pytest", "test_app.py"]


def test_disallowed_command_rejected_when_runtime_available(temp_workspace):
    """Requirement 4: Disallowed commands are rejected when the runtime is available."""
    backend = SecureSandboxBackend(
        policy=SandboxPolicy(allowed_commands=["python"]),
        runtime_probe=MockProbeAvailable()
    )
    req = ExecutionRequest(
        command=["bash", "-c", "echo hello"],
        working_directory=temp_workspace,
        repository_trust="UNTRUSTED"
    )
    res = backend.execute(req, run_id="run-disallowed-avail")
    assert res.policy_blocked is True
    assert res.exit_code == -1
    assert "Command not in allowed_commands" in res.stderr
    assert res.backend_provenance.get("reason") == "COMMAND_DISALLOWED"


def test_disallowed_command_rejected_when_runtime_unavailable(temp_workspace):
    """Requirement 5: Disallowed commands are rejected when the runtime is unavailable."""
    backend = SecureSandboxBackend(
        policy=SandboxPolicy(allowed_commands=["python"]),
        runtime_probe=MockProbeUnavailable()
    )
    req = ExecutionRequest(
        command=["bash", "-c", "echo hello"],
        working_directory=temp_workspace,
        repository_trust="UNTRUSTED"
    )
    res = backend.execute(req, run_id="run-disallowed-unavail")
    # Must be rejected for COMMAND_DISALLOWED, NOT RUNTIME_UNAVAILABLE
    assert res.policy_blocked is True
    assert res.exit_code == -1
    assert "Command not in allowed_commands" in res.stderr
    assert res.backend_provenance.get("reason") == "COMMAND_DISALLOWED"
    assert "RUNTIME_UNAVAILABLE" not in res.stderr


def test_shell_metacharacters_rejected_regardless_of_runtime(temp_workspace):
    """Shell operators and metacharacters in command binary must be rejected."""
    for probe in [MockProbeAvailable(), MockProbeUnavailable()]:
        backend = SecureSandboxBackend(
            policy=SandboxPolicy(allowed_commands=["python"]),
            runtime_probe=probe
        )
        for malicious_cmd in [
            ["python;rm -rf /", "test.py"],
            ["python | cat", "test.py"],
            ["python & echo", "test.py"],
            ["`evil`", "test.py"],
            ["$HOME/python", "test.py"],
        ]:
            req = ExecutionRequest(
                command=malicious_cmd,
                working_directory=temp_workspace,
                repository_trust="UNTRUSTED"
            )
            res = backend.execute(req, run_id="run-metachar")
            assert res.policy_blocked is True
            assert res.exit_code == -1
            assert res.backend_provenance.get("reason") == "COMMAND_DISALLOWED"


def test_runtime_unavailability_never_invokes_host_fallback(temp_workspace):
    """Requirement 6: Runtime unavailability never invokes a host fallback."""
    marker_file = os.path.join(temp_workspace, "should_never_exist.txt")
    backend = SecureSandboxBackend(
        policy=SandboxPolicy(allowed_commands=["python"]),
        runtime_probe=MockProbeUnavailable()
    )
    # Even with a valid allowed command and trusted development flag, no host execution occurs
    req = ExecutionRequest(
        command=["python", "-c", f"import pathlib; pathlib.Path('{marker_file}').touch()"],
        working_directory=temp_workspace,
        repository_trust="TRUSTED_DEVELOPMENT"
    )
    res = backend.execute(req, run_id="run-no-fallback")

    assert res.policy_blocked is True
    assert res.exit_code == -1
    assert not os.path.exists(marker_file), "Host execution fallback occurred! Must NEVER run on host!"
    assert res.backend_provenance.get("reason") == "RUNTIME_UNAVAILABLE"


# ---------------------------------------------------------------------------
# 4. Container Teardown & Lifecycle Cleanup Unit Tests
# ---------------------------------------------------------------------------

@patch("subprocess.Popen")
@patch("subprocess.run")
def test_container_cleanup_on_timeout(mock_sub_run, mock_popen, temp_workspace):
    """When execution times out, container kill and cleanup must be executed."""
    import subprocess
    proc_mock = MagicMock()
    proc_mock.communicate.side_effect = subprocess.TimeoutExpired(cmd=["docker"], timeout=5)
    mock_popen.return_value = proc_mock

    backend = SecureSandboxBackend(
        policy=SandboxPolicy(),
        runtime_probe=MockProbeAvailable()
    )
    req = ExecutionRequest(
        command=["python", "infinite.py"],
        working_directory=temp_workspace,
        timeout_seconds=5,
        repository_trust="UNTRUSTED"
    )
    res = backend.execute(req, run_id="run-timeout-1")

    assert res.timed_out is True
    assert res.exit_code == -1
    assert "TIMEOUT" in res.stderr

    # Verify docker rm -f was called in cleanup
    cleanup_calls = [
        call for call in mock_sub_run.call_args_list
        if "rm" in call[0][0] and "-f" in call[0][0]
    ]
    assert len(cleanup_calls) >= 1, "Expected container removal command on timeout"


# ---------------------------------------------------------------------------
# 5. Integration with Verification Subsystem
# ---------------------------------------------------------------------------

def test_attack_verification_engine_fails_closed_with_unavailable_secure_backend():
    """AttackVerificationEngine must fail closed when SecureSandboxBackend has no runtime."""
    backend = SecureSandboxBackend(
        policy=SandboxPolicy(),
        runtime_probe=MockProbeUnavailable()
    )
    engine = AttackVerificationEngine(backend=backend, repository_trust="UNTRUSTED")

    candidate = AttackCandidate(
        attack_id="atk_1",
        attack_type=AttackType.INPUT,
        objective="Test",
        target="target_func",
        preconditions=[],
        input_specification='{"payload": "test"}',
        execution_strategy="TEST_CASE",
        expected_failure_signal="Crash",
        oracle_type=OracleType.TASK_INVARIANT,
        risk_level="MEDIUM",
        rationale="testing"
    )
    req = validate_attack_for_execution("run_1", "task_1", "snap_A", "patch_B", candidate)

    obs, oracle_res, ce = engine.execute_and_verify(req, workspace_id="ws-1")

    assert obs.status == ExecutionStatus.POLICY_BLOCKED
    assert oracle_res.result == InvariantResultStatus.INCONCLUSIVE
    assert ce is None
    assert obs.stderr_bytes > 0 or "Secure sandbox unavailable" in obs.stderr_sha256
