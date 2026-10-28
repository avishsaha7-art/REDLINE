import hashlib
import json
import pytest
from backend.models.schemas import TaskContract, PatchCandidate
from backend.models.evidence import EvidenceReceipt, VerificationScope, verify_receipt_integrity
from backend.verification.models import (
    StructuredObservation,
    ExecutionStatus,
    TestResultSummary,
    RegressionSummary,
    InvariantEvaluation,
    InvariantResultStatus,
    SecurityObservation,
    Counterexample,
    OracleResult,
    OracleType,
    VerificationResult,
    VerificationStatus
)

TestResultSummary.__test__ = False
from backend.verification.security_models import (
    SecurityResultAggregation,
    SecurityResultClassification,
    SecurityObservation as SecObs
)
from backend.verification.policy import DeterministicVerificationPolicy
from backend.evidence.builder import EvidenceAggregator
from backend.benchmark.integrity import verify_dataset_anchor


def create_base_task():
    return TaskContract(
        task_id="TASK-STAGE7-001",
        repository_id="safe-calculator-service",
        base_commit_or_snapshot="09f78d7c69f09190d5a5fedc372945fff2b68c01d383813dd034c43e7e8bd31e",
        task_description="Fix division by zero defect in calculator microservice",
        allowed_scope=["src/calculator.py"]
    )


def create_base_patch(task):
    diff = (
        "--- a/src/calculator.py\n"
        "+++ b/src/calculator.py\n"
        "@@ -28,4 +28,6 @@\n"
        "     elif op == \"/\":\n"
        "-        return a / b\n"
        "+        if b == 0:\n"
        "+            raise ValueError(\"Division by zero is not allowed\")\n"
        "+        return a / b\n"
        "     else:\n"
    )
    return PatchCandidate(
        patch_id="REPAIR-STAGE7-01",
        task_id=task.task_id,
        base_commit_or_snapshot=task.base_commit_or_snapshot,
        diff=diff,
        changed_files=["src/calculator.py"]
    )


def create_valid_observation(task, patch):
    return StructuredObservation(
        execution_id="exec-001",
        command_identifier="pytest tests/test_calculator.py",
        exit_code=0,
        stdout_sha256=hashlib.sha256(b"4 passed in 0.1s").hexdigest(),
        stderr_sha256=hashlib.sha256(b"").hexdigest(),
        stdout_bytes=100,
        stderr_bytes=0,
        duration_ms=150,
        status=ExecutionStatus.SUCCESS,
        sandbox_backend="SecureSandboxBackend",
        security_level="SECURE_ISOLATED",
        capabilities={"network": False, "read_only_root": True},
        workspace_id="ws-stage7",
        repository_snapshot_hash=task.base_commit_or_snapshot,
        patch_hash=patch.diff_sha256
    )


def create_sec_obs(status: SecurityResultClassification, evidence: str):
    return SecObs(
        execution_id="exec-sec-01",
        attack_id="ATK-001",
        status=status,
        exit_code=0 if status == SecurityResultClassification.PASS else 1,
        stdout_hash=hashlib.sha256(evidence.encode()).hexdigest(),
        stderr_hash=hashlib.sha256(b"").hexdigest(),
        output_size=len(evidence),
        duration=100,
        resource_status="NORMAL",
        expected_condition="Zero division prevented",
        observed_condition=evidence,
        evidence_hash=hashlib.sha256(evidence.encode()).hexdigest()
    )


# 1. A valid complete run can produce VERIFIED
def test_valid_complete_run_produces_verified():
    task = create_base_task()
    patch = create_base_patch(task)
    obs = create_valid_observation(task, patch)
    tests = TestResultSummary(discovered=4, executed=4, passed=4, failed=0, errored=0, inconclusive=0)

    sec_obs = create_sec_obs(SecurityResultClassification.PASS, "Zero division prevented; ValueError raised cleanly")
    sec_agg = SecurityResultAggregation(
        overall_status=SecurityResultClassification.PASS,
        observations=[sec_obs]
    )

    policy = DeterministicVerificationPolicy()
    verdict = policy.evaluate(
        repository_snapshot_hash=task.base_commit_or_snapshot,
        patch_hash=patch.diff_sha256,
        structured_observation=obs,
        test_summary=tests,
        regression_summary=RegressionSummary(),
        invariants=[],
        security_aggregation=sec_agg,
        oracle_results=[],
        counterexamples=[],
        required_checks=["execution", "tests", "security"]
    )

    assert verdict.status == VerificationStatus.VERIFIED

    aggregator = EvidenceAggregator(task, patch_lineage=[patch.patch_id])
    receipt = aggregator.build_receipt(
        run_id="run-stage7-test-01",
        patch=patch,
        verification_result=verdict,
        attacks=[],
        model_provenance={"provider": "mock", "model": "mock-v1"},
        sandbox_provenance={"backend": "SecureSandboxBackend"},
        snapshot_hash=task.base_commit_or_snapshot
    )

    assert receipt.verdict == VerificationStatus.VERIFIED
    assert receipt.verification_scope.execution == "VERIFIED"
    assert receipt.verification_scope.tests == "VERIFIED"
    assert receipt.verification_scope.security == "VERIFIED"
    assert verify_receipt_integrity(receipt) is True


# 2. A required security check that was not executed cannot produce VERIFIED
def test_required_security_check_unexecuted_prevents_verified():
    task = create_base_task()
    patch = create_base_patch(task)
    obs = create_valid_observation(task, patch)
    tests = TestResultSummary(discovered=4, executed=4, passed=4, failed=0, errored=0, inconclusive=0)

    policy = DeterministicVerificationPolicy()
    verdict = policy.evaluate(
        repository_snapshot_hash=task.base_commit_or_snapshot,
        patch_hash=patch.diff_sha256,
        structured_observation=obs,
        test_summary=tests,
        regression_summary=RegressionSummary(),
        invariants=[],
        security_aggregation=None,  # Security check NOT executed
        oracle_results=[],
        counterexamples=[],
        required_checks=["execution", "tests", "security"]
    )

    # Must fail closed to INCONCLUSIVE, cannot be VERIFIED
    assert verdict.status == VerificationStatus.INCONCLUSIVE


# 3. A required invariant check that was not executed cannot produce VERIFIED
def test_required_invariant_check_unexecuted_prevents_verified():
    task = create_base_task()
    patch = create_base_patch(task)
    obs = create_valid_observation(task, patch)
    tests = TestResultSummary(discovered=4, executed=4, passed=4, failed=0, errored=0, inconclusive=0)

    policy = DeterministicVerificationPolicy()
    verdict = policy.evaluate(
        repository_snapshot_hash=task.base_commit_or_snapshot,
        patch_hash=patch.diff_sha256,
        structured_observation=obs,
        test_summary=tests,
        regression_summary=RegressionSummary(),
        invariants=[],  # Invariants NOT executed
        security_aggregation=None,
        oracle_results=[],
        counterexamples=[],
        required_checks=["execution", "tests", "invariants"]
    )

    assert verdict.status == VerificationStatus.INCONCLUSIVE


# 4. A required failed check prevents VERIFIED
def test_required_failed_check_prevents_verified():
    task = create_base_task()
    patch = create_base_patch(task)
    obs = create_valid_observation(task, patch)
    tests = TestResultSummary(discovered=4, executed=4, passed=4, failed=0, errored=0, inconclusive=0)

    sec_obs = create_sec_obs(SecurityResultClassification.FAIL, "Zero division crashed with unhandled exception")
    sec_agg = SecurityResultAggregation(
        overall_status=SecurityResultClassification.FAIL,
        observations=[sec_obs]
    )

    policy = DeterministicVerificationPolicy()
    verdict = policy.evaluate(
        repository_snapshot_hash=task.base_commit_or_snapshot,
        patch_hash=patch.diff_sha256,
        structured_observation=obs,
        test_summary=tests,
        regression_summary=RegressionSummary(),
        invariants=[],
        security_aggregation=sec_agg,
        oracle_results=[],
        counterexamples=[],
        required_checks=["execution", "tests", "security"]
    )

    assert verdict.status == VerificationStatus.REJECTED


# 5. An explicitly optional unexecuted check follows the documented policy
def test_optional_unexecuted_check_follows_policy():
    task = create_base_task()
    patch = create_base_patch(task)
    obs = create_valid_observation(task, patch)
    tests = TestResultSummary(discovered=4, executed=4, passed=4, failed=0, errored=0, inconclusive=0)

    policy = DeterministicVerificationPolicy()
    # Explicitly optional: only execution and tests are required
    verdict = policy.evaluate(
        repository_snapshot_hash=task.base_commit_or_snapshot,
        patch_hash=patch.diff_sha256,
        structured_observation=obs,
        test_summary=tests,
        regression_summary=RegressionSummary(),
        invariants=[],
        security_aggregation=None,
        oracle_results=[],
        counterexamples=[],
        required_checks=["execution", "tests"]
    )
    assert verdict.status == VerificationStatus.VERIFIED

    # But if an optional check is executed and FAILS, it MUST reject!
    failed_inv = InvariantEvaluation(
        invariant_id="INV-001",
        description="Memory bounded",
        result=InvariantResultStatus.FAIL,
        failure_reason="Memory leak detected",
        evidence_hash=hashlib.sha256(b"inv-fail").hexdigest()
    )
    verdict_fail = policy.evaluate(
        repository_snapshot_hash=task.base_commit_or_snapshot,
        patch_hash=patch.diff_sha256,
        structured_observation=obs,
        test_summary=tests,
        regression_summary=RegressionSummary(),
        invariants=[failed_inv],
        security_aggregation=None,
        oracle_results=[],
        counterexamples=[],
        required_checks=["execution", "tests"]
    )
    assert verdict_fail.status == VerificationStatus.REJECTED


# 6. A failed patch-application operation cannot be hidden by a successful unrelated test command
def test_failed_patch_application_cannot_be_hidden():
    task = create_base_task()
    patch = create_base_patch(task)
    obs = create_valid_observation(task, patch)
    # Test command exited 0 and passed 10 tests
    tests = TestResultSummary(discovered=10, executed=10, passed=10, failed=0, errored=0, inconclusive=0)

    ce = Counterexample(
        counterexample_id="ce-patch-fail",
        invariant_id="PATCH_APPLICATION",
        test_id=None,
        input_data=patch.diff,
        observed_output="patch failed: README.md:28",
        expected_output="Clean git apply with exit code 0",
        failure_reason="Patch apply failed on target file",
        oracle_type=OracleType.DETERMINISTIC_CONTRACT,
        execution_id="exec-patch-fail",
        evidence_hash=hashlib.sha256(b"patch-fail").hexdigest(),
        patch_id=patch.patch_id,
        target_file="README.md"
    )

    policy = DeterministicVerificationPolicy()
    verdict = policy.evaluate(
        repository_snapshot_hash=task.base_commit_or_snapshot,
        patch_hash=patch.diff_sha256,
        structured_observation=obs,
        test_summary=tests,
        regression_summary=RegressionSummary(),
        invariants=[],
        security_aggregation=None,
        oracle_results=[],
        counterexamples=[ce]
    )

    # Must be REJECTED despite passing test summary
    assert verdict.status == VerificationStatus.REJECTED

    # Tampering test: if someone manually forced verdict to VERIFIED, verify_receipt_integrity rejects it
    aggregator = EvidenceAggregator(task, patch_lineage=[patch.patch_id])
    receipt = aggregator.build_receipt(
        run_id="run-tamper-patch-01",
        patch=patch,
        verification_result=verdict.model_copy(update={"status": VerificationStatus.VERIFIED}),
        attacks=[],
        model_provenance={"provider": "mock", "model": "mock-v1"},
        sandbox_provenance={"backend": "SecureSandboxBackend"},
        snapshot_hash=task.base_commit_or_snapshot
    )
    # verify_receipt_integrity must detect the contradictory counterexample
    assert verify_receipt_integrity(receipt) is False


# 7. Counterexamples retain correct patch, file, workspace, and run provenance
def test_counterexamples_retain_correct_provenance():
    ce = Counterexample(
        counterexample_id="ce-prov-001",
        invariant_id="PATCH_APPLICATION",
        test_id="test_suite",
        input_data="diff content",
        observed_output="patch failed: src/calculator.py:28",
        expected_output="Exit 0",
        failure_reason="Hunk failed",
        oracle_type=OracleType.DETERMINISTIC_CONTRACT,
        execution_id="exec-prov-01",
        evidence_hash="hash-prov-01",
        patch_id="PATCH-PROV-A",
        target_file="src/calculator.py",
        workspace_id="ws-prov-1",
        snapshot_hash="snap-prov-1"
    )

    assert ce.patch_id == "PATCH-PROV-A"
    assert ce.target_file == "src/calculator.py"
    assert ce.workspace_id == "ws-prov-1"
    assert ce.snapshot_hash == "snap-prov-1"
    assert len(ce.hash()) == 64

    # EvidenceAggregator filters out counterexamples that belong to a superseded patch
    task = create_base_task()
    new_patch = PatchCandidate(
        patch_id="REPAIR-PROV-B",
        task_id=task.task_id,
        base_commit_or_snapshot=task.base_commit_or_snapshot,
        diff="--- a/src/calculator.py\n+++ b/src/calculator.py\n@@ -1 +1 @@\n-a\n+b\n",
        changed_files=["src/calculator.py"]
    )

    v_res = VerificationResult(
        verification_id="v-prov",
        status=VerificationStatus.VERIFIED,
        policy_version="v1.0",
        verifier_version="v1.1",
        repository_snapshot_hash=task.base_commit_or_snapshot,
        patch_hash=new_patch.diff_sha256,
        test_summary=TestResultSummary(discovered=2, executed=2, passed=2),
        counterexamples=[ce],  # CE belongs to PATCH-PROV-A
        verified_scope="EXECUTION, TESTS"
    )

    agg = EvidenceAggregator(task)
    receipt = agg.build_receipt(
        run_id="run-prov-01",
        patch=new_patch,
        verification_result=v_res,
        attacks=[],
        model_provenance={},
        sandbox_provenance={"backend": "SecureSandboxBackend"}
    )

    # Receipt for REPAIR-PROV-B must not contain counterexample from PATCH-PROV-A
    assert len(receipt.counterexamples) == 0


# 8. Test summaries reject impossible or contradictory counts
def test_test_summaries_reject_contradictory_counts():
    # Anomaly 3 reproduction: executed 7 != passed 4 + failed 0
    with pytest.raises(ValueError, match=r"(Inconsistent|Contradictory) test counts"):
        TestResultSummary(discovered=0, executed=7, passed=4, failed=0, errored=0, skipped=0, inconclusive=0)

    # Contradictory: discovered 2 < executed 5
    with pytest.raises(ValueError, match="Contradictory test counts"):
        TestResultSummary(discovered=2, executed=5, passed=5, failed=0)

    # Valid counts succeed
    valid = TestResultSummary(discovered=4, executed=4, passed=4, failed=0, errored=0, skipped=0, inconclusive=0)
    assert valid.executed == 4
    assert valid.passed == 4
    assert valid.discovered == 4


# 9. Unknown sandbox provenance is not silently converted to verified security
def test_unknown_sandbox_provenance_fails_closed():
    task = create_base_task()
    patch = create_base_patch(task)
    obs = create_valid_observation(task, patch)
    obs_unknown = obs.model_copy(update={"sandbox_backend": "UNKNOWN"})
    tests = TestResultSummary(discovered=4, executed=4, passed=4, failed=0)

    policy = DeterministicVerificationPolicy()
    verdict = policy.evaluate(
        repository_snapshot_hash=task.base_commit_or_snapshot,
        patch_hash=patch.diff_sha256,
        structured_observation=obs_unknown,
        test_summary=tests,
        regression_summary=RegressionSummary(),
        invariants=[],
        security_aggregation=None,
        oracle_results=[],
        counterexamples=[]
    )

    assert verdict.status == VerificationStatus.SANDBOX_FAILURE

    # Tampered receipt with UNKNOWN sandbox backend fails integrity check
    aggregator = EvidenceAggregator(task, patch_lineage=[patch.patch_id])
    receipt = aggregator.build_receipt(
        run_id="run-unknown-sb",
        patch=patch,
        verification_result=verdict.model_copy(update={"status": VerificationStatus.VERIFIED}),
        attacks=[],
        model_provenance={},
        sandbox_provenance={"backend": "UNKNOWN"},
        snapshot_hash=task.base_commit_or_snapshot
    )
    assert verify_receipt_integrity(receipt) is False


# 10. Patch IDs, patch digests, repository snapshot hashes, and receipt hashes are independently validated
def test_patch_ids_digests_snapshot_hashes_independent_validation():
    task = create_base_task()
    patch = create_base_patch(task)
    obs = create_valid_observation(task, patch)
    tests = TestResultSummary(discovered=4, executed=4, passed=4)

    policy = DeterministicVerificationPolicy()
    verdict = policy.evaluate(
        repository_snapshot_hash=task.base_commit_or_snapshot,
        patch_hash=patch.diff_sha256,
        structured_observation=obs,
        test_summary=tests,
        regression_summary=RegressionSummary(),
        invariants=[],
        security_aggregation=None,
        oracle_results=[],
        counterexamples=[],
        required_checks=["execution", "tests"]
    )

    aggregator = EvidenceAggregator(task, patch_lineage=[patch.patch_id])
    receipt = aggregator.build_receipt(
        run_id="run-independent-val",
        patch=patch,
        verification_result=verdict,
        attacks=[],
        model_provenance={"provider": "mock"},
        sandbox_provenance={"backend": "SecureSandboxBackend"},
        snapshot_hash=task.base_commit_or_snapshot
    )

    # Separate correctly named fields
    assert receipt.patch_id == patch.patch_id
    assert receipt.patch_digest == patch.diff_sha256
    assert receipt.patch_hash == patch.patch_id
    assert receipt.repository_snapshot_hash == task.base_commit_or_snapshot
    assert receipt.receipt_hash == receipt.calculate_integrity_hash()
    assert verify_receipt_integrity(receipt) is True


# 11. Receipt tampering or inconsistent verdict fields is detected
def test_receipt_tampering_and_inconsistent_verdict_detected():
    task = create_base_task()
    patch = create_base_patch(task)
    obs = create_valid_observation(task, patch)
    tests = TestResultSummary(discovered=4, executed=4, passed=4)

    policy = DeterministicVerificationPolicy()
    verdict = policy.evaluate(
        repository_snapshot_hash=task.base_commit_or_snapshot,
        patch_hash=patch.diff_sha256,
        structured_observation=obs,
        test_summary=tests,
        regression_summary=RegressionSummary(),
        invariants=[],
        security_aggregation=None,
        oracle_results=[],
        counterexamples=[],
        required_checks=["execution", "tests"]
    )

    aggregator = EvidenceAggregator(task)
    receipt = aggregator.build_receipt(
        run_id="run-tamper-check",
        patch=patch,
        verification_result=verdict,
        attacks=[],
        model_provenance={},
        sandbox_provenance={"backend": "SecureSandboxBackend"}
    )
    assert verify_receipt_integrity(receipt) is True

    # Tamper 1: Mutate verdict without recalculating hash
    tampered_verdict = receipt.model_copy(update={"verdict": VerificationStatus.REJECTED})
    assert verify_receipt_integrity(tampered_verdict) is False

    # Tamper 2: Mutate patch_digest without recalculating hash
    tampered_digest = receipt.model_copy(update={"patch_digest": "bad_digest"})
    assert verify_receipt_integrity(tampered_digest) is False

    # Tamper 3: Recompute hash for forged VERIFIED receipt with failed tests
    failing_tests = TestResultSummary(discovered=4, executed=4, passed=3, failed=1)
    forged_data = receipt.model_dump()
    forged_data["test_summary"] = failing_tests.model_dump()
    forged_receipt = EvidenceReceipt(**forged_data)
    forged_receipt = forged_receipt.model_copy(update={"receipt_hash": forged_receipt.calculate_integrity_hash()})
    # Must fail because test_summary.failed > 0 contradicts verdict VERIFIED
    assert verify_receipt_integrity(forged_receipt) is False


# 12. Historical receipts remain readable and unchanged
def test_historical_receipts_remain_readable():
    import sqlite3
    conn = sqlite3.connect("data/redline.db")
    c = conn.cursor()
    row = c.execute("SELECT evidence_receipt_json FROM runs WHERE run_id = 'run-b822ff1e'").fetchone()
    conn.close()

    if row and row[0]:
        receipt_data = json.loads(row[0])
        receipt = EvidenceReceipt.model_validate(receipt_data)
        assert receipt.run_id == "run-b822ff1e"
        assert receipt.receipt_hash is not None
        # Historical receipt integrity passes without modification
        assert verify_receipt_integrity(receipt) is True


# 13. The frozen benchmark integrity checks still pass
def test_frozen_benchmark_integrity_passes():
    res = verify_dataset_anchor()
    assert res.status == "VERIFIED"
    assert res.tasks_verified == 12
    assert res.artifacts_verified == 84
