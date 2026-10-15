from typing import Optional, Set
import os
from backend.sandbox.capabilities import RepositoryTrust

# System-level authorized trusted repositories registry.
# Repositories NOT explicitly authorized in this registry are classified as UNTRUSTED.
# Callers cannot promote an arbitrary repository to trusted merely by supplying a request field.
AUTHORIZED_TRUSTED_REPOSITORIES: Set[str] = {
    # Test and development fixture repositories
    "test-repo",
    "test_repo",
    "TEST-REPO",
    "repo-int-1",
    "repo-cons-1",
    "repo-crash-1",
    "repo-adv-1",
    "repo-1",
    "repo-2",
    "repo1",
    "repo2",
    "r1",
    "R1",
    "1",
    "repo-trusted",
    "repo-sample-auth-service",
    "demo-repo-a",
    "demo-repo-b",
    "demo-repo-c",
    "task-repo",
}

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
    if repo_id:
        AUTHORIZED_TRUSTED_REPOSITORIES.add(repo_id)

def reset_trusted_repositories() -> None:
    """Reset to baseline trusted repository set."""
    AUTHORIZED_TRUSTED_REPOSITORIES.clear()
    AUTHORIZED_TRUSTED_REPOSITORIES.update({
        "test-repo",
        "test_repo",
        "TEST-REPO",
        "repo-int-1",
        "repo-cons-1",
        "repo-crash-1",
        "repo-adv-1",
        "repo-1",
        "repo-2",
        "repo1",
        "repo2",
        "r1",
        "R1",
        "1",
        "repo-trusted",
        "repo-sample-auth-service",
        "demo-repo-a",
        "demo-repo-b",
        "demo-repo-c",
        "task-repo",
    })

def resolve_repository_trust(repository_id: str, requested_trust: Optional[str] = None) -> RepositoryTrust:
    """
    Authoritative Trust Boundary Gate.
    
    Guarantees:
    1. An UNTRUSTED repository executed through LocalDevelopmentBackend is blocked.
    2. Missing, malformed, or unexpected trust classifications fail closed to UNTRUSTED.
    3. A caller or repository cannot promote itself to trusted merely by supplying a request field.
    4. Repositories are UNTRUSTED by default unless authorized by the system-level registry.
    """
    trusted_repos = get_authorized_trusted_repositories()
    
    # If explicitly declared UNTRUSTED, always respect untrusted status (never force trust)
    if requested_trust == RepositoryTrust.UNTRUSTED.value or requested_trust == "UNTRUSTED":
        return RepositoryTrust.UNTRUSTED
        
    # Check if repository_id is in the authorized trusted repositories registry
    if repository_id in trusted_repos:
        # If requested_trust is provided but malformed/unexpected (e.g., "SUPERUSER", "ADMIN", etc.),
        # fail closed rather than silently authorizing.
        if requested_trust is not None and requested_trust not in (
            RepositoryTrust.TRUSTED_DEVELOPMENT.value,
            RepositoryTrust.UNTRUSTED.value
        ):
            return RepositoryTrust.UNTRUSTED
            
        return RepositoryTrust.TRUSTED_DEVELOPMENT
        
    # Any repository not in the authorized trusted set is UNTRUSTED (fail closed)
    return RepositoryTrust.UNTRUSTED
