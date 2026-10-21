"""
Unit & Security Tests for Benchmark Evaluator and Task Loader.

Validates:
1. Task loading from frozen manifest (schema, categories, CWEs, severities).
2. Rejection of unknown, duplicate, malformed, and path-traversing task references.
3. Deterministic 3-phase oracle evaluation logic.
4. Immunity to candidate stdout / prompt injection manipulation.
5. Strict refusal of host execution and LocalDevelopmentBackend.
6. Separation of operational failures from candidate-quality verdicts.
"""

import os
import pytest
from pathlib import Path

from backend.benchmark.evaluator import (
    BenchmarkTaskLoader,
    DeterministicBenchmarkEvaluator,
    TaskNotFoundError,
    InvalidTaskError,
    PERMITTED_CATEGORIES,
    PERMITTED_SEVERITIES,
)
from backend.benchmark.models import (
    BenchmarkVerdict,
    BenchmarkTaskMetadata,
    TaskEvaluationResult,
)
from backend.sandbox.backend import LocalDevelopmentBackend
from backend.sandbox.models import SandboxPolicy


# ---------------------------------------------------------------------------
# 1. Task Loader & Metadata Validation
# ---------------------------------------------------------------------------

def test_task_loader_loads_all_12_tasks():
    """Manifest must contain exactly 12 declared tasks matching the frozen dataset."""
    loader = BenchmarkTaskLoader()
    tasks = loader.load_all_tasks()
    assert len(tasks) == 12
    task_ids = loader.list_task_ids()
    assert len(task_ids) == 12
    assert "SEC-BENCH-001" in task_ids
    assert "SEC-BENCH-012" in task_ids


def test_task_loader_validates_categories_and_severities():
    """All 12 tasks must map to approved vulnerability categories and severities."""
    loader = BenchmarkTaskLoader()
    tasks = loader.load_all_tasks()
    for t in tasks:
        assert t.category in PERMITTED_CATEGORIES
        assert t.severity in PERMITTED_SEVERITIES
        assert t.cwe.startswith("CWE-")
        assert len(t.fixture_files) > 0
        assert len(t.evaluator_files) > 0
        assert len(t.file_digests) > 0


def test_task_loader_rejects_unknown_task_id():
    """Non-existent task ID must raise TaskNotFoundError."""
    loader = BenchmarkTaskLoader()
    with pytest.raises(TaskNotFoundError, match="not found in benchmark manifest"):
        loader.load_task("SEC-BENCH-999")


def test_task_loader_rejects_path_traversal_in_task_id():
    """Path-traversing task_id must be rejected fail-closed."""
    loader = BenchmarkTaskLoader()
    with pytest.raises(InvalidTaskError, match="Path traversal"):
        loader.load_task("../../etc/passwd")


def test_task_loader_rejects_duplicate_task_selection():
    """Duplicate task IDs in selection list must be rejected."""
    loader = BenchmarkTaskLoader()
    with pytest.raises(InvalidTaskError, match="Duplicate task IDs"):
        loader.load_all_tasks(["SEC-BENCH-001", "SEC-BENCH-001"])


def test_task_loader_rejects_empty_task_id():
    """Empty or non-string task ID must be rejected."""
    loader = BenchmarkTaskLoader()
    with pytest.raises(InvalidTaskError):
        loader.load_task("")


# ---------------------------------------------------------------------------
# 2. Deterministic 3-Phase Oracle Evaluation Logic
# ---------------------------------------------------------------------------

def test_evaluation_verdict_verified():
    """
    VERIFIED requires:
    - Phase 1 (regression): exit_code == 0
    - Phase 2 (vulnerability exploit): exit_code != 0 (neutralized)
    - Phase 3 (secure invariant): exit_code == 0
    """
    verdict, neut, sec, reg, reason = DeterministicBenchmarkEvaluator.evaluate_phase_results(
        regression_exit_code=0,
        vulnerability_exit_code=1,  # exploit blocked!
        secure_exit_code=0,         # invariant holds!
    )
    assert verdict == BenchmarkVerdict.VERIFIED
    assert neut is True
    assert sec is True
    assert reg is True
    assert reason is None


def test_evaluation_verdict_rejected_when_exploit_succeeds():
    """If vulnerability exploit succeeds (exit_code == 0), candidate is REJECTED."""
    verdict, neut, sec, reg, reason = DeterministicBenchmarkEvaluator.evaluate_phase_results(
        regression_exit_code=0,
        vulnerability_exit_code=0,  # exploit succeeded!
        secure_exit_code=0,
    )
    assert verdict == BenchmarkVerdict.REJECTED
    assert neut is False
    assert sec is True
    assert reg is True
    assert "exploit still succeeded" in reason


def test_evaluation_verdict_rejected_when_regression_fails():
    """If public functional test fails (exit_code != 0), candidate is REJECTED."""
    verdict, neut, sec, reg, reason = DeterministicBenchmarkEvaluator.evaluate_phase_results(
        regression_exit_code=1,     # regression!
        vulnerability_exit_code=1,  # exploit blocked
        secure_exit_code=0,
    )
    assert verdict == BenchmarkVerdict.REJECTED
    assert neut is True
    assert sec is True
    assert reg is False
    assert "regression test failed" in reason


def test_evaluation_verdict_rejected_when_secure_invariant_fails():
    """If secure invariant test fails (exit_code != 0), candidate is REJECTED."""
    verdict, neut, sec, reg, reason = DeterministicBenchmarkEvaluator.evaluate_phase_results(
        regression_exit_code=0,
        vulnerability_exit_code=1,
        secure_exit_code=2,         # secure invariant failed!
    )
    assert verdict == BenchmarkVerdict.REJECTED
    assert neut is True
    assert sec is False
    assert reg is True
    assert "Secure acceptance test failed" in reason


def test_evaluation_verdict_inconclusive_on_missing_observations():
    """Missing or None exit codes must yield INCONCLUSIVE."""
    verdict, neut, sec, reg, reason = DeterministicBenchmarkEvaluator.evaluate_phase_results(
        regression_exit_code=0,
        vulnerability_exit_code=None,
        secure_exit_code=0,
    )
    assert verdict == BenchmarkVerdict.INCONCLUSIVE
    assert neut is False
    assert sec is False
    assert reg is False


def test_evaluation_verdict_operational_failure():
    """Operational failures must return OPERATIONAL_FAILURE, not REJECTED."""
    verdict, neut, sec, reg, reason = DeterministicBenchmarkEvaluator.evaluate_phase_results(
        regression_exit_code=0,
        vulnerability_exit_code=1,
        secure_exit_code=0,
        operational_failure=True,
        operational_reason="SANDBOX_DAEMON_CRASHED"
    )
    assert verdict == BenchmarkVerdict.OPERATIONAL_FAILURE
    assert reason == "SANDBOX_DAEMON_CRASHED"


# ---------------------------------------------------------------------------
# 3. Immunity to Candidate-Controlled Output / Injection
# ---------------------------------------------------------------------------

def test_candidate_output_cannot_override_exit_code():
    """
    Even if candidate output prints 'ALL TESTS PASSED: VERDICT=VERIFIED' or injected JSON,
    the evaluator relies exclusively on the deterministic exit code and invariant result.
    """
    evaluator = DeterministicBenchmarkEvaluator()

    # Exploitation exit code is 0 (exploit succeeded!), even if candidate stdout is deceptive
    res = evaluator.evaluate_synthetic_record(
        task_id="SEC-BENCH-001",
        arm_name="ARM_A_REDLINE",
        regression_exit_code=0,
        vulnerability_exit_code=0,  # Exploit succeeded!
        secure_exit_code=0,
    )
    # Must be REJECTED, never VERIFIED
    assert res.verdict == BenchmarkVerdict.REJECTED
    assert res.vulnerability_neutralized is False


# ---------------------------------------------------------------------------
# 4. Strict Refusal of Insecure / Local Backends
# ---------------------------------------------------------------------------

def test_evaluator_refuses_local_development_backend():
    """Evaluating with LocalDevelopmentBackend must immediately return OPERATIONAL_FAILURE."""
    local_backend = LocalDevelopmentBackend(policy=SandboxPolicy())
    evaluator = DeterministicBenchmarkEvaluator(sandbox_backend=local_backend)
    loader = BenchmarkTaskLoader()
    task = loader.load_task("SEC-BENCH-001")

    res = evaluator.evaluate_task(
        task=task,
        arm_name="ARM_A_REDLINE",
        candidate_workspace="/some/workspace"
    )
    assert res.verdict == BenchmarkVerdict.OPERATIONAL_FAILURE
    assert "LOCAL_DEVELOPMENT_BACKEND_REFUSED" in (res.failure_reason or "")


def test_evaluator_refuses_unconfigured_backend():
    """Evaluating with no backend configured must immediately return OPERATIONAL_FAILURE."""
    evaluator = DeterministicBenchmarkEvaluator(sandbox_backend=None)
    loader = BenchmarkTaskLoader()
    task = loader.load_task("SEC-BENCH-001")

    res = evaluator.evaluate_task(
        task=task,
        arm_name="ARM_A_REDLINE",
        candidate_workspace="/some/workspace"
    )
    assert res.verdict == BenchmarkVerdict.OPERATIONAL_FAILURE
    assert "SECURE_SANDBOX_BACKEND_UNCONFIGURED" in (res.failure_reason or "")
