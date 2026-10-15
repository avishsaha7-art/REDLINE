import os
import re
import hashlib
from typing import List, Dict, Any, Tuple
from pydantic import BaseModel, Field
from backend.models.schemas import TaskContract, ResourceBudget
from backend.verification.patch_validation import is_safe_path

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".exe", ".dll", ".so", ".bin", ".pyc", ".o", ".a"
}

def is_secret_file(filename: str) -> bool:
    name = filename.lower()
    if name == ".env" or name.startswith(".env."):
        return True
    if name.startswith("credentials") or name.startswith("secrets"):
        return True
    if "private_key" in name or name.endswith(".pem") or name.endswith(".key"):
        return True
    return False

def is_binary_file(filename: str, file_path: str) -> bool:
    _, ext = os.path.splitext(filename.lower())
    if ext in BINARY_EXTENSIONS:
        return True
    
    # Simple content check for null bytes to detect binaries without extensions
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(1024)
            if b"\x00" in chunk:
                return True
    except Exception:
        pass
        
    return False

class RepositorySnapshot(BaseModel):
    repository_id: str
    repo_root: str
    snapshot_hash: str
    file_manifest_hash: str
    ingestion_timestamp: float
    file_count: int
    total_accepted_bytes: int
    ingestion_policy_version: str = "v1"

class DiscoveredFile(BaseModel):
    relative_path: str
    size: int
    content: str
    file_hash: str

class IngestionResult(BaseModel):
    snapshot: RepositorySnapshot
    files: List[DiscoveredFile]
    excluded_files: List[Dict[str, str]]
    context_hash: str
    
    def to_untrusted_context_string(self, budget: ResourceBudget) -> str:
        context = []
        total_bytes = 0
        
        for file in self.files:
            file_str = f"--- {file.relative_path} ---\n{file.content}\n"
            file_bytes = len(file_str.encode('utf-8'))
            
            if total_bytes + file_bytes > budget.max_context_bytes:
                # We reached context limit
                break
                
            context.append(file_str)
            total_bytes += file_bytes
            
        return "".join(context)

def discover_repository(repo_root: str, task: TaskContract, timestamp: float) -> IngestionResult:
    budget = task.resource_budget
    
    discovered_files = []
    excluded_files = []
    
    total_accepted_bytes = 0
    file_count = 0
    
    # Collect all paths deterministically
    all_paths = []
    for root, dirs, files in os.walk(repo_root):
        # Exclude .git and heavy environment/dependency directories completely from recursion
        for skip_dir in (".git", "venv", "node_modules", ".next", "__pycache__", ".pytest_cache"):
            if skip_dir in dirs:
                dirs.remove(skip_dir)
            
        for file in files:
            full_path = os.path.join(root, file)
            # Ensure safe relative path
            try:
                rel_path = os.path.relpath(full_path, repo_root).replace('\\', '/')
            except ValueError:
                continue
            all_paths.append((rel_path, full_path))
            
    # Sort paths for determinism
    all_paths.sort(key=lambda x: x[0])
    
    for rel_path, full_path in all_paths:
        if file_count >= budget.max_repo_files:
            excluded_files.append({"path": rel_path, "reason": "max_repo_files_exceeded"})
            continue
            
        # 1. Path safety check
        if not is_safe_path(rel_path):
            excluded_files.append({"path": rel_path, "reason": "unsafe_path"})
            continue
            
        # 2. Symlink policy: Do not follow symlinks
        if os.path.islink(full_path):
            excluded_files.append({"path": rel_path, "reason": "symlink_skipped"})
            continue
            
        # 3. .git policy
        if ".git/" in rel_path or rel_path.startswith(".git"):
            excluded_files.append({"path": rel_path, "reason": "git_directory_excluded"})
            continue
            
        # 4. Secret handling
        if is_secret_file(os.path.basename(rel_path)):
            excluded_files.append({"path": rel_path, "reason": "secret_file_excluded"})
            continue
            
        # 5. File size limit
        try:
            size = os.path.getsize(full_path)
        except OSError:
            excluded_files.append({"path": rel_path, "reason": "unreadable"})
            continue
            
        if size > budget.max_file_size:
            excluded_files.append({"path": rel_path, "reason": "file_too_large"})
            continue
            
        if total_accepted_bytes + size > budget.max_repo_bytes:
            excluded_files.append({"path": rel_path, "reason": "max_repo_bytes_exceeded"})
            continue
            
        # 6. Binary file handling
        if is_binary_file(os.path.basename(rel_path), full_path):
            excluded_files.append({"path": rel_path, "reason": "binary_file_excluded"})
            continue
            
        # Read content safely
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            excluded_files.append({"path": rel_path, "reason": "unicode_decode_error"})
            continue
        except Exception:
            excluded_files.append({"path": rel_path, "reason": "read_error"})
            continue
            
        # Accept file
        file_bytes = len(content.encode('utf-8'))
        file_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
        
        discovered_files.append(DiscoveredFile(
            relative_path=rel_path,
            size=file_bytes,
            content=content,
            file_hash=file_hash
        ))
        
        file_count += 1
        total_accepted_bytes += file_bytes

    # Deterministic Context Selection for MVP: Task mentioned files first, then alphabetical
    # Sort files: task.allowed_scope files first, then the rest
    allowed_scope_set = set(task.allowed_scope or [])
    discovered_files.sort(key=lambda f: (
        0 if f.relative_path in allowed_scope_set else 1,
        f.relative_path
    ))
    
    # Calculate hashes
    manifest_str = ",".join(f.relative_path for f in discovered_files)
    file_manifest_hash = hashlib.sha256(manifest_str.encode('utf-8')).hexdigest()
    
    snapshot_str = ",".join(f"{f.relative_path}:{f.file_hash}" for f in discovered_files)
    snapshot_hash = hashlib.sha256(snapshot_str.encode('utf-8')).hexdigest()
    
    context_str = ",".join(f.file_hash for f in discovered_files)
    context_hash = hashlib.sha256(context_str.encode('utf-8')).hexdigest()
    
    snapshot = RepositorySnapshot(
        repository_id=task.repository_id,
        repo_root=repo_root,
        snapshot_hash=snapshot_hash,
        file_manifest_hash=file_manifest_hash,
        ingestion_timestamp=timestamp,
        file_count=file_count,
        total_accepted_bytes=total_accepted_bytes
    )
    
    return IngestionResult(
        snapshot=snapshot,
        files=discovered_files,
        excluded_files=excluded_files,
        context_hash=context_hash
    )
