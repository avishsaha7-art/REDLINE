from enum import Enum
from pydantic import BaseModel

class SecurityLevel(str, Enum):
    SECURE = "SECURE"
    DEVELOPMENT_ONLY = "DEVELOPMENT_ONLY"
    UNAVAILABLE = "UNAVAILABLE"

class RepositoryTrust(str, Enum):
    UNTRUSTED = "UNTRUSTED"
    TRUSTED_DEVELOPMENT = "TRUSTED_DEVELOPMENT"

class SandboxCapabilities(BaseModel):
    security_level: SecurityLevel = SecurityLevel.DEVELOPMENT_ONLY
    filesystem_isolation: str = "NOT_AVAILABLE"
    process_isolation: str = "NOT_AVAILABLE"
    network_isolation: str = "NOT_AVAILABLE"
    credential_isolation: str = "ENFORCED"
    resource_enforcement: str = "SUPPORTED"
    timeout_enforcement: str = "ENFORCED"
    workspace_isolation: str = "ENFORCED"
    cleanup_guarantee: str = "ENFORCED"
    secure_untrusted_execution: bool = False
