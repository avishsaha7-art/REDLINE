import os
import shutil
import tempfile
import subprocess
import hashlib
from typing import Dict, Any, List
from backend.models.schemas import PatchCandidate
from backend.sandbox.models import SandboxPolicy, ExecutionRequest, ExecutionResult
from backend.sandbox.backend import SandboxBackend
from backend.sandbox.factory import get_sandbox_backend

from backend.sandbox.capabilities import RepositoryTrust, SecurityLevel
from backend.sandbox.workspace_sanitizer import workspace_copy_ignore, assert_and_clean_workspace_secrets

def _rmtree_readonly(path: str) -> None:
    def _onerror(func, p, exc_info):
        try:
            import stat
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except Exception:
            pass
    try:
        shutil.rmtree(path, onerror=_onerror)
    except Exception:
        shutil.rmtree(path, ignore_errors=True)

class SandboxClient:
    def __init__(self, policy: SandboxPolicy, repo_root: str, backend: SandboxBackend = None, repository_trust: RepositoryTrust = RepositoryTrust.UNTRUSTED):
        if isinstance(repository_trust, str):
            try:
                repository_trust = RepositoryTrust(repository_trust)
            except ValueError:
                repository_trust = RepositoryTrust.UNTRUSTED
        self.policy = policy
        self.repo_root = repo_root
        trust_arg = repository_trust.value if hasattr(repository_trust, "value") else str(repository_trust)
        self.backend = backend or get_sandbox_backend(policy, repository_trust=trust_arg)
        self.repository_trust = repository_trust
        
    def execute_patch(self, patch: PatchCandidate) -> Dict[str, Any]:
        """Legacy mock for Stage 7 compliance."""
        return {
            "status": "HANDOFF_SUCCESS",
            "patch_id": patch.patch_id,
            "sandbox_state": "READY"
        }

    def run_isolated(self, patch: PatchCandidate, test_command: List[str], run_id: str) -> ExecutionResult:
        # Execution Policy Check (Fail Closed)
        caps = self.backend.capabilities()
        trust_val = self.repository_trust.value if hasattr(self.repository_trust, "value") else str(self.repository_trust)
        if trust_val != RepositoryTrust.TRUSTED_DEVELOPMENT.value and caps.security_level != SecurityLevel.SECURE:
            return ExecutionResult(
                run_id=run_id,
                exit_code=-1,
                stdout="",
                stderr="POLICY_BLOCKED: Secure sandbox backend is required for non-TRUSTED_DEVELOPMENT repositories.",
                stdout_sha256=hashlib.sha256(b"").hexdigest(),
                stderr_sha256=hashlib.sha256(b"POLICY_BLOCKED: Secure sandbox backend is required for non-TRUSTED_DEVELOPMENT repositories.").hexdigest(),
                policy_blocked=True,
                backend_provenance={
                    "backend": type(self.backend).__name__,
                    "status": "OPERATIONAL_FAILURE",
                    "security_level": caps.security_level.value if hasattr(caps.security_level, "value") else str(caps.security_level),
                    "trust": trust_val,
                    "capabilities": caps.model_dump()
                }
            )

        if not (self.repo_root and os.path.isdir(self.repo_root)):
            err_msg = f"Repository root directory does not exist or is invalid: {self.repo_root}"
            return ExecutionResult(
                run_id=run_id,
                exit_code=-1,
                stdout="",
                stderr=err_msg,
                stdout_sha256=hashlib.sha256(b"").hexdigest(),
                stderr_sha256=hashlib.sha256(err_msg.encode()).hexdigest(),
                crashed=True,
                backend_provenance={
                    "backend": type(self.backend).__name__,
                    "status": "OPERATIONAL_FAILURE",
                    "reason": "INVALID_REPOSITORY_ROOT",
                    "security_level": caps.security_level.value if hasattr(caps.security_level, "value") else str(caps.security_level),
                    "trust": trust_val,
                    "capabilities": caps.model_dump()
                }
            )

        # 1. Create isolated workspace
        workspace = tempfile.mkdtemp(prefix="redline_sandbox_")
        try:
            # 2. Copy trusted repo snapshot to workspace (excluding secrets, credentials, VCS, caches)
            shutil.copytree(self.repo_root, workspace, dirs_exist_ok=True, ignore=workspace_copy_ignore)
            assert_and_clean_workspace_secrets(workspace)
            
            # 3. Apply patch
            if patch and patch.diff.strip():
                patch_file = os.path.join(workspace, "candidate.patch")
                diff_text = patch.diff if patch.diff.endswith("\n") else patch.diff + "\n"
                with open(patch_file, "w", newline="\n", encoding="utf-8") as f:
                    f.write(diff_text)
                
                # Apply using git apply. Ensure workspace is a git repo first to use git tools.
                try:
                    subprocess.run(["git", "init"], cwd=workspace, check=True, capture_output=True)
                    subprocess.run(["git", "config", "core.autocrlf", "false"], cwd=workspace, check=True, capture_output=True)
                    subprocess.run(["git", "add", "-A"], cwd=workspace, check=True, capture_output=True)
                    subprocess.run(["git", "apply", "candidate.patch"], cwd=workspace, check=True, capture_output=True)
                except subprocess.CalledProcessError as e:
                    return ExecutionResult(
                        run_id=run_id,
                        exit_code=-1,
                        stdout="",
                        stderr="Patch failed to apply:\n" + e.stderr.decode(errors='replace'),
                        stdout_sha256=hashlib.sha256(b"").hexdigest(),
                        stderr_sha256=hashlib.sha256(b"Patch failed to apply").hexdigest(),
                        timed_out=False,
                        crashed=True,
                        command_metadata=["git", "apply"],
                        backend_provenance={
                            "backend": type(self.backend).__name__,
                            "status": "PATCH_APPLY_FAILED",
                            "security_level": caps.security_level.value if hasattr(caps.security_level, "value") else str(caps.security_level),
                            "trust": trust_val,
                            "capabilities": caps.model_dump()
                        }
                    )
            
            # 4. Execute Trusted Command
            req = ExecutionRequest(
                command=test_command,
                working_directory=workspace,
                environment={}, # Clean environment isolated from host
                timeout_seconds=min(30, self.policy.max_runtime_seconds),
                repository_trust=trust_val
            )
            res = self.backend.execute(req, run_id)
            if not res.backend_provenance:
                res.backend_provenance = {}
            res.backend_provenance.update({
                "backend": type(self.backend).__name__,
                "security_level": caps.security_level.value if hasattr(caps.security_level, "value") else str(caps.security_level),
                "trust": trust_val,
                "capabilities": caps.model_dump()
            })
            return res
        finally:
            # 5. Clean up
            _rmtree_readonly(workspace)
