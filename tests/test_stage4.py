import pytest
from pydantic import ValidationError
from backend.models.schemas import TaskContract, ArchitectPlan, PatchCandidate
from backend.agents.architect import ArchitectAgent
from backend.agents.builder import BuilderAgent
from backend.verification.patch_validation import validate_patch
from backend.sandbox.client import SandboxClient

class MockModelProvider:
    def generate(self, messages, **kwargs):
        from backend.models.provider import ModelResponse
        import time
        prompt = str(messages)
        if "REDLINE Builder" in prompt:
            text = '{"changed_files": ["utils.py"], "diff": "--- a/utils.py\\n+++ b/utils.py\\n@@ -0,0 +1,2 @@\\n+def utility():\\n+    pass\\n"}'
        else:
            text = '{"objective": "Implement Add a small utility function", "files_to_inspect": [], "files_to_modify": ["utils.py"], "implementation_steps": [], "acceptance_criteria": [], "constraints": [], "risks": [], "expected_tests": []}'
            
        return ModelResponse(
            provider="mock",
            model="mock-model",
            response_text=text,
            timestamp=time.time()
        )

def test_valid_task_contract():
    task = TaskContract(
        task_id="TASK-1",
        repository_id="repo-1",
        base_commit_or_snapshot="abcdef",
        task_description="Add a small utility function.",
        allowed_scope=["utils.py"]
    )
    assert task.task_id == "TASK-1"

def test_invalid_task_contract():
    with pytest.raises(ValidationError):
        TaskContract(task_id="TASK-1")

def test_architect_plan_generation():
    task = TaskContract(
        task_id="TASK-1",
        repository_id="repo-1",
        base_commit_or_snapshot="abcdef",
        task_description="Add a small utility function",
        allowed_scope=["utils.py"]
    )
    architect = ArchitectAgent(tools=["read_file"], model_provider=MockModelProvider())
    plan = architect.plan(task)
    assert plan.objective == "Implement Add a small utility function"

def test_builder_patch_generation():
    task = TaskContract(
        task_id="TASK-1",
        repository_id="repo-1",
        base_commit_or_snapshot="abcdef",
        task_description="Add a small utility function",
        allowed_scope=["utils.py"]
    )
    plan = ArchitectPlan(objective="Fix", files_to_modify=["utils.py"])
    builder = BuilderAgent(tools=[], model_provider=MockModelProvider())
    patch = builder.build(task, plan, {})
    assert patch.task_id == "TASK-1"

# --- Patch Validation Adversarial Tests ---
def create_patch(diff_content: str, changed_files: list) -> PatchCandidate:
    return PatchCandidate(
        patch_id="P1",
        task_id="TASK-1",
        base_commit_or_snapshot="abcdef",
        diff=diff_content,
        changed_files=changed_files
    )

def test_valid_file_modification():
    diff = "--- a/utils.py\n+++ b/utils.py\n@@ -0,0 +1,2 @@\n+pass"
    patch = create_patch(diff, ["utils.py"])
    task = TaskContract(task_id="TASK-1", repository_id="repo-1", base_commit_or_snapshot="abcdef", task_description="", allowed_scope=["utils.py"])
    assert validate_patch(patch, task) == True

def test_undeclared_modified_file():
    # Diff says utils.py and other.py, metadata only says utils.py
    diff = "--- a/utils.py\n+++ b/utils.py\n@@ -1 +1 @@\n+a\n--- a/other.py\n+++ b/other.py\n@@ -1 +1 @@\n+b"
    patch = create_patch(diff, ["utils.py"])
    task = TaskContract(task_id="TASK-1", repository_id="repo-1", base_commit_or_snapshot="abcdef", task_description="", allowed_scope=["utils.py", "other.py"])
    with pytest.raises(ValueError, match="Metadata/diff mismatch"):
        validate_patch(patch, task)

def test_path_traversal_forward_slash():
    diff = "--- a/../escaped.py\n+++ b/../escaped.py\n@@ -1 +1 @@\n+a"
    patch = create_patch(diff, ["../escaped.py"])
    task = TaskContract(task_id="TASK-1", repository_id="repo-1", base_commit_or_snapshot="abcdef", task_description="")
    with pytest.raises(ValueError, match="Path traversal or absolute path detected"):
        validate_patch(patch, task)

def test_path_traversal_backslash():
    diff = "--- a/..\\escaped.py\n+++ b/..\\escaped.py\n@@ -1 +1 @@\n+a"
    patch = create_patch(diff, ["..\\escaped.py"])
    task = TaskContract(task_id="TASK-1", repository_id="repo-1", base_commit_or_snapshot="abcdef", task_description="")
    with pytest.raises(ValueError, match="Path traversal or absolute path detected"):
        validate_patch(patch, task)

def test_posix_absolute_path():
    diff = "--- a//etc/passwd\n+++ b//etc/passwd\n@@ -1 +1 @@\n+a"
    patch = create_patch(diff, ["/etc/passwd"])
    task = TaskContract(task_id="TASK-1", repository_id="repo-1", base_commit_or_snapshot="abcdef", task_description="")
    with pytest.raises(ValueError, match="Path traversal or absolute path detected"):
        validate_patch(patch, task)

def test_windows_drive_path():
    diff = "--- a/C:\\Windows\\System32\\cmd.exe\n+++ b/C:\\Windows\\System32\\cmd.exe\n@@ -1 +1 @@\n+a"
    patch = create_patch(diff, ["C:\\Windows\\System32\\cmd.exe"])
    task = TaskContract(task_id="TASK-1", repository_id="repo-1", base_commit_or_snapshot="abcdef", task_description="")
    with pytest.raises(ValueError, match="Path traversal or absolute path detected"):
        validate_patch(patch, task)

def test_windows_drive_path_forward_slash():
    diff = "--- a/C:/Windows/System32\n+++ b/C:/Windows/System32\n@@ -1 +1 @@\n+a"
    patch = create_patch(diff, ["C:/Windows/System32"])
    task = TaskContract(task_id="TASK-1", repository_id="repo-1", base_commit_or_snapshot="abcdef", task_description="")
    with pytest.raises(ValueError, match="Path traversal or absolute path detected"):
        validate_patch(patch, task)

def test_unc_path():
    diff = "--- a/\\\\server\\share\\file\n+++ b/\\\\server\\share\\file\n@@ -1 +1 @@\n+a"
    patch = create_patch(diff, ["\\\\server\\share\\file"])
    task = TaskContract(task_id="TASK-1", repository_id="repo-1", base_commit_or_snapshot="abcdef", task_description="")
    with pytest.raises(ValueError, match="Path traversal or absolute path detected"):
        validate_patch(patch, task)

def test_mixed_separators_traversal():
    diff = "--- a/dir/..\\..\\file\n+++ b/dir/..\\..\\file\n@@ -1 +1 @@\n+a"
    patch = create_patch(diff, ["dir/..\\..\\file"])
    task = TaskContract(task_id="TASK-1", repository_id="repo-1", base_commit_or_snapshot="abcdef", task_description="")
    with pytest.raises(ValueError, match="Path traversal or absolute path detected"):
        validate_patch(patch, task)

def test_case_variant_protected_file():
    diff = "--- a/.GITHUB/Workflows/deploy.yml\n+++ b/.GITHUB/Workflows/deploy.yml\n@@ -1 +1 @@\n+a"
    patch = create_patch(diff, [".GITHUB/Workflows/deploy.yml"])
    task = TaskContract(task_id="TASK-1", repository_id="repo-1", base_commit_or_snapshot="abcdef", task_description="")
    with pytest.raises(ValueError, match="Protected-file modification attempted"):
        validate_patch(patch, task)

def test_protected_workflow_modification():
    diff = "--- a/.github/workflows/deploy.yml\n+++ b/.github/workflows/deploy.yml\n@@ -1 +1 @@\n+a"
    patch = create_patch(diff, [".github/workflows/deploy.yml"])
    task = TaskContract(task_id="TASK-1", repository_id="repo-1", base_commit_or_snapshot="abcdef", task_description="")
    with pytest.raises(ValueError, match="Protected-file modification attempted"):
        validate_patch(patch, task)

def test_malformed_diff():
    diff = "This is just some random text without hunks"
    patch = create_patch(diff, ["random"])
    task = TaskContract(task_id="TASK-1", repository_id="repo-1", base_commit_or_snapshot="abcdef", task_description="")
    with pytest.raises(ValueError, match="Malformed patch format"):
        validate_patch(patch, task)

def test_metadata_diff_mismatch():
    diff = "--- a/real.py\n+++ b/real.py\n@@ -1 +1 @@\n+a"
    patch = create_patch(diff, ["fake.py"])
    task = TaskContract(task_id="TASK-1", repository_id="repo-1", base_commit_or_snapshot="abcdef", task_description="")
    with pytest.raises(ValueError, match="Metadata/diff mismatch"):
        validate_patch(patch, task)

def test_nested_valid_repository_path():
    diff = "--- a/src/backend/utils/helpers.py\n+++ b/src/backend/utils/helpers.py\n@@ -1 +1 @@\n+a"
    patch = create_patch(diff, ["src/backend/utils/helpers.py"])
    task = TaskContract(task_id="TASK-1", repository_id="repo-1", base_commit_or_snapshot="abcdef", task_description="")
    assert validate_patch(patch, task) == True

def test_create_file_diff():
    diff = "--- /dev/null\n+++ b/new_file.py\n@@ -0,0 +1,2 @@\n+a"
    patch = create_patch(diff, ["new_file.py"])
    task = TaskContract(task_id="TASK-1", repository_id="repo-1", base_commit_or_snapshot="abcdef", task_description="")
    assert validate_patch(patch, task) == True

def test_delete_file_diff():
    diff = "--- a/old_file.py\n+++ /dev/null\n@@ -1,2 +0,0 @@\n-a"
    patch = create_patch(diff, ["old_file.py"])
    task = TaskContract(task_id="TASK-1", repository_id="repo-1", base_commit_or_snapshot="abcdef", task_description="")
    assert validate_patch(patch, task) == True

def test_duplicate_paths():
    diff = "--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n+a\n--- a/file.py\n+++ b/file.py\n@@ -5 +5 @@\n+b"
    patch = create_patch(diff, ["file.py"])
    task = TaskContract(task_id="TASK-1", repository_id="repo-1", base_commit_or_snapshot="abcdef", task_description="")
    assert validate_patch(patch, task) == True
