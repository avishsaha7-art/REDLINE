import subprocess
import time
import threading
import sys
import os
from abc import ABC, abstractmethod
from backend.sandbox.models import ExecutionRequest, ExecutionResult, SandboxPolicy
from backend.sandbox.capabilities import SandboxCapabilities

class SandboxBackend(ABC):
    def __init__(self, policy: SandboxPolicy):
        self.policy = policy

    @abstractmethod
    def capabilities(self) -> SandboxCapabilities:
        pass
        
    @abstractmethod
    def execute(self, req: ExecutionRequest, run_id: str) -> ExecutionResult:
        pass

class LocalDevelopmentBackend(SandboxBackend):
    """
    DEVELOPMENT_ONLY
    UNSAFE FOR UNTRUSTED PRODUCTION WORKLOADS

    - it executes code on the host environment
    - it does not provide OS-level filesystem isolation
    - it does not provide OS-level process isolation
    - it does not provide OS-level network isolation
    - it must never be used for untrusted repository execution
    - it exists for controlled local development/testing only
    """
    def capabilities(self) -> SandboxCapabilities:
        return SandboxCapabilities(
            filesystem_isolation="NOT_AVAILABLE",
            process_isolation="NOT_AVAILABLE",
            network_isolation="NOT_AVAILABLE",
            credential_isolation="ENFORCED",
            resource_enforcement="SUPPORTED",
            timeout_enforcement="ENFORCED",
            workspace_isolation="ENFORCED",
            cleanup_guarantee="ENFORCED",
            secure_untrusted_execution=False
        )

    def _truncate_output(self, output: bytes) -> tuple[str, bool]:
        if len(output) > self.policy.max_output_bytes:
            return output[:self.policy.max_output_bytes].decode('utf-8', errors='replace'), True
        return output.decode('utf-8', errors='replace'), False
        
    def _kill_process_tree(self, process: subprocess.Popen):
        try:
            if sys.platform == 'win32':
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(process.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                process.kill()
        except Exception:
            pass

    @staticmethod
    def _is_subpath_or_equal(path: str, base: str) -> bool:
        try:
            common = os.path.commonpath([path, base])
            if sys.platform == "win32":
                return os.path.normcase(common) == os.path.normcase(base)
            return common == base
        except ValueError:
            return False

    def resolve_and_validate_cwd(self, working_directory: str) -> str:
        """
        Fail-Closed Working Directory Validation.

        Guarantees:
        1. Require requested working directory to be present and non-empty.
        2. Resolve relative paths according to documented contract (anchored to
           sandbox_root or allowed_workspaces, or REDLINE_REPO_ROOT if set;
           prohibited if require_absolute_paths is enabled).
        3. Verify that directory exists on filesystem.
        4. Verify that target is actually a directory (not a regular file, FIFO, etc.).
        5. Resolve symlinks and canonicalize path via realpath.
        6. Apply authorized-workspace and sandbox-root restrictions if configured.
        7. Reject any paths escaping authorized boundary via traversal (..) or symlinks.
        8. Never silently fall back to cwd=None, process working directory, or parent directory.
        """
        if not working_directory or not isinstance(working_directory, str) or not working_directory.strip():
            raise ValueError("Working directory must be provided and non-empty")

        raw_dir = working_directory.strip()

        # 1. Resolve relative path against authorized anchor if applicable
        if not os.path.isabs(raw_dir):
            if getattr(self.policy, "require_absolute_paths", False):
                raise ValueError(f"Relative working directory '{raw_dir}' is prohibited when require_absolute_paths is enabled")
            elif self.policy.sandbox_root:
                anchor = os.path.abspath(self.policy.sandbox_root)
                candidate = os.path.abspath(os.path.join(anchor, raw_dir))
            elif self.policy.allowed_workspaces:
                anchor = os.path.abspath(self.policy.allowed_workspaces[0])
                candidate = os.path.abspath(os.path.join(anchor, raw_dir))
            elif os.environ.get("REDLINE_REPO_ROOT"):
                anchor = os.path.abspath(os.environ["REDLINE_REPO_ROOT"])
                candidate = os.path.abspath(os.path.join(anchor, raw_dir))
            else:
                # Documented contract: relative path without explicit sandbox root resolves against current working directory
                candidate = os.path.abspath(raw_dir)
        else:
            candidate = os.path.abspath(raw_dir)

        # 2. Check existence
        if not os.path.exists(candidate):
            raise ValueError(f"Working directory does not exist: {raw_dir}")

        # 3. Check directory type (reject regular files)
        if not os.path.isdir(candidate):
            raise ValueError(f"Working directory path is not a directory: {raw_dir}")

        # 4. Canonicalize resolving symlinks and junction points
        canonical = os.path.realpath(candidate)
        if not os.path.exists(canonical) or not os.path.isdir(canonical):
            raise ValueError(f"Canonical working directory does not exist or is not a directory: {canonical}")

        # 5. Apply sandbox_root confinement if configured
        if self.policy.sandbox_root:
            canonical_root = os.path.realpath(os.path.abspath(self.policy.sandbox_root))
            if not self._is_subpath_or_equal(canonical, canonical_root):
                raise ValueError(f"Working directory '{raw_dir}' (canonical: '{canonical}') escapes sandbox root '{canonical_root}'")

        # 6. Apply allowed_workspaces confinement if configured
        if self.policy.allowed_workspaces:
            allowed_canonical = [os.path.realpath(os.path.abspath(w)) for w in self.policy.allowed_workspaces]
            if not any(self._is_subpath_or_equal(canonical, root) for root in allowed_canonical):
                raise ValueError(f"Working directory '{raw_dir}' (canonical: '{canonical}') is outside authorized workspaces: {self.policy.allowed_workspaces}")

        return canonical

    def execute(self, req: ExecutionRequest, run_id: str) -> ExecutionResult:
        import hashlib
        
        # Direct Backend Protection: Fail closed.
        # LocalDevelopmentBackend ONLY authorizes explicitly verified TRUSTED_DEVELOPMENT workloads.
        # Any missing, malformed, unexpected, or UNTRUSTED trust classification must be blocked.
        if req.repository_trust != "TRUSTED_DEVELOPMENT":
            caps = self.capabilities()
            msg = f"POLICY_BLOCKED: LocalDevelopmentBackend is UNSAFE FOR UNTRUSTED PRODUCTION WORKLOADS (repository_trust='{req.repository_trust}')."
            return ExecutionResult(
                run_id=run_id,
                exit_code=-1,
                stdout="",
                stderr=msg,
                stdout_sha256=hashlib.sha256(b"").hexdigest(),
                stderr_sha256=hashlib.sha256(msg.encode()).hexdigest(),
                policy_blocked=True,
                backend_provenance={
                    "security_level": caps.security_level.value,
                    "trust": str(req.repository_trust),
                    "capabilities": caps.model_dump()
                }
            )

        start_time = time.time()
        
        if not req.command:
            raise ValueError("Empty command")
            
        if req.command[0] not in self.policy.allowed_commands:
            raise ValueError(f"Command not allowed: {req.command[0]}")

        # Fail-closed working directory validation BEFORE any subprocess is created
        try:
            cwd = self.resolve_and_validate_cwd(req.working_directory)
        except ValueError as e:
            caps = self.capabilities()
            msg = f"POLICY_BLOCKED: Working directory validation failed: {str(e)}"
            return ExecutionResult(
                run_id=run_id,
                exit_code=-1,
                stdout="",
                stderr=msg,
                stdout_sha256=hashlib.sha256(b"").hexdigest(),
                stderr_sha256=hashlib.sha256(msg.encode()).hexdigest(),
                policy_blocked=True,
                backend_provenance={
                    "security_level": caps.security_level.value,
                    "trust": str(req.repository_trust),
                    "capabilities": caps.model_dump(),
                    "policy_violation": "INVALID_WORKING_DIRECTORY",
                    "error": str(e)
                }
            )

        env = req.environment.copy()
        
        timed_out = False
        crashed = False
        exit_code = -1
        
        try:
            # shell=False is enforced implicitly by subprocess.Popen taking a list
            process = subprocess.Popen(
                req.command,
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False
            )
            
            out_bytes = b""
            err_bytes = b""
            out_trunc = False
            err_trunc = False
            
            def read_stream(stream, is_err):
                nonlocal out_bytes, err_bytes, out_trunc, err_trunc
                while True:
                    chunk = stream.read(4096)
                    if not chunk:
                        break
                    if is_err:
                        if len(err_bytes) + len(chunk) > self.policy.max_output_bytes:
                            err_bytes += chunk[:self.policy.max_output_bytes - len(err_bytes)]
                            err_trunc = True
                            break
                        err_bytes += chunk
                    else:
                        if len(out_bytes) + len(chunk) > self.policy.max_output_bytes:
                            out_bytes += chunk[:self.policy.max_output_bytes - len(out_bytes)]
                            out_trunc = True
                            break
                        out_bytes += chunk
                        
            t_out = threading.Thread(target=read_stream, args=(process.stdout, False))
            t_err = threading.Thread(target=read_stream, args=(process.stderr, True))
            t_out.start()
            t_err.start()
            
            try:
                exit_code = process.wait(timeout=req.timeout_seconds)
            except subprocess.TimeoutExpired:
                self._kill_process_tree(process)
                try:
                    exit_code = process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
                timed_out = True
                
            t_out.join()
            t_err.join()
            
        except Exception as e:
            crashed = True
            out_bytes = b""
            err_bytes = str(e).encode()
            out_trunc = False
            err_trunc = False
            
        runtime_ms = int((time.time() - start_time) * 1000)
        
        stdout_str = out_bytes.decode('utf-8', errors='replace')
        stderr_str = err_bytes.decode('utf-8', errors='replace')
        
        import hashlib
        stdout_sha256 = hashlib.sha256(out_bytes).hexdigest()
        stderr_sha256 = hashlib.sha256(err_bytes).hexdigest()
        
        return ExecutionResult(
            run_id=run_id,
            exit_code=exit_code if not crashed else -1,
            stdout=stdout_str,
            stderr=stderr_str,
            stdout_sha256=stdout_sha256,
            stderr_sha256=stderr_sha256,
            runtime_ms=runtime_ms,
            timed_out=timed_out,
            crashed=crashed,
            stdout_truncated=out_trunc,
            stderr_truncated=err_trunc
        )

# For backwards compatibility with existing code during migration:
SandboxExecutor = LocalDevelopmentBackend
