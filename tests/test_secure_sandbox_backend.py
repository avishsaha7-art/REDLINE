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
import subprocess
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
    is_operational, _, _ = ContainerRuntimeProbe().detect_runtime()
    if is_operational:
        assert caps.security_level == SecurityLevel.SECURE
        assert caps.secure_untrusted_execution is True
    else:
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


def test_trusted_development_command_allowlist_enforcement_regardless_of_runtime(temp_workspace):
    """
    Commands in TRUSTED_DEVELOPMENT requests are strictly validated against allowlist
    regardless of runtime availability. Disallowed commands are rejected fail-closed.
    """
    for probe in [MockProbeAvailable(), MockProbeUnavailable()]:
        backend = SecureSandboxBackend(
            policy=SandboxPolicy(allowed_commands=["python"]),
            runtime_probe=probe
        )
        req = ExecutionRequest(
            command=["sh", "-c", "echo untrusted_action"],
            working_directory=temp_workspace,
            repository_trust="TRUSTED_DEVELOPMENT"
        )
        res = backend.execute(req, run_id="run-trusted-disallowed")
        assert res.policy_blocked is True
        assert res.exit_code == -1
        assert "Command not in allowed_commands" in res.stderr
        assert res.backend_provenance.get("reason") == "COMMAND_DISALLOWED"
        assert res.backend_provenance.get("trust") == "TRUSTED_DEVELOPMENT"


@patch("subprocess.Popen")
@patch("subprocess.run")
def test_allowed_command_with_available_runtime_executes_in_container(mock_sub_run, mock_popen, temp_workspace):
    """
    When runtime is available and command is allowed, execution proceeds inside
    the container (not on the host) and returns container results cleanly.
    """
    proc_mock = MagicMock()
    proc_mock.communicate.return_value = (b"container output", b"")
    proc_mock.returncode = 0
    mock_popen.return_value = proc_mock

    backend = SecureSandboxBackend(
        policy=SandboxPolicy(allowed_commands=["python"]),
        runtime_probe=MockProbeAvailable()
    )
    req = ExecutionRequest(
        command=["python", "script.py"],
        working_directory=temp_workspace,
        repository_trust="TRUSTED_DEVELOPMENT"
    )
    res = backend.execute(req, run_id="run-allowed-avail")

    assert res.policy_blocked is False
    assert res.exit_code == 0
    assert res.stdout == "container output"
    assert res.backend_provenance.get("backend") == "SecureSandboxBackend"
    assert res.backend_provenance.get("engine") == "docker"
    assert res.backend_provenance.get("trust") == "TRUSTED_DEVELOPMENT"
    mock_popen.assert_called_once()
    called_cmd = mock_popen.call_args[0][0]
    assert called_cmd[0] == "docker"
    assert "run" in called_cmd


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


# ---------------------------------------------------------------------------
# 6. Resource Limits & Hardening Unit Tests (Step 2.9.4.2A)
# ---------------------------------------------------------------------------

def test_resource_args_include_cpu_and_pids_limits(temp_workspace):
    """Container argument list must include explicit CPU, PID, and memory limits."""
    backend = SecureSandboxBackend(
        policy=SandboxPolicy(
            cpu_limit=2.5,
            pids_limit=128,
            max_memory_bytes=1024 * 1024 * 1024,
            network_enabled=False
        ),
        container_image="custom-redline:v1",
        runtime_probe=MockProbeAvailable()
    )
    canonical_ws = os.path.realpath(temp_workspace)
    args = backend.build_container_args(
        engine="docker",
        container_name="test_res_cnt",
        canonical_workspace=canonical_ws,
        command=["python", "script.py"],
        env={}
    )

    # CPU limit flag
    assert "--cpus" in args
    cpu_idx = args.index("--cpus")
    assert args[cpu_idx + 1] == "2.5"

    # PID limit flag
    assert "--pids-limit" in args
    pids_idx = args.index("--pids-limit")
    assert args[pids_idx + 1] == "128"

    # Memory limit flag
    assert "--memory" in args
    mem_idx = args.index("--memory")
    assert args[mem_idx + 1] == f"{1024 * 1024 * 1024}b"


def test_default_resource_args_constructed_into_container_args(temp_workspace):
    """Default policy must supply safe, validated defaults for CPU, PIDs, and memory."""
    backend = SecureSandboxBackend(
        policy=SandboxPolicy(),
        runtime_probe=MockProbeAvailable()
    )
    canonical_ws = os.path.realpath(temp_workspace)
    args = backend.build_container_args(
        engine="docker",
        container_name="test_default_res_cnt",
        canonical_workspace=canonical_ws,
        command=["python", "script.py"],
        env={}
    )

    assert "--cpus" in args
    assert args[args.index("--cpus") + 1] == "1.0"

    assert "--pids-limit" in args
    assert args[args.index("--pids-limit") + 1] == "64"

    assert "--memory" in args
    assert args[args.index("--memory") + 1] == f"{512 * 1024 * 1024}b"


def test_policy_resource_bounds_validation():
    """Policy must fail closed on invalid, zero, negative, or out-of-bounds resource values."""
    import pydantic

    # Invalid CPU values
    for invalid_cpu in [0, 0.0, -1.0, 16.5, 100.0, float("nan"), float("inf"), "invalid"]:
        with pytest.raises((pydantic.ValidationError, ValueError)):
            SandboxPolicy(cpu_limit=invalid_cpu)

    # Invalid PIDs values
    for invalid_pids in [0, -1, 1, 2, 3, 1025, 5000, 64.5, "64"]:
        with pytest.raises((pydantic.ValidationError, ValueError)):
            SandboxPolicy(pids_limit=invalid_pids)

    # Invalid Memory values
    for invalid_mem in [0, -1, 1024, 1024 * 1024, 9 * 1024 * 1024 * 1024]:
        with pytest.raises((pydantic.ValidationError, ValueError)):
            SandboxPolicy(max_memory_bytes=invalid_mem)

    # Invalid Runtime seconds
    for invalid_sec in [0, -5, 601, 3600]:
        with pytest.raises((pydantic.ValidationError, ValueError)):
            SandboxPolicy(max_runtime_seconds=invalid_sec)

    # Invalid Output bytes
    for invalid_out in [0, -1, 101 * 1024 * 1024]:
        with pytest.raises((pydantic.ValidationError, ValueError)):
            SandboxPolicy(max_output_bytes=invalid_out)

    # Invalid Disk bytes
    for invalid_disk in [0, -1, 512, 25 * 1024 * 1024 * 1024]:
        with pytest.raises((pydantic.ValidationError, ValueError)):
            SandboxPolicy(max_disk_bytes=invalid_disk)


def test_backend_validates_policy_resources_and_fails_closed():
    """SecureSandboxBackend must fail closed if constructed with invalid policy or objects."""
    with pytest.raises(TypeError):
        SecureSandboxBackend(policy="not_a_policy")

    # Tampered policy object passed to validation method
    tampered_policy = SandboxPolicy()
    object.__setattr__(tampered_policy, "cpu_limit", -2.0)
    with pytest.raises(ValueError, match="Invalid cpu_limit"):
        SecureSandboxBackend._validate_policy_resources(tampered_policy)

    object.__setattr__(tampered_policy, "cpu_limit", 1.0)
    object.__setattr__(tampered_policy, "pids_limit", 1)
    with pytest.raises(ValueError, match="Invalid pids_limit"):
        SecureSandboxBackend._validate_policy_resources(tampered_policy)


@patch("subprocess.Popen")
@patch("subprocess.run")
def test_server_policy_authoritatively_clamps_client_timeout(mock_sub_run, mock_popen, temp_workspace):
    """Server-side policy max_runtime_seconds authoritatively bounds client request timeout."""
    proc_mock = MagicMock()
    proc_mock.communicate.return_value = (b"output", b"")
    proc_mock.returncode = 0
    mock_popen.return_value = proc_mock

    backend = SecureSandboxBackend(
        policy=SandboxPolicy(max_runtime_seconds=25),
        runtime_probe=MockProbeAvailable()
    )
    # Client requests 100 seconds (exceeding server policy of 25)
    req = ExecutionRequest(
        command=["python", "script.py"],
        working_directory=temp_workspace,
        timeout_seconds=100,
        repository_trust="TRUSTED_DEVELOPMENT"
    )
    res = backend.execute(req, run_id="run-clamped-timeout")

    assert res.exit_code == 0
    assert res.policy_blocked is False
    # Verify communicate was called with server-enforced timeout of 25
    mock_popen.return_value.communicate.assert_called_once_with(timeout=25)
    assert res.resource_usage.get("timeout_seconds") == 25


@patch("subprocess.Popen")
@patch("subprocess.run")
def test_reactive_disk_limit_exceeded_fails_closed(mock_sub_run, mock_popen, temp_workspace):
    """Workspace exceeding max_disk_bytes is caught reactively and fails closed."""
    proc_mock = MagicMock()
    proc_mock.communicate.return_value = (b"output", b"")
    proc_mock.returncode = 0
    mock_popen.return_value = proc_mock

    # Create a 2 MB file in workspace
    with open(os.path.join(temp_workspace, "large_file.bin"), "wb") as f:
        f.write(b"X" * (2 * 1024 * 1024))

    backend = SecureSandboxBackend(
        policy=SandboxPolicy(max_disk_bytes=1024 * 1024),  # 1 MB limit
        runtime_probe=MockProbeAvailable()
    )
    req = ExecutionRequest(
        command=["python", "script.py"],
        working_directory=temp_workspace,
        repository_trust="TRUSTED_DEVELOPMENT"
    )
    res = backend.execute(req, run_id="run-disk-exceeded")

    assert res.policy_blocked is True
    assert res.exit_code == -1
    assert "POLICY_BLOCKED: Workspace disk usage" in res.stderr
    assert "exceeded limit" in res.stderr
    assert res.backend_provenance.get("reason") == "DISK_QUOTA_EXCEEDED"
    assert res.backend_provenance.get("disk_usage_bytes") >= 2 * 1024 * 1024


@patch("subprocess.Popen")
@patch("subprocess.run")
def test_cleanup_failure_and_timeout_never_trigger_host_fallback(mock_sub_run, mock_popen, temp_workspace):
    """Timeout and cleanup failures in container execution must never fall back to host."""
    marker_file = os.path.join(temp_workspace, "must_never_be_touched.txt")
    proc_mock = MagicMock()
    proc_mock.communicate.side_effect = subprocess.TimeoutExpired(cmd=["docker", "run"], timeout=5)
    mock_popen.return_value = proc_mock
    # Mock cleanup rm -f failure
    mock_sub_run.side_effect = RuntimeError("Container daemon crashed during cleanup")

    backend = SecureSandboxBackend(
        policy=SandboxPolicy(allowed_commands=["python"]),
        runtime_probe=MockProbeAvailable()
    )
    req = ExecutionRequest(
        command=["python", "-c", f"import pathlib; pathlib.Path('{marker_file}').touch()"],
        working_directory=temp_workspace,
        repository_trust="TRUSTED_DEVELOPMENT"
    )
    res = backend.execute(req, run_id="run-timeout-cleanup-fail")

    assert res.timed_out is True
    assert res.exit_code == -1
    assert "TIMEOUT" in res.stderr
    assert not os.path.exists(marker_file), "Host execution fallback must NEVER occur on timeout or cleanup failure"


@patch("subprocess.Popen")
@patch("subprocess.run")
def test_execution_result_provenance_contains_resource_usage(mock_sub_run, mock_popen, temp_workspace):
    """ExecutionResult must accurately record server resource limits in resource_usage."""
    proc_mock = MagicMock()
    proc_mock.communicate.return_value = (b"hello", b"")
    proc_mock.returncode = 0
    mock_popen.return_value = proc_mock

    backend = SecureSandboxBackend(
        policy=SandboxPolicy(
            cpu_limit=1.5,
            pids_limit=100,
            max_memory_bytes=256 * 1024 * 1024,
            max_runtime_seconds=45,
            max_output_bytes=50000
        ),
        runtime_probe=MockProbeAvailable()
    )
    req = ExecutionRequest(
        command=["python", "script.py"],
        working_directory=temp_workspace,
        repository_trust="TRUSTED_DEVELOPMENT"
    )
    res = backend.execute(req, run_id="run-provenance-check")

    assert res.resource_usage["cpu_limit"] == 1.5
    assert res.resource_usage["pids_limit"] == 100
    assert res.resource_usage["max_memory_bytes"] == 256 * 1024 * 1024
    assert res.resource_usage["timeout_seconds"] == 30  # Default req.timeout_seconds clamped by 45
    assert res.resource_usage["max_output_bytes"] == 50000


# ---------------------------------------------------------------------------
# 7. Conservative Workspace Disk Measurement & Edge Cases (Step 2.9.4.2B.3 / F-01 through F-06)
# ---------------------------------------------------------------------------

def test_disk_measurement_truthful_disclaimer(temp_workspace):
    """Disk measurement must truthfully report reactive status and disclaim hard/proactive quota."""
    total, stats, exceeded = SecureSandboxBackend.measure_workspace_disk_usage(temp_workspace)
    assert stats["hard_quota_enforced"] is False
    assert stats["is_reactive_measurement"] is True
    assert stats["proactive_quota_supported"] is False
    assert "Reactive post-execution check" in stats["limitation_notice"]
    assert exceeded is False


def test_disk_measurement_hardlinks_deduplication(temp_workspace):
    """Hard links sharing the same inode must be deduplicated and not double counted."""
    src_file = os.path.join(temp_workspace, "original.bin")
    with open(src_file, "wb") as f:
        f.write(b"A" * 8192)  # 8 KB

    # Create 3 hard links to the same file
    hl1 = os.path.join(temp_workspace, "hl1.bin")
    hl2 = os.path.join(temp_workspace, "hl2.bin")
    hl3 = os.path.join(temp_workspace, "hl3.bin")
    os.link(src_file, hl1)
    os.link(src_file, hl2)
    os.link(src_file, hl3)

    total, stats, exceeded = SecureSandboxBackend.measure_workspace_disk_usage(temp_workspace)
    assert stats["file_count"] == 1
    assert stats["hardlink_dedup_count"] == 3
    # 8192 bytes allocated, NOT 32768
    assert total == 8192
    assert exceeded is False


def test_disk_measurement_symlink_pointing_outside_workspace_not_followed(temp_workspace):
    """Symlinks pointing outside canonical workspace must not be followed or sized by target."""
    import stat

    # Create a small dummy file in workspace
    real_file = os.path.join(temp_workspace, "local.txt")
    with open(real_file, "w") as f:
        f.write("local content")

    orig_lstat = os.lstat
    canonical_ws = os.path.realpath(temp_workspace)
    symlink_path = os.path.join(temp_workspace, "evil_symlink.bin")
    outside_target = "C:\\Windows\\System32\\pagefile.sys" if os.name == "nt" else "/var/log/huge.bin"

    def mock_lstat(path):
        if os.path.abspath(path) == os.path.abspath(symlink_path):
            mock_st = MagicMock()
            mock_st.st_mode = stat.S_IFLNK
            mock_st.st_size = 40
            mock_st.st_nlink = 1
            mock_st.st_ino = 99999
            mock_st.st_dev = 1
            return mock_st
        return orig_lstat(path)

    with patch("os.lstat", side_effect=mock_lstat), \
         patch("os.walk") as mock_walk, \
         patch("os.readlink") as mock_readlink:

        mock_walk.return_value = [
            (temp_workspace, [], ["local.txt", "evil_symlink.bin"])
        ]
        mock_readlink.return_value = outside_target

        total, stats, exceeded = SecureSandboxBackend.measure_workspace_disk_usage(
            canonical_workspace=canonical_ws,
            max_disk_bytes=100000
        )

        assert stats["symlink_count"] == 1
        assert stats["outside_symlinks_skipped"] >= 1
        assert stats["file_count"] == 1
        # Total size must include symlink link length (40) + local.txt, never the external target
        assert total < 1000
        assert exceeded is False


def test_real_file_symlink_pointing_outside_workspace_if_supported(temp_workspace):
    """Real file symlink test: skipped only when OS privilege is genuinely unavailable."""
    outside_dir = tempfile.mkdtemp(prefix="outside_target_")
    try:
        target_file = os.path.join(outside_dir, "huge_target.bin")
        with open(target_file, "wb") as f:
            f.write(b"Z" * (2 * 1024 * 1024))  # 2 MB outside workspace

        symlink_path = os.path.join(temp_workspace, "symlink_file.bin")
        try:
            os.symlink(target_file, symlink_path)
        except OSError as e:
            pytest.skip(
                f"Creating symbolic links requires administrator privileges or Developer Mode on Windows: {e}"
            )

        # If symlink creation succeeded:
        total, stats, exceeded = SecureSandboxBackend.measure_workspace_disk_usage(
            canonical_workspace=temp_workspace,
            max_disk_bytes=1024 * 1024  # 1 MB limit
        )
        assert stats["symlink_count"] == 1
        # Symlink itself is sized by link text, NOT 2 MB target!
        assert total < 1024 * 1024
        assert exceeded is False
    finally:
        shutil.rmtree(outside_dir, ignore_errors=True)


def test_real_directory_junction_or_symlink_pruned_not_traversed(temp_workspace):
    """
    Real directory junction test on Windows (mklink /J) or symlink on POSIX.
    Verifies that the traversal NEVER enters the junction or counts external target contents.
    """
    outside_dir = tempfile.mkdtemp(prefix="outside_junction_")
    try:
        # Place a 5 MB file outside the workspace
        outside_file = os.path.join(outside_dir, "external_payload.bin")
        with open(outside_file, "wb") as f:
            f.write(b"M" * (5 * 1024 * 1024))

        junction_path = os.path.join(temp_workspace, "junction_dir")

        if os.name == "nt":
            # On Windows, mklink /J does NOT require admin elevation
            res = subprocess.run(
                ["cmd", "/c", "mklink", "/J", junction_path, outside_dir],
                capture_output=True,
                text=True
            )
            if res.returncode != 0:
                pytest.skip(f"Windows junction creation failed: {res.stderr}")
        else:
            try:
                os.symlink(outside_dir, junction_path, target_is_directory=True)
            except OSError as e:
                pytest.skip(f"Directory symlink creation failed: {e}")

        # Run measurement with a 1 MB quota. If the junction was traversed, total would be > 5MB and exceeded=True!
        total, stats, exceeded = SecureSandboxBackend.measure_workspace_disk_usage(
            canonical_workspace=temp_workspace,
            max_disk_bytes=1024 * 1024
        )

        assert stats["symlink_count"] >= 1, "Junction/symlink must be detected"
        assert total < 1024 * 1024, f"External 5MB file must NOT be counted! Measured: {total}"
        assert exceeded is False, "Quota must NOT be exceeded by external junction target"
    finally:
        if os.name == "nt" and os.path.exists(junction_path):
            subprocess.run(["cmd", "/c", "rmdir", junction_path], capture_output=True)
        shutil.rmtree(outside_dir, ignore_errors=True)


def test_disk_measurement_directory_symlink_pruned_not_traversed(temp_workspace):
    """Directory symlinks must never be traversed into (mocked cross-platform verification)."""
    canonical_ws = os.path.realpath(temp_workspace)
    sym_dir = os.path.join(temp_workspace, "sym_dir")
    normal_dir = os.path.join(temp_workspace, "normal_dir")
    os.mkdir(sym_dir)
    os.mkdir(normal_dir)

    with patch("os.walk") as mock_walk, \
         patch("backend.sandbox.secure_backend.SecureSandboxBackend._is_reparse_point_or_link") as mock_islink:

        mock_walk.return_value = [
            (temp_workspace, ["sym_dir", "normal_dir"], [])
        ]

        def fake_islink(path, st=None):
            return "sym_dir" in path

        mock_islink.side_effect = fake_islink

        total, stats, exceeded = SecureSandboxBackend.measure_workspace_disk_usage(
            canonical_workspace=canonical_ws,
            max_disk_bytes=100000
        )

        assert stats["symlink_count"] >= 1


def test_disk_measurement_inaccessible_file_fails_closed(temp_workspace):
    """Inaccessible files must be handled conservatively and fail closed if max_disk_bytes configured."""
    test_file = os.path.join(temp_workspace, "unreadable.bin")
    with open(test_file, "w") as f:
        f.write("content")

    def mock_lstat(path):
        if "unreadable.bin" in path:
            raise PermissionError("Access denied: unreadable file")
        return os.lstat(path)

    with patch("os.lstat", side_effect=mock_lstat):
        total, stats, exceeded = SecureSandboxBackend.measure_workspace_disk_usage(
            canonical_workspace=temp_workspace,
            max_disk_bytes=500000
        )
        assert stats["inaccessible_count"] == 1
        assert len(stats["inaccessible_paths"]) == 1
        # Conservative: fail closed because disk usage cannot be verified
        assert exceeded is True


@patch("subprocess.Popen")
@patch("subprocess.run")
def test_backend_execute_fails_closed_on_inaccessible_workspace_file(mock_sub_run, mock_popen, temp_workspace):
    """ExecutionResult must fail closed with DISK_MEASUREMENT_INACCESSIBLE on permission errors."""
    proc_mock = MagicMock()
    proc_mock.communicate.return_value = (b"ok", b"")
    proc_mock.returncode = 0
    mock_popen.return_value = proc_mock

    test_file = os.path.join(temp_workspace, "secret.bin")
    with open(test_file, "w") as f:
        f.write("data")

    def mock_lstat(path):
        if "secret.bin" in path:
            raise PermissionError("Access denied")
        return os.lstat(path)

    backend = SecureSandboxBackend(
        policy=SandboxPolicy(max_disk_bytes=1024 * 1024),
        runtime_probe=MockProbeAvailable()
    )
    req = ExecutionRequest(
        command=["python", "script.py"],
        working_directory=temp_workspace,
        repository_trust="TRUSTED_DEVELOPMENT"
    )

    with patch("os.lstat", side_effect=mock_lstat):
        res = backend.execute(req, run_id="run-inaccessible-disk")

    assert res.policy_blocked is True
    assert res.exit_code == -1
    assert "DISK_MEASUREMENT_INACCESSIBLE" == res.backend_provenance.get("reason")
    assert "cannot be authoritatively verified" in res.stderr


@patch("subprocess.Popen")
@patch("subprocess.run")
def test_backend_execute_fails_closed_on_measurement_unexpected_error(mock_sub_run, mock_popen, temp_workspace):
    """Measurement unexpected error must fail closed with DISK_MEASUREMENT_ERROR and not permit execution."""
    proc_mock = MagicMock()
    proc_mock.communicate.return_value = (b"ok", b"")
    proc_mock.returncode = 0
    mock_popen.return_value = proc_mock

    backend = SecureSandboxBackend(
        policy=SandboxPolicy(max_disk_bytes=1024 * 1024),
        runtime_probe=MockProbeAvailable()
    )
    req = ExecutionRequest(
        command=["python", "script.py"],
        working_directory=temp_workspace,
        repository_trust="TRUSTED_DEVELOPMENT"
    )

    with patch.object(
        SecureSandboxBackend,
        "measure_workspace_disk_usage",
        side_effect=RuntimeError("Simulated filesystem I/O driver failure")
    ):
        res = backend.execute(req, run_id="run-measurement-error")

    assert res.policy_blocked is True
    assert res.exit_code == -1
    assert "DISK_MEASUREMENT_ERROR" == res.backend_provenance.get("reason")
    assert "could not be measured due to error" in res.stderr


def test_disk_measurement_filesystem_race_disappearing_file(temp_workspace):
    """Disappearing files during traversal (races) must be handled gracefully without crashing."""
    dummy_file = os.path.join(temp_workspace, "vanished.txt")
    with open(dummy_file, "w") as f:
        f.write("vanished")

    def mock_lstat(path):
        if "vanished.txt" in path:
            raise FileNotFoundError("File was deleted by race")
        return os.lstat(path)

    with patch("os.lstat", side_effect=mock_lstat):
        total, stats, exceeded = SecureSandboxBackend.measure_workspace_disk_usage(
            canonical_workspace=temp_workspace,
            max_disk_bytes=500000
        )
        assert stats["disappeared_count"] == 1
        assert exceeded is False


def test_disk_measurement_outside_root_traversal_skipped(temp_workspace):
    """Directory roots resolving outside canonical workspace must be aborted immediately."""
    canonical_ws = os.path.realpath(temp_workspace)
    outside_root = "C:\\outside\\host" if os.name == "nt" else "/outside/host"

    with patch("os.walk") as mock_walk:
        mock_walk.return_value = [
            (outside_root, ["sub"], ["external_file.bin"])
        ]
        total, stats, exceeded = SecureSandboxBackend.measure_workspace_disk_usage(
            canonical_workspace=canonical_ws,
            max_disk_bytes=500000
        )
        assert stats["outside_traversal_skipped"] == 1
        assert stats["file_count"] == 0
        assert total == 0


