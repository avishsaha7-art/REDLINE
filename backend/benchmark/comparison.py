"""
Comparative Benchmark Evaluation for REDLINE.

Compares completed benchmark runs across arms/configurations.
Enforces:
1. Strict run compatibility check (same dataset, commit anchor, and manifest hash).
2. Separation of operational failures from candidate-quality metrics.
3. Explicit, mathematically rigorous denominator documentation for all rates.
4. Mandatory non-statistical limitation disclaimer.
"""

import uuid
import datetime
from typing import Dict, Any, List, Optional

from backend.benchmark.models import (
    BenchmarkRunRecord,
    ComparativeEvaluationSummary,
    BenchmarkVerdict,
)


class IncompatibleBenchmarkRunError(Exception):
    """Raised when attempting to compare benchmark runs with mismatched datasets or anchors."""
    pass


class BenchmarkComparator:
    """
    Analyzes and compares two or more benchmark runs.
    """
    STATISTICAL_DISCLAIMER = (
        "Notice: The evaluation set contains n=12 tasks across 12 distinct CWE vulnerability classes. "
        "Results demonstrate concrete comparative performance on this held-out set and do not assert "
        "statistical significance for general population extrapolation."
    )

    @classmethod
    def validate_compatibility(cls, runs: List[BenchmarkRunRecord]) -> None:
        """
        Ensures all runs evaluated against the exact same dataset version,
        commit anchor, and manifest digest.
        """
        if not runs or len(runs) < 2:
            raise ValueError("At least two benchmark runs are required for comparative evaluation.")

        first = runs[0].config
        for other in runs[1:]:
            cfg = other.config
            if cfg.dataset_name != first.dataset_name:
                raise IncompatibleBenchmarkRunError(
                    f"Dataset name mismatch: '{cfg.dataset_name}' vs '{first.dataset_name}'"
                )
            if cfg.dataset_version != first.dataset_version:
                raise IncompatibleBenchmarkRunError(
                    f"Dataset version mismatch: '{cfg.dataset_version}' vs '{first.dataset_version}'"
                )
            if cfg.target_commit_sha.lower() != first.target_commit_sha.lower():
                raise IncompatibleBenchmarkRunError(
                    f"Target commit anchor mismatch: '{cfg.target_commit_sha}' vs '{first.target_commit_sha}'"
                )
            if cfg.manifest_sha256.lower() != first.manifest_sha256.lower():
                raise IncompatibleBenchmarkRunError(
                    f"Manifest SHA-256 digest mismatch: '{cfg.manifest_sha256}' vs '{first.manifest_sha256}'"
                )

    @classmethod
    def compute_arm_metrics(
        cls, run: BenchmarkRunRecord, total_declared_tasks: int = 12
    ) -> Dict[str, Any]:
        """
        Computes granular metrics for a benchmark run.
        Explicitly separates operational failures and documents all denominators.
        """
        results = list(run.task_results.values())
        task_count = len(results)

        verified = sum(1 for r in results if r.verdict == BenchmarkVerdict.VERIFIED)
        rejected = sum(1 for r in results if r.verdict == BenchmarkVerdict.REJECTED)
        inconclusive = sum(1 for r in results if r.verdict == BenchmarkVerdict.INCONCLUSIVE)
        operational_failures = sum(1 for r in results if r.verdict == BenchmarkVerdict.OPERATIONAL_FAILURE)

        attempted_tasks = sum(1 for r in results if getattr(r, "attempted", False))
        blocked_tasks = sum(1 for r in results if not getattr(r, "attempted", False) and r.verdict == BenchmarkVerdict.OPERATIONAL_FAILURE)

        neutralized = sum(1 for r in results if r.vulnerability_neutralized is True)
        secure_passed = sum(1 for r in results if r.secure_acceptance_passed is True)
        regressions = sum(1 for r in results if r.regression_passed is False and r.verdict != BenchmarkVerdict.OPERATIONAL_FAILURE)

        exec_times = [r.execution_duration_ms for r in results if r.execution_duration_ms is not None]
        eval_times = [r.evaluation_duration_ms for r in results if r.evaluation_duration_ms is not None]

        # Valid denominator definition
        # Benchmark Pass Rate = verified / total_declared_tasks (n=12)
        denom_all = total_declared_tasks if total_declared_tasks > 0 else 12
        pass_rate_all = round(verified / denom_all, 4)

        # Candidate Evaluation Rate = verified / evaluated_tasks (excluding operational failures)
        evaluated_tasks_count = verified + rejected + inconclusive
        eval_rate = round(verified / evaluated_tasks_count, 4) if evaluated_tasks_count > 0 else None

        return {
            "run_id": run.run_id,
            "arm_type": run.config.arm_type.value,
            "state": run.state.value,
            "total_declared_tasks": denom_all,
            "total_evaluated_tasks": task_count,
            "total_attempted_tasks": attempted_tasks,
            "total_blocked_tasks": blocked_tasks,
            "verified_count": verified,
            "rejected_count": rejected,
            "inconclusive_count": inconclusive,
            "operational_failure_count": operational_failures,
            "vulnerability_neutralized_count": neutralized,
            "secure_acceptance_passed_count": secure_passed,
            "functional_regression_count": regressions,
            "benchmark_pass_rate": pass_rate_all,
            "candidate_resolution_rate": eval_rate,
            "denominator_definitions": {
                "benchmark_pass_rate_denominator": f"Total declared tasks (n={denom_all})",
                "candidate_resolution_rate_denominator": f"Evaluated tasks excluding operational failures (n={evaluated_tasks_count})",
                "operational_failure_policy": "Operational failures are recorded separately and excluded from candidate code resolution rate."
            },
            "durations": {
                "total_execution_ms": sum(exec_times),
                "avg_execution_ms": round(sum(exec_times) / len(exec_times), 2) if exec_times else 0,
                "total_evaluation_ms": sum(eval_times),
                "avg_evaluation_ms": round(sum(eval_times) / len(eval_times), 2) if eval_times else 0,
            }
        }

    @classmethod
    def compare_runs(
        cls, runs: List[BenchmarkRunRecord], total_declared_tasks: int = 12
    ) -> ComparativeEvaluationSummary:
        """
        Compares multiple runs, generating head-to-head outcomes and summary metrics.
        """
        cls.validate_compatibility(runs)

        first_config = runs[0].config
        arm_metrics: Dict[str, Dict[str, Any]] = {}
        head_to_head: Dict[str, Dict[str, Any]] = {}

        # Collect unique task IDs across all runs
        all_task_ids = set()
        for r in runs:
            all_task_ids.update(r.task_results.keys())

        # Build head-to-head matrix
        for tid in sorted(all_task_ids):
            head_to_head[tid] = {}
            for r in runs:
                arm_label = f"{r.config.arm_type.value} ({r.run_id[:8]})"
                t_res = r.task_results.get(tid)
                if not t_res:
                    head_to_head[tid][arm_label] = "NOT_EVALUATED"
                elif not getattr(t_res, "attempted", False) and t_res.verdict == BenchmarkVerdict.OPERATIONAL_FAILURE:
                    head_to_head[tid][arm_label] = "BLOCKED (OPERATIONAL_FAILURE)"
                else:
                    head_to_head[tid][arm_label] = t_res.verdict.value

        # Calculate metrics for each run
        for r in runs:
            arm_label = f"{r.config.arm_type.value} ({r.run_id[:8]})"
            arm_metrics[arm_label] = cls.compute_arm_metrics(r, total_declared_tasks)

        return ComparativeEvaluationSummary(
            comparison_id=f"comp_{uuid.uuid4().hex[:12]}",
            dataset_name=first_config.dataset_name,
            dataset_version=first_config.dataset_version,
            trust_anchor_commit=first_config.target_commit_sha,
            manifest_sha256=first_config.manifest_sha256,
            total_declared_tasks=total_declared_tasks,
            arm_metrics=arm_metrics,
            head_to_head_tasks=head_to_head,
            statistical_limitation_disclaimer=cls.STATISTICAL_DISCLAIMER,
        )
