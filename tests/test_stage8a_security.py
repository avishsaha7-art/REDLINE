import os
import sys
import time
import pytest
import tempfile
import shutil
import socket
from backend.sandbox.models import SandboxPolicy, ExecutionRequest
from backend.sandbox.backend import LocalDevelopmentBackend

@pytest.fixture
def repo_root():
    root = tempfile.mkdtemp()
    yield root
    shutil.rmtree(root, ignore_errors=True)

def test_host_escape_absolute_path_read(repo_root):
    policy = SandboxPolicy(allowed_commands=["python"])
    backend = LocalDevelopmentBackend(policy)
    
    # Try reading hosts file (Windows)
    target = "C:\\\\Windows\\\\System32\\\\drivers\\\\etc\\\\hosts" if sys.platform == 'win32' else "/etc/hosts"
    
    with open(os.path.join(repo_root, "attack.py"), "w") as f:
        f.write(f"try:\n  with open('{target}', 'r') as f: print(f.read()[:10])\nexcept: print('BLOCKED')\n")
        
    res = backend.execute(ExecutionRequest(command=["python", "attack.py"], working_directory=repo_root, repository_trust="TRUSTED_DEVELOPMENT"), "run-x")
    
    # In LocalDevelopmentBackend this actually succeeds because it's not a real sandbox
    # The requirement states we MUST explicitly report it fails to block this.
    assert backend.capabilities().filesystem_isolation == "NOT_AVAILABLE"

def test_network_escape_dns(repo_root):
    policy = SandboxPolicy(allowed_commands=["python"])
    backend = LocalDevelopmentBackend(policy)
    
    with open(os.path.join(repo_root, "attack.py"), "w") as f:
        f.write("import socket\ntry:\n  socket.gethostbyname('example.com')\n  print('SUCCESS')\nexcept:\n  print('BLOCKED')\n")
        
    res = backend.execute(ExecutionRequest(command=["python", "attack.py"], working_directory=repo_root, repository_trust="TRUSTED_DEVELOPMENT"), "run-x")
    
    # In LocalDevelopmentBackend this succeeds
    assert backend.capabilities().network_isolation == "NOT_AVAILABLE"

def test_process_escape_background(repo_root):
    policy = SandboxPolicy(allowed_commands=["python"])
    backend = LocalDevelopmentBackend(policy)
    
    # Attempt to spawn a background ping or sleep that outlives parent
    with open(os.path.join(repo_root, "attack.py"), "w") as f:
        f.write("import subprocess, sys\n")
        if sys.platform == 'win32':
            f.write("subprocess.Popen(['ping', '-n', '10', '127.0.0.1'], creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)\n")
        else:
            f.write("subprocess.Popen(['sleep', '10'])\n")
        f.write("print('SPAWNED')\n")
        
    res = backend.execute(ExecutionRequest(command=["python", "attack.py"], working_directory=repo_root, timeout_seconds=2, repository_trust="TRUSTED_DEVELOPMENT"), "run-x")
    
    # Our _kill_process_tree using taskkill /T should kill the tree, but process isolation is technically NOT_AVAILABLE
    # because they CAN spawn it, we just clean it up.
    assert backend.capabilities().process_isolation == "NOT_AVAILABLE"
    assert backend.capabilities().cleanup_guarantee == "ENFORCED"

def test_credential_escape(repo_root):
    policy = SandboxPolicy(allowed_commands=["python"])
    backend = LocalDevelopmentBackend(policy)
    
    os.environ["FAKE_SECRET_KEY"] = "supersecret123"
    
    with open(os.path.join(repo_root, "attack.py"), "w") as f:
        f.write("import os\nprint(os.environ.get('FAKE_SECRET_KEY', 'NOT_FOUND'))\n")
        
    res = backend.execute(ExecutionRequest(command=["python", "attack.py"], working_directory=repo_root, repository_trust="TRUSTED_DEVELOPMENT"), "run-x")
    
    assert "NOT_FOUND" in res.stdout
    assert "supersecret123" not in res.stdout
    assert backend.capabilities().credential_isolation == "ENFORCED"
    
    del os.environ["FAKE_SECRET_KEY"]

def test_workspace_isolation(repo_root, monkeypatch):
    monkeypatch.setenv("REDLINE_ENABLE_LOCAL_BACKEND", "1")
    # This tests the client's ability to isolate original repo from mutations
    from backend.sandbox.client import SandboxClient
    from backend.models.schemas import PatchCandidate
    
    policy = SandboxPolicy(allowed_commands=["python"])
    from backend.sandbox.capabilities import RepositoryTrust
    client = SandboxClient(policy, repo_root, repository_trust=RepositoryTrust.TRUSTED_DEVELOPMENT)
    
    with open(os.path.join(repo_root, "main.py"), "w") as f:
        f.write("def x(): pass\n")
        
    # The patch tries to just be normal, but the script it runs modifies main.py
    patch = PatchCandidate(
        patch_id="p1", task_id="t1", base_commit_or_snapshot="snap",
        diff="", changed_files=[]
    )
    
    with open(os.path.join(repo_root, "attack.py"), "w") as f:
        f.write("with open('main.py', 'w') as f: f.write('HACKED')\n")
        
    res = client.run_isolated(patch, ["python", "attack.py"], "run-x")
    
    # Original should be unmutated
    with open(os.path.join(repo_root, "main.py"), "r") as f:
        assert "HACKED" not in f.read()
    
    assert client.backend.capabilities().workspace_isolation == "ENFORCED"

def test_fail_closed_untrusted_repository(repo_root):
    from backend.sandbox.client import SandboxClient
    from backend.sandbox.capabilities import RepositoryTrust
    from backend.models.schemas import PatchCandidate
    
    policy = SandboxPolicy(allowed_commands=["python"])
    
    # Default is UNTRUSTED
    client = SandboxClient(policy, repo_root)
    
    patch = PatchCandidate(
        patch_id="p1", task_id="t1", base_commit_or_snapshot="snap",
        diff="", changed_files=[]
    )
    
    res = client.run_isolated(patch, ["python", "-c", "print('hello')"], "run-untrusted")
    
    # 1. Untrusted request must never receive or execute through LocalDevelopmentBackend
    from backend.sandbox.secure_backend import SecureSandboxBackend
    assert isinstance(client.backend, SecureSandboxBackend)
    assert not isinstance(client.backend, LocalDevelopmentBackend)

    # 2. Execution must fail closed and never run on the host
    assert res.policy_blocked is True
    assert getattr(res, "policy_blocked", False) is True
    assert res.exit_code != 0
    assert "hello" not in res.stdout

    # 3. Provenance must truthfully reflect the selected backend and its capability
    assert res.backend_provenance.get("backend") == "SecureSandboxBackend"
    if not client.backend.capabilities().secure_untrusted_execution:
        assert res.backend_provenance.get("security_level") == "UNAVAILABLE"
        assert res.backend_provenance.get("status") == "OPERATIONAL_FAILURE"
        assert "OPERATIONAL_FAILURE" in res.stderr or "POLICY_BLOCKED" in res.stderr
    else:
        assert res.backend_provenance.get("security_level") == "SECURE"

    # 4. Confirm host-execution isolation: workspace is unmodified
    main_file = os.path.join(repo_root, "main.py")
    if os.path.exists(main_file):
        with open(main_file, "r") as f:
            assert "hello" not in f.read()

def test_no_silent_fallback():
    policy = SandboxPolicy()
    backend = LocalDevelopmentBackend(policy)
    caps = backend.capabilities()
    
    # Development backend explicitly reports what is unavailable
    assert caps.security_level == "DEVELOPMENT_ONLY"
    assert caps.secure_untrusted_execution is False
    assert caps.filesystem_isolation == "NOT_AVAILABLE"
    assert caps.network_isolation == "NOT_AVAILABLE"
    assert caps.process_isolation == "NOT_AVAILABLE"

def test_direct_backend_protection_untrusted():
    from backend.sandbox.models import ExecutionRequest
    policy = SandboxPolicy()
    backend = LocalDevelopmentBackend(policy)
    
    req = ExecutionRequest(
        command=["python", "-c", "print('hello')"],
        working_directory=".",
        repository_trust="UNTRUSTED"
    )
    
    res = backend.execute(req, "run-direct")
    
    assert res.policy_blocked is True
    assert res.exit_code == -1
    assert "UNSAFE FOR UNTRUSTED PRODUCTION WORKLOADS" in res.stderr
    assert "hello" not in res.stdout
    assert res.backend_provenance["security_level"] == "DEVELOPMENT_ONLY"

def test_orchestrator_gate_prevents_execute_call(repo_root):
    from backend.sandbox.client import SandboxClient
    from backend.models.schemas import PatchCandidate
    from unittest.mock import MagicMock
    
    policy = SandboxPolicy()
    client = SandboxClient(policy, repo_root)
    
    # Mock the backend's execute method to prove it's never called
    client.backend.execute = MagicMock()
    
    patch = PatchCandidate(
        patch_id="p1", task_id="t1", base_commit_or_snapshot="snap",
        diff="", changed_files=[]
    )
    
    res = client.run_isolated(patch, ["python", "-c", "print('hello')"], "run-untrusted")
    
    # Prove the Orchestrator gate blocked it
    assert res.policy_blocked is True
    # Prove the backend was never called
    client.backend.execute.assert_not_called()

def test_patch_apply_failure_provenance_and_no_execution(repo_root, monkeypatch):
    """
    Regression test for Finding L-01:
    Verifies that when patch application fails:
    1. The target command is NOT executed (backend.execute is never called).
    2. The result is a failure (exit_code != 0, crashed=True), never a success.
    3. Provenance truthfully includes backend name, status, trust, and security_level.
    4. No host-execution fallback occurs.
    """
    from backend.sandbox.client import SandboxClient
    from backend.sandbox.capabilities import RepositoryTrust
    from backend.models.schemas import PatchCandidate
    from unittest.mock import MagicMock

    monkeypatch.setenv("REDLINE_ENABLE_LOCAL_BACKEND", "1")
    policy = SandboxPolicy(allowed_commands=["python"])
    client = SandboxClient(policy, repo_root, repository_trust=RepositoryTrust.TRUSTED_DEVELOPMENT)

    # Mock execute to prove the command is never run if patch apply fails
    client.backend.execute = MagicMock()

    # Create a corrupted patch that is guaranteed to fail git apply
    invalid_patch = PatchCandidate(
        patch_id="p-invalid",
        task_id="t-patch-fail",
        base_commit_or_snapshot="snap",
        diff="MALFORMED PATCH CORRUPT CONTENT THAT CANNOT APPLY\n@@ -1,1 +1,1 @@\n",
        changed_files=["nonexistent.py"]
    )

    res = client.run_isolated(invalid_patch, ["python", "-c", "print('MUST_NOT_EXECUTE')"], "run-patch-fail")

    # 1. Command must not be executed
    client.backend.execute.assert_not_called()

    # 2. Result must indicate failure, never success
    assert res.exit_code == -1
    assert res.crashed is True
    assert res.stdout == ""
    assert "Patch failed to apply" in res.stderr
    assert "MUST_NOT_EXECUTE" not in res.stdout

    # 3. Provenance must accurately reflect backend, status, trust, and security level
    assert res.backend_provenance is not None
    assert res.backend_provenance.get("backend") == "LocalDevelopmentBackend"
    assert res.backend_provenance.get("status") == "PATCH_APPLY_FAILED"
    assert res.backend_provenance.get("security_level") == "DEVELOPMENT_ONLY"
    assert res.backend_provenance.get("trust") == "TRUSTED_DEVELOPMENT"
    assert isinstance(res.backend_provenance.get("capabilities"), dict)
