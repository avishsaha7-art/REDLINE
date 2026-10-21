"""
Benchmark Runner and Lifecycle Orchestration for REDLINE.

Implements the deterministic benchmark lifecycle:
    CREATED -> INTEGRITY_CHECK -> CAPABILITY_CHECK -> READY -> RUNNING -> EVALUATING -> COMPLETED
    (or terminal: OPERATIONAL_FAILURE, CANCELLED, ABORTED)

Enforces mandatory fail-closed gates:
1. Integrity Gate: Verifies frozen Git commit anchor, annotated tag, and manifest digest.
2. Capability Gate: Verifies OS-enforced container sandbox (refuses host/LocalDevelopmentBackend execution).
3. Confinement Gate: Protects hidden evaluators from exposure to candidate environments.
4. Interruption Safety: Interrupted runs remain incomplete or failed, never promoted to VERIFIED.
"""

import os
import uuid
import datetime
import threading
from typing import Dict, Any, List, Optional, Tuple

from backend.benchmark.models import (
    BenchmarkRunState,
    BenchmarkVerdict,
    BenchmarkArmType,
    BenchmarkRunConfig,
    BenchmarkRunRecord,
    TaskEvaluationResult,
    BenchmarkTaskMetadata,
)
from backend.benchmark.integrity import BenchmarkIntegrityChecker, BenchmarkIntegrityError
from backend.benchmark.evaluator import BenchmarkTaskLoader, DeterministicBenchmarkEvaluator
from backend.benchmark.storage import BenchmarkRunRepository, get_benchmark_repository
from backend.sandbox.backend import SandboxBackend, LocalDevelopmentBackend
from backend.sandbox.secure_backend import SecureSandboxBackend
from backend.sandbox.capabilities import SecurityLevel


class BenchmarkRunnerError(Exception):
    """Base exception for benchmark runner execution errors."""
    pass


class BenchmarkSecurityGateError(BenchmarkRunnerError):
    """Raised when an integrity or sandbox security gate fails closed."""
    pass


class BenchmarkRunner:
    """
    Orchestrates the benchmark run lifecycle while enforcing strict fail-closed
    security and integrity guarantees.
    """
    def __init__(
        self,
        config: BenchmarkRunConfig,
        sandbox_backend: Optional[SandboxBackend] = None,
        repository: Optional[BenchmarkRunRepository] = None,
        task_loader: Optional[BenchmarkTaskLoader] = None,
        evaluator: Optional[DeterministicBenchmarkEvaluator] = None,
        repo_root: Optional[str] = None,
        dataset_root: Optional[str] = None,
    ):
        self.config = config
        self.sandbox_backend = sandbox_backend
        self.repository = repository or get_benchmark_repository()
        self.task_loader = task_loader or BenchmarkTaskLoader(dataset_root=dataset_root)
        self.evaluator = evaluator or DeterministicBenchmarkEvaluator(sandbox_backend=sandbox_backend)
        self.repo_root = repo_root or os.environ.get("REDLINE_REPO_ROOT")
        self.dataset_root = dataset_root
        self._cancel_requested = False
        self._lock = threading.RLock()

        # Initialize or retrieve persistent run record
        existing = self.repository.get_run(self.config.run_id)
        if existing:
            self.record = existing
        else:
            self.record = BenchmarkRunRecord(
                run_id=self.config.run_id,
                config=self.config,
                state=BenchmarkRunState.CREATED,
            )
            self.repository.create_run(self.record)

    def cancel(self) -> None:
        """Requests cancellation of an active benchmark run."""
        with self._lock:
            self._cancel_requested = True
            if not self.record.state.is_terminal:
                self.record.state = BenchmarkRunState.CANCELLED
                self.record.error_message = "Benchmark run cancelled by user request"
                self.repository.update_run_state(
                    self.config.run_id,
                    BenchmarkRunState.CANCELLED,
                    error_message=self.record.error_message
                )

    def run(self) -> BenchmarkRunRecord:
        """
        Executes the benchmark run through all mandatory gates and phases.
        Returns the updated BenchmarkRunRecord.
        """
        with self._lock:
            if self._cancel_requested or self.record.state.is_terminal:
                return self.record

        # =====================================================================
        # Phase 1: INTEGRITY_CHECK Gate
        # =====================================================================
        self._transition_state(BenchmarkRunState.INTEGRITY_CHECK)
        if self._check_cancellation():
            return self.record

        try:
            checker = BenchmarkIntegrityChecker(
                repo_root=self.repo_root,
                dataset_root=self.dataset_root,
                anchor_config={
                    "dataset_commit_sha": self.config.target_commit_sha,
                    "dataset_tag": self.config.annotated_tag,
                    "manifest_root_sha256": self.config.manifest_sha256,
                },
                strict_working_tree=self.config.strict_working_tree,
            )
            integrity_result = checker.verify_all()
            self.record.integrity_result = {
                "status": integrity_result.status,
                "checks_passed": integrity_result.checks_passed,
                "tasks_verified": integrity_result.tasks_verified,
                "artifacts_verified": integrity_result.artifacts_verified,
            }
            self.repository.update_run_state(
                self.config.run_id,
                BenchmarkRunState.INTEGRITY_CHECK,
                integrity_result=self.record.integrity_result
            )
        except BenchmarkIntegrityError as e:
            # Integrity check failed: halt immediately, fail closed.
            # Do NOT trust an unverified manifest to enumerate tasks.
            err_msg = (
                f"INTEGRITY_GATE_FAILED: {str(e)}. "
                "Manifest contents are unverified and untrusted; complete task-level inventory cannot safely be established."
            )
            self._fail_closed(err_msg)
            return self.record
        except Exception as e:
            err_msg = (
                f"INTEGRITY_GATE_ERROR: Unexpected error verifying dataset integrity: {str(e)}. "
                "Manifest contents are unverified and untrusted; complete task-level inventory cannot safely be established."
            )
            self._fail_closed(err_msg)
            return self.record

        # =====================================================================
        # Phase 2: CAPABILITY_CHECK Gate
        # =====================================================================
        self._transition_state(BenchmarkRunState.CAPABILITY_CHECK)
        if self._check_cancellation():
            return self.record

        capability_ok, cap_meta, cap_reason = self._verify_sandbox_capability()
        self.record.capability_result = cap_meta
        self.repository.update_run_state(
            self.config.run_id,
            BenchmarkRunState.CAPABILITY_CHECK,
            capability_result=cap_meta
        )

        if not capability_ok:
            # Capability check failed: halt immediately, fail closed.
            # Manifest has been verified, so safely enumerate tasks from trusted manifest.
            try:
                selected_ids = self.config.tasks_selected if self.config.tasks_selected else None
                tasks = self.task_loader.load_all_tasks(selected_ids)
                self._record_blocked_operational_failure_for_tasks(tasks, cap_reason)
            except Exception as load_err:
                cap_reason = f"{cap_reason} (Additionally failed to enumerate tasks: {load_err})"
            self._fail_closed(cap_reason)
            return self.record

        # =====================================================================
        # Phase 3: Task Loading & Validation (READY)
        # =====================================================================
        try:
            selected_ids = self.config.tasks_selected if self.config.tasks_selected else None
            tasks = self.task_loader.load_all_tasks(selected_ids)
        except Exception as e:
            err_msg = f"TASK_VALIDATION_FAILED: Failed to load benchmark tasks: {str(e)}"
            self._fail_closed(err_msg)
            return self.record

        self._transition_state(BenchmarkRunState.READY)
        if self._check_cancellation():
            return self.record

        # =====================================================================
        # Phase 4: RUNNING (Candidate Execution Refusal in P2-3.3)
        # =====================================================================
        self._transition_state(BenchmarkRunState.RUNNING)
        if self._check_cancellation():
            return self.record

        # In this implementation stage (P2-3.3), untrusted candidate execution
        # is held pending live container engine provisioning on host.
        # If running in SYNTHETIC mode (used for test verification):
        if self.config.arm_type == BenchmarkArmType.SYNTHETIC:
            self._transition_state(BenchmarkRunState.EVALUATING)
            self._execute_synthetic_evaluations(tasks)
            self._transition_state(BenchmarkRunState.COMPLETED)
            return self.record

        # For non-synthetic arms, if no live container engine exists,
        # fail-closed with OPERATIONAL_FAILURE without running on host:
        err_msg = (
            "OPERATIONAL_FAILURE: Live container-backed sandbox runtime is not provisioned on host. "
            "Untrusted candidate code execution is refused fail-closed per Section 4 safety rules."
        )
        self._record_operational_failure_for_all_tasks(tasks, err_msg)
        self._fail_closed(err_msg)
        return self.record

    def _verify_sandbox_capability(self) -> Tuple[bool, Dict[str, Any], str]:
        """
        Validates that the execution backend satisfies genuine OS-level isolation.
        Refuses host execution, LocalDevelopmentBackend, or missing Docker daemons.
        """
        if self.sandbox_backend is None:
            return (
                False,
                {"backend": "None", "security_level": "UNCONFIGURED"},
                "CAPABILITY_GATE_FAILED: No sandbox backend configured. Host execution forbidden."
            )

        # Explicitly refuse LocalDevelopmentBackend
        if isinstance(self.sandbox_backend, LocalDevelopmentBackend):
            return (
                False,
                {"backend": "LocalDevelopmentBackend", "security_level": "DEVELOPMENT_ONLY"},
                "CAPABILITY_GATE_FAILED: LocalDevelopmentBackend refused for benchmark evaluation. "
                "OS-enforced container isolation is mandatory."
            )

        caps = self.sandbox_backend.capabilities()
        cap_meta = {
            "backend": type(self.sandbox_backend).__name__,
            "security_level": caps.security_level.value,
            "filesystem_isolation": caps.filesystem_isolation,
            "process_isolation": caps.process_isolation,
            "network_isolation": caps.network_isolation,
            "secure_untrusted_execution": caps.secure_untrusted_execution,
        }

        # Check genuine OS-level isolation
        if caps.security_level != SecurityLevel.SECURE:
            return (
                False,
                cap_meta,
                f"CAPABILITY_GATE_FAILED: Sandbox security level is '{caps.security_level.value}'. "
                "Required: 'SECURE' with operational container runtime."
            )

        if caps.filesystem_isolation != "ENFORCED" or not caps.secure_untrusted_execution:
            return (
                False,
                cap_meta,
                "CAPABILITY_GATE_FAILED: Filesystem isolation is not ENFORCED. Untrusted execution refused."
            )

        return True, cap_meta, "SECURE_CAPABILITY_VERIFIED"

    def _transition_state(self, new_state: BenchmarkRunState) -> None:
        """Transitions run state and persists change."""
        with self._lock:
            self.record.state = new_state
            self.record.updated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            if new_state.is_terminal:
                self.record.completed_at = self.record.updated_at
            self.repository.update_run_state(self.config.run_id, new_state)

    def _fail_closed(self, error_message: str) -> None:
        """Transitions run to OPERATIONAL_FAILURE fail-closed."""
        with self._lock:
            self.record.state = BenchmarkRunState.OPERATIONAL_FAILURE
            self.record.error_message = error_message
            self.record.updated_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            self.record.completed_at = self.record.updated_at
            self.repository.update_run_state(
                self.config.run_id,
                BenchmarkRunState.OPERATIONAL_FAILURE,
                error_message=error_message
            )

    def _check_cancellation(self) -> bool:
        """Checks if cancellation was requested."""
        with self._lock:
            return self._cancel_requested or self.record.state == BenchmarkRunState.CANCELLED

    def _record_blocked_operational_failure_for_tasks(
        self, tasks: List[BenchmarkTaskMetadata], reason: str
    ) -> None:
        """
        Records an explicit, truthful task-level outcome (OPERATIONAL_FAILURE, attempted=False)
        for every task in the verified manifest when a run fails before task execution begins.
        Uses transactional batch persistence and does not overwrite stronger evidence.
        """
        blocked_results: List[TaskEvaluationResult] = []
        for t in tasks:
            existing = self.record.task_results.get(t.task_id)
            if existing and existing.verdict in (BenchmarkVerdict.VERIFIED, BenchmarkVerdict.REJECTED):
                continue

            result = TaskEvaluationResult(
                task_id=t.task_id,
                arm=self.config.arm_type.value,
                verdict=BenchmarkVerdict.OPERATIONAL_FAILURE,
                operational_result="OPERATIONAL_FAILURE",
                attempted=False,  # Truthful: never executed
                failure_reason=f"BLOCKED_BEFORE_EXECUTION: {reason}",
                sandbox_provenance=self.record.capability_result or {},
            )
            self.record.task_results[t.task_id] = result
            blocked_results.append(result)

        if blocked_results:
            self.repository.record_task_results_batch(self.config.run_id, blocked_results)

    def _record_operational_failure_for_all_tasks(
        self, tasks: List[BenchmarkTaskMetadata], reason: str
    ) -> None:
        """
        Records an explicit OPERATIONAL_FAILURE result for all declared tasks.
        Uses transactional batch persistence and preserves existing stronger evidence.
        """
        results: List[TaskEvaluationResult] = []
        for t in tasks:
            existing = self.record.task_results.get(t.task_id)
            if existing and existing.verdict in (BenchmarkVerdict.VERIFIED, BenchmarkVerdict.REJECTED):
                continue

            result = TaskEvaluationResult(
                task_id=t.task_id,
                arm=self.config.arm_type.value,
                verdict=BenchmarkVerdict.OPERATIONAL_FAILURE,
                operational_result="OPERATIONAL_FAILURE",
                attempted=False,
                failure_reason=reason,
                sandbox_provenance=self.record.capability_result or {},
            )
            self.record.task_results[t.task_id] = result
            results.append(result)

        if results:
            self.repository.record_task_results_batch(self.config.run_id, results)

    def _execute_synthetic_evaluations(self, tasks: List[BenchmarkTaskMetadata]) -> None:
        """
        Executes synthetic evaluations for test verification without executing code on host.
        """
        for t in tasks:
            if self._check_cancellation():
                break
            result = self.evaluator.evaluate_synthetic_record(
                task_id=t.task_id,
                arm_name=self.config.arm_type.value,
                regression_exit_code=0,
                vulnerability_exit_code=1,  # Exploit blocked
                secure_exit_code=0,         # Secure invariant passed
                execution_duration_ms=120,
                evaluation_duration_ms=45,
            )
            self.record.task_results[t.task_id] = result
            self.repository.record_task_result(self.config.run_id, result)
