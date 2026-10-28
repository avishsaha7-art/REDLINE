import os
import sys
import shutil
import tempfile
import hashlib
import json
import subprocess
import pytest
from fastapi.testclient import TestClient

from backend.api.app import app
from backend.storage.database import Database, set_database
from backend.storage.project_repository import SQLiteProjectRepository, get_project_repository
from backend.models.registry import set_model_provider, reset_model_provider
from backend.models.deterministic_provider import DeterministicTestProvider
from backend.sandbox.capabilities import RepositoryTrust
from backend.models.schemas import (
    TaskContract,
    Run,
    RunState,
    OperationalResult,
    ResourceBudget,
)
from backend.models.projects import ProposalRecord
from backend.sandbox.factory import get_sandbox_backend
from backend.sandbox.secure_backend import SecureSandboxBackend
from backend.sandbox.backend import LocalDevelopmentBackend
from backend.verification.models import (
    VerificationStatus,
    TestResultSummary,
    StructuredObservation,
)
from backend.models.evidence import EvidenceReceipt, VerificationScope, verify_receipt_integrity
from backend.api.routes.runs import (
    set_run_repository,
    get_repository as get_runs_repo,
    set_artifact_storage,
    get_artifact_storage_instance,
    get_run,
    _runs,
    _orchestrators,
    _threads,
    execute_run,
)
from backend.storage.artifacts import ArtifactStorage
from backend.storage.repositories import SQLiteRunRepository
from backend.orchestrator.orchestrator import Orchestrator


# Disposable project source and test code
DISPOSABLE_SRC_BUGGY = '''import time

class TokenBucket:
    def __init__(self, capacity: int, fill_rate: float):
        if capacity <= 0 or fill_rate <= 0:
            raise ValueError("Capacity and fill_rate must be positive.")
        self.capacity = capacity
        self.tokens = capacity
        self.fill_rate = fill_rate
        self.last_update = time.time()

    def consume(self, amount: int) -> bool:
        # BUG: Does not validate amount > 0 and deducts tokens even when amount exceeds capacity
        self.tokens -= amount
        return True
'''

DISPOSABLE_SRC_FIXED = '''import time

class TokenBucket:
    def __init__(self, capacity: int, fill_rate: float):
        if capacity <= 0 or fill_rate <= 0:
            raise ValueError("Capacity and fill_rate must be positive.")
        self.capacity = capacity
        self.tokens = capacity
        self.fill_rate = fill_rate
        self.last_update = time.time()

    def consume(self, amount: int) -> bool:
        if amount <= 0:
            raise ValueError("Amount must be positive.")
        if amount > self.tokens:
            return False
        self.tokens -= amount
        return True
'''

DISPOSABLE_TEST = '''import pytest
from src.token_bucket import TokenBucket

def test_initial_tokens():
    b = TokenBucket(10, 1.0)
    assert b.tokens == 10

def test_consume_valid():
    b = TokenBucket(10, 1.0)
    assert b.consume(5) is True
    assert b.tokens == 5

def test_consume_exceeding_capacity_rejected():
    b = TokenBucket(10, 1.0)
    assert b.consume(15) is False
    assert b.tokens == 10

def test_consume_negative_or_zero_rejected():
    b = TokenBucket(10, 1.0)
    with pytest.raises(ValueError):
        b.consume(-1)
'''


@pytest.fixture
def client_with_clean_db():
    temp_dir = tempfile.mkdtemp(prefix="test_stage8_disposable_")
    db_path = os.path.join(temp_dir, "test_projects.db")
    test_db = Database(db_path=db_path)
    set_database(test_db)
    orig_run_repo = get_runs_repo()
    set_run_repository(SQLiteRunRepository(test_db))
    orig_storage = get_artifact_storage_instance()
    test_storage = ArtifactStorage(root_dir=os.path.join(temp_dir, "artifacts"), database=test_db)
    set_artifact_storage(test_storage)

    set_model_provider(DeterministicTestProvider())
    client = TestClient(app)

    yield client, temp_dir

    reset_model_provider()
    set_artifact_storage(orig_storage)
    set_run_repository(orig_run_repo)
    set_database(None)
    _runs.clear()
    _orchestrators.clear()
    _threads.clear()
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir, ignore_errors=True)


# ==============================================================================
# PHASE 2: DISPOSABLE REAL-PROJECT INTEGRATION TESTS
# ==============================================================================

def test_phase2_disposable_project_e2e_workflow(client_with_clean_db):
    """
    Step 1-8 of Phase 2:
    1. Import disposable repository through normal product workflow.
    2. Display file tree and read selected file.
    3. Ask project chat a question referencing file using @filename.
    4. Request fix for known, reproducible bug.
    5. Review generated patch before approval.
    6. Reject proposal and confirm workspace is UNCHANGED.
    7. Approve valid proposal in disposable project.
    8. Verify patch only changes permitted files.
    """
    client, _ = client_with_clean_db

    # 1. Import repository
    import_payload = {
        "name": "disposable-token-bucket",
        "files": [
            {"path": "src/token_bucket.py", "content": DISPOSABLE_SRC_BUGGY},
            {"path": "tests/test_token_bucket.py", "content": DISPOSABLE_TEST},
            {"path": "README.md", "content": "# Disposable Token Bucket Service\n"}
        ]
    }
    resp = client.post("/api/v1/projects/import", json=import_payload)
    assert resp.status_code == 201
    proj_data = resp.json()
    project_id = proj_data["project_id"]
    initial_snapshot = proj_data["snapshot_hash"]
    assert proj_data["trust"] == "UNTRUSTED"
    assert proj_data["file_count"] == 3

    # 2. Display file tree and read file
    files_resp = client.get(f"/api/v1/projects/{project_id}/files")
    assert files_resp.status_code == 200
    file_list = [f["path"] for f in files_resp.json()]
    assert "src/token_bucket.py" in file_list
    assert "tests/test_token_bucket.py" in file_list
    assert "README.md" in file_list
    # Assert .baseline is strictly excluded from file explorer
    assert not any(".baseline" in p for p in file_list)

    read_resp = client.get(f"/api/v1/projects/{project_id}/file?path=src/token_bucket.py")
    assert read_resp.status_code == 200
    file_info = read_resp.json()
    assert "class TokenBucket" in file_info["content"]
    assert "self.tokens -= amount" in file_info["content"]

    # 3. Create conversation & ask question with @filename
    conv_resp = client.post(f"/api/v1/projects/{project_id}/conversations", json={"title": "Rate Limiter Audit"})
    assert conv_resp.status_code == 201
    conv_id = conv_resp.json()["conversation_id"]

    msg1_resp = client.post(f"/api/v1/projects/{project_id}/conversations/{conv_id}/messages", json={
        "message": "Can you analyze @src/token_bucket.py for race conditions and invariant violations?",
        "mentioned_files": ["src/token_bucket.py"]
    })
    assert msg1_resp.status_code == 200
    msg1_data = msg1_resp.json()
    assert msg1_data["role"] == "assistant"
    assert "src/token_bucket.py" in msg1_data["mentioned_files"]

    # 4. Request fix for known bug
    msg2_resp = client.post(f"/api/v1/projects/{project_id}/conversations/{conv_id}/messages", json={
        "message": "Fix the bug in @src/token_bucket.py where consume allows overconsumption and negative amounts.",
        "mentioned_files": ["src/token_bucket.py"]
    })
    assert msg2_resp.status_code == 200
    msg2_data = msg2_resp.json()
    proposal = msg2_data["proposal"]
    assert proposal is not None
    proposal_id = proposal["proposal_id"]

    # 5. Review generated patch proposal
    assert proposal["status"] == "PENDING"
    assert proposal["changed_files"] == ["src/token_bucket.py"]
    assert "--- a/src/token_bucket.py" in proposal["diff"]
    assert "+++ b/src/token_bucket.py" in proposal["diff"]

    # 6. Reject one proposal and confirm workspace is UNCHANGED
    reject_resp = client.post(f"/api/v1/projects/{project_id}/proposals/{proposal_id}/reject")
    assert reject_resp.status_code == 200
    assert reject_resp.json()["status"] == "REJECTED"

    # Confirm file on disk is UNMODIFIED
    file_after_reject = client.get(f"/api/v1/projects/{project_id}/file?path=src/token_bucket.py").json()
    assert file_after_reject["content"] == DISPOSABLE_SRC_BUGGY
    proj_after_reject = client.get(f"/api/v1/projects/{project_id}").json()
    assert proj_after_reject["snapshot_hash"] == initial_snapshot

    # 7. Create a valid proposal with exact fix and approve it
    repo = get_project_repository()
    now_iso = "2026-10-28T12:00:00Z"
    valid_prop_id = "prop-valid-fix-01"
    valid_diff = "--- a/src/token_bucket.py\n+++ b/src/token_bucket.py\n@@ -13,2 +13,6 @@\n"
    valid_proposal = ProposalRecord(
        proposal_id=valid_prop_id,
        project_id=project_id,
        conversation_id=conv_id,
        status="PENDING",
        description="Fix overconsumption in TokenBucket",
        diff=valid_diff,
        diff_sha256=hashlib.sha256(valid_diff.encode()).hexdigest(),
        changed_files=["src/token_bucket.py"],
        proposed_content={"src/token_bucket.py": DISPOSABLE_SRC_FIXED},
        created_at=now_iso,
    )
    repo.create_proposal(valid_proposal)

    apply_resp = client.post(f"/api/v1/projects/{project_id}/proposals/{valid_prop_id}/apply")
    assert apply_resp.status_code == 200
    assert apply_resp.json()["status"] == "APPLIED"

    # 8. Verify patch only changes permitted files
    patched_file = client.get(f"/api/v1/projects/{project_id}/file?path=src/token_bucket.py").json()
    assert patched_file["content"].replace("\r\n", "\n") == DISPOSABLE_SRC_FIXED.replace("\r\n", "\n")
    assert "if amount > self.tokens:" in patched_file["content"]

    # Verify README.md and test file remain untouched
    readme_file = client.get(f"/api/v1/projects/{project_id}/file?path=README.md").json()
    assert readme_file["content"].replace("\r\n", "\n") == "# Disposable Token Bucket Service\n"

    # Verify baseline backup in .baseline is untouched
    project_rec = repo.get_project(project_id)
    baseline_src_path = os.path.join(project_rec.root_path, ".baseline", "src", "token_bucket.py")
    assert os.path.exists(baseline_src_path)
    with open(baseline_src_path, "r", encoding="utf-8") as f:
        assert f.read().replace("\r\n", "\n") == DISPOSABLE_SRC_BUGGY.replace("\r\n", "\n")


def test_phase2_deterministic_test_outcomes_baseline_vs_patched():
    """
    Step 9: Run baseline and patched tests deterministically.
    Baseline tests must FAIL on reproducible bug.
    Patched tests must PASS.
    """
    with tempfile.TemporaryDirectory(prefix="disposable_test_run_") as tmpdir:
        src_dir = os.path.join(tmpdir, "src")
        test_dir = os.path.join(tmpdir, "tests")
        os.makedirs(src_dir)
        os.makedirs(test_dir)

        test_file = os.path.join(test_dir, "test_token_bucket.py")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(DISPOSABLE_TEST)

        # Baseline execution
        src_file = os.path.join(src_dir, "token_bucket.py")
        with open(src_file, "w", encoding="utf-8") as f:
            f.write(DISPOSABLE_SRC_BUGGY)

        win_env = os.environ.copy()
        win_env["PYTHONPATH"] = tmpdir
        res_baseline = subprocess.run(
            [sys.executable, "-m", "pytest", test_file],
            cwd=tmpdir,
            env=win_env,
            capture_output=True,
            text=True,
        )
        # Baseline must FAIL
        assert res_baseline.returncode != 0
        assert "FAILED" in res_baseline.stdout or "failed" in res_baseline.stdout

        # Patched execution
        with open(src_file, "w", encoding="utf-8") as f:
            f.write(DISPOSABLE_SRC_FIXED)

        res_patched = subprocess.run(
            [sys.executable, "-m", "pytest", test_file],
            cwd=tmpdir,
            env=win_env,
            capture_output=True,
            text=True,
        )
        # Patched must PASS
        assert res_patched.returncode == 0
        assert "4 passed" in res_patched.stdout


def test_phase2_untrusted_project_verification_fails_closed_without_docker(client_with_clean_db):
    """
    Step 9-10:
    Untrusted imported project verification must select SecureSandboxBackend.
    Because Docker is unavailable on this host, it must FAIL-CLOSED
    to POLICY_BLOCKED with operational_failure="RUNTIME_UNAVAILABLE".
    It must NEVER silently fall back to host execution.
    """
    client, _ = client_with_clean_db

    # Import untrusted project
    import_resp = client.post("/api/v1/projects/import", json={
        "name": "disposable-token-bucket",
        "files": [
            {"path": "src/token_bucket.py", "content": DISPOSABLE_SRC_BUGGY},
            {"path": "tests/test_token_bucket.py", "content": DISPOSABLE_TEST}
        ]
    })
    project_id = import_resp.json()["project_id"]

    # Trigger verification
    verify_resp = client.post(f"/api/v1/projects/{project_id}/verify", json={
        "task_description": "Verify TokenBucket invariants",
        "test_command": ["pytest"]
    })
    assert verify_resp.status_code == 201
    run_id = verify_resp.json()["run_id"]
    assert verify_resp.json()["trust"] == "UNTRUSTED"

    # Wait for the background execution to complete
    t = _threads.get(run_id)
    if t:
        t.join(timeout=10)

    run_record = client.get(f"/api/v1/runs/{run_id}").json()

    assert run_record["state"] != "VERIFIED"
    assert run_record["state"] == "ABORTED"
    assert run_record["status"] == "failed"
    assert run_record["operational_result"] == "POLICY_BLOCKED"

    # Invariant: Evidence receipt cannot claim VERIFIED on blocked run
    receipt = run_record.get("evidence_receipt")
    assert receipt is not None
    assert receipt["verdict"] != "VERIFIED"

    # Confirm event log records explicit RUN_ABORTED with POLICY_BLOCKED
    run_obj = get_run(run_id)
    events = run_obj.events or []
    aborted_events = [e for e in events if e.get("event_type") == "RUN_ABORTED"]
    assert len(aborted_events) > 0
    assert aborted_events[0].get("details", {}).get("result") == "POLICY_BLOCKED"


def test_phase2_receipt_persistence_and_independent_validation():
    """
    Step 11: Persist and independently validate an authoritative EvidenceReceipt.
    """
    receipt = EvidenceReceipt(
        run_id="run-stage8-disposable-01",
        task_id="task-stage8-01",
        repository_snapshot_hash="s" * 64,
        task_contract_hash="c" * 64,
        patch_hash="p" * 64,
        patch_id="PATCH-01",
        patch_digest="d" * 64,
        policy_version="1.0.0",
        verifier_version="1.0.0",
        timestamp="2026-10-28T12:00:00Z",
        verdict=VerificationStatus.VERIFIED,
        verification_scope=VerificationScope(execution="VERIFIED", tests="VERIFIED", invariants="VERIFIED", security="VERIFIED"),
        test_summary=TestResultSummary(discovered=4, executed=4, passed=4, failed=0),
        sandbox_provenance={
            "backend": "SecureSandboxBackend",
            "security_level": "HARDENED_CONTAINER",
            "trust": "UNTRUSTED"
        },
        structured_observation=StructuredObservation(
            execution_id="exec-stage8-01",
            command_identifier="pytest",
            exit_code=0,
            stdout_sha256="1" * 64,
            stderr_sha256="2" * 64,
            stdout_bytes=100,
            stderr_bytes=0,
            duration_ms=250,
            status="SUCCESS",
            sandbox_backend="SecureSandboxBackend",
            security_level="HARDENED_CONTAINER",
            capabilities={"network": False, "read_only_root": True, "drop_capabilities": ["ALL"]},
            workspace_id="ws-stage8-01",
            repository_snapshot_hash="s" * 64,
            patch_hash="d" * 64
        )
    )
    receipt_hash = receipt.calculate_integrity_hash()
    receipt = receipt.model_copy(update={"receipt_hash": receipt_hash})

    # Independent cryptographic validation
    assert verify_receipt_integrity(receipt) is True
    assert receipt.receipt_hash == receipt_hash
    assert receipt.sandbox_provenance["backend"] == "SecureSandboxBackend"


# ==============================================================================
# PHASE 3: NEGATIVE-PATH TESTS
# ==============================================================================

def test_negative_path_traversal_patch_rejected(client_with_clean_db):
    """Prove that a path-traversal patch is rejected and does not escape workspace."""
    client, _ = client_with_clean_db

    import_resp = client.post("/api/v1/projects/import", json={
        "name": "traversal-target",
        "files": [{"path": "src/app.py", "content": "print('ok')\n"}]
    })
    project_id = import_resp.json()["project_id"]

    repo = get_project_repository()
    # Create proposal attempting path traversal
    bad_proposal = ProposalRecord(
        proposal_id="prop-traversal-01",
        project_id=project_id,
        conversation_id="conv-01",
        status="PENDING",
        description="Malicious traversal patch",
        diff="--- /dev/null\n+++ ../evil.py\n",
        diff_sha256="0" * 64,
        changed_files=["../evil.py"],
        proposed_content={"../evil.py": "malicious code"},
        created_at="2026-10-28T12:00:00Z",
    )
    repo.create_proposal(bad_proposal)

    # Applying must fail with 400 Bad Request
    apply_resp = client.post(f"/api/v1/projects/{project_id}/proposals/prop-traversal-01/apply")
    assert apply_resp.status_code == 400
    assert "Security violation" in apply_resp.json()["detail"] or "Path traversal" in apply_resp.json()["detail"]


def test_negative_patch_targeting_protected_file_rejected(client_with_clean_db):
    """Prove that a patch targeting a protected file (.baseline) is rejected."""
    client, _ = client_with_clean_db

    import_resp = client.post("/api/v1/projects/import", json={
        "name": "protected-target",
        "files": [{"path": "src/app.py", "content": "print('safe')\n"}]
    })
    project_id = import_resp.json()["project_id"]

    repo = get_project_repository()
    # Create proposal attempting to overwrite .baseline
    bad_proposal = ProposalRecord(
        proposal_id="prop-baseline-attack-01",
        project_id=project_id,
        conversation_id="conv-01",
        status="PENDING",
        description="Malicious baseline tamper patch",
        diff="--- .baseline/src/app.py\n+++ .baseline/src/app.py\n",
        diff_sha256="0" * 64,
        changed_files=[".baseline/src/app.py"],
        proposed_content={".baseline/src/app.py": "tampered baseline"},
        created_at="2026-10-28T12:00:00Z",
    )
    repo.create_proposal(bad_proposal)

    apply_resp = client.post(f"/api/v1/projects/{project_id}/proposals/prop-baseline-attack-01/apply")
    assert apply_resp.status_code == 400
    assert "prohibited" in apply_resp.json()["detail"].lower() or "security violation" in apply_resp.json()["detail"].lower()


def test_negative_malformed_patch_rejected(client_with_clean_db):
    """Prove that a malformed patch (null bytes, colons) is rejected."""
    client, _ = client_with_clean_db

    import_resp = client.post("/api/v1/projects/import", json={
        "name": "malformed-target",
        "files": [{"path": "src/app.py", "content": "print('clean')\n"}]
    })
    project_id = import_resp.json()["project_id"]

    repo = get_project_repository()
    bad_proposal = ProposalRecord(
        proposal_id="prop-malformed-01",
        project_id=project_id,
        conversation_id="conv-01",
        status="PENDING",
        description="Malformed path patch",
        diff="",
        diff_sha256="0" * 64,
        changed_files=["src/app\0.py"],
        proposed_content={"src/app\0.py": "corrupted"},
        created_at="2026-10-28T12:00:00Z",
    )
    repo.create_proposal(bad_proposal)

    apply_resp = client.post(f"/api/v1/projects/{project_id}/proposals/prop-malformed-01/apply")
    assert apply_resp.status_code == 400
    assert "Security violation" in apply_resp.json()["detail"]


def test_negative_failing_test_cannot_produce_verified():
    """Prove that a failing test cannot produce a valid VERIFIED receipt."""
    receipt_failing = EvidenceReceipt(
        run_id="run-neg-fail-01",
        task_id="task-neg-01",
        repository_snapshot_hash="s" * 64,
        task_contract_hash="c" * 64,
        patch_hash="p" * 64,
        policy_version="1.0.0",
        verifier_version="1.0.0",
        timestamp="2026-10-28T12:00:00Z",
        verdict=VerificationStatus.VERIFIED,  # Falsely claiming VERIFIED!
        verification_scope=VerificationScope(execution="VERIFIED", tests="FAILED"),  # But tests failed!
        test_summary=TestResultSummary(discovered=2, executed=2, passed=1, failed=1),
        sandbox_provenance={"backend": "SecureSandboxBackend"},
    )
    receipt_failing = receipt_failing.model_copy(update={"receipt_hash": receipt_failing.calculate_integrity_hash()})
    assert verify_receipt_integrity(receipt_failing) is False


def test_negative_unexecuted_required_check_cannot_produce_verified():
    """Prove that an unexecuted required check cannot produce a valid VERIFIED receipt."""
    receipt_unexec = EvidenceReceipt(
        run_id="run-neg-unexec-01",
        task_id="task-neg-02",
        repository_snapshot_hash="s" * 64,
        task_contract_hash="c" * 64,
        patch_hash="p" * 64,
        policy_version="1.0.0",
        verifier_version="1.0.0",
        timestamp="2026-10-28T12:00:00Z",
        verdict=VerificationStatus.VERIFIED,
        verification_scope=VerificationScope(execution="NOT EXECUTED", tests="VERIFIED"),  # Execution NOT EXECUTED
        test_summary=TestResultSummary(discovered=2, executed=2, passed=2, failed=0),
        sandbox_provenance={"backend": "SecureSandboxBackend"},
    )
    receipt_unexec = receipt_unexec.model_copy(update={"receipt_hash": receipt_unexec.calculate_integrity_hash()})
    # Cannot be VERIFIED if execution scope is NOT EXECUTED or FAILED
    assert verify_receipt_integrity(receipt_unexec) is False


def test_negative_receipt_with_mismatched_provenance_rejected():
    """Prove that a receipt with mismatched provenance or snapshot hashes is rejected."""
    receipt_mismatch = EvidenceReceipt(
        run_id="run-neg-mismatch-01",
        task_id="task-neg-03",
        repository_snapshot_hash="a" * 64,
        task_contract_hash="c" * 64,
        patch_hash="p" * 64,
        patch_id="PATCH-01",
        patch_digest="b" * 64,
        policy_version="1.0.0",
        verifier_version="1.0.0",
        timestamp="2026-10-28T12:00:00Z",
        verdict=VerificationStatus.VERIFIED,
        verification_scope=VerificationScope(execution="VERIFIED", tests="VERIFIED"),
        test_summary=TestResultSummary(discovered=1, executed=1, passed=1, failed=0),
        sandbox_provenance={"backend": "SecureSandboxBackend"},
        structured_observation=StructuredObservation(
            execution_id="exec-01",
            command_identifier="pytest",
            exit_code=0,
            stdout_sha256="1" * 64,
            stderr_sha256="2" * 64,
            stdout_bytes=50,
            stderr_bytes=0,
            duration_ms=100,
            status="SUCCESS",
            sandbox_backend="SecureSandboxBackend",
            security_level="HARDENED_CONTAINER",
            capabilities={},
            workspace_id="ws-01",
            repository_snapshot_hash="f" * 64,  # Mismatched snapshot hash!
            patch_hash="b" * 64
        )
    )
    receipt_mismatch = receipt_mismatch.model_copy(update={"receipt_hash": receipt_mismatch.calculate_integrity_hash()})
    assert verify_receipt_integrity(receipt_mismatch) is False
