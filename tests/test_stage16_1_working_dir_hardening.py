"""
REDLINE — Stage 16.1: Sandbox Working-Directory Hardening Regression Suite.

Verifies fail-closed working directory validation on LocalDevelopmentBackend:
1. Valid authorized working directory succeeds.
2. Missing or empty working directory is rejected.
3. Non-existent working directory is rejected.
4. Regular file supplied instead of directory is rejected.
5. Relative path handling follows documented contract (anchored to sandbox_root/workspaces).
6. Path traversal escaping authorized workspace is rejected.
7. Relevant symlink / junction escapes are rejected.
8. Subprocess is NEVER created when validation fails (verified via spy).
9. Untrusted repositories remain blocked.
10. No silent fallback to cwd=None or host process working directory.
"""

import os
import sys
import tempfile
import shutil
import subprocess
from unittest.mock import patch, MagicMock
import pytest

from backend.sandbox.models import SandboxPolicy, ExecutionRequest, ExecutionResult
from backend.sandbox.backend import LocalDevelopmentBackend


@pytest.fixture
def sandbox_env():
    """Provides an isolated sandbox root and outside directory for testing."""
    root = tempfile.mkdtemp(prefix="redline_test_root_")
    outside = tempfile.mkdtemp(prefix="redline_test_outside_")
    sub = os.path.join(root, "subdir")
    os.makedirs(sub, exist_ok=True)

    yield {
        "root": root,
        "outside": outside,
        "sub": sub
    }

    shutil.rmtree(root, ignore_errors=True)
    shutil.rmtree(outside, ignore_errors=True)


def test_valid_authorized_working_directory_succeeds(sandbox_env):
    """A valid, existing authorized directory executes successfully."""
    policy = SandboxPolicy(sandbox_root=sandbox_env["root"], allowed_commands=["python"])
    backend = LocalDevelopmentBackend(policy)

    test_file = os.path.join(sandbox_env["sub"], "hello.py")
    with open(test_file, "w") as f:
        f.write("import os; print('CWD:', os.getcwd())")

    req = ExecutionRequest(
        command=["python", "hello.py"],
        working_directory=sandbox_env["sub"],
        repository_trust="TRUSTED_DEVELOPMENT"
    )

    res = backend.execute(req, "run-valid-cwd")
    assert res.policy_blocked is False
    assert res.exit_code == 0
    assert os.path.realpath(sandbox_env["sub"]) in res.stdout


def test_missing_or_empty_working_directory_rejected(monkeypatch):
    """Empty, whitespace, or None working directory fails closed."""
    policy = SandboxPolicy(allowed_commands=["python"])
    backend = LocalDevelopmentBackend(policy)

    popen_called = False
    def spy_popen(*args, **kwargs):
        nonlocal popen_called
        popen_called = True
        raise AssertionError("subprocess.Popen must NOT be called on invalid working directory!")

    monkeypatch.setattr(subprocess, "Popen", spy_popen)

    for invalid_cwd in ["", "   ", None]:
        req = ExecutionRequest(
            command=["python", "-c", "print(1)"],
            working_directory=invalid_cwd or "",
            repository_trust="TRUSTED_DEVELOPMENT"
        )
        res = backend.execute(req, "run-empty-cwd")
        assert res.policy_blocked is True
        assert res.exit_code == -1
        assert "POLICY_BLOCKED" in res.stderr
        assert "Working directory must be provided" in res.stderr
        assert popen_called is False


def test_nonexistent_working_directory_rejected(monkeypatch):
    """Non-existent directory fails closed and never launches a subprocess."""
    policy = SandboxPolicy(allowed_commands=["python"])
    backend = LocalDevelopmentBackend(policy)

    popen_called = False
    def spy_popen(*args, **kwargs):
        nonlocal popen_called
        popen_called = True
        raise AssertionError("subprocess.Popen must NOT be called on non-existent working directory!")

    monkeypatch.setattr(subprocess, "Popen", spy_popen)

    nonexistent = os.path.join(tempfile.gettempdir(), "nonexistent_redline_dir_999999")
    if os.path.exists(nonexistent):
        shutil.rmtree(nonexistent, ignore_errors=True)

    req = ExecutionRequest(
        command=["python", "-c", "print(1)"],
        working_directory=nonexistent,
        repository_trust="TRUSTED_DEVELOPMENT"
    )

    res = backend.execute(req, "run-nonexistent-cwd")
    assert res.policy_blocked is True
    assert res.exit_code == -1
    assert "Working directory does not exist" in res.stderr
    assert popen_called is False


def test_file_supplied_instead_of_directory_rejected(sandbox_env, monkeypatch):
    """Supplying a regular file instead of a directory is rejected."""
    policy = SandboxPolicy(sandbox_root=sandbox_env["root"], allowed_commands=["python"])
    backend = LocalDevelopmentBackend(policy)

    test_file = os.path.join(sandbox_env["root"], "file_not_dir.txt")
    with open(test_file, "w") as f:
        f.write("I am a file, not a directory")

    popen_called = False
    def spy_popen(*args, **kwargs):
        nonlocal popen_called
        popen_called = True
        raise AssertionError("subprocess.Popen must NOT be called when cwd is a file!")

    monkeypatch.setattr(subprocess, "Popen", spy_popen)

    req = ExecutionRequest(
        command=["python", "-c", "print(1)"],
        working_directory=test_file,
        repository_trust="TRUSTED_DEVELOPMENT"
    )

    res = backend.execute(req, "run-file-cwd")
    assert res.policy_blocked is True
    assert res.exit_code == -1
    assert "not a directory" in res.stderr
    assert popen_called is False


def test_relative_path_handling_follows_documented_contract(sandbox_env):
    """Relative paths resolve against sandbox_root and execute properly."""
    policy = SandboxPolicy(sandbox_root=sandbox_env["root"], allowed_commands=["python"])
    backend = LocalDevelopmentBackend(policy)

    test_script = os.path.join(sandbox_env["sub"], "rel_test.py")
    with open(test_script, "w") as f:
        f.write("import os; print('IN_SUBDIR')")

    # Pass relative path 'subdir'
    req = ExecutionRequest(
        command=["python", "rel_test.py"],
        working_directory="subdir",
        repository_trust="TRUSTED_DEVELOPMENT"
    )

    res = backend.execute(req, "run-rel-cwd")
    assert res.policy_blocked is False
    assert res.exit_code == 0
    assert "IN_SUBDIR" in res.stdout


def test_path_traversal_outside_sandbox_root_rejected(sandbox_env, monkeypatch):
    """Attempting directory traversal escaping sandbox root fails closed."""
    policy = SandboxPolicy(sandbox_root=sandbox_env["root"], allowed_commands=["python"])
    backend = LocalDevelopmentBackend(policy)

    popen_called = False
    def spy_popen(*args, **kwargs):
        nonlocal popen_called
        popen_called = True
        raise AssertionError("subprocess.Popen must NOT be called on traversal escape!")

    monkeypatch.setattr(subprocess, "Popen", spy_popen)

    # Traversal escaping sandbox_root
    escaping_path = os.path.join(sandbox_env["root"], "..")
    req = ExecutionRequest(
        command=["python", "-c", "print(1)"],
        working_directory=escaping_path,
        repository_trust="TRUSTED_DEVELOPMENT"
    )

    res = backend.execute(req, "run-traversal-cwd")
    assert res.policy_blocked is True
    assert res.exit_code == -1
    assert "escapes sandbox root" in res.stderr
    assert popen_called is False


def test_absolute_path_outside_sandbox_root_rejected(sandbox_env, monkeypatch):
    """Supplying an existing absolute directory outside sandbox root is rejected."""
    policy = SandboxPolicy(sandbox_root=sandbox_env["root"], allowed_commands=["python"])
    backend = LocalDevelopmentBackend(policy)

    popen_called = False
    def spy_popen(*args, **kwargs):
        nonlocal popen_called
        popen_called = True
        raise AssertionError("subprocess.Popen must NOT be called on external directory!")

    monkeypatch.setattr(subprocess, "Popen", spy_popen)

    req = ExecutionRequest(
        command=["python", "-c", "print(1)"],
        working_directory=sandbox_env["outside"],
        repository_trust="TRUSTED_DEVELOPMENT"
    )

    res = backend.execute(req, "run-outside-cwd")
    assert res.policy_blocked is True
    assert res.exit_code == -1
    assert "escapes sandbox root" in res.stderr
    assert popen_called is False


def test_allowed_workspaces_restriction(sandbox_env, monkeypatch):
    """When allowed_workspaces is configured, directories outside the set are rejected."""
    policy = SandboxPolicy(allowed_workspaces=[sandbox_env["sub"]], allowed_commands=["python"])
    backend = LocalDevelopmentBackend(policy)

    # Working dir in allowed workspace -> succeeds
    req_valid = ExecutionRequest(
        command=["python", "-c", "print('OK')"],
        working_directory=sandbox_env["sub"],
        repository_trust="TRUSTED_DEVELOPMENT"
    )
    res_valid = backend.execute(req_valid, "run-ws-valid")
    assert res_valid.policy_blocked is False
    assert res_valid.exit_code == 0

    # Working dir outside allowed workspace -> rejected
    popen_called = False
    def spy_popen(*args, **kwargs):
        nonlocal popen_called
        popen_called = True
        raise AssertionError("subprocess.Popen must NOT be called outside allowed workspaces!")

    monkeypatch.setattr(subprocess, "Popen", spy_popen)

    req_invalid = ExecutionRequest(
        command=["python", "-c", "print('FAIL')"],
        working_directory=sandbox_env["outside"],
        repository_trust="TRUSTED_DEVELOPMENT"
    )
    res_invalid = backend.execute(req_invalid, "run-ws-invalid")
    assert res_invalid.policy_blocked is True
    assert "outside authorized workspaces" in res_invalid.stderr
    assert popen_called is False


def test_symlink_or_junction_escape_rejected(sandbox_env, monkeypatch):
    """A symlink or junction inside sandbox pointing to outside is detected and blocked."""
    policy = SandboxPolicy(sandbox_root=sandbox_env["root"], allowed_commands=["python"])
    backend = LocalDevelopmentBackend(policy)

    link_path = os.path.join(sandbox_env["root"], "escape_link")

    created = False
    if sys.platform == "win32":
        try:
            import _winapi
            _winapi.CreateJunction(sandbox_env["outside"], link_path)
            created = True
        except Exception:
            pass

    if not created:
        try:
            os.symlink(sandbox_env["outside"], link_path, target_is_directory=True)
            created = True
        except OSError:
            pass

    if not created:
        pytest.skip("Filesystem links not supported with current privileges")

    popen_called = False
    def spy_popen(*args, **kwargs):
        nonlocal popen_called
        popen_called = True
        raise AssertionError("subprocess.Popen must NOT be called on symlink escape!")

    monkeypatch.setattr(subprocess, "Popen", spy_popen)

    req = ExecutionRequest(
        command=["python", "-c", "print(1)"],
        working_directory=link_path,
        repository_trust="TRUSTED_DEVELOPMENT"
    )

    res = backend.execute(req, "run-symlink-escape")
    assert res.policy_blocked is True
    assert res.exit_code == -1
    assert "escapes sandbox root" in res.stderr
    assert popen_called is False


def test_untrusted_repository_remains_blocked_regardless_of_directory(sandbox_env):
    """Untrusted repositories are blocked before directory validation or subprocess creation."""
    policy = SandboxPolicy(sandbox_root=sandbox_env["root"], allowed_commands=["python"])
    backend = LocalDevelopmentBackend(policy)

    req = ExecutionRequest(
        command=["python", "-c", "print(1)"],
        working_directory=sandbox_env["sub"],
        repository_trust="UNTRUSTED"
    )

    res = backend.execute(req, "run-untrusted-repo")
    assert res.policy_blocked is True
    assert "UNSAFE FOR UNTRUSTED PRODUCTION WORKLOADS" in res.stderr


def test_require_absolute_paths_enforcement(sandbox_env):
    """When require_absolute_paths is enabled, relative paths are rejected fail-closed."""
    policy = SandboxPolicy(sandbox_root=sandbox_env["root"], require_absolute_paths=True, allowed_commands=["python"])
    backend = LocalDevelopmentBackend(policy)

    req = ExecutionRequest(
        command=["python", "-c", "print(1)"],
        working_directory="subdir",
        repository_trust="TRUSTED_DEVELOPMENT"
    )

    res = backend.execute(req, "run-relative-prohibited")
    assert res.policy_blocked is True
    assert "require_absolute_paths" in res.stderr
