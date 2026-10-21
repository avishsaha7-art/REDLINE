import os
import json
import pytest
import shutil
import tempfile
from backend.sandbox.models import SandboxPolicy, ExecutionRequest, ExecutionResult
from backend.sandbox.executor import SandboxExecutor
from backend.sandbox.client import SandboxClient
from backend.evidence.observer import DeterministicObserver
from backend.models.schemas import PatchCandidate, TaskContract, ResourceBudget
import time

@pytest.fixture
def repo_root(monkeypatch):
    monkeypatch.setenv("REDLINE_ENABLE_LOCAL_BACKEND", "1")
    root = tempfile.mkdtemp()
    with open(os.path.join(root, "main.py"), "w") as f:
        f.write("def add(a, b):\n    return a + b\n")
    with open(os.path.join(root, "test_main.py"), "w") as f:
        f.write("from main import add\ndef test_add():\n    assert add(2, 2) == 4\n")
    yield root
    shutil.rmtree(root, ignore_errors=True)

def test_sandbox_policy_defaults():
    policy = SandboxPolicy()
    assert policy.network_enabled is False
    assert policy.max_runtime_seconds == 60
    assert "python" in policy.allowed_commands

def test_execution_request_validation():
    policy = SandboxPolicy(allowed_commands=["python"])
    executor = SandboxExecutor(policy)
    
    with pytest.raises(ValueError, match="Empty command"):
        executor.execute(ExecutionRequest(command=[], working_directory=".", repository_trust="TRUSTED_DEVELOPMENT"), "run-1")
        
    with pytest.raises(ValueError, match="Command not allowed"):
        executor.execute(ExecutionRequest(command=["bash", "-c", "echo hi"], working_directory=".", repository_trust="TRUSTED_DEVELOPMENT"), "run-1")

def test_isolated_workspace_execution(repo_root):
    from backend.sandbox.capabilities import RepositoryTrust
    policy = SandboxPolicy(allowed_commands=["python"])
    client = SandboxClient(policy, repo_root, repository_trust=RepositoryTrust.TRUSTED_DEVELOPMENT)
    
    patch = PatchCandidate(
        patch_id="1",
        task_id="t1",
        base_commit_or_snapshot="snap",
        diff="--- a/main.py\n+++ b/main.py\n@@ -1,2 +1,2 @@\n def add(a, b):\n-    return a + b\n+    return a - b\n",
        changed_files=["main.py"]
    )
    
    # We use python to run tests (or pytest if allowed). Let's use python with unittest or just run test_main.py
    with open(os.path.join(repo_root, "test_main.py"), "w") as f:
        f.write("from main import add\nassert add(2, 2) == 4, 'Math is broken!'\nprint('SUCCESS')\n")
    
    res = client.run_isolated(patch, ["python", "test_main.py"], "run-1")
    assert res.exit_code != 0
    assert "Math is broken!" in res.stderr
    assert "SUCCESS" not in res.stdout
    assert res.crashed is False
    assert res.timed_out is False
    
    # Check that original repo is unmodified
    with open(os.path.join(repo_root, "main.py"), "r") as f:
        content = f.read()
        assert "return a + b" in content

def test_output_limits(repo_root):
    policy = SandboxPolicy(allowed_commands=["python"], max_output_bytes=10)
    executor = SandboxExecutor(policy)
    
    with open(os.path.join(repo_root, "flood.py"), "w") as f:
        f.write("print('A' * 1000)\nimport sys; sys.stderr.write('B' * 1000)\n")
        
    res = executor.execute(ExecutionRequest(command=["python", "flood.py"], working_directory=repo_root, repository_trust="TRUSTED_DEVELOPMENT"), "run-1")
    
    assert res.stdout_truncated is True
    assert res.stderr_truncated is True
    assert len(res.stdout) == 10
    assert len(res.stderr) == 10

def test_timeout_handling(repo_root):
    policy = SandboxPolicy(allowed_commands=["python"])
    executor = SandboxExecutor(policy)
    
    with open(os.path.join(repo_root, "sleep.py"), "w") as f:
        f.write("import time\ntime.sleep(10)\n")
        
    res = executor.execute(ExecutionRequest(command=["python", "sleep.py"], working_directory=repo_root, timeout_seconds=1, repository_trust="TRUSTED_DEVELOPMENT"), "run-1")
    
    assert res.timed_out is True
    assert res.exit_code is not None # usually killed
    
def test_environment_isolation(repo_root):
    policy = SandboxPolicy(allowed_commands=["python"])
    executor = SandboxExecutor(policy)
    
    os.environ["SECRET_KEY"] = "supersecret"
    with open(os.path.join(repo_root, "env.py"), "w") as f:
        f.write("import os\nprint(os.environ.get('SECRET_KEY', 'NOT_FOUND'))\n")
        
    res = executor.execute(ExecutionRequest(command=["python", "env.py"], working_directory=repo_root, repository_trust="TRUSTED_DEVELOPMENT"), "run-1")
    assert "NOT_FOUND" in res.stdout
    assert "supersecret" not in res.stdout
    del os.environ["SECRET_KEY"]

def test_deterministic_observer(repo_root):
    policy = SandboxPolicy(allowed_commands=["python"])
    executor = SandboxExecutor(policy)
    
    with open(os.path.join(repo_root, "test.py"), "w") as f:
        f.write("print('Hello')\n")
        
    res = executor.execute(ExecutionRequest(command=["python", "test.py"], working_directory=repo_root, repository_trust="TRUSTED_DEVELOPMENT"), "run-1")
    
    observer = DeterministicObserver()
    obs = observer.observe(res, "hash123")
    
    assert obs.process_status == "SUCCESSFUL_EXECUTION"
    assert obs.exit_code == 0
    assert obs.stdout_hash == res.stdout_sha256
    assert obs.provenance["run_id"] == "run-1"
    assert obs.provenance["patch_hash"] == "hash123"

def test_e2e_minimal_flow(repo_root):
    # Minimal E2E test as requested in #30
    task = TaskContract(
        task_id="t2",
        repository_id="repo-int-1",
        base_commit_or_snapshot="snap",
        task_description="Ensure add(2, 2) == 4",
        allowed_scope=["main.py"],
        repository_trust="TRUSTED_DEVELOPMENT"
    )
    
    # Original main.py
    with open(os.path.join(repo_root, "main.py"), "w") as f:
        f.write("def add(a, b):\n    pass\n")
        
    # Trusted test
    with open(os.path.join(repo_root, "test_main.py"), "w") as f:
        f.write("from main import add\nassert add(2, 2) == 4\nprint('SUCCESS')\n")
        
    patch = PatchCandidate(
        patch_id="patch1",
        task_id="t2",
        base_commit_or_snapshot="snap",
        diff="--- a/main.py\n+++ b/main.py\n@@ -1,2 +1,2 @@\n def add(a, b):\n-    pass\n+    return a + b\n",
        changed_files=["main.py"]
    )
    
    from backend.sandbox.capabilities import RepositoryTrust
    client = SandboxClient(SandboxPolicy(), repo_root, repository_trust=RepositoryTrust.TRUSTED_DEVELOPMENT)
    res = client.run_isolated(patch, ["python", "test_main.py"], "run-e2e")
    
    assert res.exit_code == 0
    assert "SUCCESS" in res.stdout
    
    obs = DeterministicObserver().observe(res, patch.diff_sha256)
    assert obs.process_status == "SUCCESSFUL_EXECUTION"
