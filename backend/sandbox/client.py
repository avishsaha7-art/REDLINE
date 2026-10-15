import os
import shutil
import tempfile
import subprocess
import hashlib
from typing import Dict, Any, List
from backend.models.schemas import PatchCandidate
from backend.sandbox.models import SandboxPolicy, ExecutionRequest, ExecutionResult
from backend.sandbox.backend import SandboxBackend, LocalDevelopmentBackend

from backend.sandbox.capabilities import RepositoryTrust, SecurityLevel

class SandboxClient:
    def __init__(self, policy: SandboxPolicy, repo_root: str, backend: SandboxBackend = None, repository_trust: RepositoryTrust = RepositoryTrust.UNTRUSTED):
        self.policy = policy
        self.repo_root = repo_root
        self.backend = backend or LocalDevelopmentBackend(policy)
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
        if self.repository_trust != RepositoryTrust.TRUSTED_DEVELOPMENT and caps.security_level != SecurityLevel.SECURE:
            return ExecutionResult(
                run_id=run_id,
                exit_code=-1,
                stdout="",
                stderr="POLICY_BLOCKED: Secure sandbox backend is required for non-TRUSTED_DEVELOPMENT repositories.",
                stdout_sha256=hashlib.sha256(b"").hexdigest(),
                stderr_sha256=hashlib.sha256(b"POLICY_BLOCKED: Secure sandbox backend is required for non-TRUSTED_DEVELOPMENT repositories.").hexdigest(),
                policy_blocked=True,
                backend_provenance={
                    "security_level": caps.security_level,
                    "trust": self.repository_trust,
                    "capabilities": caps.model_dump()
                }
            )

        # 1. Create isolated workspace
        workspace = tempfile.mkdtemp(prefix="redline_sandbox_")
        try:
            # 2. Copy trusted repo snapshot to workspace (ignoring heavy/hidden dirs to speed up testing)
            shutil.copytree(self.repo_root, workspace, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git", "venv", "__pycache__", ".pytest_cache"))
            
            # 3. Apply patch
            if patch.diff.strip():
                patch_file = os.path.join(workspace, "candidate.patch")
                with open(patch_file, "w", encoding="utf-8") as f:
                    f.write(patch.diff)
                
                # Apply using git apply. Ensure workspace is a git repo first to use git tools.
                try:
                    subprocess.run(["git", "init"], cwd=workspace, check=True, capture_output=True)
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
                            "security_level": caps.security_level,
                            "trust": self.repository_trust,
                            "capabilities": caps.model_dump()
                        }
                    )
            
            # 4. Execute Trusted Command
            req = ExecutionRequest(
                command=test_command,
                working_directory=workspace,
                environment={}, # Clean environment isolated from host
                timeout_seconds=min(30, self.policy.max_runtime_seconds),
                repository_trust=self.repository_trust.value
            )
            res = self.backend.execute(req, run_id)
            res.backend_provenance = {
                "security_level": caps.security_level,
                "trust": self.repository_trust,
                "capabilities": caps.model_dump()
            }
            return res
        finally:
            # 5. Clean up
            shutil.rmtree(workspace, ignore_errors=True)
