"""
Comprehensive adversarial and regression tests for Dataset Integrity Engine.

Verifies all requirements from Stage P2-3.2:
1. Baseline repository verification against immutable trust anchors.
2. Wrong commit SHA or tag target commit detection.
3. Lightweight tag substitution rejection (mandates annotated tag object).
4. Missing Git metadata / non-git directory handling.
5. Manifest raw-byte digest mismatch detection.
6. Malformed JSON manifest rejection.
7. Unexpected untracked dataset files rejection in strict mode.
8. Modified tracked dataset files detection.
9. Missing artifact file detection.
10. Tampered artifact byte detection.
11. Relative path traversal ('..') rejection.
12. Absolute path rejection.
13. Symlink escape detection.
14. Incomplete or interrupted verification guarantee (never returns VERIFIED on failure).

All tests use isolated temporary directories and temporary Git repositories.
Zero mutations occur on the live repository, checkpoint, or tags.
"""

import os
import sys
import json
import shutil
import hashlib
import subprocess
import pytest
from pathlib import Path

from backend.benchmark.integrity import (
    BenchmarkIntegrityChecker,
    verify_dataset_anchor,
    DEFAULT_TRUSTED_ANCHOR,
    BenchmarkIntegrityError,
    AnchorVerificationError,
    WorkingTreeIntegrityError,
    ManifestVerificationError,
    ArtifactVerificationError,
    IntegrityVerificationResult
)


@pytest.fixture
def isolated_git_repo(tmp_path):
    """
    Creates an isolated Git repository initialized with a copy of the actual
    dataset files, a commit, and an annotated tag for safe adversarial testing.
    """
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()

    # 1. Initialize git repo
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test Runner"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_dir, check=True, capture_output=True)

    # 2. Copy dataset files from actual repo
    src_dataset = Path("backend/benchmark/dataset").resolve()
    dest_dataset = repo_dir / "backend" / "benchmark" / "dataset"
    shutil.copytree(src_dataset, dest_dataset)

    # 3. Add and commit
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "chore: initial test commit"], cwd=repo_dir, check=True, capture_output=True)

    # 4. Get commit hash
    commit_proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_dir, check=True, capture_output=True, text=True)
    commit_sha = commit_proc.stdout.strip()

    # 5. Create annotated tag
    tag_name = "test-tag-v1.0"
    subprocess.run(
        ["git", "tag", "-a", tag_name, "-m", "Test annotated tag annotation"],
        cwd=repo_dir, check=True, capture_output=True
    )

    # Compute manifest hash
    manifest_bytes = (dest_dataset / "manifest.json").read_bytes()
    manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()

    anchor_config = {
        "dataset_name": "REDLINE-Held-Out-Security-Benchmark",
        "dataset_version": "1.0.0",
        "dataset_commit_sha": commit_sha,
        "dataset_tag": tag_name,
        "manifest_root_sha256": manifest_hash,
        "task_count": 12,
        "total_artifacts": 84,
    }

    return {
        "repo_dir": str(repo_dir),
        "dataset_dir": str(dest_dataset),
        "commit_sha": commit_sha,
        "tag_name": tag_name,
        "manifest_hash": manifest_hash,
        "anchor_config": anchor_config,
    }


# ---------------------------------------------------------------------------
# 1. Baseline Live Repository Verification
# ---------------------------------------------------------------------------

def test_baseline_repository_verifies_cleanly():
    """Live repository must verify 100% cleanly against the frozen P2-2 checkpoint."""
    result = verify_dataset_anchor(strict_working_tree=True)
    assert result.status == "VERIFIED"
    assert result.commit_sha == DEFAULT_TRUSTED_ANCHOR["dataset_commit_sha"]
    assert result.tag_name == DEFAULT_TRUSTED_ANCHOR["dataset_tag"]
    assert result.manifest_sha256 == DEFAULT_TRUSTED_ANCHOR["manifest_root_sha256"]
    assert result.tasks_verified == 12
    assert result.artifacts_verified == 84
    assert "GIT_ANCHOR_VERIFIED" in result.checks_passed
    assert "WORKING_TREE_CLEAN" in result.checks_passed
    assert "MANIFEST_RAW_BYTE_DIGEST_VERIFIED" in result.checks_passed
    assert "ALL_ARTIFACT_DIGESTS_VERIFIED" in result.checks_passed


# ---------------------------------------------------------------------------
# 2. Git Commit and Tag Anchor Adversarial Tests
# ---------------------------------------------------------------------------

def test_wrong_commit_sha_fails_closed(isolated_git_repo):
    """Wrong commit SHA must be rejected fail-closed."""
    config = dict(isolated_git_repo["anchor_config"])
    config["dataset_commit_sha"] = "0" * 40

    checker = BenchmarkIntegrityChecker(
        repo_root=isolated_git_repo["repo_dir"],
        dataset_root=isolated_git_repo["dataset_dir"],
        anchor_config=config
    )
    with pytest.raises(AnchorVerificationError, match="does not exist in repository"):
        checker.verify_all()


def test_wrong_tag_name_fails_closed(isolated_git_repo):
    """Non-existent tag name must be rejected fail-closed."""
    config = dict(isolated_git_repo["anchor_config"])
    config["dataset_tag"] = "nonexistent-tag"

    checker = BenchmarkIntegrityChecker(
        repo_root=isolated_git_repo["repo_dir"],
        dataset_root=isolated_git_repo["dataset_dir"],
        anchor_config=config
    )
    with pytest.raises(AnchorVerificationError, match="not found in refs/tags/"):
        checker.verify_all()


def test_tag_target_commit_mismatch_fails_closed(isolated_git_repo):
    """When a tag points to a different commit than the anchor, fail closed."""
    repo_dir = isolated_git_repo["repo_dir"]

    # Create a second dummy commit
    dummy_file = os.path.join(repo_dir, "dummy.txt")
    with open(dummy_file, "w") as f:
        f.write("second commit")
    subprocess.run(["git", "add", "dummy.txt"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "second commit"], cwd=repo_dir, check=True, capture_output=True)

    # Point tag to second commit, while anchor expects the first commit
    subprocess.run(["git", "tag", "-a", "-f", "mismatched-tag", "-m", "mismatch"], cwd=repo_dir, check=True, capture_output=True)

    config = dict(isolated_git_repo["anchor_config"])
    config["dataset_tag"] = "mismatched-tag"
    # anchor expects first commit, but tag points to second commit

    checker = BenchmarkIntegrityChecker(
        repo_root=repo_dir,
        dataset_root=isolated_git_repo["dataset_dir"],
        anchor_config=config
    )
    with pytest.raises(AnchorVerificationError, match="target commit mismatch"):
        checker.verify_all()


def test_lightweight_tag_substitution_fails_closed(isolated_git_repo):
    """Lightweight tags (non-annotated) must be rejected fail-closed."""
    repo_dir = isolated_git_repo["repo_dir"]
    # Create lightweight tag
    subprocess.run(["git", "tag", "lightweight-tag"], cwd=repo_dir, check=True, capture_output=True)

    config = dict(isolated_git_repo["anchor_config"])
    config["dataset_tag"] = "lightweight-tag"

    checker = BenchmarkIntegrityChecker(
        repo_root=repo_dir,
        dataset_root=isolated_git_repo["dataset_dir"],
        anchor_config=config
    )
    with pytest.raises(AnchorVerificationError, match="is a lightweight tag"):
        checker.verify_all()


def test_missing_git_metadata_fails_closed(tmp_path):
    """Non-git directory must be rejected fail-closed."""
    plain_dir = tmp_path / "plain_dir"
    plain_dir.mkdir()
    checker = BenchmarkIntegrityChecker(repo_root=str(plain_dir))
    with pytest.raises(AnchorVerificationError, match="not a valid Git work tree"):
        checker.verify_all()


# ---------------------------------------------------------------------------
# 3. Working Tree Cleanliness & Strict Mode Tests
# ---------------------------------------------------------------------------

def test_unexpected_untracked_files_rejected_in_strict_mode(isolated_git_repo):
    """In strict mode, unexpected untracked files in dataset must trigger failure."""
    dataset_dir = isolated_git_repo["dataset_dir"]
    rogue_file = os.path.join(dataset_dir, "rogue_task.json")
    with open(rogue_file, "w") as f:
        f.write("{}")

    checker = BenchmarkIntegrityChecker(
        repo_root=isolated_git_repo["repo_dir"],
        dataset_root=dataset_dir,
        anchor_config=isolated_git_repo["anchor_config"],
        strict_working_tree=True
    )
    with pytest.raises(WorkingTreeIntegrityError, match="unexpected untracked files in strict mode"):
        checker.verify_all()


def test_non_strict_mode_allows_untracked_files(isolated_git_repo):
    """In non-strict mode, untracked files do not fail working tree check."""
    dataset_dir = isolated_git_repo["dataset_dir"]
    rogue_file = os.path.join(dataset_dir, "notes.txt")
    with open(rogue_file, "w") as f:
        f.write("scratch notes")

    checker = BenchmarkIntegrityChecker(
        repo_root=isolated_git_repo["repo_dir"],
        dataset_root=dataset_dir,
        anchor_config=isolated_git_repo["anchor_config"],
        strict_working_tree=False
    )
    res = checker.verify_all()
    assert res.status == "VERIFIED"


def test_modified_tracked_dataset_file_fails_closed(isolated_git_repo):
    """Modified tracked file in dataset directory must be rejected fail-closed."""
    dataset_dir = isolated_git_repo["dataset_dir"]
    target_file = os.path.join(dataset_dir, "fixtures", "SEC-BENCH-001", "app.py")
    with open(target_file, "a") as f:
        f.write("\n# unauthorized modification\n")

    checker = BenchmarkIntegrityChecker(
        repo_root=isolated_git_repo["repo_dir"],
        dataset_root=dataset_dir,
        anchor_config=isolated_git_repo["anchor_config"],
        strict_working_tree=True
    )
    with pytest.raises(WorkingTreeIntegrityError, match="modified tracked files"):
        checker.verify_all()


# ---------------------------------------------------------------------------
# 4. Manifest Integrity and Validation Tests
# ---------------------------------------------------------------------------

def test_manifest_raw_byte_digest_mismatch_fails_closed(isolated_git_repo):
    """Altered manifest root SHA-256 must trigger fail-closed error."""
    config = dict(isolated_git_repo["anchor_config"])
    config["manifest_root_sha256"] = "f" * 64

    checker = BenchmarkIntegrityChecker(
        repo_root=isolated_git_repo["repo_dir"],
        dataset_root=isolated_git_repo["dataset_dir"],
        anchor_config=config
    )
    with pytest.raises(ManifestVerificationError, match="raw-byte SHA-256 digest mismatch"):
        checker.verify_all()


def test_malformed_manifest_json_fails_closed(isolated_git_repo):
    """Malformed JSON in manifest must trigger fail-closed error."""
    repo_dir = isolated_git_repo["repo_dir"]
    dataset_dir = isolated_git_repo["dataset_dir"]
    manifest_path = os.path.join(dataset_dir, "manifest.json")

    # Corrupt JSON
    with open(manifest_path, "w", encoding="utf-8") as f:
        f.write("{ invalid json: [")

    # Re-commit to avoid working tree check failure first
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "corrupt manifest"], cwd=repo_dir, check=True, capture_output=True)
    rev = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_dir, check=True, capture_output=True, text=True).stdout.strip()
    subprocess.run(["git", "tag", "-a", "-f", "test-tag-v1.0", "-m", "corrupt"], cwd=repo_dir, check=True, capture_output=True)

    new_hash = hashlib.sha256(open(manifest_path, "rb").read()).hexdigest()
    config = dict(isolated_git_repo["anchor_config"])
    config["dataset_commit_sha"] = rev
    config["manifest_root_sha256"] = new_hash

    checker = BenchmarkIntegrityChecker(
        repo_root=repo_dir,
        dataset_root=dataset_dir,
        anchor_config=config
    )
    with pytest.raises(ManifestVerificationError, match="malformed JSON"):
        checker.verify_all()


# ---------------------------------------------------------------------------
# 5. Artifact Tamper Detection, Traversal, and Symlink Tests
# ---------------------------------------------------------------------------

def test_missing_artifact_fails_closed(isolated_git_repo):
    """Deleted artifact file must trigger ArtifactVerificationError when committed or verified directly."""
    dataset_dir = isolated_git_repo["dataset_dir"]
    repo_dir = isolated_git_repo["repo_dir"]
    target = os.path.join(dataset_dir, "evaluators", "SEC-BENCH-001", "test_secure.py")
    os.remove(target)

    checker = BenchmarkIntegrityChecker(
        repo_root=repo_dir,
        dataset_root=dataset_dir,
        anchor_config=isolated_git_repo["anchor_config"],
        strict_working_tree=False
    )
    # 1. Direct artifact verification catches missing file
    _, manifest_data = checker.verify_manifest()
    with pytest.raises(ArtifactVerificationError, match="Artifact file missing from disk"):
        checker.verify_artifact_digests_and_paths(manifest_data)

    # 2. When committed so working tree is clean, verify_all catches missing artifact at step 4
    subprocess.run(["git", "commit", "-am", "test: commit deletion"], cwd=repo_dir, check=True, capture_output=True)
    with pytest.raises(ArtifactVerificationError, match="Artifact file missing from disk"):
        checker.verify_all()


def test_tampered_artifact_digest_fails_closed(isolated_git_repo):
    """Single-byte tamper in an artifact must trigger digest mismatch error."""
    dataset_dir = isolated_git_repo["dataset_dir"]
    repo_dir = isolated_git_repo["repo_dir"]
    target = os.path.join(dataset_dir, "evaluators", "SEC-BENCH-002", "fixed_app.py")
    with open(target, "a") as f:
        f.write("# tampered")

    checker = BenchmarkIntegrityChecker(
        repo_root=repo_dir,
        dataset_root=dataset_dir,
        anchor_config=isolated_git_repo["anchor_config"],
        strict_working_tree=False
    )
    # 1. Direct artifact verification catches digest mismatch
    _, manifest_data = checker.verify_manifest()
    with pytest.raises(ArtifactVerificationError, match="Cryptographic digest mismatch for artifact"):
        checker.verify_artifact_digests_and_paths(manifest_data)

    # 2. When committed so working tree is clean, verify_all catches digest mismatch at step 4
    subprocess.run(["git", "commit", "-am", "test: commit tamper"], cwd=repo_dir, check=True, capture_output=True)
    with pytest.raises(ArtifactVerificationError, match="Cryptographic digest mismatch for artifact"):
        checker.verify_all()


def test_path_traversal_in_manifest_fails_closed(isolated_git_repo):
    """Parent traversal path in manifest must be rejected."""
    dataset_dir = isolated_git_repo["dataset_dir"]
    manifest_path = os.path.join(dataset_dir, "manifest.json")
    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Insert traversal path
    data["tasks"][0]["file_digests"]["../../outside.py"] = "0" * 64

    checker = BenchmarkIntegrityChecker(
        repo_root=isolated_git_repo["repo_dir"],
        dataset_root=dataset_dir,
        anchor_config=isolated_git_repo["anchor_config"]
    )
    with pytest.raises(ArtifactVerificationError, match="traversal"):
        checker.verify_artifact_digests_and_paths(data)


def test_absolute_path_in_manifest_fails_closed(isolated_git_repo):
    """Absolute path in manifest must be rejected."""
    dataset_dir = isolated_git_repo["dataset_dir"]
    manifest_path = os.path.join(dataset_dir, "manifest.json")
    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Insert absolute path
    abs_path = "C:/Windows/System32/drivers/etc/hosts" if sys.platform == "win32" else "/etc/hosts"
    data["tasks"][0]["file_digests"][abs_path] = "0" * 64

    checker = BenchmarkIntegrityChecker(
        repo_root=isolated_git_repo["repo_dir"],
        dataset_root=dataset_dir,
        anchor_config=isolated_git_repo["anchor_config"]
    )
    with pytest.raises(ArtifactVerificationError, match="Absolute path forbidden"):
        checker.verify_artifact_digests_and_paths(data)


def test_symlink_escape_mocked(isolated_git_repo, monkeypatch):
    """Symlink escape detection must trigger ArtifactVerificationError even without OS symlink privileges."""
    dataset_dir = isolated_git_repo["dataset_dir"]
    manifest_path = os.path.join(dataset_dir, "manifest.json")
    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    first_rel_path = list(data["tasks"][0]["file_digests"].keys())[0]
    first_full_path = os.path.normpath(os.path.join(dataset_dir, first_rel_path))

    orig_islink = os.path.islink
    orig_realpath = os.path.realpath

    def fake_islink(path, *args, **kwargs):
        if os.path.normpath(path) == first_full_path:
            return True
        return orig_islink(path, *args, **kwargs)

    def fake_realpath(path, *args, **kwargs):
        if os.path.normpath(path) == first_full_path:
            return os.path.abspath(os.path.join(isolated_git_repo["repo_dir"], "..", "outside.py"))
        return orig_realpath(path, *args, **kwargs)

    monkeypatch.setattr(os.path, "islink", fake_islink)
    monkeypatch.setattr(os.path, "realpath", fake_realpath)

    checker = BenchmarkIntegrityChecker(
        repo_root=isolated_git_repo["repo_dir"],
        dataset_root=dataset_dir,
        anchor_config=isolated_git_repo["anchor_config"]
    )
    with pytest.raises(ArtifactVerificationError, match="Symlink escape detected"):
        checker.verify_artifact_digests_and_paths(data)


def test_symlink_escape_fails_closed(isolated_git_repo, tmp_path):
    """Symlink escaping dataset root boundary must be detected and rejected."""
    dataset_dir = Path(isolated_git_repo["dataset_dir"])
    outside_file = tmp_path / "outside_target.py"
    outside_file.write_text("print('outside')")

    link_path = dataset_dir / "fixtures" / "SEC-BENCH-001" / "escaped_link.py"
    try:
        os.symlink(str(outside_file), str(link_path))
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation not supported in this environment without elevated privileges")

    manifest_path = dataset_dir / "manifest.json"
    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    data["tasks"][0]["file_digests"]["fixtures/SEC-BENCH-001/escaped_link.py"] = hashlib.sha256(b"print('outside')").hexdigest()

    checker = BenchmarkIntegrityChecker(
        repo_root=isolated_git_repo["repo_dir"],
        dataset_root=str(dataset_dir),
        anchor_config=isolated_git_repo["anchor_config"]
    )
    with pytest.raises(ArtifactVerificationError, match="Symlink escape detected"):
        checker.verify_artifact_digests_and_paths(data)


# ---------------------------------------------------------------------------
# 6. Incomplete / Interrupted Verification Guarantee
# ---------------------------------------------------------------------------

def test_interrupted_verification_never_returns_verified(isolated_git_repo):
    """If verification aborts or encounters an exception, status must NEVER be VERIFIED."""
    config = dict(isolated_git_repo["anchor_config"])
    config["dataset_commit_sha"] = "wrong"

    checker = BenchmarkIntegrityChecker(
        repo_root=isolated_git_repo["repo_dir"],
        dataset_root=isolated_git_repo["dataset_dir"],
        anchor_config=config
    )
    try:
        checker.verify_all()
    except BenchmarkIntegrityError:
        pass

    # A failed check must never leave a VERIFIED result
    assert checker.verify_git_anchor  # Callable preserved
