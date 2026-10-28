import os
import re
import ntpath
import posixpath
from backend.models.schemas import PatchCandidate, TaskContract

PROTECTED_FILES = [".github/workflows", "dockerfile", "docker-compose", ".env"]

def extract_paths_from_diff(diff: str) -> set:
    paths = set()
    has_valid_hunk = False
    
    lines = diff.splitlines()
    for line in lines:
        if line.startswith("+++ ") or line.startswith("--- "):
            path = line[4:].strip()
            path = path.split('\t')[0]  # Remove trailing timestamp if any
            if path == "/dev/null":
                continue
            
            # Git format prefixes
            if path.startswith("a/") or path.startswith("b/"):
                path = path[2:]
            elif path.startswith("a\\") or path.startswith("b\\"):
                path = path[2:]
                
            paths.add(path)
        elif re.match(r"^@@\s+-\d+(?:,\d+)?\s+\+\d+(?:,\d+)?\s+@@", line.strip()):
            has_valid_hunk = True

    if diff.strip() and not has_valid_hunk:
        raise ValueError("Malformed patch format: Missing hunks")
        
    return paths

def is_safe_path(path_str: str) -> bool:
    # Reject any form of traversal strings explicitly
    if ".." in path_str:
        return False
        
    # Check for drive letters or UNC paths using ntpath
    drive, _ = ntpath.splitdrive(path_str)
    if drive:
        return False
        
    # Also manually check C:/ or C:\ style explicitly to be ultra-safe
    if re.match(r"^[a-zA-Z]:", path_str):
        return False
        
    # Reject absolute paths
    if posixpath.isabs(path_str) or ntpath.isabs(path_str) or path_str.startswith("/") or path_str.startswith("\\"):
        return False
        
    # Normalize with mixed slashes handled
    # Convert all to forward slash
    unified_path = path_str.replace('\\', '/')
    normalized = posixpath.normpath(unified_path)
    
    if normalized.startswith("../") or normalized == ".." or posixpath.isabs(normalized):
        return False
        
    return True

def validate_patch(patch: PatchCandidate, task: TaskContract) -> bool:
    if patch.base_commit_or_snapshot != task.base_commit_or_snapshot:
        raise ValueError("Patch base snapshot does not match Task Contract")
        
    if len(patch.diff) > task.resource_budget.max_patch_size:
        raise ValueError("Patch size exceeds resource limits")
        
    if not patch.diff.strip():
        # Empty patch is okay if no files are changed
        actual_diff_paths = set()
    else:
        if not patch.diff.startswith("--- "):
            raise ValueError("Malformed patch format")
        if not any(l.startswith("+++ ") for l in patch.diff.splitlines()):
            raise ValueError("Malformed patch format: Missing target header")
        actual_diff_paths = extract_paths_from_diff(patch.diff)
        
    # Diff/Metadata mismatch
    declared_paths = set(patch.changed_files)
    if declared_paths != actual_diff_paths:
        raise ValueError(f"Metadata/diff mismatch. Declared: {declared_paths}, Actual: {actual_diff_paths}")

    # Validate each actual path
    for file in actual_diff_paths:
        if not is_safe_path(file):
            raise ValueError(f"Path traversal or absolute path detected in file: {file}")
            
        if task.allowed_scope and file not in task.allowed_scope:
            raise ValueError(f"Unauthorized file modification: {file}")
            
        file_lower = file.lower()
        for protected in PROTECTED_FILES:
            if protected.lower() in file_lower:
                raise ValueError(f"Protected-file modification attempted: {file}")

    return True
