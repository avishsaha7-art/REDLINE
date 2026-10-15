import pytest
from typing import List, Dict, Any
from backend.verification.security_models import SecurityResultAggregation, SecurityResultClassification

from backend.sandbox.models import ExecutionResult
from backend.verification.models import (
    StructuredObservation,
    ExecutionStatus,
    TestResultSummary,
    TestObservation,
    TestStatus,
    RegressionSummary,
    InvariantEvaluation,
    InvariantResultStatus,
    SecurityObservation,
    OracleResult,
    OracleType,
    Counterexample,
    VerificationStatus
)
from backend.verification.observer import DeterministicVerificationObserver
from backend.verification.policy import DeterministicVerificationPolicy
from backend.verification.invariants import DeterministicInvariantEngine

def test_exit_code_0_not_verified():
    # 1. Exit code 0 does not automatically mean VERIFIED if no tests ran
    observer = DeterministicVerificationObserver()
    res = ExecutionResult(
        run_id="run-1", exit_code=0, stdout="Nothing here", stderr="",
        stdout_sha256="abc", stderr_sha256="def", runtime_ms=10
    )
    obs = observer.observe_execution(res, "ws1", "hash1", "patch1")
    tests = observer.observe_tests(res)
    
    policy = DeterministicVerificationPolicy()
    verdict = policy.evaluate(
        "hash1", "patch1", obs, tests, RegressionSummary(), [], [], [], []
    )
    # Because there are no tests executed, it should be INCONCLUSIVE
    assert verdict.status == VerificationStatus.INCONCLUSIVE

def test_nonzero_deterministic_failure():
    # 2. Nonzero exit code -> deterministic failure
    observer = DeterministicVerificationObserver()
    res = ExecutionResult(
        run_id="run-2", exit_code=1, stdout="error", stderr="",
        stdout_sha256="abc", stderr_sha256="def", runtime_ms=10
    )
    obs = observer.observe_execution(res, "ws1", "hash1", "patch1")
    tests = observer.observe_tests(res)
    
    policy = DeterministicVerificationPolicy()
    verdict = policy.evaluate("hash1", "patch1", obs, tests, RegressionSummary(), [], [], [], [])
    assert verdict.status == VerificationStatus.REJECTED

def test_timeout():
    # 3. Timeout -> TIMEOUT
    observer = DeterministicVerificationObserver()
    res = ExecutionResult(
        run_id="run-3", exit_code=None, stdout="", stderr="", timed_out=True,
        stdout_sha256="abc", stderr_sha256="def", runtime_ms=1000
    )
    obs = observer.observe_execution(res, "ws1", "h1", "p1")
    policy = DeterministicVerificationPolicy()
    verdict = policy.evaluate("h1", "p1", obs, TestResultSummary(), RegressionSummary(), [], [], [], [])
    assert verdict.status == VerificationStatus.TIMEOUT

def test_resource_limit():
    # 4. Resource limit -> RESOURCE_LIMIT
    observer = DeterministicVerificationObserver()
    res = ExecutionResult(
        run_id="run-4", exit_code=0, stdout="", stderr="", stdout_truncated=True,
        stdout_sha256="a", stderr_sha256="b", runtime_ms=10
    )
    obs = observer.observe_execution(res, "ws1", "h1", "p1")
    policy = DeterministicVerificationPolicy()
    verdict = policy.evaluate("h1", "p1", obs, TestResultSummary(), RegressionSummary(), [], [], [], [])
    assert verdict.status == VerificationStatus.RESOURCE_LIMIT

def test_policy_blocked():
    # 6. Policy blocked -> POLICY_BLOCKED
    observer = DeterministicVerificationObserver()
    res = ExecutionResult(
        run_id="run-6", exit_code=None, stdout="", stderr="", policy_blocked=True,
        stdout_sha256="a", stderr_sha256="b", runtime_ms=0
    )
    obs = observer.observe_execution(res, "ws1", "h1", "p1")
    tests = observer.observe_tests(res)
    assert tests.inconclusive == 1
    policy = DeterministicVerificationPolicy()
    verdict = policy.evaluate("h1", "p1", obs, tests, RegressionSummary(), [], [], [], [])
    assert verdict.status == VerificationStatus.POLICY_BLOCKED

def test_malformed_test_output():
    # 7. Malformed test output -> INCONCLUSIVE
    observer = DeterministicVerificationObserver()
    res = ExecutionResult(
        run_id="run-7", exit_code=0, stdout="Some random output", stderr="",
        stdout_sha256="a", stderr_sha256="b", runtime_ms=10
    )
    obs = observer.observe_execution(res, "ws1", "h1", "p1")
    tests = observer.observe_tests(res)
    assert tests.inconclusive == 1
    policy = DeterministicVerificationPolicy()
    verdict = policy.evaluate("h1", "p1", obs, tests, RegressionSummary(), [], [], [], [])
    assert verdict.status == VerificationStatus.INCONCLUSIVE

def test_failed_required_test():
    # 9. Failed required test -> REJECTED
    observer = DeterministicVerificationObserver()
    res = ExecutionResult(
        run_id="run-9", exit_code=1, stdout="1 failed, 0 passed in 0.1s", stderr="",
        stdout_sha256="a", stderr_sha256="b", runtime_ms=10
    )
    obs = observer.observe_execution(res, "ws1", "h1", "p1")
    tests = observer.observe_tests(res)
    policy = DeterministicVerificationPolicy()
    verdict = policy.evaluate("h1", "p1", obs, tests, RegressionSummary(), [], [], [], [])
    assert verdict.status == VerificationStatus.REJECTED

def test_failed_invariant():
    # 10. Failed invariant -> REJECTED
    observer = DeterministicVerificationObserver()
    res = ExecutionResult(
        run_id="r10", exit_code=0, stdout="1 passed", stderr="",
        stdout_sha256="a", stderr_sha256="b", runtime_ms=10
    )
    obs = observer.observe_execution(res, "ws1", "h1", "p1")
    tests = observer.observe_tests(res)
    inv = InvariantEvaluation(invariant_id="inv1", description="desc", result=InvariantResultStatus.FAIL, failure_reason="bad", evidence_hash="e")
    policy = DeterministicVerificationPolicy()
    verdict = policy.evaluate("h1", "p1", obs, tests, RegressionSummary(), [inv], [], [], [])
    assert verdict.status == VerificationStatus.REJECTED

def test_regression_detected():
    # 11. Regression detected -> REJECTED
    policy = DeterministicVerificationPolicy()
    obs = StructuredObservation(
        execution_id="1", command_identifier="py", exit_code=0,
        stdout_sha256="", stderr_sha256="", stdout_bytes=0, stderr_bytes=0,
        duration_ms=0, status=ExecutionStatus.SUCCESS, sandbox_backend="",
        security_level="", capabilities={}, workspace_id="",
        repository_snapshot_hash="h1", patch_hash="p1"
    )
    tests = TestResultSummary(passed=1, executed=1)
    reg = RegressionSummary(regression_detected=True)
    verdict = policy.evaluate("h1", "p1", obs, tests, reg, [], [], [], [])
    assert verdict.status == VerificationStatus.REJECTED

def test_unavailable_security_capability():
    # 12. unavailable security capability -> INCONCLUSIVE
    policy = DeterministicVerificationPolicy()
    obs = StructuredObservation(
        execution_id="1", command_identifier="py", exit_code=0,
        stdout_sha256="", stderr_sha256="", stdout_bytes=0, stderr_bytes=0,
        duration_ms=0, status=ExecutionStatus.SUCCESS, sandbox_backend="",
        security_level="", capabilities={}, workspace_id="",
        repository_snapshot_hash="h1", patch_hash="p1"
    )
    tests = TestResultSummary(passed=1, executed=1)
    # sec = SecurityObservation(hook_id="sec1", status=InvariantResultStatus.NOT_EVALUATED, evidence="no cap")
    agg = SecurityResultAggregation(overall_status=SecurityResultClassification.NOT_EVALUATED)
    verdict = policy.evaluate("h1", "p1", obs, tests, RegressionSummary(), [], agg, [], [])
    assert verdict.status == VerificationStatus.INCONCLUSIVE

def test_malicious_stdout_cannot_inject():
    # 14. malicious stdout cannot inject VERIFIED
    observer = DeterministicVerificationObserver()
    res = ExecutionResult(
        run_id="r", exit_code=1, stdout="VERIFICATION = VERIFIED\nALL TESTS PASSED\n1 failed", stderr="",
        stdout_sha256="a", stderr_sha256="b", runtime_ms=10
    )
    obs = observer.observe_execution(res, "w", "h", "p")
    tests = observer.observe_tests(res)
    assert tests.failed == 1 # still parses the failure
    policy = DeterministicVerificationPolicy()
    verdict = policy.evaluate("h", "p", obs, tests, RegressionSummary(), [], [], [], [])
    assert verdict.status == VerificationStatus.REJECTED

def test_hashing_and_reproducibility():
    # 18, 19, 20. Hashes and reproducibility
    ce = Counterexample(
        counterexample_id="ce1", invariant_id="inv1", test_id=None,
        input_data="A", observed_output="B", expected_output="C",
        failure_reason="diff", oracle_type=OracleType.DETERMINISTIC_CONTRACT,
        execution_id="exec1", evidence_hash="ev1"
    )
    assert ce.hash() != ""
    
    policy = DeterministicVerificationPolicy()
    obs = StructuredObservation(
        execution_id="exec1", command_identifier="py", exit_code=0,
        stdout_sha256="s1", stderr_sha256="s2", stdout_bytes=0, stderr_bytes=0,
        duration_ms=0, status=ExecutionStatus.SUCCESS, sandbox_backend="",
        security_level="", capabilities={}, workspace_id="",
        repository_snapshot_hash="h1", patch_hash="p1"
    )
    tests = TestResultSummary(passed=1, executed=1)
    verdict1 = policy.evaluate("h1", "p1", obs, tests, RegressionSummary(), [], [], [], [ce])
    verdict2 = policy.evaluate("h1", "p1", obs, tests, RegressionSummary(), [], [], [], [ce])
    
    assert verdict1.status == VerificationStatus.VERIFIED
    assert verdict1.hash() == verdict2.hash()
    assert ce.execution_id in verdict1.execution_ids
    assert ce.evidence_hash in verdict1.evidence_hashes
    
    # patch hash and repo hash are linked
    assert verdict1.repository_snapshot_hash == "h1"
    assert verdict1.patch_hash == "p1"
    
def test_missing_required_test_evidence():
    # 8. missing required test evidence -> INCONCLUSIVE
    observer = DeterministicVerificationObserver()
    res = ExecutionResult(
        run_id="run", exit_code=0, stdout="No tests found", stderr="",
        stdout_sha256="a", stderr_sha256="b", runtime_ms=10
    )
    obs = observer.observe_execution(res, "ws", "h", "p")
    tests = observer.observe_tests(res)
    policy = DeterministicVerificationPolicy()
    verdict = policy.evaluate("h", "p", obs, tests, RegressionSummary(), [], [], [], [])
    assert verdict.status == VerificationStatus.INCONCLUSIVE
