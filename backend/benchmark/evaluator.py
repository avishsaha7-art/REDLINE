"""
Deterministic Benchmark Evaluator for REDLINE.

Implements:
1. BenchmarkTaskLoader: Validates task metadata, categories, CWEs, and paths against
   the frozen held-out benchmark dataset manifest.
2. DeterministicBenchmarkEvaluator: Executes out-of-sandbox 3-phase oracle evaluation:
   - Phase 1: Public Functional Regression (test_public.py) -> exit_code == 0
   - Phase 2: Vulnerability Exploitation (test_vulnerability.py) -> exit_code != 0 (neutralized)
   - Phase 3: Secure Acceptance Invariant (test_secure.py) -> exit_code == 0
3. Deterministic 4-way verdict assignment (VERIFIED, REJECTED, INCONCLUSIVE, OPERATIONAL_FAILURE).
   Candidate stdout/model text CANNOT override exit codes or invariants.
"""

import os
import json
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from backend.benchmark.models import (
    BenchmarkTaskMetadata,
    BenchmarkVerdict,
    TaskEvaluationResult,
)
from backend.sandbox.backend import SandboxBackend, LocalDevelopmentBackend
from backend.sandbox.models import ExecutionRequest, ExecutionResult, SandboxPolicy
from backend.sandbox.capabilities import SecurityLevel, RepositoryTrust

# Frozen dataset taxonomy constants
PERMITTED_CATEGORIES = {
    "SQL_INJECTION",
    "PATH_TRAVERSAL",
    "RACE_CONDITION",
    "AUTH_BYPASS",
    "AUTHORIZATION",
    "CACHE_INVALIDATION",
    "RESOURCE_LEAK",
    "COMMAND_INJECTION",
    "DUPLICATE_TRANSACTION",
    "UNBOUNDED_PAGINATION",
    "PRIVILEGE_ESCALATION",
    "SECRET_LEAKAGE",
}

PERMITTED_SEVERITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}


class BenchmarkTaskError(Exception):
    """Base exception for benchmark task loading and validation errors."""
    pass


class TaskNotFoundError(BenchmarkTaskError):
    """Raised when a task ID is not found in the frozen dataset manifest."""
    pass


class InvalidTaskError(BenchmarkTaskError):
    """Raised when task metadata or paths violate schema or security bounds."""
    pass


class BenchmarkTaskLoader:
    """
    Loads and validates task definitions from the frozen benchmark dataset manifest.
    Prevents directory traversal, unknown tasks, and out-of-dataset references.
    """
    def __init__(self, dataset_root: Optional[str] = None):
        if dataset_root:
            self.dataset_root = Path(dataset_root).resolve()
        else:
            repo_root = os.environ.get("REDLINE_REPO_ROOT")
            if not repo_root:
                repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            self.dataset_root = Path(repo_root) / "backend" / "benchmark" / "dataset"
        
        self.manifest_path = self.dataset_root / "manifest.json"

    def load_manifest(self) -> Dict[str, Any]:
        """Loads and parses manifest.json from dataset root."""
        if not self.manifest_path.is_file():
            raise BenchmarkTaskError(f"Benchmark manifest not found at: {self.manifest_path}")
        try:
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            raise BenchmarkTaskError(f"Failed to parse benchmark manifest: {str(e)}")

    def list_task_ids(self) -> List[str]:
        """Returns ordered list of all declared task IDs."""
        manifest = self.load_manifest()
        return [task["task_id"] for task in manifest.get("tasks", [])]

    def load_task(self, task_id: str) -> BenchmarkTaskMetadata:
        """
        Validates and returns metadata for a single task.
        Rejects invalid IDs, unknown tasks, and path traversal attempts.
        """
        if not task_id or not isinstance(task_id, str):
            raise InvalidTaskError("Task ID must be a non-empty string")
        
        # Prevent traversal in task_id
        if ".." in task_id or "/" in task_id or "\\" in task_id:
            raise InvalidTaskError(f"Path traversal detected in task_id: {task_id}")

        manifest = self.load_manifest()
        matching = [t for t in manifest.get("tasks", []) if t.get("task_id") == task_id]
        if not matching:
            raise TaskNotFoundError(f"Task '{task_id}' not found in benchmark manifest")
        
        raw = matching[0]

        # Validate category
        category = raw.get("category", "")
        if category not in PERMITTED_CATEGORIES:
            raise InvalidTaskError(f"Task '{task_id}' has unrecognized category: '{category}'")

        # Validate severity
        severity = raw.get("severity", "")
        if severity not in PERMITTED_SEVERITIES:
            raise InvalidTaskError(f"Task '{task_id}' has unrecognized severity: '{severity}'")

        # Validate file paths in file_digests
        digests = raw.get("file_digests", {})
        for rel_file in digests.keys():
            norm = rel_file.replace("\\", "/")
            if ".." in norm.split("/") or os.path.isabs(rel_file) or norm.startswith("/"):
                raise InvalidTaskError(f"Path traversal forbidden in task '{task_id}' file: {rel_file}")

        fixture_files = raw.get("fixture_files") or [f for f in digests.keys() if f.startswith("fixtures/")]
        evaluator_files = raw.get("evaluator_files") or [f for f in digests.keys() if f.startswith("evaluators/")]

        return BenchmarkTaskMetadata(
            task_id=raw["task_id"],
            category=category,
            cwe=raw.get("cwe_id", raw.get("cwe", "")),
            severity=severity,
            description=raw.get("description", raw.get("title", "")),
            fixture_files=fixture_files,
            evaluator_files=evaluator_files,
            file_digests=digests,
            resource_budget=raw.get("resource_budget", {})
        )

    def load_all_tasks(self, selected_ids: Optional[List[str]] = None) -> List[BenchmarkTaskMetadata]:
        """
        Loads all declared tasks or a validated subset.
        Rejects duplicates and unknown task IDs.
        """
        if selected_ids is not None:
            # Check for duplicates
            if len(selected_ids) != len(set(selected_ids)):
                raise InvalidTaskError(f"Duplicate task IDs provided in selection: {selected_ids}")
            return [self.load_task(tid) for tid in selected_ids]
        
        manifest = self.load_manifest()
        return [self.load_task(t["task_id"]) for t in manifest.get("tasks", [])]


class DeterministicBenchmarkEvaluator:
    """
    Authoritative out-of-sandbox ground truth evaluation engine.
    Preserves the oracle hierarchy and assigns deterministic verdicts:
    - Phase 1: Public Functional Regression -> exit_code == 0
    - Phase 2: Vulnerability Exploitation -> exit_code != 0 (neutralized)
    - Phase 3: Secure Acceptance Invariant -> exit_code == 0
    """
    def __init__(self, sandbox_backend: Optional[SandboxBackend] = None):
        self.sandbox_backend = sandbox_backend

    @staticmethod
    def evaluate_phase_results(
        regression_exit_code: Optional[int],
        vulnerability_exit_code: Optional[int],
        secure_exit_code: Optional[int],
        operational_failure: bool = False,
        operational_reason: Optional[str] = None,
        is_inconclusive: bool = False,
    ) -> Tuple[BenchmarkVerdict, bool, bool, bool, Optional[str]]:
        """
        Pure deterministic decision function mapping 3-phase execution outcomes to a verdict.
        
        Returns:
            (verdict, vulnerability_neutralized, secure_acceptance_passed, regression_passed, failure_reason)
        """
        # 1. Operational failures (sandbox missing, timeout, crash, policy block)
        if operational_failure:
            return (
                BenchmarkVerdict.OPERATIONAL_FAILURE,
                False,
                False,
                False,
                operational_reason or "OPERATIONAL_FAILURE"
            )

        # 2. Inconclusive outcomes (missing observation, output truncated)
        if is_inconclusive or regression_exit_code is None or vulnerability_exit_code is None or secure_exit_code is None:
            return (
                BenchmarkVerdict.INCONCLUSIVE,
                False,
                False,
                False,
                operational_reason or "INCONCLUSIVE_EVIDENCE"
            )

        # 3. Deterministic Phase Checks
        # Phase 1: Regression Test (must be 0 to pass)
        regression_passed = (regression_exit_code == 0)

        # Phase 2: Vulnerability Exploit (must be non-zero to prove neutralization)
        vulnerability_neutralized = (vulnerability_exit_code != 0)

        # Phase 3: Secure Invariant (must be 0 to pass)
        secure_passed = (secure_exit_code == 0)

        # Verdict assignment
        if regression_passed and vulnerability_neutralized and secure_passed:
            return (BenchmarkVerdict.VERIFIED, True, True, True, None)

        reasons = []
        if not regression_passed:
            reasons.append(f"Public regression test failed (exit_code={regression_exit_code})")
        if not vulnerability_neutralized:
            reasons.append(f"Vulnerability exploit still succeeded (exit_code={vulnerability_exit_code})")
        if not secure_passed:
            reasons.append(f"Secure acceptance test failed (exit_code={secure_exit_code})")

        return (
            BenchmarkVerdict.REJECTED,
            vulnerability_neutralized,
            secure_passed,
            regression_passed,
            "; ".join(reasons)
        )

    def evaluate_synthetic_record(
        self,
        task_id: str,
        arm_name: str,
        regression_exit_code: Optional[int],
        vulnerability_exit_code: Optional[int],
        secure_exit_code: Optional[int],
        execution_duration_ms: int = 100,
        evaluation_duration_ms: int = 50,
        patch_id: Optional[str] = None,
        patch_sha256: Optional[str] = None,
        operational_failure: bool = False,
        operational_reason: Optional[str] = None,
        is_inconclusive: bool = False,
    ) -> TaskEvaluationResult:
        """
        Creates an authoritative TaskEvaluationResult from synthetic execution records.
        Used for safe deterministic testing without invoking real candidate execution on host.
        """
        verdict, neut, sec, reg, reason = self.evaluate_phase_results(
            regression_exit_code=regression_exit_code,
            vulnerability_exit_code=vulnerability_exit_code,
            secure_exit_code=secure_exit_code,
            operational_failure=operational_failure,
            operational_reason=operational_reason,
            is_inconclusive=is_inconclusive,
        )

        evidence_hashes = {
            "regression_exit_code": str(regression_exit_code),
            "vulnerability_exit_code": str(vulnerability_exit_code),
            "secure_exit_code": str(secure_exit_code),
        }
        if patch_sha256:
            evidence_hashes["patch_sha256"] = patch_sha256

        return TaskEvaluationResult(
            task_id=task_id,
            arm=arm_name,
            verdict=verdict,
            operational_result=operational_reason if operational_failure else None,
            vulnerability_neutralized=neut,
            secure_acceptance_passed=sec,
            regression_passed=reg,
            execution_duration_ms=execution_duration_ms,
            evaluation_duration_ms=evaluation_duration_ms,
            patch_id=patch_id,
            patch_sha256=patch_sha256,
            evidence_hashes=evidence_hashes,
            failure_reason=reason,
            sandbox_provenance={
                "evaluator": "DeterministicBenchmarkEvaluator",
                "mode": "SYNTHETIC_OBSERVATION" if not self.sandbox_backend else "SECURE_SANDBOX",
            }
        )

    def evaluate_task(
        self,
        task: BenchmarkTaskMetadata,
        arm_name: str,
        candidate_workspace: str,
        patch_sha256: Optional[str] = None
    ) -> TaskEvaluationResult:
        """
        Evaluates a candidate task execution against the ground truth evaluators.
        Enforces strict fail-closed capability check:
        - If no secure sandbox backend is configured or if capabilities are not SECURE,
          refuses execution and returns OPERATIONAL_FAILURE.
        - Never executes candidate code on host.
        - Never falls back to LocalDevelopmentBackend.
        """
        if self.sandbox_backend is None:
            return self.evaluate_synthetic_record(
                task_id=task.task_id,
                arm_name=arm_name,
                regression_exit_code=None,
                vulnerability_exit_code=None,
                secure_exit_code=None,
                operational_failure=True,
                operational_reason="SECURE_SANDBOX_BACKEND_UNCONFIGURED"
            )

        # Capability check: reject LocalDevelopmentBackend and insecure backends
        if isinstance(self.sandbox_backend, LocalDevelopmentBackend):
            return self.evaluate_synthetic_record(
                task_id=task.task_id,
                arm_name=arm_name,
                regression_exit_code=None,
                vulnerability_exit_code=None,
                secure_exit_code=None,
                operational_failure=True,
                operational_reason="LOCAL_DEVELOPMENT_BACKEND_REFUSED_FOR_BENCHMARK"
            )

        caps = self.sandbox_backend.capabilities()
        if (
            caps.security_level != SecurityLevel.SECURE
            or caps.filesystem_isolation != "ENFORCED"
            or not caps.secure_untrusted_execution
        ):
            return self.evaluate_synthetic_record(
                task_id=task.task_id,
                arm_name=arm_name,
                regression_exit_code=None,
                vulnerability_exit_code=None,
                secure_exit_code=None,
                operational_failure=True,
                operational_reason="OPERATIONAL_FAILURE: Secure sandbox runtime is UNAVAILABLE. Candidate execution refused."
            )

        # In this implementation stage (P2-3.3), untrusted container-backed execution
        # is held pending live container provisioning per Section 4.
        return self.evaluate_synthetic_record(
            task_id=task.task_id,
            arm_name=arm_name,
            regression_exit_code=None,
            vulnerability_exit_code=None,
            secure_exit_code=None,
            operational_failure=True,
            operational_reason="OPERATIONAL_FAILURE: Candidate execution paused until verified container provisioning."
        )
