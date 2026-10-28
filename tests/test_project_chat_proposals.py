import os
import shutil
import tempfile
import pytest
from fastapi.testclient import TestClient

from backend.api.app import app
from backend.models.projects import ProjectFile
from backend.storage.database import Database, set_database
from backend.storage.project_repository import SQLiteProjectRepository, get_project_repository
from backend.models.registry import set_model_provider, reset_model_provider
from backend.models.deterministic_provider import DeterministicTestProvider
from backend.sandbox.capabilities import RepositoryTrust


from backend.api.routes.runs import set_run_repository, get_repository as get_runs_repo
from backend.storage.repositories import SQLiteRunRepository

@pytest.fixture
def client_with_db():
    temp_dir = tempfile.mkdtemp(prefix="test_stage3_db_")
    db_path = os.path.join(temp_dir, "test_projects.db")
    test_db = Database(db_path=db_path)
    set_database(test_db)
    orig_run_repo = get_runs_repo()
    set_run_repository(SQLiteRunRepository(test_db))

    # Use Deterministic provider for repeatable testing
    set_model_provider(DeterministicTestProvider())

    client = TestClient(app)
    yield client, temp_dir

    reset_model_provider()
    set_run_repository(orig_run_repo)
    set_database(None)
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir, ignore_errors=True)



def test_project_import_and_file_inspection_flow(client_with_db):
    client, _ = client_with_db

    # 1. Import Python project
    import_payload = {
        "name": "auth-microservice",
        "files": [
            {"path": "src/main.py", "content": "def authenticate(user, pwd):\n    return user == 'admin'\n"},
            {"path": "tests/test_main.py", "content": "def test_auth(): assert True\n"},
            {"path": "config.json", "content": "{\"env\": \"test\"}\n"}
        ]
    }
    resp = client.post("/api/v1/projects/import", json=import_payload)
    assert resp.status_code == 201
    proj_data = resp.json()
    project_id = proj_data["project_id"]
    assert project_id.startswith("project-")
    assert proj_data["trust"] == "UNTRUSTED"
    assert proj_data["file_count"] == 3

    # 2. List project files
    files_resp = client.get(f"/api/v1/projects/{project_id}/files")
    assert files_resp.status_code == 200
    files = files_resp.json()
    paths = [f["path"] for f in files]
    assert "src/main.py" in paths
    assert "tests/test_main.py" in paths
    assert "config.json" in paths

    # 3. Read specific file
    content_resp = client.get(f"/api/v1/projects/{project_id}/file?path=src/main.py")
    assert content_resp.status_code == 200
    file_info = content_resp.json()
    assert "authenticate(user, pwd)" in file_info["content"]
    assert file_info["sha256"] is not None

    # 4. Reject path traversal
    bad_resp = client.get(f"/api/v1/projects/{project_id}/file?path=../etc/passwd")
    assert bad_resp.status_code == 400


def test_project_isolation_prevents_cross_project_access(client_with_db):
    client, _ = client_with_db

    # Create Project A
    resp_a = client.post("/api/v1/projects/import", json={
        "name": "project-alpha",
        "files": [{"path": "secret.txt", "content": "Alpha Secret"}]
    })
    proj_a_id = resp_a.json()["project_id"]

    # Create Project B
    resp_b = client.post("/api/v1/projects/import", json={
        "name": "project-beta",
        "files": [{"path": "secret.txt", "content": "Beta Secret"}]
    })
    proj_b_id = resp_b.json()["project_id"]

    # Read from Project A
    read_a = client.get(f"/api/v1/projects/{proj_a_id}/file?path=secret.txt").json()
    assert read_a["content"] == "Alpha Secret"

    # Read from Project B
    read_b = client.get(f"/api/v1/projects/{proj_b_id}/file?path=secret.txt").json()
    assert read_b["content"] == "Beta Secret"

    # Attempting to escape project A to access project B fails
    cross_read = client.get(f"/api/v1/projects/{proj_a_id}/file?path=../{proj_b_id}/secret.txt")
    assert cross_read.status_code == 400


def test_conversational_chat_and_file_mentions(client_with_db):
    client, _ = client_with_db

    # Import project
    import_resp = client.post("/api/v1/projects/import", json={
        "name": "demo-chat-app",
        "files": [
            {"path": "src/service.py", "content": "def compute():\n    return 42\n"},
            {"path": "tests/test_service.py", "content": "def test_compute(): assert True\n"}
        ]
    })
    project_id = import_resp.json()["project_id"]

    # Create conversation
    conv_resp = client.post(f"/api/v1/projects/{project_id}/conversations", json={"title": "Audit Thread"})
    assert conv_resp.status_code == 201
    conv_id = conv_resp.json()["conversation_id"]

    # Send message with @ file mention
    chat_resp = client.post(f"/api/v1/projects/{project_id}/conversations/{conv_id}/messages", json={
        "message": "@src/service.py Explain what this function does and verify invariant boundaries.",
        "mentioned_files": ["src/service.py"]
    })
    assert chat_resp.status_code == 200
    chat_data = chat_resp.json()
    assert chat_data["conversation_id"] == conv_id
    assert chat_data["role"] == "assistant"
    assert "src/service.py" in chat_data["mentioned_files"]

    # Check that messages were persisted in database
    msgs_resp = client.get(f"/api/v1/projects/{project_id}/conversations/{conv_id}/messages")
    assert msgs_resp.status_code == 200
    msgs = msgs_resp.json()
    assert len(msgs) == 2  # 1 user + 1 assistant
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"


def test_proposal_generation_diff_review_approve_and_reject(client_with_db):
    client, _ = client_with_db

    # Import project with a vulnerable function
    import_resp = client.post("/api/v1/projects/import", json={
        "name": "repair-target",
        "files": [
            {"path": "src/parser.py", "content": "def parse(input_val):\n    return input_val.split(',')\n"}
        ]
    })
    proj_data = import_resp.json()
    project_id = proj_data["project_id"]
    initial_snapshot_hash = proj_data["snapshot_hash"]

    # Create conversation
    conv_resp = client.post(f"/api/v1/projects/{project_id}/conversations", json={"title": "Repair"})
    conv_id = conv_resp.json()["conversation_id"]

    # Request code repair
    chat_resp = client.post(f"/api/v1/projects/{project_id}/conversations/{conv_id}/messages", json={
        "message": "Repair the input validation bug in @src/parser.py by checking for empty input.",
        "mentioned_files": ["src/parser.py"]
    })
    assert chat_resp.status_code == 200
    chat_data = chat_resp.json()
    proposal = chat_data["proposal"]
    assert proposal is not None
    proposal_id = proposal["proposal_id"]
    assert proposal["status"] == "PENDING"
    assert "src/parser.py" in proposal["changed_files"]
    assert "--- a/src/parser.py" in proposal["diff"]
    assert "+++ b/src/parser.py" in proposal["diff"]

    # 1. Test Reject flow first
    reject_resp = client.post(f"/api/v1/projects/{project_id}/proposals/{proposal_id}/reject")
    assert reject_resp.status_code == 200
    assert reject_resp.json()["status"] == "REJECTED"

    # Confirm file content was NOT changed
    file_after_reject = client.get(f"/api/v1/projects/{project_id}/file?path=src/parser.py").json()
    assert file_after_reject["content"] == "def parse(input_val):\n    return input_val.split(',')\n"

    # 2. Generate a second proposal and approve it
    chat_resp2 = client.post(f"/api/v1/projects/{project_id}/conversations/{conv_id}/messages", json={
        "message": "Fix the bug in @src/parser.py now please.",
        "mentioned_files": ["src/parser.py"]
    })
    prop2 = chat_resp2.json()["proposal"]
    assert prop2 is not None
    prop2_id = prop2["proposal_id"]

    apply_resp = client.post(f"/api/v1/projects/{project_id}/proposals/{prop2_id}/apply")
    assert apply_resp.status_code == 200
    applied_data = apply_resp.json()
    assert applied_data["status"] == "APPLIED"

    # Confirm file content WAS updated on disk
    file_after_apply = client.get(f"/api/v1/projects/{project_id}/file?path=src/parser.py").json()
    assert "validate_input" in file_after_apply["content"] or "def parse" in file_after_apply["content"]

    # Confirm snapshot digest was updated
    proj_updated = client.get(f"/api/v1/projects/{project_id}").json()
    assert proj_updated["snapshot_hash"] != initial_snapshot_hash


def test_launch_project_verification_triggers_genuine_run(client_with_db):
    client, _ = client_with_db

    # Import project
    import_resp = client.post("/api/v1/projects/import", json={
        "name": "verify-target",
        "files": [
            {"path": "src/calc.py", "content": "def calculate(): return 100\n"},
            {"path": "test_main.py", "content": "def test_calc(): assert True\n"}
        ]
    })
    project_id = import_resp.json()["project_id"]

    # Launch verification run
    verify_resp = client.post(f"/api/v1/projects/{project_id}/verify", json={
        "task_description": "Validate calculate invariants",
        "test_command": ["python", "test_main.py"]
    })
    assert verify_resp.status_code == 201
    verify_data = verify_resp.json()
    assert verify_data["run_id"].startswith("run-")
    assert verify_data["trust"] == "UNTRUSTED"
    assert verify_data["status"] == "QUEUED"

    # Check that run exists in standard runs endpoint
    run_status_resp = client.get(f"/api/v1/runs/{verify_data['run_id']}")
    assert run_status_resp.status_code == 200
    run_status = run_status_resp.json()
    assert run_status["run_id"] == verify_data["run_id"]
