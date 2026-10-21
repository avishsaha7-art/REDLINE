"""
Authoritative Sandbox Backend Factory for REDLINE.

Enforces strict separation between trusted-development host execution
and untrusted production container execution.
"""
from typing import Optional, Union
from backend.sandbox.models import SandboxPolicy
from backend.sandbox.capabilities import RepositoryTrust
from backend.sandbox.backend import SandboxBackend, LocalDevelopmentBackend
from backend.sandbox.secure_backend import SecureSandboxBackend, ContainerRuntimeProbe
from backend.sandbox.trust import is_local_backend_enabled


class SandboxFactoryError(Exception):
    """Raised when sandbox backend selection or instantiation fails closed."""
    pass


def get_sandbox_backend(
    policy: Optional[SandboxPolicy] = None,
    repository_trust: Optional[Union[RepositoryTrust, str]] = None,
    runtime_probe: Optional[ContainerRuntimeProbe] = None,
    container_image: Optional[str] = None,
) -> SandboxBackend:
    """
    Authoritative factory for resolving the appropriate SandboxBackend.

    Guarantees:
    1. Untrusted workloads ALWAYS select SecureSandboxBackend.
       Untrusted workloads NEVER receive LocalDevelopmentBackend under ANY circumstance.
    2. Trusted development workloads may select LocalDevelopmentBackend ONLY IF:
       a) repository_trust is authoritatively resolved as TRUSTED_DEVELOPMENT, AND
       b) local backend execution is explicitly enabled (e.g. REDLINE_ENABLE_LOCAL_BACKEND=1).
       If local execution is disabled, SecureSandboxBackend is selected instead.
    3. Missing or unavailable container runtime results in a truthful fail-closed
       operational error within SecureSandboxBackend; there is NO host fallback.
    4. An environment flag alone (REDLINE_ENABLE_LOCAL_BACKEND=1) is INSUFFICIENT
       to grant host execution to untrusted or unknown repositories.
    """
    resolved_policy = policy or SandboxPolicy()

    # Normalize trust classification
    if isinstance(repository_trust, RepositoryTrust):
        trust_enum = repository_trust
    elif isinstance(repository_trust, str):
        if repository_trust == RepositoryTrust.TRUSTED_DEVELOPMENT.value or repository_trust == "TRUSTED_DEVELOPMENT":
            trust_enum = RepositoryTrust.TRUSTED_DEVELOPMENT
        else:
            trust_enum = RepositoryTrust.UNTRUSTED
    else:
        trust_enum = RepositoryTrust.UNTRUSTED

    # Invariant 1: UNTRUSTED workloads MUST ALWAYS receive SecureSandboxBackend
    if trust_enum != RepositoryTrust.TRUSTED_DEVELOPMENT:
        kwargs = {}
        if container_image:
            kwargs["container_image"] = container_image
        if runtime_probe:
            kwargs["runtime_probe"] = runtime_probe
        return SecureSandboxBackend(policy=resolved_policy, **kwargs)

    # Invariant 2: Trusted development path requires explicit opt-in
    if is_local_backend_enabled():
        return LocalDevelopmentBackend(policy=resolved_policy)

    # Invariant 3: If local backend execution is not enabled, route trusted development
    # to SecureSandboxBackend (fails closed safely if no container engine is present).
    kwargs = {}
    if container_image:
        kwargs["container_image"] = container_image
    if runtime_probe:
        kwargs["runtime_probe"] = runtime_probe
    return SecureSandboxBackend(policy=resolved_policy, **kwargs)
