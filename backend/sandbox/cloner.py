import os
import re
import stat
import shutil
import socket
import ipaddress
import urllib.parse
import subprocess
import hashlib
import tempfile
import datetime
import uuid
from typing import Optional, List, Tuple, Dict, Any
from pydantic import BaseModel, Field

from backend.sandbox.capabilities import RepositoryTrust
from backend.models.schemas import ResourceBudget
from backend.sandbox.registry import get_repository_registry, RepositoryTarget

# Prohibited destination hostnames (fail closed)
DISALLOWED_HOSTNAMES = {
    "localhost",
    "127.0.0.1",
    "::1",
    "0.0.0.0",
    "metadata.google.internal",
    "instance-data",
    "metadata.internal",
    "internal",
}

# Restricted IP networks (RFC 1918, loopback, link-local, multicast, cloud metadata, CGNAT)
PROHIBITED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),          # Current network
    ipaddress.ip_network("10.0.0.0/8"),          # Private RFC 1918
    ipaddress.ip_network("100.64.0.0/10"),       # Shared Address Space (Carrier-grade NAT)
    ipaddress.ip_network("127.0.0.0/8"),         # Loopback
    ipaddress.ip_network("169.254.0.0/16"),      # Link-local / AWS & cloud metadata
    ipaddress.ip_network("172.16.0.0/12"),       # Private RFC 1918
    ipaddress.ip_network("192.0.0.0/24"),        # IETF Protocol Assignments
    ipaddress.ip_network("192.0.2.0/24"),        # Documentation (TEST-NET-1)
    ipaddress.ip_network("192.88.99.0/24"),      # 6to4 Relay Anycast
    ipaddress.ip_network("192.168.0.0/16"),      # Private RFC 1918
    ipaddress.ip_network("198.18.0.0/15"),       # Benchmarking
    ipaddress.ip_network("198.51.100.0/24"),     # Documentation (TEST-NET-2)
    ipaddress.ip_network("203.0.113.0/24"),      # Documentation (TEST-NET-3)
    ipaddress.ip_network("224.0.0.0/4"),         # Multicast
    ipaddress.ip_network("240.0.0.0/4"),         # Reserved for future use
    ipaddress.ip_network("255.255.255.255/32"),  # Broadcast
    # IPv6
    ipaddress.ip_network("::1/128"),             # Loopback
    ipaddress.ip_network("::/128"),              # Unspecified
    ipaddress.ip_network("fc00::/7"),            # Unique local
    ipaddress.ip_network("fe80::/10"),           # Link-local
    ipaddress.ip_network("ff00::/8"),            # Multicast
]

COMMIT_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$|^[0-9a-fA-F]{64}$")


class ClonerError(Exception):
    """Base exception for all cloner errors."""
    pass


class ClonerSecurityError(ClonerError):
    """Raised when URL validation, SSRF boundary, or network policy is violated."""
    pass


class ClonerResourceLimitError(ClonerError):
    """Raised when repository byte size, file count, or runtime budget is exceeded."""
    pass


class ClonerCommitVerificationError(ClonerError):
    """Raised when commit SHA is invalid, missing, or fails checkout verification."""
    pass


class ClonerExecutionError(ClonerError):
    """Raised when external Git execution fails."""
    pass


class QuarantinedRepositoryMetadata(BaseModel):
    target_id: str
    repository_url: str
    commit_sha: str
    snapshot_hash: str
    file_manifest_hash: str
    quarantine_path: str
    file_count: int
    total_bytes: int
    trust: RepositoryTrust = RepositoryTrust.UNTRUSTED
    imported_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())


def _rmtree_readonly(path: str) -> None:
    """Safely cleans up directories with read-only files (common with Git objects on Windows)."""
    def _onerror(func, p, exc_info):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except Exception:
            pass

    try:
        shutil.rmtree(path, onerror=_onerror)
    except Exception:
        shutil.rmtree(path, ignore_errors=True)


def validate_ip_address(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
    """Enforces SSRF boundary checks on an IP address object."""
    # Check for IPv4-mapped IPv6 addresses (e.g. ::ffff:127.0.0.1)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        validate_ip_address(ip.ipv4_mapped)
        return

    if ip.is_loopback:
        raise ClonerSecurityError(f"Prohibited loopback destination: {ip}")
    if ip.is_private:
        raise ClonerSecurityError(f"Prohibited private IP destination: {ip}")
    if ip.is_link_local:
        raise ClonerSecurityError(f"Prohibited link-local destination (e.g. cloud metadata): {ip}")
    if ip.is_reserved:
        raise ClonerSecurityError(f"Prohibited reserved IP destination: {ip}")
    if ip.is_multicast:
        raise ClonerSecurityError(f"Prohibited multicast destination: {ip}")
    if ip.is_unspecified:
        raise ClonerSecurityError(f"Prohibited unspecified destination: {ip}")

    for net in PROHIBITED_NETWORKS:
        if ip in net:
            raise ClonerSecurityError(f"Prohibited destination IP in restricted network {net}: {ip}")

    # Cloud metadata address protection
    if str(ip) in {"169.254.169.254", "169.254.170.2", "fd00:ec2::254"}:
        raise ClonerSecurityError(f"Prohibited cloud metadata address: {ip}")


def resolve_and_validate_hostname(hostname: str) -> List[str]:
    """
    Resolves hostname to IP addresses and strictly validates that none of them
    point to private, loopback, link-local, multicast, or cloud metadata ranges.
    Fails closed if DNS resolution fails or if any IP is prohibited.
    """
    clean_host = hostname.strip().lower()
    if not clean_host:
        raise ClonerSecurityError("Repository URL host is empty.")

    if clean_host in DISALLOWED_HOSTNAMES:
        raise ClonerSecurityError(f"Prohibited hostname: '{clean_host}'.")

    for blocked_suffix in (".localhost", ".local", ".internal", ".corp", ".lan", ".onion"):
        if clean_host.endswith(blocked_suffix):
            raise ClonerSecurityError(f"Prohibited domain suffix in hostname: '{clean_host}'.")

    # If hostname is an IP literal:
    try:
        direct_ip = ipaddress.ip_address(clean_host)
        validate_ip_address(direct_ip)
        return [str(direct_ip)]
    except ValueError:
        pass

    try:
        addr_info = socket.getaddrinfo(clean_host, 443, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
    except Exception as exc:
        raise ClonerSecurityError(f"DNS resolution failed for '{clean_host}': {str(exc)}")

    if not addr_info:
        raise ClonerSecurityError(f"DNS resolution returned no addresses for '{clean_host}'.")

    resolved_ips = []
    for item in addr_info:
        ip_str = item[4][0]
        try:
            ip_obj = ipaddress.ip_address(ip_str)
            validate_ip_address(ip_obj)
            resolved_ips.append(ip_str)
        except ClonerSecurityError:
            raise
        except Exception as e:
            raise ClonerSecurityError(f"Invalid resolved IP '{ip_str}': {str(e)}")

    return resolved_ips


def validate_repository_url(url: str) -> urllib.parse.SplitResult:
    """
    Strictly validates a public HTTPS Git repository URL.
    Enforces scheme, credentials, port, path traversal, and SSRF restrictions.
    """
    if not url or not isinstance(url, str):
        raise ClonerSecurityError("Repository URL must be a non-empty string.")

    url = url.strip()
    if len(url) > 2048:
        raise ClonerSecurityError("Repository URL exceeds maximum allowed length of 2048 characters.")

    parsed = urllib.parse.urlsplit(url)

    if parsed.scheme.lower() != "https":
        raise ClonerSecurityError(
            f"Invalid URL scheme '{parsed.scheme}'. Only public HTTPS Git repositories ('https://') are permitted."
        )

    if parsed.username or parsed.password or "@" in (parsed.netloc or ""):
        raise ClonerSecurityError("Embedded credentials in repository URL are strictly prohibited.")

    if parsed.port and parsed.port not in (443,):
        raise ClonerSecurityError(f"Non-standard port '{parsed.port}' is prohibited. Only standard HTTPS (443) is allowed.")

    if not parsed.hostname:
        raise ClonerSecurityError("Repository URL missing hostname.")

    if ".." in parsed.path or "%2e%2e" in parsed.path.lower():
        raise ClonerSecurityError("Path traversal sequences in repository URL are strictly prohibited.")

    # DNS and SSRF enforcement
    resolve_and_validate_hostname(parsed.hostname)

    return parsed


def validate_commit_sha(commit_sha: str) -> str:
    """
    Validates that a commit reference is a full 40-char or 64-char hexadecimal Git commit SHA.
    Refuses snapshot labels, branch names, tags, and short SHAs.
    """
    if not commit_sha or not isinstance(commit_sha, str):
        raise ClonerCommitVerificationError("A commit SHA must be provided as a non-empty string.")

    sha = commit_sha.strip()
    if not COMMIT_SHA_PATTERN.match(sha):
        raise ClonerCommitVerificationError(
            f"Invalid commit reference '{sha}'. A full 40-character or 64-character Git commit SHA is required. "
            "Branch names, tags, and snapshot labels are not permitted for unverified remote repositories."
        )
    return sha.lower()


def inspect_and_enforce_workspace_limits(
    workspace_path: str,
    budget: ResourceBudget
) -> Tuple[int, int]:
    """
    Recursively scans workspace to enforce:
    1. No symlink escapes (pointing outside workspace or broken links).
    2. Total file count <= budget.max_repo_files.
    3. Total bytes <= budget.max_repo_bytes.
    4. Individual file size <= budget.max_file_size.
    Returns (file_count, total_bytes).
    """
    total_bytes = 0
    file_count = 0
    canonical_root = os.path.realpath(workspace_path)

    for root, dirs, files in os.walk(workspace_path, followlinks=False):
        for d in list(dirs):
            dir_path = os.path.join(root, d)
            if os.path.islink(dir_path):
                real_dir = os.path.realpath(dir_path)
                if not real_dir.startswith(canonical_root + os.sep) and real_dir != canonical_root:
                    raise ClonerSecurityError(f"Directory symlink escape detected: '{dir_path}' points to '{real_dir}' outside workspace.")

        for f in files:
            file_path = os.path.join(root, f)

            if os.path.islink(file_path):
                real_file = os.path.realpath(file_path)
                if not real_file.startswith(canonical_root + os.sep) and real_file != canonical_root:
                    raise ClonerSecurityError(f"Symlink escape detected: '{file_path}' points to '{real_file}' outside workspace.")
                if not os.path.exists(real_file):
                    raise ClonerSecurityError(f"Dangling symlink detected: '{file_path}'.")

            try:
                stat_res = os.lstat(file_path)
            except OSError as e:
                raise ClonerSecurityError(f"Failed to inspect file '{file_path}': {str(e)}")

            size = stat_res.st_size
            if size > budget.max_file_size:
                raise ClonerResourceLimitError(
                    f"File '{f}' exceeds max_file_size limit ({size} bytes > {budget.max_file_size} bytes limit)."
                )

            total_bytes += size
            file_count += 1

            if file_count > budget.max_repo_files:
                raise ClonerResourceLimitError(
                    f"Repository file count exceeds max_repo_files limit ({file_count} > {budget.max_repo_files} limit)."
                )

            if total_bytes > budget.max_repo_bytes:
                raise ClonerResourceLimitError(
                    f"Repository byte size exceeds max_repo_bytes limit ({total_bytes} bytes > {budget.max_repo_bytes} bytes limit)."
                )

    return file_count, total_bytes


def calculate_workspace_digests(workspace_path: str) -> Tuple[str, str]:
    """
    Calculates deterministic file_manifest_hash and snapshot_hash for a checked-out workspace.
    """
    all_files = []
    for root, _, files in os.walk(workspace_path):
        for file in files:
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, workspace_path).replace("\\", "/")
            all_files.append((rel_path, full_path))

    all_files.sort(key=lambda x: x[0])

    manifest_entries = []
    snapshot_entries = []

    for rel_path, full_path in all_files:
        try:
            with open(full_path, "rb") as f:
                content = f.read()
            file_hash = hashlib.sha256(content).hexdigest()
            manifest_entries.append(rel_path)
            snapshot_entries.append(f"{rel_path}:{file_hash}")
        except Exception:
            continue

    manifest_str = ",".join(manifest_entries)
    file_manifest_hash = hashlib.sha256(manifest_str.encode("utf-8")).hexdigest()

    snapshot_str = ",".join(snapshot_entries)
    snapshot_hash = hashlib.sha256(snapshot_str.encode("utf-8")).hexdigest()

    return snapshot_hash, file_manifest_hash


class QuarantinedRepositoryCloner:
    """
    Secure Quarantined Remote Repository Cloner.
    Performs bounded shallow checkout of public HTTPS Git repositories at a pinned commit SHA.
    Enforces SSRF boundaries, timeout limits, quarantine containment, and fail-closed security.
    """
    def __init__(self, quarantine_base: Optional[str] = None):
        if quarantine_base:
            self.quarantine_base = os.path.abspath(quarantine_base)
        else:
            self.quarantine_base = os.path.abspath(os.path.join("data", "quarantine"))
        os.makedirs(self.quarantine_base, exist_ok=True)

    def import_repository(
        self,
        url: str,
        commit_sha: str,
        budget: Optional[ResourceBudget] = None,
        timeout: Optional[int] = None
    ) -> QuarantinedRepositoryMetadata:
        budget = budget or ResourceBudget()
        exec_timeout = timeout or min(60, budget.max_runtime)

        # 1. Strictly validate URL & SSRF boundary
        validate_repository_url(url)

        # 2. Strictly validate commit SHA
        clean_sha = validate_commit_sha(commit_sha)

        # 3. Create isolated quarantine download workspace
        tmp_dir = tempfile.mkdtemp(prefix=".tmp_cloning_", dir=self.quarantine_base)

        try:
            safe_env = {
                **os.environ,
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_ASKPASS": "",
                "GIT_CONFIG_NOSYSTEM": "1",
            }

            # Initialize empty repo and disable hooks and redirects
            subprocess.run(["git", "init"], cwd=tmp_dir, check=True, capture_output=True, timeout=10)
            subprocess.run(["git", "config", "core.hooksPath", ""], cwd=tmp_dir, check=True, capture_output=True, timeout=10)
            subprocess.run(["git", "config", "http.followRedirects", "false"], cwd=tmp_dir, check=True, capture_output=True, timeout=10)
            subprocess.run(["git", "remote", "add", "origin", url], cwd=tmp_dir, check=True, capture_output=True, timeout=10)

            # Fetch exact commit SHA with bounded execution time
            fetch_res = subprocess.run(
                ["git", "fetch", "--depth", "1", "origin", clean_sha],
                cwd=tmp_dir,
                capture_output=True,
                timeout=exec_timeout,
                env=safe_env
            )
            if fetch_res.returncode != 0:
                # Fallback to bounded fetch if direct sha fetch is unsupported by server
                fallback_res = subprocess.run(
                    ["git", "fetch", "--depth", "50", "origin"],
                    cwd=tmp_dir,
                    capture_output=True,
                    timeout=exec_timeout,
                    env=safe_env
                )
                if fallback_res.returncode != 0:
                    err_msg = fetch_res.stderr.decode("utf-8", errors="replace").strip() or fallback_res.stderr.decode("utf-8", errors="replace").strip()
                    raise ClonerExecutionError(f"Git fetch failed for {url} at commit {clean_sha}: {err_msg}")

            # Checkout exact commit
            co_res = subprocess.run(
                ["git", "-c", "core.hooksPath=", "checkout", clean_sha],
                cwd=tmp_dir,
                capture_output=True,
                timeout=15,
                env=safe_env
            )
            if co_res.returncode != 0:
                err_msg = co_res.stderr.decode("utf-8", errors="replace").strip()
                raise ClonerCommitVerificationError(f"Git checkout failed for commit {clean_sha}: {err_msg}")

            # Verify checked out HEAD commit matches clean_sha exactly
            head_res = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=tmp_dir,
                capture_output=True,
                check=True,
                timeout=10
            )
            actual_sha = head_res.stdout.decode().strip().lower()
            if actual_sha != clean_sha:
                raise ClonerCommitVerificationError(f"Checked out commit mismatch: requested {clean_sha}, got {actual_sha}")

            # Remove .git directory so the quarantined snapshot cannot execute git hooks later
            git_dir = os.path.join(tmp_dir, ".git")
            if os.path.exists(git_dir):
                _rmtree_readonly(git_dir)

            # 4. Enforce workspace limits (file count, file size, total bytes, symlink escape)
            file_count, total_bytes = inspect_and_enforce_workspace_limits(tmp_dir, budget)

            # 5. Calculate source snapshot digest
            snapshot_hash, manifest_hash = calculate_workspace_digests(tmp_dir)

            # 6. Generate opaque target ID and move to permanent quarantine location
            target_id = f"repo-remote-{uuid.uuid4().hex[:12]}"
            final_path = os.path.join(self.quarantine_base, target_id)

            os.rename(tmp_dir, final_path)
            tmp_dir = None  # Successfully moved, clear so finally does not delete it

            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            meta = QuarantinedRepositoryMetadata(
                target_id=target_id,
                repository_url=url,
                commit_sha=actual_sha,
                snapshot_hash=snapshot_hash,
                file_manifest_hash=manifest_hash,
                quarantine_path=final_path,
                file_count=file_count,
                total_bytes=total_bytes,
                trust=RepositoryTrust.UNTRUSTED,
                imported_at=now_iso
            )

            # 7. Register target in RepositoryRegistry
            target = RepositoryTarget(
                repository_id=target_id,
                repo_root=final_path,
                trust=RepositoryTrust.UNTRUSTED,
                repository_url=url,
                commit_sha=actual_sha,
                snapshot_hash=snapshot_hash,
                file_manifest_hash=manifest_hash,
                file_count=file_count,
                total_bytes=total_bytes,
                is_quarantined=True,
                registered_at=now_iso
            )
            get_repository_registry().register(target)

            return meta

        except subprocess.TimeoutExpired as e:
            raise ClonerResourceLimitError(f"Git operation timed out after {exec_timeout} seconds.") from e
        except Exception:
            raise
        finally:
            if tmp_dir and os.path.exists(tmp_dir):
                _rmtree_readonly(tmp_dir)
