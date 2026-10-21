from typing import Optional, Set
import os
from backend.sandbox.capabilities import RepositoryTrust

# System-level authorized trusted repositories registry.
# Repositories NOT explicitly authorized in this registry are classified as UNTRUSTED.
# Generic names (1, r1, repo-1, task-repo, etc.) are strictly excluded.
AUTHORIZED_TRUSTED_REPOSITORIES: Set[str] = {
    # Specifically designated internal development & demo fixture repositories
    "repo-int-1",
    "repo-cons-1",
    "repo-crash-1",
    "repo-adv-1",
    "repo-trusted",
    "repo-sample-auth-service",
    "demo-repo-a",
    "demo-repo-b",
    "demo-repo-c",
}

_local_backend_override: Optional[bool] = None


def is_local_backend_enabled() -> bool:
    """
    Checks whether local host execution via LocalDevelopmentBackend is explicitly enabled.
    Requires REDLINE_ENABLE_LOCAL_BACKEND=1 (or 'true', 'yes', 'on') in the environment,
    or programmatic test override via set_local_backend_override().
    """
    global _local_backend_override
    if _local_backend_override is not None:
        return _local_backend_override
    val = os.environ.get("REDLINE_ENABLE_LOCAL_BACKEND", "").strip().lower()
    return val in ("1", "true", "yes", "on")


def set_local_backend_override(enabled: Optional[bool]) -> None:
    """Sets a programmatic override for local backend enablement (primarily for test fixtures)."""
    global _local_backend_override
    _local_backend_override = enabled


def get_authorized_trusted_repositories() -> Set[str]:
    """
    Returns the set of repositories authorized for TRUSTED_DEVELOPMENT execution.
    Can be augmented via the REDLINE_TRUSTED_REPOSITORIES environment variable.
    """
    extra = os.environ.get("REDLINE_TRUSTED_REPOSITORIES", "")
    if extra:
        extra_set = {r.strip() for r in extra.split(",") if r.strip()}
        return AUTHORIZED_TRUSTED_REPOSITORIES | extra_set
    return AUTHORIZED_TRUSTED_REPOSITORIES


def register_trusted_repository(repo_id: str) -> None:
    """Dynamically register a trusted repository for testing/local setups."""
    if repo_id and isinstance(repo_id, str):
        AUTHORIZED_TRUSTED_REPOSITORIES.add(repo_id.strip())


def reset_trusted_repositories() -> None:
    """Reset to baseline hardened trusted repository set."""
    AUTHORIZED_TRUSTED_REPOSITORIES.clear()
    AUTHORIZED_TRUSTED_REPOSITORIES.update({
        "repo-int-1",
        "repo-cons-1",
        "repo-crash-1",
        "repo-adv-1",
        "repo-trusted",
        "repo-sample-auth-service",
        "demo-repo-a",
        "demo-repo-b",
        "demo-repo-c",
    })


def resolve_repository_trust(repository_id: str, requested_trust: Optional[str] = None) -> RepositoryTrust:
    """
    Authoritative Trust Boundary Gate.
    
    Guarantees:
    1. An UNTRUSTED repository executed through LocalDevelopmentBackend is blocked.
    2. Missing, malformed, or unexpected trust classifications fail closed to UNTRUSTED.
    3. A caller or repository cannot promote itself to trusted merely by supplying a request field.
    4. Repositories are UNTRUSTED by default unless authorized by the system-level registry.
    5. Ambiguous, empty, or whitespace repository IDs default to UNTRUSTED.
    """
    if not repository_id or not isinstance(repository_id, str) or not repository_id.strip():
        return RepositoryTrust.UNTRUSTED

    clean_repo = repository_id.strip()
    trusted_repos = get_authorized_trusted_repositories()
    
    # If explicitly declared UNTRUSTED, always respect untrusted status (never force trust)
    if requested_trust == RepositoryTrust.UNTRUSTED.value or requested_trust == "UNTRUSTED":
        return RepositoryTrust.UNTRUSTED
        
    # Check if repository_id is in the authorized trusted repositories registry
    if clean_repo in trusted_repos:
        # If requested_trust is provided but malformed/unexpected (e.g., "SUPERUSER", "ADMIN", etc.),
        # fail closed rather than silently authorizing.
        if requested_trust is not None and requested_trust not in (
            RepositoryTrust.TRUSTED_DEVELOPMENT.value,
            RepositoryTrust.UNTRUSTED.value
        ):
            return RepositoryTrust.UNTRUSTED
            
        return RepositoryTrust.TRUSTED_DEVELOPMENT
        
    # Any repository not in the authorized trusted set is UNTRUSTED (fail closed).
    # Client-supplied trust strings (e.g. TRUSTED_DEVELOPMENT) cannot independently grant trust.
    return RepositoryTrust.UNTRUSTED
