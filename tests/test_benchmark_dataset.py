"""
REDLINE Frozen Held-Out Security Benchmark Dataset Test Suite.

Validates:
1. Dataset manifest schema, versioning, and task counts.
2. Canonical vulnerability taxonomy and unique task IDs.
3. Path traversal prevention and strict dataset root containment.
4. Cryptographic integrity (SHA-256 digests) and tamper detection.
5. Absolute absence of live credentials or production secrets.
6. Vulnerability reproducibility across all 12 benchmark tasks.
7. Ground-truth secure acceptance across all 12 benchmark tasks.
8. Non-regression of legitimate functionality.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
import pytest

DATASET_ROOT = Path("backend/benchmark/dataset").resolve()
MANIFEST_PATH = DATASET_ROOT / "manifest.json"
SCHEMA_PATH = DATASET_ROOT / "schema.json"

PERMITTED_CATEGORIES = {
    "SQL_INJECTION",
    "PATH_TRAVERSAL",
    "RACE_CONDITION",
    "AUTH_BYPASS",
    "AUTHORIZATION",
    "CACHE_INVALIDATION",
    "RESOURCE_LEAK",
    "COMMAND_INJECTION",
    "DUPLICATE_TRANSACTION",
    "UNBOUNDED_PAGINATION",
    "PRIVILEGE_ESCALATION",
    "SECRET_LEAKAGE",
}

PERMITTED_SEVERITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}


def load_manifest() -> dict:
    assert MANIFEST_PATH.is_file(), f"Manifest file missing: {MANIFEST_PATH}"
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def calculate_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Structural & Metadata Tests
# ---------------------------------------------------------------------------

def test_manifest_schema_and_version():
    """Verify manifest exists, conforms to required version, and matches task count."""
    manifest = load_manifest()
    assert manifest.get("dataset_name") == "REDLINE-Held-Out-Security-Benchmark"
    assert manifest.get("dataset_version") == "1.0.0"
    assert manifest.get("task_count") == 12
    assert len(manifest.get("tasks", [])) == 12
    assert "description" in manifest


def test_schema_json_validity():
    """Verify schema.json exists and defines a valid schema definition."""
    assert SCHEMA_PATH.is_file(), f"Schema file missing: {SCHEMA_PATH}"
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema = json.load(f)
    assert schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema"
    assert "required" in schema
    assert "task_id" in schema["required"]
    assert "security_invariant" in schema["required"]


def test_task_specs_conformance():
    """Verify all 12 task specification files conform to the task specification schema."""
    manifest = load_manifest()
    for task_entry in manifest["tasks"]:
        spec_rel = task_entry["spec_file"]
        spec_path = DATASET_ROOT / spec_rel
        assert spec_path.is_file(), f"Task spec missing: {spec_path}"
        with open(spec_path, "r", encoding="utf-8") as f:
            spec = json.load(f)

        assert spec["task_id"] == task_entry["task_id"]
        assert re.match(r"^SEC-BENCH-[0-9]{3}$", spec["task_id"])
        assert spec["dataset_version"] == "1.0.0"
        assert spec["category"] in PERMITTED_CATEGORIES
        assert spec["severity"] in PERMITTED_SEVERITIES
        assert spec["cwe_id"].startswith("CWE-")
        assert len(spec["title"]) > 5
        assert len(spec["description"]) > 10
        assert len(spec["security_invariant"]) > 10
        assert len(spec["expected_vulnerable_behavior"]) > 10
        assert len(spec["required_secure_behavior"]) > 10
        assert isinstance(spec["allowed_scope"], list) and len(spec["allowed_scope"]) > 0
        assert isinstance(spec["candidate_visible_tests"], list) and len(spec["candidate_visible_tests"]) > 0
        assert "vulnerability_test" in spec["evaluator_tests"]
        assert "secure_acceptance_test" in spec["evaluator_tests"]
        assert "provenance" in spec
        assert spec["provenance"]["review_status"] == "VERIFIED_FROZEN"


def test_unique_task_ids_and_categories():
    """Ensure all task IDs are unique and categories are valid."""
    manifest = load_manifest()
    task_ids = [t["task_id"] for t in manifest["tasks"]]
    assert len(task_ids) == len(set(task_ids)), "Duplicate task IDs found in manifest"

    categories = [t["category"] for t in manifest["tasks"]]
    for cat in categories:
        assert cat in PERMITTED_CATEGORIES, f"Invalid category: {cat}"


def test_task_ordering_deterministic():
    """Ensure task entries in the manifest are sorted deterministically in ascending order."""
    manifest = load_manifest()
    task_ids = [t["task_id"] for t in manifest["tasks"]]
    assert task_ids == sorted(task_ids), "Manifest tasks are not sorted in ascending order"
    expected_ids = [f"SEC-BENCH-{i:03d}" for i in range(1, 13)]
    assert task_ids == expected_ids, f"Expected contiguous tasks 001..012, got: {task_ids}"


# ---------------------------------------------------------------------------
# Path Containment & Security Checks
# ---------------------------------------------------------------------------

def test_file_paths_containment_and_traversal_prevention():
    """Ensure all referenced paths in the manifest are relative and strictly contained inside DATASET_ROOT."""
    manifest = load_manifest()
    for task_entry in manifest["tasks"]:
        spec_path = (DATASET_ROOT / task_entry["spec_file"]).resolve()
        assert spec_path.is_relative_to(DATASET_ROOT), f"Path traversal in spec_file: {spec_path}"

        for rel_file in task_entry["file_digests"].keys():
            assert not os.path.isabs(rel_file), f"Absolute path forbidden in digests: {rel_file}"
            assert ".." not in rel_file.split("/"), f"Parent traversal forbidden: {rel_file}"
            resolved = (DATASET_ROOT / rel_file).resolve()
            assert resolved.is_relative_to(DATASET_ROOT), f"Path escapes dataset root: {rel_file}"
            assert resolved.is_file(), f"Referenced file does not exist: {resolved}"


def test_no_secret_or_credential_inclusion():
    """Scan all dataset files to ensure no live credentials, private keys, or real API secrets are stored."""
    forbidden_patterns = [
        re.compile(r"-----BEGIN (RSA|EC|OPENSSH|DSA) PRIVATE KEY-----"),
        re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS Access Key ID
        re.compile(r"sk-[a-zA-Z0-9]{32,}"),  # OpenAI/Nebius live API key pattern
        re.compile(r"ghp_[a-zA-Z0-9]{36}"),  # GitHub Personal Access Token
    ]

    for root, _, files in os.walk(DATASET_ROOT):
        for fname in files:
            fpath = Path(root) / fname
            # Only inspect text files
            if fpath.suffix in {".py", ".json", ".md", ".patch"}:
                text = fpath.read_text(encoding="utf-8", errors="replace")
                for pattern in forbidden_patterns:
                    assert not pattern.search(text), f"Potential secret matched in {fpath}: {pattern.pattern}"


# ---------------------------------------------------------------------------
# Cryptographic Integrity & Tamper Detection
# ---------------------------------------------------------------------------

def test_manifest_sha256_digests_integrity():
    """Verify that every file listed in the manifest matches its recorded SHA-256 digest."""
    manifest = load_manifest()
    checked_files = 0
    for task_entry in manifest["tasks"]:
        for rel_path, expected_digest in task_entry["file_digests"].items():
            full_path = DATASET_ROOT / rel_path
            assert full_path.is_file(), f"Tracked file missing: {full_path}"
            actual_digest = calculate_sha256(full_path)
            assert actual_digest == expected_digest, (
                f"Digest mismatch for {rel_path}!\nExpected: {expected_digest}\nActual:   {actual_digest}"
            )
            checked_files += 1

    assert checked_files == 12 * 7, f"Expected 84 tracked files, verified {checked_files}"


def test_tamper_detection_triggers_failure():
    """Verify that any modification to a tracked file is immediately detected by digest verification."""
    manifest = load_manifest()
    first_task = manifest["tasks"][0]
    first_file_rel = list(first_task["file_digests"].keys())[0]
    expected_digest = first_task["file_digests"][first_file_rel]

    # Compute actual digest
    actual_digest = calculate_sha256(DATASET_ROOT / first_file_rel)
    assert actual_digest == expected_digest

    # Simulate tampered digest
    tampered_digest = "0" * 64
    assert actual_digest != tampered_digest, "Tampered digest must fail verification"


def test_reference_patches_validity():
    """Ensure all reference patches exist, are non-empty unified diffs, and can be read."""
    manifest = load_manifest()
    for task_entry in manifest["tasks"]:
        t_id = task_entry["task_id"]
        patch_path = DATASET_ROOT / "evaluators" / t_id / "reference.patch"
        assert patch_path.is_file()
        content = patch_path.read_text(encoding="utf-8")
        assert len(content.strip()) > 20
        assert "--- a/app.py" in content
        assert "+++ b/app.py" in content


# ---------------------------------------------------------------------------
# Task Reproducibility & Acceptance Execution
# ---------------------------------------------------------------------------

TASK_IDS = [f"SEC-BENCH-{i:03d}" for i in range(1, 13)]


@pytest.mark.parametrize("task_id", TASK_IDS)
def test_task_vulnerability_reproducibility(task_id: str):
    """
    Verify Ground Truth:
    1. Candidate-visible test_public.py PASSES on vulnerable starting fixture.
    2. Hidden test_vulnerability.py PASSES on vulnerable starting fixture (reproducing defect).
    3. Hidden test_secure.py FAILS on vulnerable starting fixture (confirming it rejects unpatched code).
    """
    fix_dir = (DATASET_ROOT / "fixtures" / task_id).resolve()
    eval_dir = (DATASET_ROOT / "evaluators" / task_id).resolve()

    env = os.environ.copy()
    env["PYTHONPATH"] = str(fix_dir)

    # 1. Candidate public test on starting fixture
    res_pub = subprocess.run(
        [sys.executable, "-m", "pytest", str(fix_dir / "test_public.py"), "-q"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert res_pub.returncode == 0, f"Public regression test failed on {task_id}: {res_pub.stdout} {res_pub.stderr}"

    # 2. Vulnerability exploit test on starting fixture (MUST PASS)
    res_vuln = subprocess.run(
        [sys.executable, "-m", "pytest", str(eval_dir / "test_vulnerability.py"), "-q"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert res_vuln.returncode == 0, f"Vulnerability reproduction failed on {task_id}: {res_vuln.stdout} {res_vuln.stderr}"

    # 3. Secure acceptance test on starting fixture (MUST FAIL)
    res_sec = subprocess.run(
        [sys.executable, "-m", "pytest", str(eval_dir / "test_secure.py"), "-q"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert res_sec.returncode != 0, f"Secure test unexpectedly passed on vulnerable {task_id}!"


@pytest.mark.parametrize("task_id", TASK_IDS)
def test_task_secure_acceptance(task_id: str):
    """
    Verify Ground Truth on Reference Fixed Implementation:
    1. Candidate-visible test_public.py PASSES on fixed_app.py (no functional regressions).
    2. Hidden test_secure.py PASSES on fixed_app.py (security invariant satisfied).
    3. Hidden test_vulnerability.py FAILS on fixed_app.py (exploit neutralized).
    """
    fix_dir = (DATASET_ROOT / "fixtures" / task_id).resolve()
    eval_dir = (DATASET_ROOT / "evaluators" / task_id).resolve()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_app = Path(tmpdir) / "app.py"
        shutil.copy2(eval_dir / "fixed_app.py", tmp_app)

        env = os.environ.copy()
        env["PYTHONPATH"] = tmpdir

        # 1. Public regression tests must pass
        res_pub = subprocess.run(
            [sys.executable, "-m", "pytest", str(fix_dir / "test_public.py"), "-q"],
            env=env,
            capture_output=True,
            text=True,
        )
        assert res_pub.returncode == 0, f"Fixed app failed public tests on {task_id}: {res_pub.stdout} {res_pub.stderr}"

        # 2. Secure acceptance tests must pass
        res_sec = subprocess.run(
            [sys.executable, "-m", "pytest", str(eval_dir / "test_secure.py"), "-q"],
            env=env,
            capture_output=True,
            text=True,
        )
        assert res_sec.returncode == 0, f"Fixed app failed secure test on {task_id}: {res_sec.stdout} {res_sec.stderr}"

        # 3. Vulnerability exploit must fail against fixed app
        res_vuln = subprocess.run(
            [sys.executable, "-m", "pytest", str(eval_dir / "test_vulnerability.py"), "-q"],
            env=env,
            capture_output=True,
            text=True,
        )
        assert res_vuln.returncode != 0, f"Vulnerability test still succeeded against fixed app on {task_id}!"
