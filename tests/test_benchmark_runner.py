"""
Unit & Security Tests for Benchmark Runner and Lifecycle Gates.

Validates:
1. Deterministic lifecycle progression: CREATED -> INTEGRITY_CHECK -> CAPABILITY_CHECK -> ...
2. Integrity Gate: Failed integrity check halts immediately with OPERATIONAL_FAILURE.
3. Capability Gate: Missing container engine (Docker/Podman) halts with OPERATIONAL_FAILURE.
4. Refusal of LocalDevelopmentBackend: Host execution is strictly blocked.
5. Incomplete / interrupted runs are never promoted to VERIFIED or COMPLETED.
6. Cancellation halts execution cleanly.
7. Zero candidate code execution on host.
"""

import os
import pytest
from pathlib import Path

from backend.benchmark.models import (
    BenchmarkRunConfig,
    BenchmarkRunState,
    BenchmarkVerdict,
    BenchmarkArmType,
)
from backend.benchmark.runner import BenchmarkRunner
from backend.benchmark.storage import BenchmarkRunRepository
from backend.sandbox.backend import LocalDevelopmentBackend
from backend.sandbox.secure_backend import SecureSandboxBackend, ContainerRuntimeProbe
from backend.sandbox.models import SandboxPolicy
from backend.sandbox.capabilities import SandboxCapabilities, SecurityLevel


class MockProbe:
    """Mock container runtime probe for testing capability gates."""
    def __init__(self, operational: bool, engine: str = "docker"):
        self.operational = operational
        self.engine = engine

    def detect_runtime(self):
        if self.operational:
            return True, self.engine, {"executable": f"/usr/bin/{self.engine}", "server_version": "26.0.0"}
        return False, "NONE", {"error": "Mocked daemon unavailable"}


@pytest.fixture
def temp_repo(tmp_path):
    """Provides an isolated SQLite benchmark repository for testing."""
    db_file = tmp_path / "test_benchmark.db"
    return BenchmarkRunRepository(db_path=str(db_file))


def test_runner_initializes_in_created_state(temp_repo):
    """A new runner instance must initialize and persist in CREATED state."""
    config = BenchmarkRunConfig(run_id="run_init_test", arm_type=BenchmarkArmType.SYNTHETIC)
    runner = BenchmarkRunner(config=config, repository=temp_repo)
    assert runner.record.state == BenchmarkRunState.CREATED
    persisted = temp_repo.get_run("run_init_test")
    assert persisted is not None
    assert persisted.state == BenchmarkRunState.CREATED


def test_runner_fails_closed_on_integrity_error(temp_repo):
    """Corrupted or invalid commit anchor must fail closed at INTEGRITY_CHECK."""
    config = BenchmarkRunConfig(
        run_id="run_bad_commit",
        target_commit_sha="0000000000000000000000000000000000000000",  # Invalid anchor!
        arm_type=BenchmarkArmType.SYNTHETIC
    )
    runner = BenchmarkRunner(config=config, repository=temp_repo)
    result = runner.run()

    assert result.state == BenchmarkRunState.OPERATIONAL_FAILURE
    assert "INTEGRITY_GATE_FAILED" in (result.error_message or "")
    # Must not have advanced to READY, RUNNING, or COMPLETED
    assert result.state != BenchmarkRunState.COMPLETED
    assert len(result.task_results) == 0


def test_runner_fails_closed_when_sandbox_backend_is_none(temp_repo):
    """Missing sandbox backend must fail closed at CAPABILITY_CHECK."""
    config = BenchmarkRunConfig(run_id="run_no_backend", arm_type=BenchmarkArmType.SYNTHETIC)
    runner = BenchmarkRunner(config=config, sandbox_backend=None, repository=temp_repo)
    result = runner.run()

    assert result.state == BenchmarkRunState.OPERATIONAL_FAILURE
    assert "CAPABILITY_GATE_FAILED" in (result.error_message or "")


def test_runner_fails_closed_on_local_development_backend(temp_repo):
    """LocalDevelopmentBackend must be strictly rejected fail-closed."""
    local_backend = LocalDevelopmentBackend(policy=SandboxPolicy())
    config = BenchmarkRunConfig(run_id="run_local_backend", arm_type=BenchmarkArmType.SYNTHETIC)
    runner = BenchmarkRunner(config=config, sandbox_backend=local_backend, repository=temp_repo)
    result = runner.run()

    assert result.state == BenchmarkRunState.OPERATIONAL_FAILURE
    assert "LocalDevelopmentBackend refused" in (result.error_message or "")


def test_runner_fails_closed_when_container_runtime_is_unavailable(temp_repo):
    """
    Requirement 1 & 3: When SecureSandboxBackend probes the host and finds no Docker/Podman runtime,
    it must truthfully report UNAVAILABLE, halt at CAPABILITY_CHECK, and produce complete
    task-level blocked outcomes (attempted=False) for every task in the verified manifest.
    No blocked task may be falsely marked as executed or verified.
    """
    failing_probe = MockProbe(operational=False)
    secure_backend = SecureSandboxBackend(policy=SandboxPolicy(), runtime_probe=failing_probe)

    config = BenchmarkRunConfig(run_id="run_missing_daemon", arm_type=BenchmarkArmType.SYNTHETIC)
    runner = BenchmarkRunner(config=config, sandbox_backend=secure_backend, repository=temp_repo)
    result = runner.run()

    # Overall run status must be OPERATIONAL_FAILURE
    assert result.state == BenchmarkRunState.OPERATIONAL_FAILURE
    assert "CAPABILITY_GATE_FAILED" in (result.error_message or "")
    assert "UNAVAILABLE" in (result.error_message or "")

    # Requirement 1: All 12 tasks from the verified manifest must have explicit blocked outcomes
    assert len(result.task_results) == 12, "Expected complete task-level records for all 12 tasks"
    for tid, tres in result.task_results.items():
        assert tres.verdict == BenchmarkVerdict.OPERATIONAL_FAILURE
        assert tres.operational_result == "OPERATIONAL_FAILURE"
        assert "BLOCKED_BEFORE_EXECUTION" in tres.failure_reason
        # Requirement 3: No blocked task is falsely marked as executed or verified
        assert tres.attempted is False, f"Task {tid} must have attempted=False"
        assert tres.vulnerability_neutralized is None
        assert tres.secure_acceptance_passed is None
        assert tres.regression_passed is None

    # Verify transactional database persistence
    persisted = temp_repo.get_run("run_missing_daemon")
    assert persisted is not None
    assert persisted.state == BenchmarkRunState.OPERATIONAL_FAILURE
    assert len(persisted.task_results) == 12
    for tid, tres in persisted.task_results.items():
        assert tres.attempted is False
        assert tres.verdict == BenchmarkVerdict.OPERATIONAL_FAILURE


def test_integrity_failure_does_not_trust_unverified_manifest(temp_repo):
    """
    Requirement 2: If integrity verification fails, manifest contents are unverified and untrusted.
    The runner must NOT use untrusted manifest contents to enumerate tasks.
    """
    config = BenchmarkRunConfig(
        run_id="run_tampered_manifest_gate",
        manifest_sha256="0000000000000000000000000000000000000000000000000000000000000000",
        arm_type=BenchmarkArmType.SYNTHETIC
    )
    runner = BenchmarkRunner(config=config, repository=temp_repo)
    result = runner.run()

    assert result.state == BenchmarkRunState.OPERATIONAL_FAILURE
    assert "INTEGRITY_GATE_FAILED" in (result.error_message or "")
    assert "Manifest contents are unverified and untrusted" in (result.error_message or "")
    # Zero task records must be enumerated from untrusted manifest
    assert len(result.task_results) == 0

    persisted = temp_repo.get_run("run_tampered_manifest_gate")
    assert persisted is not None
    assert len(persisted.task_results) == 0


def test_storage_preserves_stronger_evidence_against_operational_failure(temp_repo):
    """
    Repeated failure handling cannot duplicate task records or overwrite stronger evidence
    (VERIFIED / REJECTED).
    """
    from backend.benchmark.models import TaskEvaluationResult

    config = BenchmarkRunConfig(run_id="run_evidence_protect", arm_type=BenchmarkArmType.SYNTHETIC)
    runner = BenchmarkRunner(config=config, repository=temp_repo)

    # 1. Record a verified result (strong empirical evidence)
    strong_result = TaskEvaluationResult(
        task_id="SEC-BENCH-001",
        arm=BenchmarkArmType.SYNTHETIC.value,
        verdict=BenchmarkVerdict.VERIFIED,
        attempted=True,
        vulnerability_neutralized=True,
        secure_acceptance_passed=True,
        regression_passed=True
    )
    temp_repo.record_task_result("run_evidence_protect", strong_result)

    # 2. Attempt to overwrite with an operational failure
    weak_result = TaskEvaluationResult(
        task_id="SEC-BENCH-001",
        arm=BenchmarkArmType.SYNTHETIC.value,
        verdict=BenchmarkVerdict.OPERATIONAL_FAILURE,
        operational_result="OPERATIONAL_FAILURE",
        attempted=False,
        failure_reason="Late failure simulation"
    )
    temp_repo.record_task_result("run_evidence_protect", weak_result)

    # Verify the database preserved the stronger evidence
    persisted = temp_repo.get_run("run_evidence_protect")
    assert persisted is not None
    stored_t1 = persisted.task_results["SEC-BENCH-001"]
    assert stored_t1.verdict == BenchmarkVerdict.VERIFIED
    assert stored_t1.attempted is True

    # 3. Batch insert also preserves stronger evidence
    temp_repo.record_task_results_batch("run_evidence_protect", [weak_result])
    persisted_after_batch = temp_repo.get_run("run_evidence_protect")
    assert persisted_after_batch.task_results["SEC-BENCH-001"].verdict == BenchmarkVerdict.VERIFIED


def test_runner_synthetic_execution_progresses_cleanly(temp_repo):
    """
    When operational container runtime is mocked as available and SYNTHETIC arm is used,
    lifecycle advances cleanly from CREATED through to COMPLETED.
    """
    operational_probe = MockProbe(operational=True)
    secure_backend = SecureSandboxBackend(policy=SandboxPolicy(), runtime_probe=operational_probe)

    config = BenchmarkRunConfig(
        run_id="run_synthetic_success",
        arm_type=BenchmarkArmType.SYNTHETIC,
        tasks_selected=["SEC-BENCH-001", "SEC-BENCH-002"]
    )
    runner = BenchmarkRunner(config=config, sandbox_backend=secure_backend, repository=temp_repo)
    result = runner.run()

    assert result.state == BenchmarkRunState.COMPLETED
    assert len(result.task_results) == 2
    for tid, tres in result.task_results.items():
        assert tres.verdict == BenchmarkVerdict.VERIFIED
        assert tres.vulnerability_neutralized is True
        assert tres.secure_acceptance_passed is True
        assert tres.regression_passed is True

    # Confirm persistence
    persisted = temp_repo.get_run("run_synthetic_success")
    assert persisted is not None
    assert persisted.state == BenchmarkRunState.COMPLETED
    assert len(persisted.task_results) == 2


def test_runner_cancellation(temp_repo):
    """Cancellation request must set CANCELLED state and block further execution."""
    config = BenchmarkRunConfig(run_id="run_cancel_test", arm_type=BenchmarkArmType.SYNTHETIC)
    runner = BenchmarkRunner(config=config, repository=temp_repo)
    runner.cancel()

    assert runner.record.state == BenchmarkRunState.CANCELLED
    persisted = temp_repo.get_run("run_cancel_test")
    assert persisted.state == BenchmarkRunState.CANCELLED

    # Calling run() on cancelled run returns immediately
    result = runner.run()
    assert result.state == BenchmarkRunState.CANCELLED


def test_interrupted_run_recovery_never_promotes_to_verified(temp_repo):
    """
    Runs left in an interrupted non-terminal state (e.g. process crashed during RUNNING)
    must be recovered to OPERATIONAL_FAILURE, never marked COMPLETED or VERIFIED.
    """
    config = BenchmarkRunConfig(run_id="run_interrupted", arm_type=BenchmarkArmType.SYNTHETIC)
    runner = BenchmarkRunner(config=config, repository=temp_repo)
    # Manually simulate in-flight crash state
    temp_repo.update_run_state("run_interrupted", BenchmarkRunState.RUNNING)

    # Trigger process recovery
    recovered_count = temp_repo.recover_interrupted_runs()
    assert recovered_count == 1

    recovered = temp_repo.get_run("run_interrupted")
    assert recovered is not None
    assert recovered.state == BenchmarkRunState.OPERATIONAL_FAILURE
    assert "INTERRUPTED_PROCESS_RECOVERY" in (recovered.error_message or "")


def test_runner_failure_before_task_loading_when_loader_fails(temp_repo):
    """
    Finding 1: Operational failure before task loading (e.g. loader raises error)
    halts runner at TASK_VALIDATION_FAILED without enumerating partial or corrupted tasks.
    """
    from unittest.mock import MagicMock
    mock_loader = MagicMock()
    mock_loader.load_all_tasks.side_effect = RuntimeError("Simulated task definition parse error")

    operational_probe = MockProbe(operational=True)
    secure_backend = SecureSandboxBackend(policy=SandboxPolicy(), runtime_probe=operational_probe)

    config = BenchmarkRunConfig(run_id="run_loader_fail", arm_type=BenchmarkArmType.SYNTHETIC)
    runner = BenchmarkRunner(
        config=config,
        sandbox_backend=secure_backend,
        repository=temp_repo,
        task_loader=mock_loader
    )
    result = runner.run()

    assert result.state == BenchmarkRunState.OPERATIONAL_FAILURE
    assert "TASK_VALIDATION_FAILED" in (result.error_message or "")
    assert len(result.task_results) == 0

    persisted = temp_repo.get_run("run_loader_fail")
    assert persisted is not None
    assert persisted.state == BenchmarkRunState.OPERATIONAL_FAILURE
    assert len(persisted.task_results) == 0


def test_runner_failure_after_validated_task_loading_records_all_tasks(temp_repo):
    """
    Finding 1: Failure after validated task loading (e.g. non-synthetic arm execution
    refused fail-closed without live container engine) produces complete, truthful
    task-level audit outcomes with attempted=False and verdict=OPERATIONAL_FAILURE.
    """
    operational_probe = MockProbe(operational=True)
    secure_backend = SecureSandboxBackend(policy=SandboxPolicy(), runtime_probe=operational_probe)

    config = BenchmarkRunConfig(
        run_id="run_non_synthetic_fail_closed",
        arm_type=BenchmarkArmType.ARM_A_REDLINE,  # Non-synthetic arm
        tasks_selected=["SEC-BENCH-001", "SEC-BENCH-002"]
    )
    runner = BenchmarkRunner(config=config, sandbox_backend=secure_backend, repository=temp_repo)
    result = runner.run()

    # Run halts at OPERATIONAL_FAILURE without executing untrusted code on host
    assert result.state == BenchmarkRunState.OPERATIONAL_FAILURE
    assert "OPERATIONAL_FAILURE" in (result.error_message or "")
    assert len(result.task_results) == 2

    for tid in ["SEC-BENCH-001", "SEC-BENCH-002"]:
        tres = result.task_results[tid]
        assert tres.verdict == BenchmarkVerdict.OPERATIONAL_FAILURE
        assert tres.operational_result == "OPERATIONAL_FAILURE"
        assert tres.attempted is False
        assert "Live container-backed sandbox runtime is not provisioned" in tres.failure_reason
        # Not marked as rejected or insecure
        assert tres.vulnerability_neutralized is None
        assert tres.secure_acceptance_passed is None

    # Verify persistence
    persisted = temp_repo.get_run("run_non_synthetic_fail_closed")
    assert persisted is not None
    assert persisted.state == BenchmarkRunState.OPERATIONAL_FAILURE
    assert len(persisted.task_results) == 2


def test_repeated_failure_handling_is_idempotent(temp_repo):
    """
    Finding 1: Repeated calls to run() or repeated failure handling are idempotent
    and never duplicate task records or corrupt terminal state.
    """
    failing_probe = MockProbe(operational=False)
    secure_backend = SecureSandboxBackend(policy=SandboxPolicy(), runtime_probe=failing_probe)

    config = BenchmarkRunConfig(
        run_id="run_idempotent_test",
        arm_type=BenchmarkArmType.SYNTHETIC,
        tasks_selected=["SEC-BENCH-001", "SEC-BENCH-002"]
    )
    runner = BenchmarkRunner(config=config, sandbox_backend=secure_backend, repository=temp_repo)
    result_first = runner.run()

    assert result_first.state == BenchmarkRunState.OPERATIONAL_FAILURE
    assert len(result_first.task_results) == 2

    # Second invocation on terminal state must return immediately without duplicating or altering state
    result_second = runner.run()
    assert result_second.state == BenchmarkRunState.OPERATIONAL_FAILURE
    assert len(result_second.task_results) == 2
    assert result_second.updated_at == result_first.updated_at

    persisted = temp_repo.get_run("run_idempotent_test")
    assert persisted is not None
    assert len(persisted.task_results) == 2

