import os
import shutil
import tempfile
import socket
import pytest
from unittest.mock import patch, MagicMock

from backend.sandbox.cloner import (
    QuarantinedRepositoryCloner,
    ClonerError,
    ClonerSecurityError,
    ClonerResourceLimitError,
    ClonerCommitVerificationError,
    ClonerExecutionError,
    validate_repository_url,
    validate_commit_sha,
    resolve_and_validate_hostname,
    inspect_and_enforce_workspace_limits,
)
from backend.models.schemas import ResourceBudget
from backend.sandbox.capabilities import RepositoryTrust


# ==============================================================================
# URL Syntax & Scheme Validation Tests
# ==============================================================================

def test_valid_public_https_url_syntax():
    """Valid public HTTPS repository URLs pass syntax and scheme validation."""
    with patch("backend.sandbox.cloner.resolve_and_validate_hostname", return_value=["93.184.216.34"]):
        parsed = validate_repository_url("https://github.com/example-owner/example-repo.git")
        assert parsed.scheme == "https"
        assert parsed.hostname == "github.com"


def test_invalid_schemes_rejected():
    """Non-HTTPS schemes (http, git, ssh, file, ftp) are strictly rejected."""
    disallowed_urls = [
        "http://github.com/owner/repo.git",
        "git://github.com/owner/repo.git",
        "ssh://git@github.com/owner/repo.git",
        "file:///etc/passwd",
        "ftp://github.com/owner/repo.git",
        "gopher://github.com/owner/repo",
    ]
    for url in disallowed_urls:
        with pytest.raises(ClonerSecurityError, match="Invalid URL scheme|Only public HTTPS"):
            validate_repository_url(url)


def test_embedded_credentials_rejected():
    """URLs with embedded credentials or tokens are strictly rejected."""
    urls_with_creds = [
        "https://username:password@github.com/owner/repo.git",
        "https://ghp_token123456@github.com/owner/repo.git",
        "https://user@github.com/owner/repo.git",
    ]
    for url in urls_with_creds:
        with pytest.raises(ClonerSecurityError, match="Embedded credentials"):
            validate_repository_url(url)


def test_non_standard_port_rejected():
    """Non-standard ports (e.g. 8080, 22, 8443) are rejected to prevent port probing."""
    with pytest.raises(ClonerSecurityError, match="Non-standard port"):
        validate_repository_url("https://github.com:8443/owner/repo.git")


def test_path_traversal_in_url_rejected():
    """Path traversal sequences in repository URLs are strictly rejected."""
    bad_urls = [
        "https://github.com/owner/repo/../../etc/passwd",
        "https://github.com/owner/repo/%2e%2e/forbidden",
    ]
    for url in bad_urls:
        with pytest.raises(ClonerSecurityError, match="Path traversal"):
            validate_repository_url(url)


# ==============================================================================
# SSRF, DNS & Destination IP Tests
# ==============================================================================

def test_localhost_and_loopback_destinations_rejected():
    """Localhost and loopback destinations (127.0.0.1, ::1) are strictly rejected."""
    for host in ("localhost", "127.0.0.1", "127.0.0.2", "::1"):
        with pytest.raises(ClonerSecurityError, match="Prohibited.*(destination|IP|hostname|loopback|private)"):
            resolve_and_validate_hostname(host)


def test_private_rfc1918_destinations_rejected():
    """Private RFC 1918 IP addresses are rejected."""
    private_ips = ["10.0.0.1", "172.16.0.1", "192.168.1.1", "100.64.0.1"]
    for ip in private_ips:
        with pytest.raises(ClonerSecurityError, match="Prohibited private IP|restricted network"):
            resolve_and_validate_hostname(ip)


def test_cloud_metadata_destinations_rejected():
    """AWS, GCP, and Azure cloud metadata endpoints are strictly rejected."""
    metadata_destinations = ["169.254.169.254", "metadata.google.internal", "instance-data"]
    for dest in metadata_destinations:
        with pytest.raises(ClonerSecurityError, match="Prohibited"):
            resolve_and_validate_hostname(dest)


def test_dns_rebinding_to_private_ip_rejected():
    """A hostname resolving to an internal private IP address fails closed."""
    with patch("socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.50", 443))]):
        with pytest.raises(ClonerSecurityError, match="Prohibited private IP"):
            resolve_and_validate_hostname("legitimate-looking-domain.com")


def test_dns_resolution_failure_fails_closed():
    """Failed DNS resolution fails closed with ClonerSecurityError."""
    with patch("socket.getaddrinfo", side_effect=socket.gaierror("Name or service not known")):
        with pytest.raises(ClonerSecurityError, match="DNS resolution failed"):
            resolve_and_validate_hostname("nonexistent.unresolvable.example")


# ==============================================================================
# Commit Reference Verification Tests
# ==============================================================================

def test_commit_sha_validation_strict():
    """Commit validation strictly accepts 40-char/64-char hex SHAs and rejects branches/tags/labels."""
    # Valid 40-char SHA
    valid_40 = "a" * 40
    assert validate_commit_sha(valid_40) == valid_40

    # Valid 64-char SHA (SHA-256 repos)
    valid_64 = "f" * 64
    assert validate_commit_sha(valid_64) == valid_64

    # Invalid references: branch names, tags, snapshot labels, short SHAs
    invalid_refs = [
        "main",
        "master",
        "v1.0.0",
        "snap-demo-a",
        "123456",
        "HEAD",
        "feature/fix-bug",
        "a" * 39,
        "g" * 40,  # Non-hex characters
        "",
        "   ",
    ]
    for ref in invalid_refs:
        with pytest.raises(ClonerCommitVerificationError, match="Invalid commit reference|full 40-character|must be provided as a non-empty string"):
            validate_commit_sha(ref)


# ==============================================================================
# Workspace Limits & Symlink Escape Tests
# ==============================================================================

def test_symlink_escape_pointing_outside_workspace_rejected(tmp_path):
    """Symlinks pointing outside the quarantined workspace are detected and blocked."""
    outside_file = tmp_path / "secret.txt"
    outside_file.write_text("secret")

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "valid.py").write_text("print('hello')")

    # Create escaping symlink
    symlink_file = workspace / "escape.txt"
    try:
        os.symlink(str(outside_file), str(symlink_file))
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation not supported on this OS/user privilege level")

    budget = ResourceBudget()
    with pytest.raises(ClonerSecurityError, match="Symlink escape detected"):
        inspect_and_enforce_workspace_limits(str(workspace), budget)


def test_oversized_repository_bytes_limit(tmp_path):
    """Repository exceeding max_repo_bytes raises ClonerResourceLimitError."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "large_file.dat").write_bytes(b"A" * 500)

    # Budget with max 200 bytes
    budget = ResourceBudget(max_repo_bytes=200, max_file_size=1000)
    with pytest.raises(ClonerResourceLimitError, match="Repository byte size exceeds max_repo_bytes"):
        inspect_and_enforce_workspace_limits(str(workspace), budget)


def test_excessive_file_count_limit(tmp_path):
    """Repository exceeding max_repo_files raises ClonerResourceLimitError."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    for i in range(10):
        (workspace / f"f_{i}.txt").write_text("hello")

    # Budget with max 5 files
    budget = ResourceBudget(max_repo_files=5)
    with pytest.raises(ClonerResourceLimitError, match="Repository file count exceeds max_repo_files"):
        inspect_and_enforce_workspace_limits(str(workspace), budget)


def test_oversized_individual_file_limit(tmp_path):
    """Individual file exceeding max_file_size raises ClonerResourceLimitError."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "big.py").write_bytes(b"X" * 1500)

    # Budget with max 1000 bytes per file
    budget = ResourceBudget(max_file_size=1000, max_repo_bytes=10000)
    with pytest.raises(ClonerResourceLimitError, match="exceeds max_file_size limit"):
        inspect_and_enforce_workspace_limits(str(workspace), budget)


# ==============================================================================
# Cloner Integration & Cleanup Tests
# ==============================================================================

def test_clone_failure_cleans_up_quarantine_temp_dir(tmp_path):
    """If a Git clone operation fails, temporary download directories are completely removed."""
    cloner = QuarantinedRepositoryCloner(quarantine_base=str(tmp_path / "quarantine"))
    target_sha = "a" * 40

    with patch("backend.sandbox.cloner.validate_repository_url"), \
         patch("subprocess.run") as mock_subproc:
        # Mock git fetch failing
        mock_subproc.return_value = MagicMock(returncode=128, stderr=b"fatal: repository not found")

        with pytest.raises(ClonerExecutionError, match="Git fetch failed"):
            cloner.import_repository("https://github.com/example/repo.git", target_sha)

    # Ensure no lingering .tmp_cloning_ directories remain in quarantine base
    lingering = [d for d in os.listdir(cloner.quarantine_base) if d.startswith(".tmp_cloning_")]
    assert len(lingering) == 0, f"Found lingering temporary directories: {lingering}"


def test_successful_mock_import_returns_untrusted_metadata(tmp_path):
    """A verified clone produces an opaque target ID and strictly UNTRUSTED trust status."""
    cloner = QuarantinedRepositoryCloner(quarantine_base=str(tmp_path / "quarantine"))
    target_sha = "b" * 40

    def fake_subprocess_run(cmd, *args, **kwargs):
        cwd = kwargs.get("cwd")
        if "init" in cmd:
            return MagicMock(returncode=0)
        elif "config" in cmd:
            return MagicMock(returncode=0)
        elif "remote" in cmd:
            return MagicMock(returncode=0)
        elif "fetch" in cmd:
            return MagicMock(returncode=0)
        elif "checkout" in cmd:
            # Create a dummy file in the checked-out workspace
            if cwd:
                with open(os.path.join(cwd, "main.py"), "w") as f:
                    f.write("print('safe code')\n")
            return MagicMock(returncode=0)
        elif "rev-parse" in cmd:
            return MagicMock(returncode=0, stdout=target_sha.encode())
        return MagicMock(returncode=0)

    with patch("backend.sandbox.cloner.validate_repository_url"), \
         patch("subprocess.run", side_effect=fake_subprocess_run):

        meta = cloner.import_repository(
            url="https://github.com/example/safe-repo.git",
            commit_sha=target_sha
        )

        assert meta.target_id.startswith("repo-remote-")
        assert meta.commit_sha == target_sha
        assert meta.trust == RepositoryTrust.UNTRUSTED
        assert meta.file_count == 1
        assert meta.total_bytes > 0
        assert os.path.isdir(meta.quarantine_path)
        assert os.path.exists(os.path.join(meta.quarantine_path, "main.py"))
        # Ensure .git directory was stripped
        assert not os.path.exists(os.path.join(meta.quarantine_path, ".git"))
