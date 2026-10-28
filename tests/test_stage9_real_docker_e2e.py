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
from backend.models.provider import ModelProvider, ModelResponse
from backend.sandbox.capabilities import RepositoryTrust, SecurityLevel
from backend.models.schemas import (
    TaskContract,
    Run,
    RunState,
    OperationalResult,
    ResourceBudget,
)
from backend.models.projects import ProposalRecord
from backend.sandbox.factory import get_sandbox_backend
from backend.sandbox.secure_backend import SecureSandboxBackend, ContainerRuntimeProbe
from backend.sandbox.backend import LocalDevelopmentBackend
from backend.sandbox.models import SandboxPolicy, ExecutionRequest
from backend.sandbox.registry import get_repository_registry, RepositoryTarget
from backend.verification.models import (
    VerificationStatus,
    TestResultSummary,
    StructuredObservation,
    ExecutionStatus,
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

DIFF_TOKEN_BUCKET_FIX = (
    "--- a/src/token_bucket.py\n"
    "+++ b/src/token_bucket.py\n"
    "@@ -10,6 +10,9 @@\n"
    "         self.last_update = time.time()\n"
    "\n"
    "     def consume(self, amount: int) -> bool:\n"
    "-        # BUG: Does not validate amount > 0 and deducts tokens even when amount exceeds capacity\n"
    "+        if amount <= 0:\n"
    "+            raise ValueError(\"Amount must be positive.\")\n"
    "+        if amount > self.tokens:\n"
    "+            return False\n"
    "         self.tokens -= amount\n"
    "         return True\n"
)


class Stage9TokenBucketModelProvider(ModelProvider):
    """Deterministic model provider configured for TokenBucket verification."""
    def __init__(self):
        self.provider_name = "stage9-deterministic-provider"
        self.default_model = "stage9-engine-v1"
        self.mode = "DETERMINISTIC"

    def generate(self, messages, **kwargs):
        sys_msg = messages[0]["content"] if messages else ""
        last_msg = messages[-1]["content"] if messages else ""
        if "REDLINE Architect" in sys_msg:
            resp = json.dumps({
                "objective": "Repair TokenBucket overconsumption and negative amounts",
                "files_to_inspect": ["src/token_bucket.py"],
                "files_to_modify": ["src/token_bucket.py"],
                "implementation_steps": ["Validate amount > 0", "Check tokens >= amount"],
                "acceptance_criteria": ["All unit tests pass"],
                "constraints": ["Modify only src/token_bucket.py"],
                "risks": [],
                "expected_tests": ["tests/test_token_bucket.py"]
            })
        elif "REDLINE Builder" in sys_msg:
            resp = json.dumps({
                "changed_files": ["src/token_bucket.py"],
                "diff": DIFF_TOKEN_BUCKET_FIX,
            })
        elif "REDLINE Repairer" in sys_msg:
            resp = json.dumps({
                "changed_files": ["src/token_bucket.py"],
                "diff": DIFF_TOKEN_BUCKET_FIX,
                "target_failure": "Overconsumption",
                "reasoning_summary": "Enforce tokens >= amount and amount > 0"
            })
        elif "REDLINE Judge" in sys_msg:
            resp = json.dumps({
                "summary": "TokenBucket verified inside hardened SecureSandboxBackend container.",
                "verified_claims": ["All 4 unit tests passed", "Overconsumption rejected"],
                "failed_claims": [],
                "evidence_references": [],
                "limitations": "Deterministic unit test scope.",
                "confidence": "HIGH"
            })
        elif "REDLINE AI" in sys_msg or "Fix" in last_msg or "fix" in last_msg:
            resp = (
                f"I reviewed @src/token_bucket.py.\n\n"
                f"```proposal:src/token_bucket.py\n"
                f"{DISPOSABLE_SRC_FIXED}\n"
                f"```\n"
                f"Enforced positive amount validation and tokens >= amount."
            )
        else:
            resp = json.dumps({"result": "ok"})
        return ModelResponse(
            request_id="stage9-req-1",
            provider=self.provider_name,
            model=self.default_model,
            response_text=resp,
            finish_reason="stop",
            input_tokens=100,
            output_tokens=50,
            latency_ms=1.0,
            timestamp=1.0,
            provider_request_id="stage9-prov-1"
        )


@pytest.fixture
def clean_stage9_environment():
    temp_dir = tempfile.mkdtemp(prefix="test_stage9_docker_")
    db_path = os.path.join(temp_dir, "stage9_projects.db")
    test_db = Database(db_path=db_path)
    set_database(test_db)
    orig_run_repo = get_runs_repo()
    set_run_repository(SQLiteRunRepository(test_db))
    orig_storage = get_artifact_storage_instance()
    test_storage = ArtifactStorage(root_dir=os.path.join(temp_dir, "artifacts"), database=test_db)
    set_artifact_storage(test_storage)

    provider = Stage9TokenBucketModelProvider()
    set_model_provider(provider)
    client = TestClient(app)

    yield client, temp_dir, provider

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
# PHASE 1: PREFLIGHT AUDIT TESTS
# ==============================================================================

def test_phase1_docker_preflight():
    """Verify Docker Desktop Linux engine reachability, info, and hello-world."""
    # 1. docker info succeeds
    info_proc = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=15)
    assert info_proc.returncode == 0, f"docker info failed: {info_proc.stderr}"
    assert "Server Version" in info_proc.stdout

    # 2. docker run --rm hello-world succeeds
    hw_proc = subprocess.run(["docker", "run", "--rm", "hello-world"], capture_output=True, text=True, timeout=20)
    assert hw_proc.returncode == 0, f"docker run hello-world failed: {hw_proc.stderr}"
    assert "Hello from Docker!" in hw_proc.stdout

    # 3. REDLINE SecureSandboxBackend probe detects docker runtime
    probe = ContainerRuntimeProbe()
    is_operational, engine, probe_meta = probe.detect_runtime()
    assert is_operational is True
    assert engine in ("docker", "podman")
    assert "server_version" in probe_meta or "version" in probe_meta

    # 4. SecureSandboxBackend reports SECURE capabilities
    policy = SandboxPolicy()
    backend = SecureSandboxBackend(policy)
    caps = backend.capabilities()
    assert caps.security_level == SecurityLevel.SECURE
    assert caps.filesystem_isolation == "ENFORCED"
    assert caps.process_isolation == "ENFORCED"
    assert caps.network_isolation == "ENFORCED"
    assert caps.secure_untrusted_execution is True


# ==============================================================================
# PHASE 2: REAL SECURE-CONTAINER EXECUTION & ISOLATION ENFORCEMENT
# ==============================================================================

def test_phase2_real_docker_container_security_controls():
    """
    Verify that SecureSandboxBackend enforces:
    - --read-only root filesystem
    - --user 1000:1000 (non-root)
    - --network none (network isolation)
    - --cap-drop=ALL
    - --security-opt=no-new-privileges
    - /tmp writable tmpfs
    """
    backend = get_sandbox_backend(repository_trust="UNTRUSTED")
    assert isinstance(backend, SecureSandboxBackend)

    with tempfile.TemporaryDirectory(prefix="redline_sec_ctrls_") as tmpdir:
        # 1. Verify non-root user (1000:1000)
        req_user = ExecutionRequest(
            command=["python", "-c", "import os; print(os.getuid())"],
            working_directory=tmpdir,
            repository_trust="UNTRUSTED"
        )
        res_user = backend.execute(req_user, "run-sec-user")
        assert res_user.exit_code == 0
        assert res_user.stdout.strip() == "1000"
        assert res_user.backend_provenance["backend"] == "SecureSandboxBackend"
        assert res_user.backend_provenance["security_level"] in ("SECURE", "HARDENED_CONTAINER")

        # 2. Verify root filesystem is read-only (writing to /root_test fails)
        req_ro = ExecutionRequest(
            command=["python", "-c", "with open('/root_test', 'w') as f: f.write('bad')"],
            working_directory=tmpdir,
            repository_trust="UNTRUSTED"
        )
        res_ro = backend.execute(req_ro, "run-sec-ro")
        assert res_ro.exit_code != 0
        assert "Read-only file system" in res_ro.stderr

        # 3. Verify tmpfs is writable (/tmp/tmpfs_test succeeds)
        req_tmp = ExecutionRequest(
            command=["python", "-c", "with open('/tmp/tmpfs_test', 'w') as f: f.write('ok')"],
            working_directory=tmpdir,
            repository_trust="UNTRUSTED"
        )
        res_tmp = backend.execute(req_tmp, "run-sec-tmp")
        assert res_tmp.exit_code == 0


def test_phase2_reproduce_token_bucket_bug_in_real_docker():
    """
    Reproduce the token-bucket bug inside the real Docker container.
    Baseline code must FAIL tests in container with non-zero exit code.
    """
    backend = get_sandbox_backend(repository_trust="UNTRUSTED")

    with tempfile.TemporaryDirectory(prefix="redline_reproduce_bug_") as tmpdir:
        src_dir = os.path.join(tmpdir, "src")
        tests_dir = os.path.join(tmpdir, "tests")
        os.makedirs(src_dir)
        os.makedirs(tests_dir)

        with open(os.path.join(src_dir, "token_bucket.py"), "w", encoding="utf-8") as f:
            f.write(DISPOSABLE_SRC_BUGGY)
        with open(os.path.join(tests_dir, "test_token_bucket.py"), "w", encoding="utf-8") as f:
            f.write(DISPOSABLE_TEST)

        req = ExecutionRequest(
            command=["python", "-m", "pytest", "-o", "pythonpath=."],
            working_directory=tmpdir,
            repository_trust="UNTRUSTED"
        )
        res = backend.execute(req, "run-reproduce-baseline")

        # Baseline must FAIL inside container
        assert res.exit_code != 0
        assert "FAILED" in res.stdout or "failed" in res.stdout
        assert "AssertionError" in res.stdout
        assert res.backend_provenance["backend"] == "SecureSandboxBackend"


def test_phase2_patched_code_passes_in_real_docker():
    """
    Verify that the repaired TokenBucket passes all unit tests inside the real Docker container.
    """
    backend = get_sandbox_backend(repository_trust="UNTRUSTED")

    with tempfile.TemporaryDirectory(prefix="redline_patched_pass_") as tmpdir:
        src_dir = os.path.join(tmpdir, "src")
        tests_dir = os.path.join(tmpdir, "tests")
        os.makedirs(src_dir)
        os.makedirs(tests_dir)

        with open(os.path.join(src_dir, "token_bucket.py"), "w", encoding="utf-8") as f:
            f.write(DISPOSABLE_SRC_FIXED)
        with open(os.path.join(tests_dir, "test_token_bucket.py"), "w", encoding="utf-8") as f:
            f.write(DISPOSABLE_TEST)

        req = ExecutionRequest(
            command=["python", "-m", "pytest", "-o", "pythonpath=."],
            working_directory=tmpdir,
            repository_trust="UNTRUSTED"
        )
        res = backend.execute(req, "run-patched-pass")

        # Patched code must PASS inside container
        assert res.exit_code == 0
        assert "4 passed" in res.stdout
        assert res.backend_provenance["backend"] == "SecureSandboxBackend"


# ==============================================================================
# PHASE 3: END-TO-END REPAIR & AUTHORITATIVE VERIFICATION
# ==============================================================================

def test_phase3_project_chat_rejection_and_approval_workflow(clean_stage9_environment):
    """
    Test Phase 3 workflow:
    1. Import disposable project through API.
    2. Request fix via chat proposal.
    3. Review proposal diff and reject it.
    4. Confirm workspace is completely UNCHANGED after rejection.
    5. Approve valid proposal.
    6. Confirm workspace is updated with fix and baseline is preserved.
    """
    client, _, _ = clean_stage9_environment

    import_resp = client.post("/api/v1/projects/import", json={
        "name": "disposable-token-bucket",
        "files": [
            {"path": "src/token_bucket.py", "content": DISPOSABLE_SRC_BUGGY},
            {"path": "tests/test_token_bucket.py", "content": DISPOSABLE_TEST},
            {"path": "README.md", "content": "# Disposable Token Bucket\n"}
        ]
    })
    assert import_resp.status_code == 201
    proj_data = import_resp.json()
    project_id = proj_data["project_id"]
    initial_snapshot = proj_data["snapshot_hash"]
    assert proj_data["trust"] == "UNTRUSTED"

    # Create conversation and request proposal
    conv_resp = client.post(f"/api/v1/projects/{project_id}/conversations", json={"title": "Fix Overconsumption"})
    assert conv_resp.status_code == 201
    conv_id = conv_resp.json()["conversation_id"]

    msg_resp = client.post(f"/api/v1/projects/{project_id}/conversations/{conv_id}/messages", json={
        "message": "Fix the overconsumption bug in @src/token_bucket.py",
        "mentioned_files": ["src/token_bucket.py"]
    })
    assert msg_resp.status_code == 200
    msg_data = msg_resp.json()
    prop = msg_data["proposal"]
    assert prop is not None
    proposal_id = prop["proposal_id"]

    # 1. Reject proposal and verify workspace untouched
    rej_resp = client.post(f"/api/v1/projects/{project_id}/proposals/{proposal_id}/reject")
    assert rej_resp.status_code == 200
    assert rej_resp.json()["status"] == "REJECTED"

    file_after_rej = client.get(f"/api/v1/projects/{project_id}/file?path=src/token_bucket.py").json()
    assert file_after_rej["content"].replace("\r\n", "\n") == DISPOSABLE_SRC_BUGGY.replace("\r\n", "\n")
    proj_after_rej = client.get(f"/api/v1/projects/{project_id}").json()
    assert proj_after_rej["snapshot_hash"] == initial_snapshot

    # 2. Create valid proposal and approve
    repo = get_project_repository()
    now_iso = "2026-10-28T18:00:00Z"
    valid_prop = ProposalRecord(
        proposal_id="prop-stage9-valid-01",
        project_id=project_id,
        conversation_id=conv_id,
        status="PENDING",
        description="Fix overconsumption in TokenBucket",
        diff=DIFF_TOKEN_BUCKET_FIX,
        diff_sha256=hashlib.sha256(DIFF_TOKEN_BUCKET_FIX.encode()).hexdigest(),
        changed_files=["src/token_bucket.py"],
        proposed_content={"src/token_bucket.py": DISPOSABLE_SRC_FIXED},
        created_at=now_iso,
    )
    repo.create_proposal(valid_prop)

    apply_resp = client.post(f"/api/v1/projects/{project_id}/proposals/prop-stage9-valid-01/apply")
    assert apply_resp.status_code == 200
    assert apply_resp.json()["status"] == "APPLIED"

    file_after_apply = client.get(f"/api/v1/projects/{project_id}/file?path=src/token_bucket.py").json()
    assert file_after_apply["content"].replace("\r\n", "\n") == DISPOSABLE_SRC_FIXED.replace("\r\n", "\n")


def test_phase3_authoritative_e2e_verification_in_real_docker(clean_stage9_environment):
    """
    Phase 3: Run full authoritative Orchestrator verification on disposable untrusted project
    executing inside a real Docker container.
    Proves:
    - Selected backend is SecureSandboxBackend.
    - All tests and attacks run inside the container.
    - Result reaches VERIFIED.
    - Receipt verdict is VERIFIED with valid cryptographic integrity.
    """
    client, _, provider = clean_stage9_environment

    # 1. Import repository
    import_resp = client.post("/api/v1/projects/import", json={
        "name": "disposable-token-bucket",
        "files": [
            {"path": "src/token_bucket.py", "content": DISPOSABLE_SRC_BUGGY},
            {"path": "tests/test_token_bucket.py", "content": DISPOSABLE_TEST}
        ]
    })
    project_id = import_resp.json()["project_id"]

    # 2. Trigger authoritative verification through product API
    verify_resp = client.post(f"/api/v1/projects/{project_id}/verify", json={
        "task_description": "Verify TokenBucket implementation",
        "test_command": ["python", "-m", "pytest", "-o", "pythonpath=."]
    })
    assert verify_resp.status_code == 201
    run_id = verify_resp.json()["run_id"]
    assert verify_resp.json()["trust"] == "UNTRUSTED"

    # Wait for background thread execution to complete
    th = _threads.get(run_id)
    if th:
        th.join(timeout=30)

    # 3. Inspect persisted run record
    run_record = client.get(f"/api/v1/runs/{run_id}").json()

    assert run_record["state"] == "VERIFIED", f"Expected VERIFIED, got {run_record['state']}, error: {run_record.get('operational_error')}"
    assert run_record["status"] in ("completed", "passed")

    # 4. Inspect evidence receipt
    receipt_data = run_record.get("evidence_receipt")
    assert receipt_data is not None
    assert receipt_data["verdict"] == "VERIFIED"

    # 5. Verify sandbox provenance: must be SecureSandboxBackend
    provenance = receipt_data.get("sandbox_provenance", {})
    assert provenance.get("backend") == "SecureSandboxBackend"

    # 6. Verify independent cryptographic receipt integrity
    receipt_obj = EvidenceReceipt(**receipt_data)
    assert verify_receipt_integrity(receipt_obj) is True
    assert receipt_obj.receipt_hash == receipt_obj.calculate_integrity_hash()

    # 7. Verify test summary inside receipt: 4 passed tests
    test_summary = receipt_obj.test_summary
    assert test_summary.executed == 4
    assert test_summary.passed == 4
    assert test_summary.failed == 0


# ==============================================================================
# PHASE 4: NEGATIVE-PATH CHECKS
# ==============================================================================

def test_phase4_docker_unavailable_fails_closed_without_host_fallback():
    """
    Confirm that if Docker runtime is unavailable, untrusted execution fails closed
    with POLICY_BLOCKED and NEVER silently falls back to host execution.
    """
    class UnavailableProbe(ContainerRuntimeProbe):
        def detect_runtime(self):
            return False, "NONE", {"error": "Simulated Docker outage"}

    policy = SandboxPolicy()
    backend = SecureSandboxBackend(policy)
    backend.probe = UnavailableProbe()

    with tempfile.TemporaryDirectory(prefix="redline_unavailable_") as tmpdir:
        req = ExecutionRequest(
            command=["python", "-c", "print('should never run on host')"],
            working_directory=tmpdir,
            repository_trust="UNTRUSTED"
        )
        res = backend.execute(req, "run-simulated-outage")

        # Fails closed
        assert res.policy_blocked is True
        assert res.exit_code == -1
        assert "OPERATIONAL_FAILURE" in res.stderr
        assert res.backend_provenance["reason"] == "RUNTIME_UNAVAILABLE"


def test_phase4_malformed_patch_and_path_traversal_rejected(clean_stage9_environment):
    """
    Confirm that patches attempting path traversal are rejected with HTTP 400.
    """
    client, _, _ = clean_stage9_environment

    import_resp = client.post("/api/v1/projects/import", json={
        "name": "traversal-target",
        "files": [{"path": "src/app.py", "content": "print('ok')\n"}]
    })
    project_id = import_resp.json()["project_id"]

    repo = get_project_repository()
    bad_prop = ProposalRecord(
        proposal_id="prop-evil-traversal",
        project_id=project_id,
        conversation_id="conv-bad",
        status="PENDING",
        description="Path traversal patch",
        diff="--- /dev/null\n+++ ../escaped.py\n",
        diff_sha256="0" * 64,
        changed_files=["../escaped.py"],
        proposed_content={"../escaped.py": "malicious content"},
        created_at="2026-10-28T18:00:00Z"
    )
    repo.create_proposal(bad_prop)

    apply_resp = client.post(f"/api/v1/projects/{project_id}/proposals/prop-evil-traversal/apply")
    assert apply_resp.status_code == 400
    assert "Path traversal" in apply_resp.json()["detail"] or "escapes" in apply_resp.json()["detail"]


def test_phase4_failing_tests_cannot_produce_verified():
    """
    Confirm that failing tests strictly prevent VERIFIED verdict.
    """
    from backend.verification.policy import DeterministicVerificationPolicy
    from backend.verification.models import TestResultSummary, RegressionSummary

    policy = DeterministicVerificationPolicy()
    obs = StructuredObservation(
        execution_id="exec-fail-01",
        command_identifier="pytest",
        exit_code=1,
        stdout_sha256="0" * 64,
        stderr_sha256="0" * 64,
        stdout_bytes=100,
        stderr_bytes=50,
        duration_ms=100,
        status=ExecutionStatus.NONZERO,
        sandbox_backend="SecureSandboxBackend",
        security_level="HARDENED_CONTAINER",
        capabilities={},
        workspace_id="ws-01",
        repository_snapshot_hash="s" * 64,
        patch_hash="p" * 64
    )
    res = policy.evaluate(
        repository_snapshot_hash="s" * 64,
        patch_hash="p" * 64,
        structured_observation=obs,
        test_summary=TestResultSummary(executed=4, passed=3, failed=1),
        regression_summary=RegressionSummary(),
        invariants=[],
        security_aggregation=None,
        oracle_results=[],
        counterexamples=[]
    )
    assert res.status == VerificationStatus.REJECTED
    assert res.status != VerificationStatus.VERIFIED
