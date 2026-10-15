from typing import Any
from backend.models.schemas import RunState, OperationalResult, ArchitectPlan, PatchCandidate

class TransitionPolicy:
    def get_next_state(self, current_state: RunState, result: Any) -> RunState:
        # 1. Operational failures lead directly to ABORTED
        if isinstance(result, OperationalResult):
            return RunState.ABORTED

        # 2. Map current state + deterministic result to next state
        if current_state == RunState.INIT:
            if result == "TASK_ACCEPTED":
                return RunState.RECON
                
        elif current_state == RunState.RECON:
            if result == "RECON_COMPLETE":
                return RunState.PLAN
                
        elif current_state == RunState.PLAN:
            # We require a structured ArchitectPlan payload
            if isinstance(result, ArchitectPlan):
                return RunState.BASELINE
                
        elif current_state == RunState.BASELINE:
            if result == "BASELINE_READY":
                return RunState.BUILD
                
        elif current_state == RunState.BUILD:
            # We require a structured PatchCandidate payload
            if isinstance(result, PatchCandidate):
                return RunState.TEST
                
        elif current_state == RunState.TEST:
            if result == "TEST_SUCCESS":
                return RunState.ATTACK
            elif result == "TEST_FAILED":
                return RunState.ANALYZE
                
        elif current_state == RunState.ATTACK:
            if result == "ATTACK_SUCCESS":
                return RunState.VERIFY
            elif result == "ATTACK_FAILED":
                return RunState.ANALYZE
                
        elif current_state == RunState.ANALYZE:
            if result == "NEEDS_REPAIR":
                return RunState.REPAIR
            elif result == "UNREPAIRABLE":
                return RunState.ABORTED
                
        elif current_state == RunState.REPAIR:
            if isinstance(result, PatchCandidate):
                return RunState.TEST
                
        elif current_state == RunState.VERIFY:
            if result in ("VERIFY_SUCCESS", "VERIFY_INCONCLUSIVE"):
                return RunState.JUDGE
            elif result == "VERIFY_FAILED":
                return RunState.ANALYZE
                
        elif current_state == RunState.JUDGE:
            if result == "JUDGE_PASS":
                return RunState.VERIFIED
            elif result == "JUDGE_FAIL":
                return RunState.ABORTED

        # Fail closed: reject unknown states/events
        return RunState.ABORTED