"""
Unit & Security Tests for Comparative Benchmark Evaluation.

Validates:
1. Incompatible benchmark runs (mismatched dataset, commit anchor, manifest) are rejected.
2. Operational failures are strictly separated from candidate-quality metrics.
3. Pass rate denominators are mathematically correct and explicitly documented (n=12).
4. Head-to-head comparison matrix accurately reflects task outcomes.
5. Mandatory statistical limitation disclaimer is present.
"""

import pytest
from backend.benchmark.models import (
    BenchmarkRunConfig,
    BenchmarkRunRecord,
    BenchmarkRunState,
    BenchmarkVerdict,
    BenchmarkArmType,
    TaskEvaluationResult,
)
from backend.benchmark.comparison import (
    BenchmarkComparator,
    IncompatibleBenchmarkRunError,
)


def make_test_run(
    run_id: str,
    arm_type: BenchmarkArmType,
    task_outcomes: dict,
    dataset_name: str = "REDLINE-Held-Out-Security-Benchmark",
    dataset_version: str = "1.0.0",
    commit_sha: str = "6e476bccaba2187055254d1cd71b539d7903b34f",
    manifest_sha: str = "d2cd37b9a588151975c992426338b0341f39bc824e1627c32d51e02ed1ac20c2",
) -> BenchmarkRunRecord:
    config = BenchmarkRunConfig(
        run_id=run_id,
        dataset_name=dataset_name,
        dataset_version=dataset_version,
        target_commit_sha=commit_sha,
        manifest_sha256=manifest_sha,
        arm_type=arm_type,
    )
    record = BenchmarkRunRecord(
        run_id=run_id,
        config=config,
        state=BenchmarkRunState.COMPLETED,
    )
    for tid, verdict in task_outcomes.items():
        is_verified = (verdict == BenchmarkVerdict.VERIFIED)
        is_op_fail = (verdict == BenchmarkVerdict.OPERATIONAL_FAILURE)
        record.task_results[tid] = TaskEvaluationResult(
            task_id=tid,
            arm=arm_type.value,
            verdict=verdict,
            vulnerability_neutralized=is_verified,
            secure_acceptance_passed=is_verified,
            regression_passed=not is_op_fail,
            execution_duration_ms=100,
            evaluation_duration_ms=50,
        )
    return record


def test_comparison_rejects_mismatched_dataset_name():
    """Mismatched dataset name must raise IncompatibleBenchmarkRunError."""
    r1 = make_test_run("r1", BenchmarkArmType.ARM_A_REDLINE, {}, dataset_name="SetA")
    r2 = make_test_run("r2", BenchmarkArmType.ARM_B_VANILLA_BASELINE, {}, dataset_name="SetB")

    with pytest.raises(IncompatibleBenchmarkRunError, match="Dataset name mismatch"):
        BenchmarkComparator.compare_runs([r1, r2])


def test_comparison_rejects_mismatched_commit_anchor():
    """Mismatched git commit anchor must raise IncompatibleBenchmarkRunError."""
    r1 = make_test_run("r1", BenchmarkArmType.ARM_A_REDLINE, {}, commit_sha="aaaa" * 10)
    r2 = make_test_run("r2", BenchmarkArmType.ARM_B_VANILLA_BASELINE, {}, commit_sha="bbbb" * 10)

    with pytest.raises(IncompatibleBenchmarkRunError, match="commit anchor mismatch"):
        BenchmarkComparator.compare_runs([r1, r2])


def test_comparison_rejects_mismatched_manifest_digest():
    """Mismatched manifest digest must raise IncompatibleBenchmarkRunError."""
    r1 = make_test_run("r1", BenchmarkArmType.ARM_A_REDLINE, {}, manifest_sha="1111" * 16)
    r2 = make_test_run("r2", BenchmarkArmType.ARM_B_VANILLA_BASELINE, {}, manifest_sha="2222" * 16)

    with pytest.raises(IncompatibleBenchmarkRunError, match="Manifest SHA-256 digest mismatch"):
        BenchmarkComparator.compare_runs([r1, r2])


def test_metrics_computation_separates_operational_failures():
    """
    Operational failures must be reported separately and excluded from candidate
    resolution rate denominator.
    """
    # 6 VERIFIED, 3 REJECTED, 3 OPERATIONAL_FAILURE out of 12
    outcomes = {
        f"SEC-BENCH-{i:03d}": BenchmarkVerdict.VERIFIED for i in range(1, 7)
    }
    outcomes.update({
        f"SEC-BENCH-{i:03d}": BenchmarkVerdict.REJECTED for i in range(7, 10)
    })
    outcomes.update({
        f"SEC-BENCH-{i:03d}": BenchmarkVerdict.OPERATIONAL_FAILURE for i in range(10, 13)
    })

    run = make_test_run("run_mixed", BenchmarkArmType.ARM_A_REDLINE, outcomes)
    metrics = BenchmarkComparator.compute_arm_metrics(run, total_declared_tasks=12)

    assert metrics["verified_count"] == 6
    assert metrics["rejected_count"] == 3
    assert metrics["operational_failure_count"] == 3

    # Benchmark pass rate = 6 / 12 = 0.5000 (50%)
    assert metrics["benchmark_pass_rate"] == 0.5

    # Candidate resolution rate = 6 / 9 (only evaluated tasks, excluding operational failures) = 0.6667
    assert metrics["candidate_resolution_rate"] == 0.6667
    assert "n=12" in metrics["denominator_definitions"]["benchmark_pass_rate_denominator"]


def test_comparative_summary_head_to_head_matrix():
    """Head-to-head comparison matrix must accurately align task verdicts."""
    outcomes_a = {
        "SEC-BENCH-001": BenchmarkVerdict.VERIFIED,
        "SEC-BENCH-002": BenchmarkVerdict.VERIFIED,
    }
    outcomes_b = {
        "SEC-BENCH-001": BenchmarkVerdict.REJECTED,
        "SEC-BENCH-002": BenchmarkVerdict.VERIFIED,
    }

    run_a = make_test_run("run_a", BenchmarkArmType.ARM_A_REDLINE, outcomes_a)
    run_b = make_test_run("run_b", BenchmarkArmType.ARM_B_VANILLA_BASELINE, outcomes_b)

    summary = BenchmarkComparator.compare_runs([run_a, run_b], total_declared_tasks=12)

    assert len(summary.arm_metrics) == 2
    assert "SEC-BENCH-001" in summary.head_to_head_tasks
    assert "SEC-BENCH-002" in summary.head_to_head_tasks

    # Verify head to head verdicts
    arm_a_key = "ARM_A_REDLINE (run_a)"
    arm_b_key = "ARM_B_VANILLA_BASELINE (run_b)"

    assert summary.head_to_head_tasks["SEC-BENCH-001"][arm_a_key] == "VERIFIED"
    assert summary.head_to_head_tasks["SEC-BENCH-001"][arm_b_key] == "REJECTED"
    assert summary.head_to_head_tasks["SEC-BENCH-002"][arm_a_key] == "VERIFIED"
    assert summary.head_to_head_tasks["SEC-BENCH-002"][arm_b_key] == "VERIFIED"

    # Confirm mandatory non-statistical disclaimer
    assert "n=12" in summary.statistical_limitation_disclaimer
    assert "statistical significance" in summary.statistical_limitation_disclaimer
