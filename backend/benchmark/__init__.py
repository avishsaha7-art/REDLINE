"""REDLINE benchmark package."""

from backend.benchmark.models import (
    BenchmarkRunState,
    BenchmarkVerdict,
    BenchmarkArmType,
    BenchmarkTaskMetadata,
    BenchmarkRunConfig,
    BenchmarkRunRecord,
    TaskEvaluationResult,
    ComparativeEvaluationSummary,
    BenchmarkReport,
)
from backend.benchmark.integrity import (
    BenchmarkIntegrityChecker,
    verify_dataset_anchor,
    DEFAULT_TRUSTED_ANCHOR,
)
from backend.benchmark.evaluator import (
    BenchmarkTaskLoader,
    DeterministicBenchmarkEvaluator,
)
from backend.benchmark.runner import BenchmarkRunner
from backend.benchmark.comparison import BenchmarkComparator
from backend.benchmark.report import BenchmarkReportGenerator

__all__ = [
    "BenchmarkRunState",
    "BenchmarkVerdict",
    "BenchmarkArmType",
    "BenchmarkTaskMetadata",
    "BenchmarkRunConfig",
    "BenchmarkRunRecord",
    "TaskEvaluationResult",
    "ComparativeEvaluationSummary",
    "BenchmarkReport",
    "BenchmarkIntegrityChecker",
    "verify_dataset_anchor",
    "DEFAULT_TRUSTED_ANCHOR",
    "BenchmarkTaskLoader",
    "DeterministicBenchmarkEvaluator",
    "BenchmarkRunner",
    "BenchmarkComparator",
    "BenchmarkReportGenerator",
]
