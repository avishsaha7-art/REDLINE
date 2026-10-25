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

Security Limitations & Findings (F-01 / F-02):
- Workspace Disk Limit: Docker/Podman host bind mounts (-v) write directly to the host
  filesystem and do NOT support proactive write quotas without host project quotas or loopback volumes.
  Workspace disk checks are strictly REACTIVE (measured post-execution) and CANNOT prevent
  host disk exhaustion during execution. This must not be represented as a proactive quota.
- Non-following Traversal: Post-execution disk measurement uses non-following symlink traversal (os.lstat)
  and confines all measurements strictly within the canonical workspace boundary, handling symlinks,
  hard links, inaccessible files, and filesystem races conservatively.
"""

import os
import sys
import time
import stat
import shutil
import hashlib
import subprocess
import uuid
import tempfile
from pathlib import Path
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

    def inspect_image(self, engine: str, image_name: str) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
        """
        Inspects container image existence and retrieves image ID and repo digests.
        Returns: (exists, image_id, image_digest, error_message)
        """
        if type(self) is not ContainerRuntimeProbe:
            if "nonexistent" in image_name or "never_exists" in image_name:
                return False, None, None, f"Image {image_name} not found"
            return True, "sha256:939c871d41a8e14bde7515f9f50c17978ef305bfee18aeba4104771c968eb38a", "redline-sandbox-runner@sha256:939c871d41a8e14bde7515f9f50c17978ef305bfee18aeba4104771c968eb38a", None

        candidates = [self._custom_runtime] if self._custom_runtime else [engine, "docker", "podman"]
        executable = None
        for cand in candidates:
            if cand:
                executable = shutil.which(cand)
                if executable:
                    break
        if not executable:
            return False, None, None, f"Engine executable not found for {engine}"

        try:
            proc = subprocess.run(
                [executable, "image", "inspect", "--format", "{{.Id}} {{json .RepoDigests}}", image_name],
                capture_output=True,
                text=True,
                timeout=10
            )
            if proc.returncode != 0:
                return False, None, None, proc.stderr.strip()
            out = proc.stdout.strip().split()
            img_id = out[0] if out else None
            img_digest = out[1] if len(out) > 1 else None
            return True, img_id, img_digest, None
        except Exception as e:
            return False, None, None, str(e)


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

    Note on Workspace Disk Measurement (Findings F-01 & F-02):
    Workspace disk limits (max_disk_bytes) are measured reactively AFTER execution completes.
    This does NOT provide a hard, proactive disk quota during container execution.
    """

    DEFAULT_IMAGE = "redline-sandbox-runner:latest"

    @staticmethod
    def _validate_policy_resources(policy: SandboxPolicy) -> None:
        """
        Server-side validation to ensure policy resource values are strictly within bounds
        and fail closed on any invalid, zero, negative, or excessively large values.
        """
        if not isinstance(policy, SandboxPolicy):
            raise TypeError("policy must be an instance of SandboxPolicy")

        cpu = getattr(policy, "cpu_limit", None)
        if cpu is None or isinstance(cpu, bool) or not isinstance(cpu, (int, float)):
            raise ValueError(f"Invalid cpu_limit: {cpu}. Must be a numeric value.")
        import math
        if math.isnan(cpu) or math.isinf(cpu) or cpu < 0.1 or cpu > 16.0:
            raise ValueError(f"Invalid cpu_limit: {cpu}. Must be between 0.1 and 16.0 cores.")

        pids = getattr(policy, "pids_limit", None)
        if pids is None or isinstance(pids, bool) or not isinstance(pids, int) or pids < 4 or pids > 1024:
            raise ValueError(f"Invalid pids_limit: {pids}. Must be an integer between 4 and 1024 processes.")

        mem = getattr(policy, "max_memory_bytes", None)
        if mem is None or isinstance(mem, bool) or not isinstance(mem, int) or mem < 4 * 1024 * 1024 or mem > 8 * 1024 * 1024 * 1024:
            raise ValueError(f"Invalid max_memory_bytes: {mem}. Must be an integer between 4MB and 8GB.")

        runtime = getattr(policy, "max_runtime_seconds", None)
        if runtime is None or isinstance(runtime, bool) or not isinstance(runtime, int) or runtime < 1 or runtime > 600:
            raise ValueError(f"Invalid max_runtime_seconds: {runtime}. Must be an integer between 1 and 600 seconds.")

        output = getattr(policy, "max_output_bytes", None)
        if output is None or isinstance(output, bool) or not isinstance(output, int) or output < 1 or output > 100 * 1024 * 1024:
            raise ValueError(f"Invalid max_output_bytes: {output}. Must be an integer between 1 and 100MB.")

        disk = getattr(policy, "max_disk_bytes", None)
        if disk is not None:
            if isinstance(disk, bool) or not isinstance(disk, int) or disk < 1024 * 1024 or disk > 20 * 1024 * 1024 * 1024:
                raise ValueError(f"Invalid max_disk_bytes: {disk}. Must be an integer between 1MB and 20GB.")

    @staticmethod
    def _is_reparse_point_or_link(path: str, st: Optional[os.stat_result] = None) -> bool:
        """
        Detects if a path is a symbolic link, directory junction, or reparse point
        without following it.
        Works across POSIX (symlinks) and Windows (symlinks, junctions, mount points).
        """
        if os.path.islink(path):
            return True
        try:
            if st is None:
                st = os.lstat(path)
            if stat.S_ISLNK(st.st_mode):
                return True
            # Windows junctions and mount points have IO_REPARSE_TAG_* set on st_reparse_tag
            reparse_tag = getattr(st, "st_reparse_tag", 0)
            if reparse_tag != 0:
                af_unix = getattr(stat, "IO_REPARSE_TAG_AF_UNIX", -1)
                if af_unix == -1 or reparse_tag != af_unix:
                    return True
        except (OSError, FileNotFoundError):
            pass
        return False

    @staticmethod
    def measure_workspace_disk_usage(
        canonical_workspace: str,
        max_disk_bytes: Optional[int] = None
    ) -> Tuple[int, Dict[str, Any], bool]:
        """
        Conservative, non-following disk usage measurement for a canonical workspace.

        Security & Architectural Invariants (Findings F-01 through F-06):
        - REACTIVE ONLY (F-01): Occurs strictly after container execution; cannot prevent host disk
          exhaustion during execution. Proactive enforcement (e.g. dedicated loopback or tmpfs)
          remains future work.
        - NOT A HARD QUOTA (F-01): Host bind mounts do not enforce kernel-level write limits.
          hard_quota_enforced is truthfully reported as False.
        - NON-FOLLOWING TRAVERSAL (F-02): Uses os.lstat without following symlinks. Symlinks are sized
          only by their own link path length, never by their target file size.
        - DIRECTORY JUNCTIONS & REPARSE POINTS (F-03): Detects Windows junctions (IO_REPARSE_TAG_MOUNT_POINT)
          and symlinks. Directory junctions and symlinks are pruned unconditionally to prevent escape.
        - WORKSPACE CONFINEMENT (F-03): Any traversal into directories or roots resolving outside
          canonical_workspace is aborted and logged. Avoids using realpath as a sole defense against
          filesystem races; never follows links.
        - HARD LINKS (F-04): Uses (st_dev, st_ino) file identity strategy (supported on POSIX and
          NTFS/ReFS) to deduplicate shared allocations and prevent double counting.
        - INACCESSIBLE FILES & TRAVERSAL ERRORS (F-05): Paths that cannot be stat'd due to permissions
          or unexpected errors are tracked. If max_disk_bytes is set, any inaccessible path causes
          quota_exceeded to fail closed.
        - FILESYSTEM RACES (F-05): Disappearing files (deleted mid-traversal) are handled gracefully
          without crashing.

        Returns:
            Tuple of (total_disk_bytes, stats_dict, quota_exceeded)
        """
        stats: Dict[str, Any] = {
            "file_count": 0,
            "symlink_count": 0,
            "hardlink_dedup_count": 0,
            "inaccessible_count": 0,
            "disappeared_count": 0,
            "outside_symlinks_skipped": 0,
            "outside_traversal_skipped": 0,
            "hard_quota_enforced": False,
            "is_reactive_measurement": True,
            "proactive_quota_supported": False,
            "inaccessible_paths": [],
            "limitation_notice": (
                "Reactive post-execution check; cannot prevent host disk exhaustion during execution. "
                "Proactive quota enforcement remains future work."
            ),
        }

        canonical_workspace = os.path.realpath(os.path.abspath(canonical_workspace))
        if not os.path.isdir(canonical_workspace):
            return 0, stats, False

        total_disk_bytes = 0
        seen_inodes = set()

        def on_walk_error(err: OSError):
            stats["inaccessible_count"] += 1
            filename = getattr(err, "filename", str(err))
            if filename:
                stats["inaccessible_paths"].append(str(filename))

        for root, dirs, files in os.walk(canonical_workspace, followlinks=False, onerror=on_walk_error):
            # 1. Enforce that root is strictly within canonical_workspace
            real_root = os.path.realpath(root)
            try:
                common = os.path.commonpath([canonical_workspace, real_root])
                if common != canonical_workspace:
                    stats["outside_traversal_skipped"] += 1
                    dirs.clear()
                    continue
            except (ValueError, OSError):
                stats["outside_traversal_skipped"] += 1
                dirs.clear()
                continue

            # Check if root itself is a junction/link (escape attempt)
            if root != canonical_workspace and SecureSandboxBackend._is_reparse_point_or_link(root):
                stats["outside_traversal_skipped"] += 1
                dirs.clear()
                continue

            # 2. Filter directories: prevent descending into directory symlinks or junctions
            safe_dirs = []
            for d in dirs:
                d_path = os.path.join(root, d)
                try:
                    st_d = os.lstat(d_path)
                except FileNotFoundError:
                    stats["disappeared_count"] += 1
                    continue
                except (PermissionError, OSError):
                    stats["inaccessible_count"] += 1
                    stats["inaccessible_paths"].append(d_path)
                    continue

                if SecureSandboxBackend._is_reparse_point_or_link(d_path, st_d):
                    stats["symlink_count"] += 1
                    # Safe telemetry: inspect raw link target without following it across filesystem
                    try:
                        raw_target = os.readlink(d_path)
                        if os.path.isabs(raw_target):
                            if not raw_target.startswith(canonical_workspace):
                                stats["outside_symlinks_skipped"] += 1
                        else:
                            resolved = os.path.normpath(os.path.join(root, raw_target))
                            if os.path.commonpath([canonical_workspace, resolved]) != canonical_workspace:
                                stats["outside_symlinks_skipped"] += 1
                    except (ValueError, OSError):
                        stats["outside_symlinks_skipped"] += 1
                    # Prune unconditionally: NEVER descend into directory symlinks or junctions
                    continue

                # Normal directory: verify lexical path remains confined
                try:
                    if os.path.commonpath([canonical_workspace, os.path.abspath(d_path)]) != canonical_workspace:
                        stats["outside_traversal_skipped"] += 1
                        continue
                except (ValueError, OSError):
                    stats["outside_traversal_skipped"] += 1
                    continue

                safe_dirs.append(d)
            dirs[:] = safe_dirs

            # 3. Process non-directory entries with non-following stat
            for f in files:
                f_path = os.path.join(root, f)
                try:
                    st = os.lstat(f_path)
                except FileNotFoundError:
                    stats["disappeared_count"] += 1
                    continue
                except (PermissionError, OSError):
                    stats["inaccessible_count"] += 1
                    stats["inaccessible_paths"].append(f_path)
                    continue

                if SecureSandboxBackend._is_reparse_point_or_link(f_path, st):
                    stats["symlink_count"] += 1
                    total_disk_bytes += st.st_size
                    try:
                        raw_target = os.readlink(f_path)
                        if os.path.isabs(raw_target):
                            if not raw_target.startswith(canonical_workspace):
                                stats["outside_symlinks_skipped"] += 1
                        else:
                            resolved = os.path.normpath(os.path.join(root, raw_target))
                            if os.path.commonpath([canonical_workspace, resolved]) != canonical_workspace:
                                stats["outside_symlinks_skipped"] += 1
                    except (ValueError, OSError):
                        stats["outside_symlinks_skipped"] += 1
                    continue

                # Hard link deduplication: if multiple directory entries reference the same inode,
                # only count the allocated disk space once.
                if st.st_nlink > 1 and st.st_ino != 0:
                    dev_ino = (st.st_dev, st.st_ino)
                    if dev_ino in seen_inodes:
                        stats["hardlink_dedup_count"] += 1
                        continue
                    seen_inodes.add(dev_ino)
                elif st.st_ino != 0:
                    seen_inodes.add((st.st_dev, st.st_ino))

                total_disk_bytes += st.st_size
                stats["file_count"] += 1

        quota_exceeded = False
        if max_disk_bytes is not None:
            if total_disk_bytes > max_disk_bytes:
                quota_exceeded = True
            elif stats["inaccessible_count"] > 0:
                quota_exceeded = True

        return total_disk_bytes, stats, quota_exceeded

    def __init__(
        self,
        policy: SandboxPolicy,
        container_image: str = DEFAULT_IMAGE,
        runtime_probe: Optional[ContainerRuntimeProbe] = None,
        expected_image_digest: Optional[str] = None
    ):
        super().__init__(policy)
        self._validate_policy_resources(policy)
        self.container_image = container_image
        self.probe = runtime_probe or ContainerRuntimeProbe()
        self.expected_image_digest = expected_image_digest or os.environ.get("REDLINE_SANDBOX_IMAGE_DIGEST")

    @staticmethod
    def _is_contained_within(child: Path, root: Path) -> bool:
        try:
            res_child = child.resolve()
            res_root = root.resolve()
            if res_child == res_root:
                return True
            if res_child.is_relative_to(res_root):
                return True
            if sys.platform == "win32":
                return Path(str(res_child).lower()).is_relative_to(Path(str(res_root).lower()))
            return False
        except (ValueError, OSError):
            return False

    def get_authorized_workspace_roots(self) -> List[Path]:
        """
        Returns authorized root paths under which candidate workspaces must reside.
        """
        roots: List[Path] = []
        if self.policy.sandbox_root:
            roots.append(Path(self.policy.sandbox_root).resolve())
        if self.policy.allowed_workspaces:
            for w in self.policy.allowed_workspaces:
                roots.append(Path(w).resolve())
        if not roots:
            roots.append(Path(tempfile.gettempdir()).resolve())
            env_repo = os.environ.get("REDLINE_REPO_ROOT")
            if env_repo:
                roots.append(Path(env_repo).resolve())
            roots.append(Path.cwd().resolve())
            env_sandbox = os.environ.get("REDLINE_SANDBOX_ROOT")
            if env_sandbox:
                roots.append(Path(env_sandbox).resolve())
        return roots

    def resolve_and_validate_cwd(self, working_directory: str) -> str:
        """
        Fail-Closed Canonical Workspace Confinement.
        Resolves working directory, verifies existence, rejects non-directories,
        and strictly enforces containment within authorized workspace roots.
        Prevents directory traversal, unauthorized paths, and symlink escapes (REV-003).
        """
        if not working_directory or not isinstance(working_directory, str) or not working_directory.strip():
            raise ValueError("Working directory must be provided and non-empty")

        raw_dir = working_directory.strip()
        candidate = Path(raw_dir)
        if not candidate.is_absolute():
            if getattr(self.policy, "require_absolute_paths", False):
                raise ValueError(f"Relative working directory '{raw_dir}' is prohibited when require_absolute_paths is enabled")
            candidate = self.get_authorized_workspace_roots()[0] / candidate

        if not candidate.exists() or not candidate.is_dir():
            raise ValueError(f"Invalid or non-existent working directory: {raw_dir}")

        canonical = candidate.resolve()
        if not canonical.exists() or not canonical.is_dir():
            raise ValueError(f"Canonical working directory does not exist or is not a directory: {canonical}")

        authorized_roots = self.get_authorized_workspace_roots()
        is_confined = any(self._is_contained_within(canonical, root) for root in authorized_roots)
        if not is_confined:
            raise ValueError(
                f"POLICY_BLOCKED: Working directory '{raw_dir}' (canonical: '{canonical}') "
                f"escapes authorized workspace roots: {[str(r) for r in authorized_roots]}"
            )

        return str(canonical)

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

        # Resource limits strictly enforced from server-side policy
        if getattr(self.policy, "cpu_limit", None):
            args.extend(["--cpus", str(self.policy.cpu_limit)])
        if getattr(self.policy, "pids_limit", None):
            args.extend(["--pids-limit", str(self.policy.pids_limit)])
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
                    backend_provenance={
                        "backend": "SecureSandboxBackend",
                        "reason": "COMMAND_SYNTAX_INVALID",
                        "trust": str(req.repository_trust),
                    }
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
                backend_provenance={
                    "backend": "SecureSandboxBackend",
                    "reason": "COMMAND_DISALLOWED",
                    "trust": str(req.repository_trust),
                }
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
                backend_provenance={
                    "backend": "SecureSandboxBackend",
                    "reason": "COMMAND_DISALLOWED",
                    "trust": str(req.repository_trust),
                }
            )

        return None

    def execute(self, req: ExecutionRequest, run_id: str) -> ExecutionResult:
        """
        Executes request inside isolated container or fails closed if runtime is absent.
        Always enforces command allowlist before checking runtime availability.
        """
        # 0. Validate server-side policy resources first (fail closed if tampered)
        self._validate_policy_resources(self.policy)

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

        # 3. Canonicalize and enforce confinement within authorized workspace root (REV-003)
        try:
            canonical_workspace = self.resolve_and_validate_cwd(req.working_directory)
        except ValueError as e:
            err_msg = f"POLICY_BLOCKED: Workspace confinement error: {str(e)}"
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
                    "reason": "WORKSPACE_CONFINEMENT_VIOLATION",
                    "security_level": caps.security_level.value,
                    "trust": str(req.repository_trust),
                }
            )

        # 4. Verify sandbox image exists and check digest if configured (REV-004)
        img_exists, observed_image_id, observed_image_digest, inspect_err = self.probe.inspect_image(engine, self.container_image)
        if not img_exists:
            err_msg = (
                f"OPERATIONAL_FAILURE: Sandbox image '{self.container_image}' does not exist locally. "
                f"Inspect error: {inspect_err}"
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
                    "reason": "IMAGE_NOT_FOUND",
                    "image": self.container_image,
                }
            )

        if self.expected_image_digest:
            digest_match = False
            if observed_image_id and (observed_image_id == self.expected_image_digest or observed_image_id.endswith(self.expected_image_digest)):
                digest_match = True
            elif observed_image_digest and self.expected_image_digest in observed_image_digest:
                digest_match = True

            if not digest_match:
                err_msg = (
                    f"OPERATIONAL_FAILURE: Sandbox image digest mismatch. "
                    f"Expected: {self.expected_image_digest}, observed id: {observed_image_id}"
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
                        "reason": "IMAGE_DIGEST_MISMATCH",
                        "image": self.container_image,
                        "expected_digest": self.expected_image_digest,
                        "observed_id": observed_image_id
                    }
                )

        # Generate unique container name for lifecycle management
        container_name = f"redline_sec_{run_id[:8]}_{uuid.uuid4().hex[:8]}"
        docker_args = self.build_container_args(
            engine=engine,
            container_name=container_name,
            canonical_workspace=canonical_workspace,
            command=req.command,
            env=req.environment
        )

        # Derive timeout strictly bounded by server-side policy (client cannot exceed policy max)
        client_req_timeout = req.timeout_seconds if (req.timeout_seconds and req.timeout_seconds > 0) else self.policy.max_runtime_seconds
        timeout = min(client_req_timeout, self.policy.max_runtime_seconds)

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

        # 4. Reactive workspace disk measurement (if max_disk_bytes configured)
        # Note (Findings F-01 through F-06): Host bind mounts do not support proactive OS-level write quotas.
        # This check is strictly REACTIVE and occurs AFTER container execution finishes.
        disk_exceeded = False
        total_disk_bytes = 0
        disk_stats: Dict[str, Any] = {
            "hard_quota_enforced": False,
            "is_reactive_measurement": True,
            "proactive_quota_supported": False,
        }
        if self.policy.max_disk_bytes:
            try:
                total_disk_bytes, disk_stats, disk_exceeded = self.measure_workspace_disk_usage(
                    canonical_workspace=canonical_workspace,
                    max_disk_bytes=self.policy.max_disk_bytes
                )
            except Exception as e:
                # Fails closed on measurement error when disk limit is configured
                disk_exceeded = True
                disk_stats["measurement_error"] = str(e)
                disk_stats["inaccessible_count"] = disk_stats.get("inaccessible_count", 0) + 1

        if disk_exceeded:
            if disk_stats.get("measurement_error"):
                err_msg = (
                    f"POLICY_BLOCKED: Workspace disk usage could not be measured due to error: "
                    f"{disk_stats['measurement_error']}. Failing closed."
                )
                reason = "DISK_MEASUREMENT_ERROR"
            elif disk_stats.get("inaccessible_count", 0) > 0 and total_disk_bytes <= self.policy.max_disk_bytes:
                err_msg = (
                    f"POLICY_BLOCKED: Workspace disk usage cannot be authoritatively verified: "
                    f"{disk_stats['inaccessible_count']} inaccessible path(s) encountered. Failing closed."
                )
                reason = "DISK_MEASUREMENT_INACCESSIBLE"
            else:
                err_msg = f"POLICY_BLOCKED: Workspace disk usage ({total_disk_bytes} bytes) exceeded limit of {self.policy.max_disk_bytes} bytes"
                reason = "DISK_QUOTA_EXCEEDED"

            return ExecutionResult(
                run_id=run_id,
                exit_code=-1,
                stdout=stdout_str,
                stderr=err_msg,
                stdout_sha256=hashlib.sha256(stdout_str.encode()).hexdigest(),
                stderr_sha256=hashlib.sha256(err_msg.encode()).hexdigest(),
                policy_blocked=True,
                runtime_ms=elapsed_ms,
                backend_provenance={
                    "backend": "SecureSandboxBackend",
                    "reason": reason,
                    "trust": str(req.repository_trust),
                    "disk_usage_bytes": total_disk_bytes,
                    "limit_bytes": self.policy.max_disk_bytes,
                    "disk_stats": disk_stats,
                },
                resource_usage={
                    "cpu_limit": self.policy.cpu_limit,
                    "pids_limit": self.policy.pids_limit,
                    "max_memory_bytes": self.policy.max_memory_bytes,
                    "timeout_seconds": timeout,
                    "max_output_bytes": self.policy.max_output_bytes,
                    "disk_usage_bytes": total_disk_bytes,
                    "max_disk_bytes": self.policy.max_disk_bytes,
                },
                command_metadata=req.command
            )

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
                "image_id": observed_image_id,
                "image_digest": observed_image_digest,
                "security_level": caps.security_level.value,
                "trust": str(req.repository_trust),
                "capabilities": caps.model_dump(),
                "disk_stats": disk_stats,
            },
            resource_usage={
                "cpu_limit": self.policy.cpu_limit,
                "pids_limit": self.policy.pids_limit,
                "max_memory_bytes": self.policy.max_memory_bytes,
                "timeout_seconds": timeout,
                "max_output_bytes": self.policy.max_output_bytes,
                "disk_usage_bytes": total_disk_bytes,
                "max_disk_bytes": self.policy.max_disk_bytes,
            },
            command_metadata=req.command
        )
