"""
Dataset Commit Anchoring & Cryptographic Integrity Verification Engine.

Enforces cryptographic trust anchors for Stage P2-3 and REDLINE Benchmark Dataset v1.0.0.
Verifies:
1. Git commit anchor existence and ancestry in repository history.
2. Annotated tag existence, tag object type ('tag'), and target commit match.
3. Cleanliness of the dataset working tree (strict detection of modified or unexpected untracked files).
4. Manifest raw-byte SHA-256 digest match against immutable anchor.
5. All 84 registered artifact SHA-256 digests against manifest entries.
6. Path containment: zero absolute paths, zero parent traversals ('..').
7. Symlink safety: rejects symlinks escaping the dataset root boundary.
8. Fail-closed guarantee: any failure, exception, or partial verification leaves status != 'VERIFIED'.
"""

import os
import sys
import json
import hashlib
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from pydantic import BaseModel, Field


# Canonical Frozen Trust Anchors for Stage P2-3
DEFAULT_TRUSTED_ANCHOR: Dict[str, Any] = {
    "dataset_name": "REDLINE-Held-Out-Security-Benchmark",
    "dataset_version": "1.0.0",
    "dataset_commit_sha": "6e476bccaba2187055254d1cd71b539d7903b34f",
    "dataset_tag": "benchmark-v1.0.0",
    "manifest_root_sha256": "d2cd37b9a588151975c992426338b0341f39bc824e1627c32d51e02ed1ac20c2",
    "task_count": 12,
    "total_artifacts": 84,
}


# Custom Exception Hierarchy
class BenchmarkIntegrityError(Exception):
    """Base exception for all benchmark integrity verification failures."""
    pass


class AnchorVerificationError(BenchmarkIntegrityError):
    """Raised when Git commit, tag, or repository metadata verification fails."""
    pass


class WorkingTreeIntegrityError(BenchmarkIntegrityError):
    """Raised when working tree contains modified tracked files or unexpected untracked dataset files."""
    pass


class ManifestVerificationError(BenchmarkIntegrityError):
    """Raised when manifest file is missing, malformed, or fails root SHA-256 validation."""
    pass


class ArtifactVerificationError(BenchmarkIntegrityError):
    """Raised when artifact files are missing, tampered with, or violate path/symlink safety."""
    pass


class IntegrityVerificationResult(BaseModel):
    """Structured report of integrity verification."""
    status: str = "INCOMPLETE"  # Starts INCOMPLETE; only becomes VERIFIED when all stages pass
    dataset_name: str = ""
    dataset_version: str = ""
    commit_sha: str = ""
    tag_name: str = ""
    manifest_sha256: str = ""
    tasks_verified: int = 0
    artifacts_verified: int = 0
    checks_passed: List[str] = Field(default_factory=list)
    failure_reason: Optional[str] = None
    verification_metadata: Dict[str, Any] = Field(default_factory=dict)


class BenchmarkIntegrityChecker:
    """
    Authoritative verifier for the REDLINE benchmark dataset integrity.
    Operates fail-closed; never returns VERIFIED if any check fails or is interrupted.
    """

    def __init__(
        self,
        repo_root: Optional[str] = None,
        dataset_root: Optional[str] = None,
        anchor_config: Optional[Dict[str, Any]] = None,
        strict_working_tree: bool = True
    ):
        self.repo_root = os.path.abspath(repo_root or os.environ.get("REDLINE_REPO_ROOT", os.getcwd()))
        if dataset_root:
            self.dataset_root = os.path.abspath(dataset_root)
        else:
            self.dataset_root = os.path.abspath(os.path.join(self.repo_root, "backend", "benchmark", "dataset"))
        self.anchor = dict(DEFAULT_TRUSTED_ANCHOR)
        if anchor_config:
            self.anchor.update(anchor_config)
        self.strict_working_tree = strict_working_tree

    def _run_git_cmd(self, args: List[str]) -> Tuple[int, str, str]:
        """Executes a git command anchored to repo_root."""
        try:
            proc = subprocess.run(
                ["git", "-C", self.repo_root] + args,
                capture_output=True,
                text=True,
                timeout=15
            )
            return proc.returncode, proc.stdout, proc.stderr.strip()
        except FileNotFoundError:
            raise AnchorVerificationError("Git executable not found on system PATH")
        except Exception as e:
            raise AnchorVerificationError(f"Git command failed to execute: {str(e)}")

    def verify_git_anchor(self) -> Dict[str, Any]:
        """
        Verifies Git repository metadata, commit ancestry, tag object type, and target commit.
        """
        # 1. Confirm inside a git work tree
        rc, out, err = self._run_git_cmd(["rev-parse", "--is-inside-work-tree"])
        if rc != 0 or out.strip() != "true":
            raise AnchorVerificationError(f"Directory is not a valid Git work tree: {self.repo_root}. Error: {err}")

        expected_commit = self.anchor["dataset_commit_sha"].lower()
        expected_tag = self.anchor["dataset_tag"]

        # 2. Check commit exists in object database
        rc, out, err = self._run_git_cmd(["cat-file", "-e", f"{expected_commit}^{{commit}}"])
        if rc != 0:
            raise AnchorVerificationError(f"Anchor commit '{expected_commit}' does not exist in repository. Error: {err}")

        # 3. Check commit is an ancestor of HEAD (or is HEAD)
        rc, out, err = self._run_git_cmd(["merge-base", "--is-ancestor", expected_commit, "HEAD"])
        if rc != 0:
            raise AnchorVerificationError(
                f"Anchor commit '{expected_commit}' is not an ancestor of current HEAD. Error: {err}"
            )

        # 4. Check tag exists and query its object type
        rc, tag_type, err = self._run_git_cmd(["cat-file", "-t", f"refs/tags/{expected_tag}"])
        if rc != 0:
            raise AnchorVerificationError(f"Anchor tag '{expected_tag}' not found in refs/tags/. Error: {err}")

        tag_type = tag_type.strip()
        # Strict check: tag must be an annotated tag object ('tag'), NOT a lightweight tag ('commit')
        if tag_type != "tag":
            raise AnchorVerificationError(
                f"Anchor tag '{expected_tag}' is a lightweight tag (type '{tag_type}'). "
                "REDLINE requires an annotated tag object ('tag') for immutable provenance."
            )

        # 5. Check tag resolves to the expected dataset commit
        rc, tag_target_commit, err = self._run_git_cmd(["rev-parse", f"refs/tags/{expected_tag}^{{commit}}"])
        if rc != 0:
            raise AnchorVerificationError(f"Failed to resolve target commit for tag '{expected_tag}': {err}")

        tag_target_commit = tag_target_commit.strip().lower()
        if tag_target_commit != expected_commit:
            raise AnchorVerificationError(
                f"Anchor tag '{expected_tag}' target commit mismatch: "
                f"expected '{expected_commit}', got '{tag_target_commit}'"
            )

        return {
            "verified_commit": expected_commit,
            "verified_tag": expected_tag,
            "tag_object_type": tag_type,
            "tag_target_commit": tag_target_commit,
        }

    def verify_working_tree_cleanliness(self) -> Dict[str, Any]:
        """
        Verifies that the dataset directory contains no modified tracked files
        and, in strict mode, no unexpected untracked files.
        """
        # Compute path of dataset relative to repo_root
        try:
            rel_dataset = os.path.relpath(self.dataset_root, self.repo_root)
        except ValueError:
            rel_dataset = self.dataset_root

        # Query git status on the dataset path
        cmd = ["status", "--porcelain=v1"]
        if self.strict_working_tree:
            cmd.append("-uall")
        cmd.extend(["--", rel_dataset])

        rc, out, err = self._run_git_cmd(cmd)
        if rc != 0:
            raise WorkingTreeIntegrityError(f"Failed to query git status for dataset: {err}")

        modified_tracked = []
        untracked = []

        if out:
            for line in out.splitlines():
                if not line.strip():
                    continue
                status_code = line[:2]
                file_path = line[3:].strip()
                if "?" in status_code:
                    untracked.append(file_path)
                else:
                    modified_tracked.append((status_code.strip(), file_path))

        if modified_tracked:
            raise WorkingTreeIntegrityError(
                f"Dataset working tree contains modified tracked files: {modified_tracked}"
            )

        if self.strict_working_tree and untracked:
            raise WorkingTreeIntegrityError(
                f"Dataset working tree contains unexpected untracked files in strict mode: {untracked}"
            )

        return {
            "clean": True,
            "strict_mode": self.strict_working_tree,
            "dataset_rel_path": rel_dataset,
        }

    def verify_manifest(self) -> Tuple[bytes, Dict[str, Any]]:
        """
        Reads manifest.json raw bytes, computes its SHA-256 digest, validates against anchor,
        and parses JSON structure.
        """
        manifest_path = os.path.join(self.dataset_root, "manifest.json")
        if not os.path.isfile(manifest_path):
            raise ManifestVerificationError(f"manifest.json missing at {manifest_path}")

        try:
            with open(manifest_path, "rb") as f:
                raw_bytes = f.read()
        except Exception as e:
            raise ManifestVerificationError(f"Failed to read manifest.json: {str(e)}")

        actual_digest = hashlib.sha256(raw_bytes).hexdigest().lower()
        expected_digest = self.anchor["manifest_root_sha256"].lower()

        if actual_digest != expected_digest:
            raise ManifestVerificationError(
                f"manifest.json raw-byte SHA-256 digest mismatch: "
                f"expected '{expected_digest}', got '{actual_digest}'"
            )

        try:
            manifest = json.loads(raw_bytes.decode("utf-8"))
        except Exception as e:
            raise ManifestVerificationError(f"manifest.json is malformed JSON: {str(e)}")

        # Validate top-level metadata
        if manifest.get("dataset_name") != self.anchor["dataset_name"]:
            raise ManifestVerificationError(
                f"Manifest dataset_name mismatch: expected '{self.anchor['dataset_name']}', "
                f"got '{manifest.get('dataset_name')}'"
            )

        if manifest.get("dataset_version") != self.anchor["dataset_version"]:
            raise ManifestVerificationError(
                f"Manifest dataset_version mismatch: expected '{self.anchor['dataset_version']}', "
                f"got '{manifest.get('dataset_version')}'"
            )

        tasks = manifest.get("tasks")
        if not isinstance(tasks, list) or len(tasks) != self.anchor["task_count"]:
            raise ManifestVerificationError(
                f"Manifest task count mismatch: expected {self.anchor['task_count']}, "
                f"got {len(tasks) if isinstance(tasks, list) else 'invalid'}"
            )

        return raw_bytes, manifest

    def verify_artifact_digests_and_paths(self, manifest: Dict[str, Any]) -> int:
        """
        Verifies all declared artifact file paths, directory confinement,
        symlink safety, and SHA-256 digests.
        """
        tasks = manifest.get("tasks", [])
        dataset_path_obj = Path(self.dataset_root).resolve()
        total_artifacts_verified = 0

        for task_entry in tasks:
            task_id = task_entry.get("task_id", "UNKNOWN")
            file_digests = task_entry.get("file_digests")
            if not isinstance(file_digests, dict) or not file_digests:
                raise ArtifactVerificationError(f"Task '{task_id}' has missing or empty file_digests")

            for rel_file, expected_hash in file_digests.items():
                total_artifacts_verified += 1

                # 1. Path Safety & Traversal checks
                norm_rel = rel_file.replace("\\", "/")
                if os.path.isabs(rel_file) or norm_rel.startswith("/"):
                    raise ArtifactVerificationError(f"Absolute path forbidden in manifest: {rel_file}")

                parts = norm_rel.split("/")
                if ".." in parts:
                    raise ArtifactVerificationError(f"Parent directory traversal '..' forbidden in path: {rel_file}")

                full_path = os.path.normpath(os.path.join(self.dataset_root, rel_file))

                # 2. Symlink Escape check
                if os.path.islink(full_path):
                    resolved_link = os.path.realpath(full_path)
                    try:
                        is_safe_link = Path(resolved_link).resolve().is_relative_to(dataset_path_obj)
                    except AttributeError:
                        is_safe_link = os.path.commonpath([Path(resolved_link).resolve(), dataset_path_obj]) == str(dataset_path_obj)
                    if not is_safe_link:
                        raise ArtifactVerificationError(
                            f"Symlink escape detected: '{rel_file}' points outside dataset root ({resolved_link})"
                        )

                # 3. Path Containment check
                try:
                    full_path_obj = Path(full_path)
                    if not full_path_obj.resolve().is_relative_to(dataset_path_obj):
                        raise ArtifactVerificationError(f"Path escapes dataset root boundary: {rel_file}")
                except AttributeError:
                    # Fallback for Python < 3.9 (is_relative_to)
                    common = os.path.commonpath([full_path_obj.resolve(), dataset_path_obj])
                    if common != str(dataset_path_obj):
                        raise ArtifactVerificationError(f"Path escapes dataset root boundary: {rel_file}")

                # 4. Existence check
                if not os.path.isfile(full_path):
                    raise ArtifactVerificationError(f"Artifact file missing from disk: {rel_file} (path: {full_path})")

                # 5. SHA-256 Digest Recomputation
                try:
                    hasher = hashlib.sha256()
                    with open(full_path, "rb") as af:
                        while chunk := af.read(65536):
                            hasher.update(chunk)
                    actual_hash = hasher.hexdigest().lower()
                except Exception as e:
                    raise ArtifactVerificationError(f"Failed to read artifact '{rel_file}': {str(e)}")

                if actual_hash != expected_hash.lower():
                    raise ArtifactVerificationError(
                        f"Cryptographic digest mismatch for artifact '{rel_file}': "
                        f"expected '{expected_hash}', got '{actual_hash}'"
                    )

        expected_total = self.anchor["total_artifacts"]
        if total_artifacts_verified != expected_total:
            raise ArtifactVerificationError(
                f"Total artifact count mismatch: expected {expected_total}, verified {total_artifacts_verified}"
            )

        return total_artifacts_verified

    def verify_all(self) -> IntegrityVerificationResult:
        """
        Executes complete verification pipeline.
        Fail-Closed: if any check fails, returns status='FAILED' with reason,
        or raises BenchmarkIntegrityError.
        Status only becomes 'VERIFIED' when all stages succeed.
        """
        result = IntegrityVerificationResult(status="INCOMPLETE")

        try:
            # Stage 1: Git Trust Anchor
            git_meta = self.verify_git_anchor()
            result.checks_passed.append("GIT_ANCHOR_VERIFIED")
            result.commit_sha = git_meta["verified_commit"]
            result.tag_name = git_meta["verified_tag"]

            # Stage 2: Working Tree Cleanliness
            wt_meta = self.verify_working_tree_cleanliness()
            result.checks_passed.append("WORKING_TREE_CLEAN")

            # Stage 3: Manifest Raw-Byte Digest
            raw_bytes, manifest = self.verify_manifest()
            result.checks_passed.append("MANIFEST_RAW_BYTE_DIGEST_VERIFIED")
            result.manifest_sha256 = hashlib.sha256(raw_bytes).hexdigest().lower()
            result.dataset_name = manifest["dataset_name"]
            result.dataset_version = manifest["dataset_version"]

            # Stage 4: Artifact Digests, Containment, Symlink Safety
            verified_count = self.verify_artifact_digests_and_paths(manifest)
            result.checks_passed.append("ALL_ARTIFACT_DIGESTS_VERIFIED")
            result.tasks_verified = len(manifest["tasks"])
            result.artifacts_verified = verified_count

            # Final Seal: Only assign VERIFIED when all stages are complete
            result.status = "VERIFIED"
            result.verification_metadata = {
                "git": git_meta,
                "working_tree": wt_meta,
                "total_checks": len(result.checks_passed)
            }
            return result

        except Exception as e:
            result.status = "FAILED"
            result.failure_reason = str(e)
            raise


def verify_dataset_anchor(
    repo_root: Optional[str] = None,
    dataset_root: Optional[str] = None,
    anchor_config: Optional[Dict[str, Any]] = None,
    strict_working_tree: bool = True
) -> IntegrityVerificationResult:
    """Convenience functional wrapper for BenchmarkIntegrityChecker."""
    checker = BenchmarkIntegrityChecker(
        repo_root=repo_root,
        dataset_root=dataset_root,
        anchor_config=anchor_config,
        strict_working_tree=strict_working_tree
    )
    return checker.verify_all()
