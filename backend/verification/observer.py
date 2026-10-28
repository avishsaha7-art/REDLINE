import re
from typing import Optional
from backend.sandbox.models import ExecutionResult
from backend.verification.models import (
    StructuredObservation,
    ExecutionStatus,
    TestResultSummary,
    TestObservation,
    TestStatus
)

class DeterministicVerificationObserver:
    def observe_execution(self, result: ExecutionResult, workspace_id: str, repository_snapshot_hash: str, patch_hash: str) -> StructuredObservation:
        # Determine exit code logic
        status = ExecutionStatus.SUCCESS
        if getattr(result, "policy_blocked", False):
            status = ExecutionStatus.POLICY_BLOCKED
        elif result.timed_out:
            status = ExecutionStatus.TIMEOUT
        elif getattr(result, "crashed", False) or (result.exit_code is not None and result.exit_code < 0):
            # E.g. signal kills
            status = ExecutionStatus.EXECUTION_FAILURE
        elif getattr(result, "resource_limited", False) or result.stdout_truncated or result.stderr_truncated:
            status = ExecutionStatus.RESOURCE_LIMIT
        elif result.exit_code != 0:
            status = ExecutionStatus.NONZERO

        backend_prov = getattr(result, "backend_provenance", {})
        backend_name = (
            backend_prov.get("backend")
            or backend_prov.get("backend_name")
            or backend_prov.get("backend_type")
            or "UNKNOWN"
        )
        
        return StructuredObservation(
            execution_id=result.run_id,
            command_identifier=" ".join(result.command_metadata) if hasattr(result, "command_metadata") else "",
            exit_code=result.exit_code,
            stdout_sha256=result.stdout_sha256,
            stderr_sha256=result.stderr_sha256,
            stdout_bytes=len(result.stdout.encode('utf-8')),
            stderr_bytes=len(result.stderr.encode('utf-8')),
            duration_ms=result.runtime_ms,
            status=status,
            sandbox_backend=backend_name,
            security_level=backend_prov.get("security_level", "UNKNOWN"),
            capabilities=backend_prov.get("capabilities", {}),
            workspace_id=workspace_id,
            repository_snapshot_hash=repository_snapshot_hash,
            patch_hash=patch_hash
        )

    def observe_tests(self, result: ExecutionResult) -> TestResultSummary:
        stdout = result.stdout
        summary = TestResultSummary()
        
        if result.timed_out or getattr(result, "policy_blocked", False) or result.stdout_truncated:
            summary.inconclusive = 1
            summary.executed = 1
            summary.discovered = 1
            return summary
            
        passed_m = re.search(r'(\d+)\s+passed', stdout)
        failed_m = re.search(r'(\d+)\s+failed', stdout)
        error_m = re.search(r'(\d+)\s+error', stdout)
        skipped_m = re.search(r'(\d+)\s+skipped', stdout)
        collected_m = re.search(r'collected (\d+) items?', stdout)
        
        passed = int(passed_m.group(1)) if passed_m else 0
        failed = int(failed_m.group(1)) if failed_m else 0
        errored = int(error_m.group(1)) if error_m else 0
        skipped = int(skipped_m.group(1)) if skipped_m else 0
        
        # unittest regex support: "Ran X test(s) ... OK" / "FAILED"
        if not passed_m and not failed_m and not error_m:
            ran_m = re.search(r'Ran (\d+) test', stdout)
            if ran_m:
                total_ran = int(ran_m.group(1))
                if 'OK' in stdout:
                    passed = total_ran
                elif 'FAILED' in stdout:
                    failed = total_ran

        # Fail closed: if exit code != 0 and no failures were parsed, test harness errored/crashed
        if result.exit_code != 0 and passed == 0 and failed == 0 and errored == 0:
            errored = 1
        
        summary.passed = passed
        summary.failed = failed
        summary.errored = errored
        summary.skipped = skipped
        summary.executed = passed + failed + errored
        discovered = int(collected_m.group(1)) if collected_m else (summary.executed + skipped)
        summary.discovered = max(discovered, summary.executed + skipped)
        
        # If exit code is 0 but we found no tests, it's INCONCLUSIVE
        # If exit code is 0 and we found tests, it's successfully parsed
        if summary.executed == 0 and result.exit_code == 0:
            summary.inconclusive = 1
            summary.executed = 1
            summary.discovered = max(summary.discovered, 1)
            
        return summary
