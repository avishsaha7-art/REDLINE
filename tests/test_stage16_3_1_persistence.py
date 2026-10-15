import os
import time
import json
import sqlite3
import threading
import pytest
from starlette.testclient import TestClient

from backend.models.schemas import TaskContract, ResourceBudget, Run, RunState, OperationalResult, PatchCandidate
from backend.models.evidence import EvidenceReceipt, JudgeExplanation, VerificationScope, verify_receipt_integrity
from backend.verification.models import VerificationStatus
from backend.storage.database import Database
from backend.storage.repositories import SQLiteRunRepository, RunStoreProxy
from backend.api.app import app
from backend.api.routes.runs import set_run_repository, reset_run_store, set_model_provider
from backend.models.deterministic_provider import DeterministicTestProvider


def make_test_contract(task_id: str = "task-test-1", repo_id: str = "demo-repo-a") -> TaskContract:
    return TaskContract(
        task_id=task_id,
        repository_id=repo_id,
        base_commit_or_snapshot="base123",
        task_description="Fix bug in main.py",
        constraints=["Do not modify other files"],
        acceptance_criteria=["Tests must pass"],
        allowed_scope=["main.py"],
        resource_budget=ResourceBudget(max_iterations=10, max_runtime=60),
        repository_trust="TRUSTED_DEVELOPMENT"
    )


def make_test_receipt(run_id: str, task_id: str, verdict: VerificationStatus = VerificationStatus.VERIFIED) -> EvidenceReceipt:
    receipt = EvidenceReceipt(
        receipt_schema_version="1.0",
        run_id=run_id,
        task_id=task_id,
        repository_snapshot_hash="snap-hash-abc",
        task_contract_hash="contract-hash-xyz",
        patch_hash="diff-sha256-123",
        patch_lineage=["patch-1", "patch-2"],
        verdict=verdict,
        verification_scope=VerificationScope(execution="PASS", tests="PASS", invariants="PASS", security="PASS"),
        policy_version="1.0",
        verifier_version="1.0",
        evidence_hashes=["ev1", "ev2"],
        timestamp="2026-10-13T12:00:00Z"
    )
    h = receipt.calculate_integrity_hash()
    return receipt.model_copy(update={"receipt_hash": h})


@pytest.fixture
def temp_db(tmp_path):
    db_file = str(tmp_path / "test_redline.db")
    db = Database(db_path=db_file)
    repo = SQLiteRunRepository(database=db)
    set_run_repository(repo)
    set_model_provider(DeterministicTestProvider())
    yield repo, db, db_file
    reset_run_store()
    db.close()


def test_1_create_and_retrieve_run(temp_db):
    """Test 1: Creating and retrieving a run durably."""
    repo, db, _ = temp_db
    contract = make_test_contract("task-c1")
    run = Run(
        run_id="run-c1",
        task_id="task-c1",
        task_contract=contract,
        current_state=RunState.INIT,
        events=[{"event_type": "RUN_CREATED", "timestamp": "2026-10-13T12:00:00Z"}]
    )
    repo.save_new_run(run)

    retrieved = repo.get_run("run-c1")
    assert retrieved is not None
    assert retrieved.run_id == "run-c1"
    assert retrieved.task_id == "task-c1"
    assert retrieved.current_state == RunState.INIT
    assert retrieved.task_contract.task_id == "task-c1"
    assert len(retrieved.events) == 1
    assert retrieved.events[0]["event_type"] == "RUN_CREATED"


def test_2_listing_runs_deterministic_order(temp_db):
    """Test 2: Listing runs with deterministic ordering (created_at DESC, run_id DESC)."""
    repo, db, _ = temp_db
    for i in range(3):
        contract = make_test_contract(f"task-order-{i}")
        run = Run(
            run_id=f"run-order-{i:02d}",
            task_id=f"task-order-{i}",
            task_contract=contract,
            current_state=RunState.INIT,
            events=[{"event_type": "RUN_CREATED", "timestamp": f"2026-10-13T12:00:0{i}Z"}]
        )
        repo.save_new_run(run)

    runs = repo.list_runs()
    assert len(runs) == 3
    # Most recent timestamp should be first
    assert runs[0].run_id == "run-order-02"
    assert runs[1].run_id == "run-order-01"
    assert runs[2].run_id == "run-order-00"


def test_3_reading_run_after_reopening_database(temp_db):
    """Test 3: Reading a run after closing and reopening the database connection."""
    repo, db, db_file = temp_db
    contract = make_test_contract("task-reopen")
    receipt = make_test_receipt("run-reopen", "task-reopen", VerificationStatus.VERIFIED)
    patch = PatchCandidate(
        patch_id="patch-reopen-1",
        task_id="task-reopen",
        base_commit_or_snapshot="base1",
        diff="--- a/test.py\n+++ b/test.py\n@@ -1 +1 @@\n-old\n+new",
        changed_files=["test.py"]
    )
    run = Run(
        run_id="run-reopen",
        task_id="task-reopen",
        task_contract=contract,
        current_state=RunState.VERIFIED,
        patches=[patch],
        evidence_receipt=receipt,
        events=[{"event_type": "RUN_COMPLETED", "timestamp": "2026-10-13T12:10:00Z"}]
    )
    repo.save_new_run(run)
    db.close()

    # Reopen new connection to same file
    new_db = Database(db_path=db_file)
    new_repo = SQLiteRunRepository(database=new_db)
    loaded = new_repo.get_run("run-reopen")

    assert loaded is not None
    assert loaded.run_id == "run-reopen"
    assert loaded.current_state == RunState.VERIFIED
    assert loaded.evidence_receipt is not None
    assert loaded.evidence_receipt.verdict == VerificationStatus.VERIFIED
    assert verify_receipt_integrity(loaded.evidence_receipt) is True
    assert len(loaded.patches) == 1
    assert loaded.patches[0].diff == patch.diff
    new_db.close()


def test_4_reading_historical_runs_via_api_after_restart(temp_db):
    """Test 4: Reading historical runs after application restart via API."""
    repo, db, db_file = temp_db
    client = TestClient(app)

    # 1. Create a run via API
    resp = client.post("/api/v1/runs", json=make_test_contract("task-restart").model_dump())
    assert resp.status_code == 201
    run_id = resp.json()["run_id"]

    # Wait for run to reach terminal state
    for _ in range(50):
        status_resp = client.get(f"/api/v1/runs/{run_id}")
        if status_resp.status_code == 200 and status_resp.json()["status"] in ("completed", "failed"):
            break
        time.sleep(0.05)

    # 2. Simulate complete application restart:
    # Clear in-memory references and attach brand new repository to the same DB file
    new_db = Database(db_path=db_file)
    new_repo = SQLiteRunRepository(database=new_db)
    set_run_repository(new_repo)

    # 3. Verify historical run is retrievable via API endpoints
    hist_resp = client.get(f"/api/v1/runs/{run_id}")
    assert hist_resp.status_code == 200
    hist_data = hist_resp.json()
    assert hist_data["run_id"] == run_id
    assert hist_data["task_id"] == "task-restart"
    assert hist_data["status"] in ("completed", "failed")

    # Verify receipt, diff, and list endpoints
    list_resp = client.get("/api/v1/runs")
    assert list_resp.status_code == 200
    all_runs = list_resp.json()
    assert any(r["run_id"] == run_id for r in all_runs)

    if hist_data["status"] == "completed":
        rec_resp = client.get(f"/api/v1/runs/{run_id}/receipt")
        assert rec_resp.status_code == 200
        assert rec_resp.json()["verdict"] == VerificationStatus.VERIFIED.value

        diff_resp = client.get(f"/api/v1/runs/{run_id}/diff")
        assert diff_resp.status_code == 200
        assert diff_resp.json()["run_id"] == run_id

    new_db.close()


def test_5_terminal_states_and_verdicts_preserved(temp_db):
    """Test 5: Preserving terminal states (VERIFIED, ABORTED) and verdicts."""
    repo, db, _ = temp_db
    contract = make_test_contract("task-terminal")

    # Run with REJECTED verdict
    receipt_rej = make_test_receipt("run-rej", "task-terminal", VerificationStatus.REJECTED)
    run_rej = Run(
        run_id="run-rej",
        task_id="task-terminal",
        task_contract=contract,
        current_state=RunState.ABORTED,
        evidence_receipt=receipt_rej,
        operational_result=OperationalResult.POLICY_BLOCKED,
        events=[{"event_type": "RUN_ABORTED", "timestamp": "2026-10-13T12:00:00Z"}]
    )
    repo.save_new_run(run_rej)

    loaded_rej = repo.get_run("run-rej")
    assert loaded_rej.current_state == RunState.ABORTED
    assert loaded_rej.operational_result == OperationalResult.POLICY_BLOCKED
    assert loaded_rej.evidence_receipt.verdict == VerificationStatus.REJECTED

    # Invariant: REJECTED verdict cannot become VERIFIED during round-trip
    assert loaded_rej.current_state != RunState.VERIFIED
    assert loaded_rej.evidence_receipt.verdict != VerificationStatus.VERIFIED


def test_6_evidence_receipt_hashes_and_lineage_preserved(temp_db):
    """Test 6: Preserving evidence receipt hashes, integrity and patch lineage."""
    repo, db, _ = temp_db
    contract = make_test_contract("task-lineage")
    receipt = make_test_receipt("run-lin", "task-lineage", VerificationStatus.VERIFIED)
    run = Run(
        run_id="run-lin",
        task_id="task-lineage",
        task_contract=contract,
        current_state=RunState.VERIFIED,
        evidence_receipt=receipt,
        events=[{"event_type": "RUN_COMPLETED", "timestamp": "2026-10-13T12:00:00Z"}]
    )
    repo.save_new_run(run)

    loaded = repo.get_run("run-lin")
    assert loaded.evidence_receipt.patch_lineage == ["patch-1", "patch-2"]
    assert loaded.evidence_receipt.receipt_hash == receipt.receipt_hash
    assert verify_receipt_integrity(loaded.evidence_receipt) is True


def test_7_handling_missing_run_ids(temp_db):
    """Test 7: Missing run IDs return None / 404 cleanly."""
    repo, db, _ = temp_db
    client = TestClient(app)

    assert repo.get_run("run-nonexistent") is None

    resp = client.get("/api/v1/runs/run-nonexistent")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Run not found"

    rec_resp = client.get("/api/v1/runs/run-nonexistent/receipt")
    assert rec_resp.status_code == 404


def test_8_handling_corrupt_records_fails_closed(temp_db):
    """Test 8: Handling corrupt database records fails closed without fabricating success."""
    repo, db, _ = temp_db
    # Insert a corrupt row directly into SQL
    with db.connection() as conn:
        conn.execute(
            """
            INSERT INTO runs (
                run_id, task_id, current_state, current_iteration, task_contract_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("run-corrupt", "task-bad", "VERIFIED", 0, "{invalid json", "2026-10-13T12:00:00Z", "2026-10-13T12:00:00Z")
        )

    # Reconstructing should raise a validation error, never fabricate defaults or success
    with pytest.raises(Exception):
        repo.get_run("run-corrupt")


def test_9_transaction_failure_and_rollback(temp_db):
    """Test 9: Database write failures roll back cleanly without partial phantom records."""
    repo, db, _ = temp_db
    contract = make_test_contract("task-tx")
    run = Run(
        run_id="run-tx",
        task_id="task-tx",
        task_contract=contract,
        current_state=RunState.INIT,
        events=[{"event_type": "RUN_CREATED", "timestamp": "2026-10-13T12:00:00Z"}]
    )
    repo.save_new_run(run)

    # Attempting to save same primary key should raise IntegrityError and rollback
    with pytest.raises(sqlite3.IntegrityError):
        repo.save_new_run(run)

    # Verify existing run is intact and no duplicate events inserted
    loaded = repo.get_run("run-tx")
    assert loaded is not None
    assert len(loaded.events) == 1


def test_10_concurrent_read_write_safety(temp_db):
    """Test 10: Concurrent reads and writes execute without locking errors under WAL mode."""
    repo, db, _ = temp_db
    errors = []

    def writer(thread_id: int):
        try:
            for j in range(10):
                contract = make_test_contract(f"task-t{thread_id}-{j}")
                run = Run(
                    run_id=f"run-t{thread_id}-{j}",
                    task_id=f"task-t{thread_id}-{j}",
                    task_contract=contract,
                    current_state=RunState.INIT,
                    events=[{"event_type": "STEP", "timestamp": "2026-10-13T12:00:00Z"}]
                )
                repo.save_new_run(run)
        except Exception as e:
            errors.append(e)

    def reader():
        try:
            for _ in range(20):
                repo.list_runs()
                time.sleep(0.01)
        except Exception as e:
            errors.append(e)

    threads = [
        threading.Thread(target=writer, args=(1,)),
        threading.Thread(target=writer, args=(2,)),
        threading.Thread(target=reader),
        threading.Thread(target=reader),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
    all_runs = repo.list_runs()
    assert len(all_runs) == 20


def test_11_incomplete_runs_never_marked_verified_on_recovery(temp_db):
    """Test 11: In-flight/incomplete runs interrupted by restart transition to ABORTED, never VERIFIED."""
    repo, db, _ = temp_db
    contract = make_test_contract("task-in-flight")

    # Simulate runs in intermediate non-terminal states
    for state in [RunState.INIT, RunState.PLAN, RunState.BUILD, RunState.TEST, RunState.VERIFY, RunState.JUDGE]:
        run = Run(
            run_id=f"run-{state.value.lower()}",
            task_id="task-in-flight",
            task_contract=contract,
            current_state=state,
            events=[{"event_type": "STAGE_START", "timestamp": "2026-10-13T12:00:00Z"}]
        )
        repo.save_new_run(run)

    # Run recovery sweep (simulating restart recovery)
    recovered = repo.recover_interrupted_runs()
    assert recovered == 6

    # Verify all in-flight runs are now ABORTED with TOOL_FAILURE
    for state in [RunState.INIT, RunState.PLAN, RunState.BUILD, RunState.TEST, RunState.VERIFY, RunState.JUDGE]:
        loaded = repo.get_run(f"run-{state.value.lower()}")
        assert loaded.current_state == RunState.ABORTED
        assert loaded.current_state != RunState.VERIFIED
        assert loaded.operational_result == OperationalResult.TOOL_FAILURE
        assert "PROCESS_INTERRUPTED" in loaded.operational_error
        assert loaded.events[-1]["event_type"] == "RUN_ABORTED"


def test_12_interrupted_untrusted_runs_do_not_resume_execution(temp_db):
    """Test 12: Interrupted runs remain halted as ABORTED; untrusted code is never auto-resumed."""
    repo, db, db_file = temp_db
    contract = make_test_contract("task-untrusted", repo_id="untrusted-repo")
    contract.repository_trust = "UNTRUSTED"

    run = Run(
        run_id="run-untrusted-interrupted",
        task_id="task-untrusted",
        task_contract=contract,
        current_state=RunState.BUILD,
        events=[{"event_type": "BUILD_START", "timestamp": "2026-10-13T12:00:00Z"}]
    )
    repo.save_new_run(run)

    # Simulate restart
    new_db = Database(db_path=db_file)
    new_repo = SQLiteRunRepository(database=new_db)
    new_repo.recover_interrupted_runs()

    loaded = new_repo.get_run("run-untrusted-interrupted")
    assert loaded.current_state == RunState.ABORTED
    # Run is in terminal aborted state; background threads/execution are not spawned
    client = TestClient(app)
    set_run_repository(new_repo)
    status_resp = client.get("/api/v1/runs/run-untrusted-interrupted")
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "failed"
    assert status_resp.json()["state"] == RunState.ABORTED.value
    new_db.close()


def test_13_defense_in_depth_tampered_state_verdict_contradiction(temp_db):
    """Test 13: Invariant: VERIFIED state requires VERIFIED receipt verdict. Inconsistency fails closed to ABORTED."""
    repo, db, _ = temp_db
    contract = make_test_contract("task-tamper")

    # Manually persist a contradiction: current_state=VERIFIED, but verdict=INCONCLUSIVE
    receipt_inc = make_test_receipt("run-tamper", "task-tamper", VerificationStatus.INCONCLUSIVE)
    run = Run(
        run_id="run-tamper",
        task_id="task-tamper",
        task_contract=contract,
        current_state=RunState.VERIFIED,  # Contradiction
        evidence_receipt=receipt_inc,
        events=[{"event_type": "TAMPERED", "timestamp": "2026-10-13T12:00:00Z"}]
    )
    repo.save_new_run(run)

    # Re-reading through repo must fail closed to ABORTED
    loaded = repo.get_run("run-tamper")
    assert loaded.current_state == RunState.ABORTED
    assert loaded.current_state != RunState.VERIFIED

    # API list endpoint must also enforce this invariant
    client = TestClient(app)
    set_run_repository(repo)
    list_resp = client.get("/api/v1/runs")
    assert list_resp.status_code == 200
    item = next(r for r in list_resp.json() if r["run_id"] == "run-tamper")
    assert item["final_state"] == RunState.ABORTED.value
    assert item["final_state"] != RunState.VERIFIED.value
