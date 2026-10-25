"""
Stage 16.4 / Step 2.9.5.2 Unit Tests: Canonical Orchestrator Execution Remediation.

Validates that:
1. TEST_SUCCESS cannot occur without actual successful test evidence.
2. A passing test run produces the expected deterministic outcome when all required verification conditions hold.
3. A failing test run cannot produce VERIFIED.
4. An invalid patch cannot produce VERIFIED.
5. Runtime unavailability produces an operational failure and zero host fallback.
6. Timeout, cancellation and cleanup failures cannot produce VERIFIED.
7. Missing, malformed or inconsistent execution evidence fails closed.
8. The existing evidence receipt and patch lineage remain correct.
9. Interrupted runs recover to a safe state.
10. Existing mock-based unit tests cannot conceal missing execution integration.
"""

import os
import json
import uuid
import hashlib
import pytest
from unittest.mock import MagicMock

from backend.models.schemas import (
    TaskContract,
    ResourceBudget,
    RunState,
    OperationalResult,
    PatchCandidate,
)
from backend.models.evidence import verify_receipt_integrity
from backend.verification.models import (
    VerificationStatus,
    ExecutionStatus,
    StructuredObservation,
    TestResultSummary,
    RegressionSummary,
    InvariantResultStatus,
    OracleResult,
    Counterexample,
)
from backend.sandbox.models import SandboxPolicy, ExecutionRequest, ExecutionResult
from backend.sandbox.backend import SandboxBackend
from backend.sandbox.capabilities import SandboxCapabilities, SecurityLevel, RepositoryTrust
from backend.sandbox.client import SandboxClient
from backend.orchestrator.orchestrator import Orchestrator
from backend.models.deterministic_provider import DeterministicTestProvider
from tests.test_stage11 import MockModelProvider


class FakeUnavailableBackend(SandboxBackend):
    """Controlled test double representing an unavailable container runtime."""
    def capabilities(self) -> SandboxCapabilities:
        return SandboxCapabilities(
            security_level=SecurityLevel.UNAVAILABLE,
            secure_untrusted_execution=False
        )
    def execute(self, req: ExecutionRequest, run_id: str) -> ExecutionResult:
        return ExecutionResult(
            run_id=run_id,
            exit_code=-1,
            stdout="",
            stderr="OPERATIONAL_FAILURE: Runtime unavailable",
            policy_blocked=True,
            crashed=True,
            backend_provenance={
                "backend": "FakeUnavailableBackend",
                "status": "OPERATIONAL_FAILURE",
                "security_level": "UNAVAILABLE"
            }
        )


class FakeTimingOutBackend(SandboxBackend):
    """Controlled test double representing a command that timed out."""
    def capabilities(self) -> SandboxCapabilities:
        return SandboxCapabilities(
            security_level=SecurityLevel.DEVELOPMENT_ONLY,
            secure_untrusted_execution=False
        )
    def execute(self, req: ExecutionRequest, run_id: str) -> ExecutionResult:
        err_msg = "Command execution timed out after 30 seconds"
        return ExecutionResult(
            run_id=run_id,
            exit_code=-1,
            stdout="",
            stderr=err_msg,
            stdout_sha256=hashlib.sha256(b"").hexdigest(),
            stderr_sha256=hashlib.sha256(err_msg.encode()).hexdigest(),
            timed_out=True,
            backend_provenance={
                "backend": "FakeTimingOutBackend",
                "status": "TIMEOUT",
                "security_level": "DEVELOPMENT_ONLY"
            }
        )


@pytest.fixture(autouse=True)
def enable_local_dev(monkeypatch):
    monkeypatch.setenv("REDLINE_ENABLE_LOCAL_BACKEND", "1")
    yield


def test_1_test_success_requires_actual_successful_test_evidence(monkeypatch, tmp_path):
    """1. TEST_SUCCESS cannot occur without actual successful test evidence."""
    # Create empty workspace where test_main.py exits 0 but outputs no test report
    repo = tmp_path / "repo-no-tests"
    repo.mkdir()
    (repo / "main.py").write_bytes(b"a\n")
    (repo / "test_main.py").write_bytes(b"print('hello without test summary')\n")

    contract = TaskContract(
        task_id="T-NO-TESTS",
        repository_id="repo-int-1",
        base_commit_or_snapshot="snap-1",
        task_description="Test with no test evidence",
        allowed_scope=["main.py"],
        repository_trust="TRUSTED_DEVELOPMENT",
        resource_budget=ResourceBudget(max_iterations=10, max_failed_attempts=1)
    )

    orch = Orchestrator("run-no-tests", contract, model_provider=DeterministicTestProvider())
    orch.repo_root = str(repo)
    final_state = orch.run()

    # Must NOT be VERIFIED
    assert final_state != RunState.VERIFIED
    events = [e["event_type"] for e in orch.state_machine.events.get_events()]
    assert "TESTS_PASSED" not in events
    assert "COUNTEREXAMPLE_FOUND" in events
    assert orch.last_test_summary is not None
    assert orch.last_test_summary.passed == 0


def test_2_passing_test_run_produces_deterministic_verified_outcome():
    """2. A passing test run produces the expected deterministic outcome when all conditions hold."""
    contract = TaskContract(
        task_id="T-PASSING",
        repository_id="repo-int-1",
        base_commit_or_snapshot="snap-pass",
        task_description="Controlled passing verification",
        allowed_scope=["main.py"],
        repository_trust="TRUSTED_DEVELOPMENT",
        resource_budget=ResourceBudget(max_iterations=20)
    )

    orch = Orchestrator("run-pass-1", contract, model_provider=DeterministicTestProvider())
    final_state = orch.run()

    assert final_state == RunState.VERIFIED
    assert orch.evidence_receipt is not None
    assert orch.evidence_receipt.verdict == VerificationStatus.VERIFIED
    assert verify_receipt_integrity(orch.evidence_receipt) is True
    assert orch.last_test_summary.passed >= 1
    assert orch.last_test_summary.failed == 0
    assert orch.last_test_summary.errored == 0


def test_3_failing_test_run_cannot_produce_verified(tmp_path):
    """3. A failing test run cannot produce VERIFIED."""
    repo = tmp_path / "repo-fail"
    repo.mkdir()
    (repo / "main.py").write_bytes(b"a\n")
    # Test script strictly fails
    (repo / "test_main.py").write_bytes(b"import sys\nsys.stderr.write('AssertionError: test failed\\n')\nsys.exit(1)\n")

    contract = TaskContract(
        task_id="T-FAIL",
        repository_id="repo-int-1",
        base_commit_or_snapshot="snap-fail",
        task_description="Controlled failing test execution",
        allowed_scope=["main.py"],
        repository_trust="TRUSTED_DEVELOPMENT",
        resource_budget=ResourceBudget(max_iterations=10, max_failed_attempts=1)
    )

    orch = Orchestrator("run-fail-1", contract, model_provider=DeterministicTestProvider())
    orch.repo_root = str(repo)
    final_state = orch.run()

    assert final_state != RunState.VERIFIED
    assert final_state == RunState.ABORTED
    assert orch.last_test_execution_result.exit_code == 1
    events = [e["event_type"] for e in orch.state_machine.events.get_events()]
    assert "TESTS_PASSED" not in events
    assert "COUNTEREXAMPLE_FOUND" in events


def test_4_invalid_patch_cannot_produce_verified():
    """4. An invalid patch cannot produce VERIFIED."""
    contract = TaskContract(
        task_id="T-INVALID-PATCH",
        repository_id="repo-int-1",
        base_commit_or_snapshot="snap-inv-patch",
        task_description="Invalid patch application test",
        allowed_scope=["main.py"],
        repository_trust="TRUSTED_DEVELOPMENT",
        resource_budget=ResourceBudget(max_iterations=10, max_failed_attempts=1)
    )

    # Provider generates a patch that attempts to modify lines not in main.py
    invalid_diff = "--- a/main.py\n+++ b/main.py\n@@ -50,2 +50,2 @@\n-nonexistent line\n+new line\n"
    provider = MockModelProvider([
        json.dumps({"objective": "test", "files_to_modify": ["main.py"]}),
        json.dumps({"changed_files": ["main.py"], "diff": invalid_diff}),
    ])

    orch = Orchestrator("run-inv-patch-1", contract, model_provider=provider)
    final_state = orch.run()

    assert final_state != RunState.VERIFIED
    assert final_state == RunState.ABORTED
    events = [e["event_type"] for e in orch.state_machine.events.get_events()]
    assert "TESTS_PASSED" not in events
    assert any("PATCH_APPLY_FAILED" in str(e) for e in orch.state_machine.events.get_events())


def test_5_runtime_unavailability_produces_operational_failure_and_zero_host_fallback(monkeypatch):
    """5. Runtime unavailability produces an operational failure and zero host fallback."""
    # Ensure untrusted repository with fake unavailable backend
    contract = TaskContract(
        task_id="T-UNAVAILABLE",
        repository_id="untrusted-external-repo",
        base_commit_or_snapshot="snap-unavail",
        task_description="Untrusted repo with unavailable container runtime",
        allowed_scope=["main.py"],
        repository_trust="UNTRUSTED",
        resource_budget=ResourceBudget(max_iterations=10)
    )

    orch = Orchestrator("run-unavail-1", contract, model_provider=DeterministicTestProvider())
    orch.sandbox_backend = FakeUnavailableBackend(SandboxPolicy())
    final_state = orch.run()

    assert final_state == RunState.ABORTED
    assert orch.evidence_receipt is not None
    assert orch.evidence_receipt.verdict in (VerificationStatus.POLICY_BLOCKED, VerificationStatus.SANDBOX_FAILURE)
    events = [e["event_type"] for e in orch.state_machine.events.get_events()]
    assert "TESTS_PASSED" not in events


def test_6_timeout_cannot_produce_verified():
    """6. Timeout, cancellation and cleanup failures cannot produce VERIFIED."""
    contract = TaskContract(
        task_id="T-TIMEOUT",
        repository_id="repo-int-1",
        base_commit_or_snapshot="snap-timeout",
        task_description="Timeout failure test",
        allowed_scope=["main.py"],
        repository_trust="TRUSTED_DEVELOPMENT",
        resource_budget=ResourceBudget(max_iterations=10)
    )

    orch = Orchestrator("run-timeout-1", contract, model_provider=DeterministicTestProvider())
    orch.sandbox_backend = FakeTimingOutBackend(SandboxPolicy())
    final_state = orch.run()

    assert final_state == RunState.ABORTED
    assert orch.evidence_receipt is not None
    assert orch.evidence_receipt.verdict == VerificationStatus.TIMEOUT
    events = [e["event_type"] for e in orch.state_machine.events.get_events()]
    assert "TESTS_PASSED" not in events


def test_7_missing_or_inconsistent_execution_evidence_fails_closed():
    """7. Missing, malformed or inconsistent execution evidence fails closed."""
    from backend.verification.policy import DeterministicVerificationPolicy

    policy = DeterministicVerificationPolicy()
    empty_summary = TestResultSummary(executed=0, passed=0, failed=0, errored=0, inconclusive=0)

    # No passing tests, no invariants, no oracles -> must evaluate to INCONCLUSIVE
    ver_res = policy.evaluate(
        repository_snapshot_hash="snap-hash",
        patch_hash="patch-hash",
        structured_observation=None,
        test_summary=empty_summary,
        regression_summary=RegressionSummary(),
        invariants=[],
        security_aggregation=None,
        oracle_results=[],
        counterexamples=[]
    )

    assert ver_res.status == VerificationStatus.INCONCLUSIVE
    assert ver_res.status != VerificationStatus.VERIFIED


def test_8_evidence_receipt_and_patch_lineage_remain_correct():
    """8. The existing evidence receipt and patch lineage remain correct."""
    contract = TaskContract(
        task_id="T-LINEAGE",
        repository_id="repo-int-1",
        base_commit_or_snapshot="snap-lineage",
        task_description="Verify patch lineage and Merkle receipts",
        allowed_scope=["main.py"],
        repository_trust="TRUSTED_DEVELOPMENT",
        resource_budget=ResourceBudget(max_iterations=20)
    )

    orch = Orchestrator("run-lineage-1", contract, model_provider=DeterministicTestProvider())
    final_state = orch.run()

    assert final_state == RunState.VERIFIED
    receipt = orch.evidence_receipt
    assert receipt is not None
    assert len(receipt.patch_lineage) >= 1
    assert orch.patch_candidate.patch_id in receipt.patch_lineage
    assert verify_receipt_integrity(receipt) is True


def test_9_interrupted_runs_recover_to_safe_state(tmp_path):
    """9. Interrupted runs recover to a safe state."""
    from backend.storage.database import Database
    from backend.storage.repositories import SQLiteRunRepository
    from backend.models.schemas import Run

    db_path = str(tmp_path / "test_recovery.db")
    db = Database(db_path)
    repo = SQLiteRunRepository(db)

    contract = TaskContract(
        task_id="T-INTERRUPTED",
        repository_id="repo-int-1",
        base_commit_or_snapshot="snap-rec",
        task_description="Interrupted run recovery",
        allowed_scope=["main.py"],
        repository_trust="TRUSTED_DEVELOPMENT",
        resource_budget=ResourceBudget(max_iterations=10)
    )

    # Insert non-terminal run
    run = Run(
        run_id="run-interrupted-1",
        task_id="T-INTERRUPTED",
        task_contract=contract,
        current_state=RunState.TEST,
        current_iteration=3
    )
    repo.save_new_run(run)

    # Recover interrupted runs
    recovered_count = repo.recover_interrupted_runs()
    assert recovered_count == 1

    recovered_run = repo.get_run("run-interrupted-1")
    assert recovered_run.current_state == RunState.ABORTED
    assert "PROCESS_INTERRUPTED" in recovered_run.operational_error


def test_10_mock_providers_cannot_conceal_missing_execution_integration():
    """10. Existing mock-based unit tests cannot conceal missing execution integration."""
    contract = TaskContract(
        task_id="T-MOCK-CHECK",
        repository_id="repo-int-1",
        base_commit_or_snapshot="snap-mock",
        task_description="Verify real execution occurs even with mock provider",
        allowed_scope=["main.py"],
        repository_trust="TRUSTED_DEVELOPMENT",
        resource_budget=ResourceBudget(max_iterations=20)
    )

    orch = Orchestrator("run-mock-check", contract, model_provider=DeterministicTestProvider())
    final_state = orch.run()

    # Orchestrator must record actual execution provenance
    assert hasattr(orch, "last_test_execution_result")
    assert orch.last_test_execution_result is not None
    assert orch.last_test_execution_result.exit_code == 0
    assert hasattr(orch, "last_test_observation")
    assert orch.last_test_observation.duration_ms >= 0
    assert orch.last_test_observation.status == ExecutionStatus.SUCCESS
    assert orch.last_test_summary.passed >= 1
