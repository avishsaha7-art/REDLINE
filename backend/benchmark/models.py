"""
Benchmark Models, Schemas, and Lifecycles for REDLINE.

Defines:
- BenchmarkRunState lifecycle states.
- BenchmarkVerdict and EvaluationStatus.
- BenchmarkTaskMetadata and manifest schemas.
- BenchmarkRunConfig and BenchmarkRunRecord.
- TaskEvaluationResult capturing deterministic 3-phase verdicts.
- ComparativeEvaluationSummary and BenchmarkReport models.
"""

from enum import Enum
from typing import Dict, Any, List, Optional
import datetime
import hashlib
from pydantic import BaseModel, Field, ConfigDict


class BenchmarkRunState(str, Enum):
    """
    Deterministic benchmark run lifecycle states.
    Terminal states block further advancement.
    """
    CREATED = "CREATED"
    INTEGRITY_CHECK = "INTEGRITY_CHECK"
    CAPABILITY_CHECK = "CAPABILITY_CHECK"
    READY = "READY"
    RUNNING = "RUNNING"
    EVALUATING = "EVALUATING"
    COMPLETED = "COMPLETED"
    OPERATIONAL_FAILURE = "OPERATIONAL_FAILURE"
    REJECTED = "REJECTED"
    INCONCLUSIVE = "INCONCLUSIVE"
    CANCELLED = "CANCELLED"
    ABORTED = "ABORTED"

    @property
    def is_terminal(self) -> bool:
        return self in (
            BenchmarkRunState.COMPLETED,
            BenchmarkRunState.OPERATIONAL_FAILURE,
            BenchmarkRunState.REJECTED,
            BenchmarkRunState.INCONCLUSIVE,
            BenchmarkRunState.CANCELLED,
            BenchmarkRunState.ABORTED,
        )


class BenchmarkVerdict(str, Enum):
    """Authoritative out-of-sandbox 4-way evaluation verdict."""
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    INCONCLUSIVE = "INCONCLUSIVE"
    OPERATIONAL_FAILURE = "OPERATIONAL_FAILURE"


class BenchmarkArmType(str, Enum):
    """Benchmark evaluation candidate arm type."""
    ARM_A_REDLINE = "ARM_A_REDLINE"
    ARM_B_VANILLA_BASELINE = "ARM_B_VANILLA_BASELINE"
    SYNTHETIC = "SYNTHETIC"
    CUSTOM = "CUSTOM"


class BenchmarkTaskMetadata(BaseModel):
    """Validated task metadata loaded from frozen dataset manifest."""
    task_id: str
    category: str
    cwe: str
    severity: str
    description: str
    fixture_files: List[str] = Field(default_factory=list)
    evaluator_files: List[str] = Field(default_factory=list)
    file_digests: Dict[str, str] = Field(default_factory=dict)
    resource_budget: Dict[str, Any] = Field(default_factory=dict)


class BenchmarkRunConfig(BaseModel):
    """Immutable configuration for a benchmark run."""
    model_config = ConfigDict(extra="forbid")
    run_id: str
    dataset_name: str = "REDLINE-Held-Out-Security-Benchmark"
    dataset_version: str = "1.0.0"
    target_commit_sha: str = "6e476bccaba2187055254d1cd71b539d7903b34f"
    manifest_sha256: str = "d2cd37b9a588151975c992426338b0341f39bc824e1627c32d51e02ed1ac20c2"
    annotated_tag: str = "benchmark-v1.0.0"
    arm_type: BenchmarkArmType = BenchmarkArmType.ARM_A_REDLINE
    tasks_selected: List[str] = Field(default_factory=list)  # Empty means all 12 tasks
    strict_working_tree: bool = True
    timeout_seconds_per_task: int = 120
    max_iterations_per_task: int = 10
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())


class TaskEvaluationResult(BaseModel):
    """Deterministic evaluation outcome for an individual benchmark task."""
    model_config = ConfigDict(extra="forbid")
    task_id: str
    arm: str
    verdict: BenchmarkVerdict
    attempted: bool = False
    operational_result: Optional[str] = None
    vulnerability_neutralized: Optional[bool] = None
    secure_acceptance_passed: Optional[bool] = None
    regression_passed: Optional[bool] = None
    execution_duration_ms: Optional[int] = None
    evaluation_duration_ms: Optional[int] = None
    patch_id: Optional[str] = None
    patch_sha256: Optional[str] = None
    evidence_hashes: Dict[str, str] = Field(default_factory=dict)
    failure_reason: Optional[str] = None
    sandbox_provenance: Dict[str, Any] = Field(default_factory=dict)


class BenchmarkRunRecord(BaseModel):
    """Full persistent record of a benchmark run and its task results."""
    run_id: str
    config: BenchmarkRunConfig
    state: BenchmarkRunState = BenchmarkRunState.CREATED
    integrity_result: Optional[Dict[str, Any]] = None
    capability_result: Optional[Dict[str, Any]] = None
    task_results: Dict[str, TaskEvaluationResult] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    completed_at: Optional[str] = None
    error_message: Optional[str] = None


class ComparativeEvaluationSummary(BaseModel):
    """Comparative analysis across two or more compatible benchmark runs."""
    comparison_id: str
    dataset_name: str
    dataset_version: str
    trust_anchor_commit: str
    manifest_sha256: str
    total_declared_tasks: int
    arm_metrics: Dict[str, Dict[str, Any]]  # arm_name -> metrics dict
    head_to_head_tasks: Dict[str, Dict[str, Any]]  # task_id -> {arm_name: verdict}
    statistical_limitation_disclaimer: str
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())


class BenchmarkReport(BaseModel):
    """Auditable, immutable benchmark report with cryptographic evidence links."""
    model_config = ConfigDict(extra="forbid")
    report_id: str
    schema_version: str = "1.0.0"
    run_id: str
    dataset_name: str
    dataset_version: str
    git_anchor_commit: str
    git_annotated_tag: str
    manifest_sha256: str
    runner_version: str = "1.0.0"
    evaluator_version: str = "1.0.0"
    sandbox_provenance: Dict[str, Any] = Field(default_factory=dict)
    config: BenchmarkRunConfig
    summary_metrics: Dict[str, Any] = Field(default_factory=dict)
    task_details: List[TaskEvaluationResult] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    disclaimer: str
    report_sha256: str = ""

    def canonical_bytes(self) -> bytes:
        """
        Produces deterministic canonical JSON bytes for digest calculation:
        - Excludes 'report_sha256' from the hashed payload.
        - Employs lexicographically sorted keys (sort_keys=True).
        - Uses compact separators without trailing whitespace (',', ':').
        - Uses UTF-8 encoding with unescaped Unicode characters (ensure_ascii=False).
        - Uses standard Python JSON number-formatting semantics.

        Note: This is a deterministic Python JSON serialization format tailored for
        internal repeatability and digest verification. It is not guaranteed to be
        cross-language RFC 8785 (JSON Canonicalization Scheme) compliant.
        """
        import json
        payload = self.model_dump(exclude={"report_sha256"}, mode="json")
        return json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

    def compute_digest(self) -> str:
        """
        Computes deterministic SHA-256 cryptographic integrity digest over the
        canonical report content excluding report_sha256.
        """
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    def verify_digest(self) -> bool:
        """
        Verifies that report_sha256 matches the recomputed canonical digest over
        the report payload. Returns True if valid, False if altered or missing.
        """
        if not self.report_sha256:
            return False
        import hmac
        expected = self.compute_digest()
        return hmac.compare_digest(self.report_sha256.lower(), expected.lower())
