"""
Workspace Sanitizer for REDLINE Sandbox Execution.
Enforces strict secret and credential exclusion from candidate workspaces.
"""
import os
import fnmatch
from typing import Set, List, Sequence

# Patterns matching secret and credential files that must never enter a candidate workspace
SECRET_FILE_PATTERNS: Sequence[str] = (
    ".env",
    ".env.*",
    "*.env",
    "*secret*",
    "*credential*",
    "*private_key*",
    "*.pem",
    "*.key",
    "*.pfx",
    "*.pkcs12",
    "id_rsa*",
    "id_ed25519*",
    "*.token",
)

# VCS, cache, and virtual environment directories
CACHE_AND_VCS_PATTERNS: Sequence[str] = (
    ".git",
    "venv",
    ".venv",
    "__pycache__",
    ".pytest_cache",
)

EXCLUDED_PATTERNS: Sequence[str] = tuple(list(SECRET_FILE_PATTERNS) + list(CACHE_AND_VCS_PATTERNS))


def is_secret_file(filename: str) -> bool:
    """Returns True if the filename matches any known secret or credential pattern."""
    lower_name = filename.lower()
    return any(fnmatch.fnmatch(lower_name, pattern) for pattern in SECRET_FILE_PATTERNS)


def workspace_copy_ignore(directory: str, files: List[str]) -> Set[str]:
    """
    shutil.copytree ignore callable that excludes all secrets, credentials,
    VCS metadata, caches, and virtual environments.
    """
    ignored = set()
    for f in files:
        lower_f = f.lower()
        if any(fnmatch.fnmatch(lower_f, p) for p in EXCLUDED_PATTERNS):
            ignored.add(f)
    return ignored


def assert_and_clean_workspace_secrets(workspace_dir: str) -> None:
    """
    Post-copy security sweep of the candidate workspace.
    Verifies that no excluded secret files entered the workspace.
    If any secret file is detected, removes it immediately and raises a RuntimeError.
    """
    found_secrets = []
    for root, dirs, files in os.walk(workspace_dir):
        for f in files:
            if is_secret_file(f):
                bad_path = os.path.join(root, f)
                found_secrets.append(bad_path)
                try:
                    os.remove(bad_path)
                except Exception:
                    pass

    if found_secrets:
        raise RuntimeError(
            f"SECURITY_VIOLATION: Secret or credential files were detected in candidate workspace: {found_secrets}. "
            "Files were removed and workspace initialization aborted."
        )
