from typing import Any, Optional, List, Dict
from backend.models.schemas import RunState, OperationalResult, TaskContract
from backend.orchestrator.transition_policy import TransitionPolicy
from backend.orchestrator.limits import GovernanceController
from backend.orchestrator.events import EventRecorder

class StateMachine:
    def __init__(self, run_id: str, task_contract: TaskContract):
        self.run_id = run_id
        self.task_contract = task_contract
        self.current_state = RunState.INIT
        self.transition_policy = TransitionPolicy()
        self.governance = GovernanceController(task_contract.resource_budget)
        self.events = EventRecorder(run_id)
        self.operational_result: Optional[OperationalResult] = None
        
    def advance(self, event_or_result: Any) -> RunState:
        # Check budget limits first
        if self.governance.is_exhausted():
            return self._abort(OperationalResult.RESOURCE_LIMIT, "Resource budget exhausted")
            
        # Terminal states block further advancement
        if self.current_state in (RunState.VERIFIED, RunState.ABORTED):
            return self.current_state
            
        # Query deterministic transition policy
        next_state = self.transition_policy.get_next_state(self.current_state, event_or_result)
        
        # If transition leads to ABORTED:
        if next_state == RunState.ABORTED:
            # 1. Operational failure result
            if isinstance(event_or_result, OperationalResult):
                return self._abort(event_or_result, str(event_or_result.value))
                
            # 2. Planned deterministic non-operational verification conclusions
            #    (e.g., UNREPAIRABLE from ANALYZE, or JUDGE_FAIL from JUDGE)
            if (self.current_state == RunState.ANALYZE and event_or_result == "UNREPAIRABLE") or \
               (self.current_state == RunState.JUDGE and event_or_result == "JUDGE_FAIL"):
                self._record_transition(next_state, event_or_result)
                self.current_state = next_state
                return self.current_state
                
            # 3. Fail closed: illegal or unexpected event/result rejected by policy
            return self._abort(OperationalResult.POLICY_BLOCKED, "Transition policy rejected the event/result")
            
        self._record_transition(next_state, event_or_result)
        self.current_state = next_state
        return self.current_state

    def _abort(self, result: OperationalResult, reason: str) -> RunState:
        self.current_state = RunState.ABORTED
        self.operational_result = result
        self.events.record_event("RUN_ABORTED", {"result": result.value, "reason": reason})
        return self.current_state

    def _record_transition(self, new_state: RunState, payload: Optional[Any]):
        self.events.record_event(f"{new_state.value}_STARTED", {"payload_type": type(payload).__name__})
        if new_state in (RunState.VERIFIED, RunState.ABORTED):
            self.events.record_event(f"{new_state.value}_COMPLETED")

    def increment_iteration(self) -> None:
        self.governance.increment_iteration()

    def increment_tool_calls(self) -> None:
        self.governance.increment_tool_calls()