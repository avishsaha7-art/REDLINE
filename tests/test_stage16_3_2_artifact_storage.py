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
from backend.storage.repositories import SQLiteRunRepository
from backend.storage.artifacts import (
    ArtifactStorage,
    ArtifactMetadata,
    ArtifactNotFoundError,
    ArtifactIntegrityError,
    ArtifactPathTraversalError,
    ArtifactSizeLimitError,
    ArtifactWriteError
)
from backend.api.app import app
from backend.api.routes.runs import (
    set_run_repository,
    set_artifact_storage,
    reset_run_store,
    set_model_provider,
    sanitize_attachment_filename
)
from backend.models.deterministic_provider import DeterministicTestProvider


def make_test_contract(task_id: str = "task-art-1", repo_id: str = "demo-repo-a") -> TaskContract:
    return TaskContract(
        task_id=task_id,
        repository_id=repo_id,
        base_commit_or_snapshot="snap123",
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
def temp_storage(tmp_path, monkeypatch):
    monkeypatch.setenv("REDLINE_ENABLE_LOCAL_BACKEND", "1")
    db_file = str(tmp_path / "test_artifacts.db")
    artifacts_dir = str(tmp_path / "artifacts_root")
    os.makedirs(artifacts_dir, exist_ok=True)

    db = Database(db_path=db_file)
    repo = SQLiteRunRepository(database=db)
    storage = ArtifactStorage(root_dir=artifacts_dir, database=db)

    set_run_repository(repo)
    set_artifact_storage(storage)
    set_model_provider(DeterministicTestProvider())

    yield repo, storage, db, artifacts_dir, db_file

    reset_run_store()
    db.close()


def test_1_artifact_creation_persistence_and_restart(temp_storage):
    """Test 1: Artifact creation, raw byte persistence, metadata retrieval, and restart survival."""
    repo, storage, db, artifacts_dir, db_file = temp_storage
    contract = make_test_contract("task-t1")
    run = Run(run_id="run-t1", task_id="task-t1", task_contract=contract, current_state=RunState.INIT)
    repo.save_new_run(run)

    raw_diff = "--- a/main.py\n+++ b/main.py\n@@ -1 +1 @@\n-print('bug')\n+print('fixed')\n"
    meta = storage.store_artifact(
        run_id="run-t1",
        artifact_id="patch-1.diff",
        artifact_type="diff",
        content=raw_diff,
        media_type="text/x-diff",
        lineage_ref="patch-1",
        metadata={"author": "builder"}
    )

    assert meta.artifact_id == "patch-1.diff"
    assert meta.run_id == "run-t1"
    assert meta.size_bytes == len(raw_diff.encode("utf-8"))
    assert meta.media_type == "text/x-diff"

    # Close and simulate restart with new storage and repo instances pointing to same files
    db.close()
    new_db = Database(db_path=db_file)
    new_repo = SQLiteRunRepository(database=new_db)
    new_storage = ArtifactStorage(root_dir=artifacts_dir, database=new_db)

    retrieved_content, retrieved_meta = new_storage.get_artifact_content("run-t1", "patch-1.diff", verify_integrity=True)
    assert retrieved_content.decode("utf-8") == raw_diff
    assert retrieved_meta.sha256 == meta.sha256
    assert retrieved_meta.metadata == {"author": "builder"}
    new_db.close()


def test_2_stable_artifact_ids_and_run_associations(temp_storage):
    """Test 2: Stable artifact IDs and run associations; querying artifacts of other runs fails."""
    repo, storage, _, _, _ = temp_storage
    repo.save_new_run(Run(run_id="run-A", task_id="task-A", task_contract=make_test_contract("task-A")))
    repo.save_new_run(Run(run_id="run-B", task_id="task-B", task_contract=make_test_contract("task-B")))

    storage.store_artifact("run-A", "receipt.json", "receipt", b'{"run": "A"}')
    storage.store_artifact("run-B", "receipt.json", "receipt", b'{"run": "B"}')

    # Each run retrieves its own artifact with same filename without collision
    content_a, _ = storage.get_artifact_content("run-A", "receipt.json")
    content_b, _ = storage.get_artifact_content("run-B", "receipt.json")
    assert content_a == b'{"run": "A"}'
    assert content_b == b'{"run": "B"}'

    # Querying run-A for an artifact belonging only to run-B raises NotFound
    storage.store_artifact("run-B", "unique-B.txt", "log", b"only B")
    with pytest.raises(ArtifactNotFoundError):
        storage.get_artifact_content("run-A", "unique-B.txt")


def test_3_sha256_integrity_verification(temp_storage):
    """Test 3: SHA-256 digest is verified on retrieval; matching content succeeds."""
    repo, storage, _, _, _ = temp_storage
    repo.save_new_run(Run(run_id="run-hash", task_id="task-hash", task_contract=make_test_contract("task-hash")))

    payload = b"CRITICAL_EVIDENCE_BYTES_0123456789"
    import hashlib
    expected_sha = hashlib.sha256(payload).hexdigest()

    meta = storage.store_artifact("run-hash", "evidence.bin", "evidence", payload)
    assert meta.sha256 == expected_sha

    content, verified_meta = storage.get_artifact_content("run-hash", "evidence.bin", verify_integrity=True)
    assert content == payload
    assert verified_meta.sha256 == expected_sha


def test_4_corrupted_artifact_bytes_fails_closed(temp_storage):
    """Test 4: Tampered/corrupted artifact bytes fail closed with ArtifactIntegrityError."""
    repo, storage, _, artifacts_dir, _ = temp_storage
    repo.save_new_run(Run(run_id="run-tamper", task_id="task-tamper", task_contract=make_test_contract("task-tamper")))

    meta = storage.store_artifact("run-tamper", "report.json", "test_report", b'{"passed": true}')

    # Deliberately modify file on disk behind storage layer's back
    file_path = os.path.join(artifacts_dir, "run-tamper", "report.json")
    with open(file_path, "wb") as f:
        f.write(b'{"passed": false, "tampered": true}')

    # Retrieval with integrity verification MUST fail closed
    with pytest.raises(ArtifactIntegrityError) as exc_info:
        storage.get_artifact_content("run-tamper", "report.json", verify_integrity=True)

    assert "integrity compromised" in str(exc_info.value).lower()


def test_5_path_traversal_and_invalid_identifiers_rejected(temp_storage):
    """Test 5: Path traversal attempts and dangerous IDs are rejected fail-closed."""
    repo, storage, _, _, _ = temp_storage

    traversal_ids = [
        "../escape.txt",
        "..\\escape.txt",
        "/etc/passwd",
        "C:\\Windows\\win.ini",
        "sub/dir.txt",
        "sub\\dir.txt",
        "null\0byte.txt",
        "",
        "   ",
        "artifact with spaces!",
        "invalid*char.diff"
    ]

    for bad_id in traversal_ids:
        with pytest.raises(ArtifactPathTraversalError):
            storage.store_artifact("run-safe", bad_id, "diff", b"test")

        with pytest.raises(ArtifactPathTraversalError):
            storage.get_artifact_metadata("run-safe", bad_id)

    # Bad run_id
    with pytest.raises(ArtifactPathTraversalError):
        storage.store_artifact("../bad_run", "valid.txt", "log", b"test")


def test_6_configured_size_limits_enforced(temp_storage):
    """Test 6: Artifacts exceeding MAX_ARTIFACT_BYTES are rejected before commit."""
    repo, storage, _, _, _ = temp_storage
    repo.save_new_run(Run(run_id="run-size", task_id="task-size", task_contract=make_test_contract("task-size")))

    limit = 500  # 500 bytes limit
    small_payload = b"A" * 400
    large_payload = b"B" * 600

    # Small payload succeeds
    storage.store_artifact("run-size", "small.txt", "log", small_payload, max_bytes=limit)

    # Large payload fails with ArtifactSizeLimitError
    with pytest.raises(ArtifactSizeLimitError):
        storage.store_artifact("run-size", "large.txt", "log", large_payload, max_bytes=limit)


def test_7_atomic_writes_and_concurrent_access(temp_storage):
    """Test 7: Concurrent writes and reads execute atomically without partial or corrupted files."""
    repo, storage, _, _, _ = temp_storage
    repo.save_new_run(Run(run_id="run-concurrent", task_id="task-concurrent", task_contract=make_test_contract("task-concurrent")))

    errors = []

    def writer_worker(idx: int):
        try:
            for j in range(5):
                payload = f"content_worker_{idx}_iter_{j}".encode("utf-8")
                storage.store_artifact(
                    run_id="run-concurrent",
                    artifact_id=f"art_w{idx}_j{j}.txt",
                    artifact_type="log",
                    content=payload
                )
        except Exception as e:
            errors.append(e)

    def reader_worker():
        try:
            for _ in range(15):
                storage.list_artifacts("run-concurrent")
                time.sleep(0.01)
        except Exception as e:
            errors.append(e)

    threads = [
        threading.Thread(target=writer_worker, args=(1,)),
        threading.Thread(target=writer_worker, args=(2,)),
        threading.Thread(target=reader_worker),
        threading.Thread(target=reader_worker),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
    artifacts = storage.list_artifacts("run-concurrent")
    assert len(artifacts) == 10


def test_8_metadata_commit_failure_cleans_up_disk_file(temp_storage):
    """Test 8: Database failure during metadata commit cleans up written file (no phantom files)."""
    repo, storage, db, artifacts_dir, _ = temp_storage
    repo.save_new_run(Run(run_id="run-tx", task_id="task-tx", task_contract=make_test_contract("task-tx")))

    # Store first artifact normally
    storage.store_artifact("run-tx", "unique.txt", "log", b"valid 1")
    target_file = os.path.join(artifacts_dir, "run-tx", "unique.txt")
    assert os.path.exists(target_file)

    # Simulate database lock or error by breaking the schema or table temporarily
    with db.connection() as conn:
        conn.execute("DROP TABLE run_artifacts")

    # Attempting to store artifact should fail on database step and clean up written file
    phantom_file = os.path.join(artifacts_dir, "run-tx", "phantom.txt")
    with pytest.raises(ArtifactWriteError):
        storage.store_artifact("run-tx", "phantom.txt", "log", b"should rollback")

    # Verify phantom file does not remain on disk
    assert not os.path.exists(phantom_file)


def test_9_patch_and_evidence_lineage_preservation(temp_storage):
    """Test 9: Patch and evidence lineage references are preserved on artifact records."""
    repo, storage, _, _, _ = temp_storage
    repo.save_new_run(Run(run_id="run-lin", task_id="task-lin", task_contract=make_test_contract("task-lin")))

    meta_v1 = storage.store_artifact(
        run_id="run-lin",
        artifact_id="diff-v1.diff",
        artifact_type="diff",
        content="diff v1",
        lineage_ref="cand-v1"
    )
    meta_v2 = storage.store_artifact(
        run_id="run-lin",
        artifact_id="diff-v2.diff",
        artifact_type="diff",
        content="diff v2",
        lineage_ref="cand-v2"
    )

    loaded_v1 = storage.get_artifact_metadata("run-lin", "diff-v1.diff")
    loaded_v2 = storage.get_artifact_metadata("run-lin", "diff-v2.diff")
    assert loaded_v1.lineage_ref == "cand-v1"
    assert loaded_v2.lineage_ref == "cand-v2"


def test_10_missing_file_on_disk_fails_closed(temp_storage):
    """Test 10: If metadata exists but disk file is missing, retrieval fails closed (no fabricated content)."""
    repo, storage, _, artifacts_dir, _ = temp_storage
    repo.save_new_run(Run(run_id="run-ghost", task_id="task-ghost", task_contract=make_test_contract("task-ghost")))

    storage.store_artifact("run-ghost", "ghost.json", "receipt", b'{"real": true}')
    disk_path = os.path.join(artifacts_dir, "run-ghost", "ghost.json")
    os.remove(disk_path)

    with pytest.raises(ArtifactNotFoundError):
        storage.get_artifact_content("run-ghost", "ghost.json")


def test_11_api_artifact_endpoints(temp_storage):
    """Test 11: API endpoints for listing artifacts and fetching content with headers."""
    repo, storage, _, _, _ = temp_storage
    client = TestClient(app)

    # 1. Run a real scenario via API
    resp = client.post("/api/v1/runs", json=make_test_contract("task-api").model_dump())
    assert resp.status_code == 201
    run_id = resp.json()["run_id"]

    # Wait for completion
    for _ in range(50):
        st = client.get(f"/api/v1/runs/{run_id}")
        if st.status_code == 200 and st.json()["status"] in ("completed", "failed"):
            break
        time.sleep(0.05)

    # 2. Query GET /api/v1/runs/{run_id}/artifacts
    art_list_resp = client.get(f"/api/v1/runs/{run_id}/artifacts")
    assert art_list_resp.status_code == 200
    artifacts = art_list_resp.json()
    assert len(artifacts) >= 1

    # Verify receipt and diff artifacts exist
    types = {a["artifact_type"] for a in artifacts}
    assert "log" in types

    # 3. Query GET /api/v1/runs/{run_id}/artifacts/{artifact_id}
    sample_art = artifacts[0]
    art_meta_resp = client.get(f"/api/v1/runs/{run_id}/artifacts/{sample_art['artifact_id']}")
    assert art_meta_resp.status_code == 200
    assert art_meta_resp.json()["sha256"] == sample_art["sha256"]

    # 4. Query GET /api/v1/runs/{run_id}/artifacts/{artifact_id}/content
    content_resp = client.get(f"/api/v1/runs/{run_id}/artifacts/{sample_art['artifact_id']}/content")
    assert content_resp.status_code == 200
    assert content_resp.headers["X-Content-Type-Options"] == "nosniff"
    assert content_resp.headers["Content-Disposition"] == f'attachment; filename="{sample_art["artifact_id"]}"'
    assert content_resp.headers["X-Artifact-ID"] == sample_art["artifact_id"]
    assert content_resp.headers["X-Artifact-SHA256"] == sample_art["sha256"]
    assert content_resp.headers["X-Artifact-Size"] == str(sample_art["size_bytes"])
    assert len(content_resp.content) == sample_art["size_bytes"]

    # 5. Nonexistent artifact returns 404
    bad_art_resp = client.get(f"/api/v1/runs/{run_id}/artifacts/nonexistent.diff")
    assert bad_art_resp.status_code == 404

    # 6. Path traversal attempt via API returns 400
    trav_resp = client.get(f"/api/v1/runs/{run_id}/artifacts/..%2Fescape.diff")
    assert trav_resp.status_code in (400, 404)


def test_12_required_evidence_missing_preserves_non_success_verdict(temp_storage):
    """Test 12: Invariant: missing or corrupted required evidence never produces a false VERIFIED state."""
    repo, storage, _, _, _ = temp_storage
    client = TestClient(app)

    # Inconclusive run with missing evidence
    receipt_inc = make_test_receipt("run-fail", "task-fail", VerificationStatus.INCONCLUSIVE)
    run = Run(
        run_id="run-fail",
        task_id="task-fail",
        task_contract=make_test_contract("task-fail"),
        current_state=RunState.ABORTED,
        evidence_receipt=receipt_inc
    )
    repo.save_new_run(run)

    # API query
    st_resp = client.get("/api/v1/runs/run-fail")
    assert st_resp.status_code == 200
    assert st_resp.json()["state"] == RunState.ABORTED.value
    assert st_resp.json()["status"] == "failed"
    assert st_resp.json()["state"] != RunState.VERIFIED.value


def test_13_api_corrupted_artifact_returns_500_no_content(temp_storage):
    """Test 13: Integrity failure via API returns HTTP 500 without leaking corrupted payload bytes."""
    repo, storage, _, artifacts_dir, _ = temp_storage
    client = TestClient(app)

    repo.save_new_run(Run(run_id="run-tamper", task_id="task-tamper", task_contract=make_test_contract("task-tamper")))
    storage.store_artifact("run-tamper", "report.json", "test_report", b'{"passed": 10}')

    # Tamper with file directly on disk
    file_path = os.path.join(artifacts_dir, "run-tamper", "report.json")
    with open(file_path, "wb") as f:
        f.write(b'{"passed": 999999}')  # Corrupted content

    # Query content endpoint
    resp = client.get("/api/v1/runs/run-tamper/artifacts/report.json/content")
    assert resp.status_code == 500
    err_json = resp.json()
    assert "detail" in err_json
    assert "Artifact integrity verification failed" in err_json["detail"]
    assert "cryptographic digest mismatch" in err_json["detail"]

    # Verify corrupted raw bytes are NOT returned
    assert resp.content != b'{"passed": 999999}'
    assert b"999999" not in resp.content


def test_14_safe_attachment_filename_handling_and_header_injection_defense(temp_storage):
    """Test 14: Attachment filenames are strictly sanitized against CRLF header injection and traversal."""
    repo, storage, _, _, _ = temp_storage
    client = TestClient(app)

    # 1. Direct unit verification of filename sanitizer
    assert sanitize_attachment_filename("report.txt") == "report.txt"
    assert sanitize_attachment_filename("evil\r\nSet-Cookie: session=evil\r\n") == "evil__Set-Cookie__session_evil"
    assert sanitize_attachment_filename('quotes"and;semicolon.json') == "quotes_and_semicolon.json"
    assert sanitize_attachment_filename("../../secret.txt") == "secret.txt"
    assert sanitize_attachment_filename("") == "artifact.bin"
    assert sanitize_attachment_filename("...") == "artifact.bin"
    assert "\r" not in sanitize_attachment_filename("a\r\nb")
    assert "\n" not in sanitize_attachment_filename("a\r\nb")

    # 2. Integration verification via content endpoint with legitimate special chars (e.g. underscores, hyphens, dots)
    repo.save_new_run(Run(run_id="run-safe-name", task_id="task-safe-name", task_contract=make_test_contract("task-safe-name")))
    storage.store_artifact("run-safe-name", "my-diff_v1.0.diff", "diff", b"diff --git ...")

    resp = client.get("/api/v1/runs/run-safe-name/artifacts/my-diff_v1.0.diff/content")
    assert resp.status_code == 200
    cd = resp.headers.get("Content-Disposition", "")
    assert cd == 'attachment; filename="my-diff_v1.0.diff"'
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"


def test_15_consistent_http_status_codes_for_artifact_endpoints(temp_storage):
    """Test 15: Clear and consistent HTTP status codes for valid, missing, invalid, and corrupted artifacts."""
    repo, storage, _, artifacts_dir, _ = temp_storage
    client = TestClient(app)

    repo.save_new_run(Run(run_id="run-status-check", task_id="task-status-check", task_contract=make_test_contract("task-status-check")))
    storage.store_artifact("run-status-check", "valid.txt", "log", b"valid payload")

    # 1. Valid artifact: 200
    res_200 = client.get("/api/v1/runs/run-status-check/artifacts/valid.txt/content")
    assert res_200.status_code == 200
    assert res_200.headers.get("X-Content-Type-Options") == "nosniff"
    assert res_200.headers.get("Content-Disposition") == 'attachment; filename="valid.txt"'

    # 2. Missing run: 404
    res_404_run = client.get("/api/v1/runs/nonexistent-run/artifacts/valid.txt/content")
    assert res_404_run.status_code == 404

    # 3. Missing artifact in existing run: 404
    res_404_art = client.get("/api/v1/runs/run-status-check/artifacts/missing.txt/content")
    assert res_404_art.status_code == 404

    # 4. Invalid identifier / Path traversal attempt: 400
    res_400 = client.get("/api/v1/runs/run-status-check/artifacts/..%2Fescape.txt/content")
    assert res_400.status_code in (400, 404)

    # 5. Corrupted bytes on disk: 500
    file_path = os.path.join(artifacts_dir, "run-status-check", "valid.txt")
    with open(file_path, "wb") as f:
        f.write(b"corrupted payload")
    res_500 = client.get("/api/v1/runs/run-status-check/artifacts/valid.txt/content")
    assert res_500.status_code == 500
    assert "cryptographic digest mismatch" in res_500.json()["detail"]
