from typing import Dict, List, Optional
from .security_models import (
    SecurityTestSpec,
    SecurityTestCategory,
    SecurityTestSeverity,
    SecurityTestStatus
)

class SecurityTestCatalog:
    def __init__(self):
        self._tests: Dict[str, SecurityTestSpec] = {}
        self._register_default_tests()

    def _register_default_tests(self):
        # 1. Path Traversal
        self.register(SecurityTestSpec(
            attack_id="PATH_TRAVERSAL",
            name="Path Traversal Escapes Workspace",
            category=SecurityTestCategory.PATH_TRAVERSAL,
            description="Attempt to read/write outside the designated workspace using ../ sequences.",
            severity=SecurityTestSeverity.HIGH,
            preconditions=[],
            input_fixture="path_traversal.patch",
            expected_security_invariant="FILESYSTEM_ISOLATION",
            resource_budget=1024 * 1024,
            clean_state_required=True,
            deterministic=True,
            version="1.0",
            status=SecurityTestStatus.NOT_AVAILABLE  # Blocked because LocalDevelopmentBackend cannot securely run untrusted tests
        ))
        
        # 2. Evidence Tampering
        self.register(SecurityTestSpec(
            attack_id="EVIDENCE_TAMPERING",
            name="Tamper with Verification Evidence",
            category=SecurityTestCategory.EVIDENCE_TAMPERING,
            description="Attempt to forge or alter security test output in stdout to trick verification.",
            severity=SecurityTestSeverity.CRITICAL,
            preconditions=[],
            input_fixture="fake_evidence.patch",
            expected_security_invariant="EVIDENCE_INTEGRITY",
            resource_budget=1024 * 1024,
            clean_state_required=True,
            deterministic=True,
            version="1.0",
            status=SecurityTestStatus.IMPLEMENTED
        ))
        
        # 3. Process Escape
        self.register(SecurityTestSpec(
            attack_id="PROCESS_ESCAPE",
            name="Process Escape via Fork/Exec",
            category=SecurityTestCategory.ISOLATION_ESCAPE,
            description="Attempt to spawn independent processes outside the sandbox policy.",
            severity=SecurityTestSeverity.CRITICAL,
            preconditions=[],
            input_fixture="process_escape.patch",
            expected_security_invariant="PROCESS_ISOLATION",
            resource_budget=1024 * 1024,
            clean_state_required=True,
            deterministic=True,
            version="1.0",
            status=SecurityTestStatus.NOT_AVAILABLE
        ))
        
        # 4. Resource Exhaustion
        self.register(SecurityTestSpec(
            attack_id="RESOURCE_EXHAUSTION",
            name="Memory and Output Bomb",
            category=SecurityTestCategory.RESOURCE_EXHAUSTION,
            description="Attempt to exhaust memory or generate infinite stdout to crash observer.",
            severity=SecurityTestSeverity.MEDIUM,
            preconditions=[],
            input_fixture="resource_exhaustion.patch",
            expected_security_invariant="RESOURCE_LIMIT",
            resource_budget=1024 * 1024,
            clean_state_required=True,
            deterministic=True,
            version="1.0",
            status=SecurityTestStatus.IMPLEMENTED
        ))

    def register(self, spec: SecurityTestSpec):
        self._tests[spec.attack_id] = spec

    def get_test(self, attack_id: str) -> Optional[SecurityTestSpec]:
        return self._tests.get(attack_id)
        
    def get_all_tests(self) -> List[SecurityTestSpec]:
        return list(self._tests.values())
