import os
import re
import shutil
import hashlib
import uuid
import datetime
from typing import List, Tuple, Optional, Set
from pydantic import BaseModel

from backend.sandbox.capabilities import RepositoryTrust
from backend.models.schemas import ResourceBudget
from backend.models.projects import ProjectFile, ProjectRecord
from backend.sandbox.registry import get_repository_registry, RepositoryTarget
from backend.storage.project_repository import get_project_repository
from backend.sandbox.cloner import calculate_workspace_digests, _rmtree_readonly


EXCLUDED_DIR_PATTERNS = {
    ".git",
    ".baseline",
    "node_modules",
    "venv",
    ".venv",
    "env",
    ".env",
    "__pycache__",
    ".pytest_cache",
    ".next",
    "dist",
    "build",
    ".idea",
    ".vscode",
    "coverage",
    ".tox",
}

EXCLUDED_FILE_PATTERNS = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    "id_rsa",
    "id_ed25519",
    "id_ecdsa",
    "credentials.json",
}

EXCLUDED_EXTENSIONS = {
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".pyc",
    ".pyo",
}


class LocalImportError(Exception):
    """Base exception for local project import errors."""
    pass


class LocalImportSecurityError(LocalImportError):
    """Raised when path traversal, escaping project root, or banned files are detected."""
    pass


class LocalImportResourceLimitError(LocalImportError):
    """Raised when file count, file size, or total project size limits are exceeded."""
    pass


def sanitize_and_validate_relative_path(raw_path: str) -> str:
    """
    Strictly validates and normalizes a relative file path within an imported project.
    Rejects:
    - Path traversal sequences (../, ..\\)
    - Absolute paths (/foo, \\foo, C:\\foo)
    - Null bytes (\0)
    - Drive letters or stream colons (:)
    - Empty or whitespace paths
    Returns a normalized posix relative path (e.g. 'src/main.py').
    """
    if not raw_path or not isinstance(raw_path, str):
        raise LocalImportSecurityError("Relative file path must be a non-empty string.")

    cleaned = raw_path.strip().replace("\\", "/")

    if "\0" in cleaned:
        raise LocalImportSecurityError("Path contains null byte.")

    if ":" in cleaned:
        raise LocalImportSecurityError(f"Drive colon or stream specifier forbidden in relative path '{raw_path}'.")

    if cleaned.startswith("/"):
        raise LocalImportSecurityError(f"Absolute path '{raw_path}' is prohibited. Must be a relative path.")

    # Remove leading './' if present
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]

    parts = cleaned.split("/")
    normalized_parts = []

    for part in parts:
        part = part.strip()
        if not part or part == ".":
            continue
        if part == "..":
            raise LocalImportSecurityError(f"Path traversal ('..') detected in relative path '{raw_path}'.")
        normalized_parts.append(part)

    if not normalized_parts:
        raise LocalImportSecurityError("Relative path resolves to empty root.")

    normalized_path = "/".join(normalized_parts)

    # Double check for banned directory segments
    for part in normalized_parts:
        if part in EXCLUDED_DIR_PATTERNS:
            raise LocalImportSecurityError(
                f"Path '{normalized_path}' includes prohibited/excluded directory '{part}'."
            )

    filename = normalized_parts[-1]
    if filename in EXCLUDED_FILE_PATTERNS:
        raise LocalImportSecurityError(f"Prohibited sensitive file name '{filename}' in path '{normalized_path}'.")

    ext = os.path.splitext(filename)[1].lower()
    if ext in EXCLUDED_EXTENSIONS:
        raise LocalImportSecurityError(f"Prohibited file extension '{ext}' in path '{normalized_path}'.")

    return normalized_path


def is_path_excluded(raw_path: str) -> bool:
    """
    Returns True if a relative path belongs to generated, cached, or secret files
    that should be silently filtered out during directory import.
    """
    if not raw_path:
        return True
    norm = raw_path.strip().replace("\\", "/")
    parts = norm.split("/")
    for part in parts:
        part_clean = part.strip().lower()
        if part_clean in EXCLUDED_DIR_PATTERNS:
            return True
    filename = parts[-1].strip().lower()
    if filename in EXCLUDED_FILE_PATTERNS:
        return True
    ext = os.path.splitext(filename)[1].lower()
    if ext in EXCLUDED_EXTENSIONS:
        return True
    return False


class LocalProjectImporter:
    """
    Authoritative Local Project Importer.
    Validates, sanitizes, and stages user project code into a managed workspace under data/projects/.
    Enforces deterministic snapshot calculation, strict UNTRUSTED trust tier, and fail-closed security.
    """
    def __init__(self, projects_base: Optional[str] = None):
        if projects_base:
            self.projects_base = os.path.abspath(projects_base)
        else:
            self.projects_base = os.path.abspath(os.path.join("data", "projects"))
        os.makedirs(self.projects_base, exist_ok=True)

    def import_project(
        self,
        name: str,
        files: List[ProjectFile],
        budget: Optional[ResourceBudget] = None,
    ) -> ProjectRecord:
        """
        Imports and validates a local project workspace from structured files.
        """
        effective_budget = budget or ResourceBudget()
        clean_name = (name or "Untitled Project").strip()
        if len(clean_name) > 128:
            clean_name = clean_name[:128]

        # Generate unique project ID
        project_id = f"project-{uuid.uuid4().hex[:12]}"
        project_dir = os.path.join(self.projects_base, project_id)
        baseline_dir = os.path.join(project_dir, ".baseline")

        if os.path.exists(project_dir):
            _rmtree_readonly(project_dir)

        os.makedirs(project_dir, exist_ok=True)
        os.makedirs(baseline_dir, exist_ok=True)

        accepted_files: List[Tuple[str, bytes]] = []
        total_bytes = 0

        try:
            for file_entry in files:
                # If path should be filtered, skip
                if is_path_excluded(file_entry.path):
                    continue

                # Validate and normalize
                norm_rel_path = sanitize_and_validate_relative_path(file_entry.path)

                content_bytes = (
                    file_entry.content.encode("utf-8")
                    if file_entry.content is not None
                    else b""
                )
                file_size = len(content_bytes)

                if file_size > effective_budget.max_file_size:
                    raise LocalImportResourceLimitError(
                        f"File '{norm_rel_path}' size ({file_size} bytes) exceeds max_file_size limit ({effective_budget.max_file_size} bytes)."
                    )

                total_bytes += file_size
                if total_bytes > effective_budget.max_repo_bytes:
                    raise LocalImportResourceLimitError(
                        f"Total project size exceeds max_repo_bytes limit ({total_bytes} bytes > {effective_budget.max_repo_bytes} bytes)."
                    )

                accepted_files.append((norm_rel_path, content_bytes))

                if len(accepted_files) > effective_budget.max_repo_files:
                    raise LocalImportResourceLimitError(
                        f"Project exceeds max_repo_files limit ({len(accepted_files)} files > {effective_budget.max_repo_files} limit)."
                    )

            if not accepted_files:
                raise LocalImportError("No valid, non-excluded source files were provided for project import.")

            # Write files to project_dir and baseline_dir
            for rel_path, content_bytes in accepted_files:
                dest_path = os.path.join(project_dir, rel_path)
                base_path = os.path.join(baseline_dir, rel_path)

                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                os.makedirs(os.path.dirname(base_path), exist_ok=True)

                with open(dest_path, "wb") as f:
                    f.write(content_bytes)
                with open(base_path, "wb") as f:
                    f.write(content_bytes)

            # Calculate deterministic digests
            snapshot_hash, file_manifest_hash = calculate_workspace_digests(project_dir)

            record = ProjectRecord(
                project_id=project_id,
                name=clean_name,
                root_path=os.path.abspath(project_dir),
                trust=RepositoryTrust.UNTRUSTED.value,
                snapshot_hash=snapshot_hash,
                file_manifest_hash=file_manifest_hash,
                file_count=len(accepted_files),
                total_bytes=total_bytes,
                created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                updated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            )

            # Register in authoritative RepositoryRegistry for orchestrator execution
            target = RepositoryTarget(
                repository_id=project_id,
                repo_root=os.path.abspath(project_dir),
                trust=RepositoryTrust.UNTRUSTED,
                snapshot_hash=snapshot_hash,
                file_manifest_hash=file_manifest_hash,
                file_count=len(accepted_files),
                total_bytes=total_bytes,
                is_quarantined=True,
                registered_at=record.created_at,
            )
            get_repository_registry().register(target)

            # Persist in SQLite
            get_project_repository().create_project(record)

            return record

        except Exception:
            # Clean up on failure (fail closed)
            if os.path.exists(project_dir):
                _rmtree_readonly(project_dir)
            raise
