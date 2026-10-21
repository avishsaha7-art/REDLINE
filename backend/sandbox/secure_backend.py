"""
Secure Sandbox Backend for REDLINE.

Provides container-backed OS-level isolation for untrusted candidate code execution.
In accordance with Stage P2-3 and REDLINE Architecture v1.1:
- Fails closed if the secure container runtime (e.g., Docker daemon) is unavailable.
- Reports capabilities truthfully (does NOT claim SECURE if runtime is missing).
- Enforces filesystem isolation: mounts ONLY the designated ephemeral workspace.
- Disables network access by default (--network none).
- Drops all privileges (--cap-drop=ALL, non-root user, no-new-privileges).
- Strictly prevents host Docker socket exposure or host filesystem leakage.
- Cleans up containers deterministically across success, error, timeout, and cancellation.
- Returns structured operational failures (OPERATIONAL_FAILURE) rather than code rejections.
"""

import os
import sys
import time
import shutil
import hashlib
import subprocess
import uuid
from typing import List, Dict, Optional, Any, Tuple
from backend.sandbox.backend import SandboxBackend
from backend.sandbox.models import SandboxPolicy, ExecutionRequest, ExecutionResult
from backend.sandbox.capabilities import SandboxCapabilities, SecurityLevel, RepositoryTrust


class ContainerRuntimeProbe:
    """
    Probes host system for operational container runtimes (Docker, Podman).
    Allows dependency injection for testing and runtime mocking.
    """
    def __init__(self, runtime_executable: Optional[str] = None):
        self._custom_runtime = runtime_executable

    def detect_runtime(self) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Detects if an operational container engine is accessible.
        Returns: (is_operational, engine_name, metadata)
        """
        candidates = [self._custom_runtime] if self._custom_runtime else ["docker", "podman"]

        for engine in candidates:
            if not engine:
                continue
            executable = shutil.which(engine)
            if not executable:
                continue

            # Check daemon responsiveness (not just CLI presence)
            try:
                proc = subprocess.run(
                    [executable, "info", "--format", "{{.ServerVersion}}"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if proc.returncode == 0:
                    version = proc.stdout.strip()
                    return True, engine, {"executable": executable, "server_version": version}
                else:
                    return False, engine, {
                        "executable": executable,
                        "error": "Daemon unreachable or permission denied",
                        "stderr": proc.stderr.strip()
                    }
            except Exception as e:
                return False, engine, {"executable": executable, "error": str(e)}

        return False, "NONE", {"error": "No container runtime CLI (docker/podman) found in PATH"}


class SecureSandboxBackend(SandboxBackend):
    """
    Secure Container-Backed Sandbox Backend.

    Provides OS-level filesystem, network, and process isolation for untrusted workloads.
    When an operational runtime is detected:
        capabilities().security_level == SecurityLevel.SECURE
        capabilities().filesystem_isolation == "ENFORCED"
        capabilities().secure_untrusted_execution == True
    When no operational runtime is detected:
        capabilities().security_level == SecurityLevel.UNAVAILABLE
        capabilities().filesystem_isolation == "NOT_AVAILABLE"
        capabilities().secure_untrusted_execution == False
        Fails closed on any untrusted execution request.
    """

    DEFAULT_IMAGE = "redline-sandbox-runner:latest"

    def __init__(
        self,
        policy: SandboxPolicy,
        container_image: str = DEFAULT_IMAGE,
        runtime_probe: Optional[ContainerRuntimeProbe] = None
    ):
        super().__init__(policy)
        self.container_image = container_image
        self.probe = runtime_probe or ContainerRuntimeProbe()

    def capabilities(self) -> SandboxCapabilities:
        """
        Truthful capability reporting based on verified runtime presence.
        Never claims SECURE unless the container engine is actively responsive.
        """
        is_operational, engine, _ = self.probe.detect_runtime()

        if is_operational:
            return SandboxCapabilities(
                security_level=SecurityLevel.SECURE,
                filesystem_isolation="ENFORCED",
                process_isolation="ENFORCED",
                network_isolation="ENFORCED",
                credential_isolation="ENFORCED",
                resource_enforcement="ENFORCED",
                timeout_enforcement="ENFORCED",
                workspace_isolation="ENFORCED",
                cleanup_guarantee="ENFORCED",
                secure_untrusted_execution=True
            )
        else:
            return SandboxCapabilities(
                security_level=SecurityLevel.UNAVAILABLE,
                filesystem_isolation="NOT_AVAILABLE",
                process_isolation="NOT_AVAILABLE",
                network_isolation="NOT_AVAILABLE",
                credential_isolation="ENFORCED",
                resource_enforcement="NOT_AVAILABLE",
                timeout_enforcement="NOT_AVAILABLE",
                workspace_isolation="NOT_AVAILABLE",
                cleanup_guarantee="NOT_AVAILABLE",
                secure_untrusted_execution=False
            )

    def _truncate_output(self, output: bytes) -> Tuple[str, bool]:
        if len(output) > self.policy.max_output_bytes:
            return output[:self.policy.max_output_bytes].decode('utf-8', errors='replace'), True
        return output.decode('utf-8', errors='replace'), False

    def build_container_args(
        self,
        engine: str,
        container_name: str,
        canonical_workspace: str,
        command: List[str],
        env: Dict[str, str]
    ) -> List[str]:
        """
        Constructs hardened container execution argument list.
        Guarantees:
        - Only canonical_workspace is mounted (at /workspace:rw)
        - Read-only container root filesystem
        - Disabled network by default (--network none)
        - Dropped Linux capabilities (--cap-drop=ALL)
        - Non-root user (--user 1000:1000)
        - No-new-privileges flag
        - Explicit tmpfs mount for temporary files
        - No Docker socket or host root exposure
        """
        args = [
            engine, "run",
            "--name", container_name,
            "--rm",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--user", "1000:1000",
            "-v", f"{canonical_workspace}:/workspace:rw",
            "-w", "/workspace",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
        ]

        # Network isolation
        if not self.policy.network_enabled:
            args.extend(["--network", "none"])

        # Resource limits where configured
        if self.policy.max_memory_bytes:
            args.extend(["--memory", f"{self.policy.max_memory_bytes}b"])

        # Environment variables (strictly controlled; zero host leaks)
        for k, v in env.items():
            args.extend(["-e", f"{k}={v}"])

        # Container image and target command
        args.append(self.container_image)
        args.extend(command)

        return args

    def _validate_command(self, req: ExecutionRequest, run_id: str) -> Optional[ExecutionResult]:
        """
        Validates command syntax and enforces the command allowlist.
        Must be invoked BEFORE checking runtime availability.
        Returns an ExecutionResult if rejected, or None if valid.
        """
        if not req.command or not isinstance(req.command, list) or len(req.command) == 0:
            raise ValueError("Empty command")

        for i, arg in enumerate(req.command):
            if not isinstance(arg, str):
                raise ValueError(f"Command argument at index {i} must be a string")
            if "\0" in arg or "\r" in arg or "\n" in arg:
                err_msg = f"POLICY_BLOCKED: Command argument at index {i} contains invalid control characters"
                return ExecutionResult(
                    run_id=run_id,
                    exit_code=-1,
                    stdout="",
                    stderr=err_msg,
                    stdout_sha256=hashlib.sha256(b"").hexdigest(),
                    stderr_sha256=hashlib.sha256(err_msg.encode()).hexdigest(),
                    policy_blocked=True,
                    backend_provenance={"backend": "SecureSandboxBackend", "reason": "COMMAND_SYNTAX_INVALID"}
                )

        raw_bin = req.command[0].strip()
        if not raw_bin:
            raise ValueError("Empty command binary")

        # Disallow shell operators and metacharacters in binary token
        disallowed_chars = {";", "&", "|", ">", "<", "$", "`", "(", ")", "{", "}", "!", "\t"}
        if any(c in raw_bin for c in disallowed_chars):
            err_msg = f"POLICY_BLOCKED: Command binary contains disallowed shell metacharacters: {raw_bin}"
            return ExecutionResult(
                run_id=run_id,
                exit_code=-1,
                stdout="",
                stderr=err_msg,
                stdout_sha256=hashlib.sha256(b"").hexdigest(),
                stderr_sha256=hashlib.sha256(err_msg.encode()).hexdigest(),
                policy_blocked=True,
                backend_provenance={"backend": "SecureSandboxBackend", "reason": "COMMAND_DISALLOWED"}
            )

        # Allowlist check: command binary must be in allowed_commands
        # Prevent path-based evasion: if path separators exist, must match exact configured entry
        is_allowed = False
        if raw_bin in self.policy.allowed_commands:
            is_allowed = True
        elif "/" not in raw_bin and "\\" not in raw_bin:
            # Allow matching Windows executable extension (e.g. python.exe -> python) if configured without extension
            if raw_bin.lower().endswith(".exe") and raw_bin[:-4] in self.policy.allowed_commands:
                is_allowed = True

        if not is_allowed:
            err_msg = f"POLICY_BLOCKED: Command not in allowed_commands: {raw_bin}"
            return ExecutionResult(
                run_id=run_id,
                exit_code=-1,
                stdout="",
                stderr=err_msg,
                stdout_sha256=hashlib.sha256(b"").hexdigest(),
                stderr_sha256=hashlib.sha256(err_msg.encode()).hexdigest(),
                policy_blocked=True,
                backend_provenance={"backend": "SecureSandboxBackend", "reason": "COMMAND_DISALLOWED"}
            )

        return None

    def execute(self, req: ExecutionRequest, run_id: str) -> ExecutionResult:
        """
        Executes request inside isolated container or fails closed if runtime is absent.
        Always enforces command allowlist before checking runtime availability.
        """
        # 1. Enforce command syntax validation and allowlist FIRST (Finding 2)
        cmd_err = self._validate_command(req, run_id)
        if cmd_err is not None:
            return cmd_err

        # 2. Check runtime availability and fail-closed gate
        caps = self.capabilities()
        is_operational, engine, probe_meta = self.probe.detect_runtime()

        # Fail-closed gate: refuse untrusted execution if secure runtime is unavailable
        if not is_operational or not caps.secure_untrusted_execution:
            err_msg = (
                "OPERATIONAL_FAILURE: Secure sandbox runtime (Docker/Podman) is UNAVAILABLE. "
                "Untrusted candidate execution is refused fail-closed. "
                f"Probe result: {probe_meta}"
            )
            return ExecutionResult(
                run_id=run_id,
                exit_code=-1,
                stdout="",
                stderr=err_msg,
                stdout_sha256=hashlib.sha256(b"").hexdigest(),
                stderr_sha256=hashlib.sha256(err_msg.encode()).hexdigest(),
                policy_blocked=True,
                backend_provenance={
                    "backend": "SecureSandboxBackend",
                    "status": "OPERATIONAL_FAILURE",
                    "reason": "RUNTIME_UNAVAILABLE",
                    "security_level": caps.security_level.value,
                    "trust": str(req.repository_trust),
                    "capabilities": caps.model_dump(),
                    "probe_metadata": probe_meta
                }
            )

        # 3. Validate working directory exists on host
        if not req.working_directory or not os.path.isdir(req.working_directory):
            raise ValueError(f"Invalid or non-existent working directory: {req.working_directory}")
        canonical_workspace = os.path.realpath(os.path.abspath(req.working_directory))

        # Generate unique container name for lifecycle management
        container_name = f"redline_sec_{run_id[:8]}_{uuid.uuid4().hex[:8]}"
        docker_args = self.build_container_args(
            engine=engine,
            container_name=container_name,
            canonical_workspace=canonical_workspace,
            command=req.command,
            env=req.environment
        )

        timeout = req.timeout_seconds or self.policy.max_runtime_seconds
        start_time = time.time()
        timed_out = False
        crashed = False

        try:
            proc = subprocess.Popen(
                docker_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout_bytes, stderr_bytes = proc.communicate(timeout=timeout)
            exit_code = proc.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            exit_code = -1
            # Deterministic container kill & teardown
            try:
                subprocess.run([engine, "rm", "-f", container_name], capture_output=True, timeout=10)
            except Exception:
                pass
            stdout_bytes = b""
            stderr_bytes = f"TIMEOUT: Container execution exceeded {timeout} seconds".encode()
        except Exception as e:
            crashed = True
            exit_code = -1
            stdout_bytes = b""
            stderr_bytes = f"CRASH: Execution failed with exception: {str(e)}".encode()
        finally:
            # Guarantee container cleanup even on abnormal termination
            try:
                subprocess.run([engine, "rm", "-f", container_name], capture_output=True, timeout=5)
            except Exception:
                pass

        elapsed_ms = int((time.time() - start_time) * 1000)
        stdout_str, stdout_trunc = self._truncate_output(stdout_bytes)
        stderr_str, stderr_trunc = self._truncate_output(stderr_bytes)

        return ExecutionResult(
            run_id=run_id,
            exit_code=exit_code,
            stdout=stdout_str,
            stderr=stderr_str,
            stdout_sha256=hashlib.sha256(stdout_str.encode()).hexdigest(),
            stderr_sha256=hashlib.sha256(stderr_str.encode()).hexdigest(),
            timed_out=timed_out,
            crashed=crashed,
            stdout_truncated=stdout_trunc,
            stderr_truncated=stderr_trunc,
            policy_blocked=False,
            runtime_ms=elapsed_ms,
            backend_provenance={
                "backend": "SecureSandboxBackend",
                "engine": engine,
                "container_name": container_name,
                "image": self.container_image,
                "security_level": caps.security_level.value,
                "trust": str(req.repository_trust),
                "capabilities": caps.model_dump()
            },
            command_metadata=req.command
        )
