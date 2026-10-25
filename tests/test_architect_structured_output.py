"""
Step 2.9.6.4 Regression Tests: Architect Structured-Output Remediation.

Validates that:
1. Valid JSON plan with list fields is accepted.
2. List fields returned as strings are normalized safely without weakening the schema.
3. Malformed JSON fails closed to MODEL_FAILURE.
4. Missing required fields fails closed to MODEL_FAILURE.
5. Unexpected / extra fields are strictly forbidden and fail closed.
6. Empty or structurally invalid plans fail closed.
7. Provider timeout or request failure fails closed.
8. Invalid Architect output never reaches Builder patch application or Sandbox execution.
9. A failed run cannot receive a VERIFIED verdict.
10. Evidence receipt integrity is preserved on failure.
"""

import json
import time
import pytest
from unittest.mock import MagicMock

from backend.models.schemas import (
    TaskContract,
    ResourceBudget,
    ArchitectPlan,
    OperationalResult,
    RunState,
)
from backend.models.provider import (
    ModelProvider,
    ModelResponse,
    ModelProviderError,
    ModelErrorType,
)
from backend.models.evidence import verify_receipt_integrity
from backend.verification.models import VerificationStatus
from backend.agents.architect import ArchitectAgent
from backend.orchestrator.events import EventRecorder
from backend.orchestrator.orchestrator import Orchestrator


class MockProviderWithResponse(ModelProvider):
    def __init__(self, response_text: str = "", raises_error: Exception = None):
        self.response_text = response_text
        self.raises_error = raises_error
        self.provider_name = "mock"
        self.calls = []

    def generate(self, messages, *, model=None, temperature=None, max_tokens=None, request_id=None, **kwargs):
        self.calls.append(messages)
        if self.raises_error:
            raise self.raises_error
        return ModelResponse(
            provider=self.provider_name,
            model=model or "mock-model",
            response_text=self.response_text,
            timestamp=time.time(),
            provider_request_id="req-123",
            latency_ms=10.0,
            input_tokens=50,
            output_tokens=50,
        )


def _make_task() -> TaskContract:
    return TaskContract(
        task_id="TASK-REGRESSION-1",
        repository_id="repo-cons-1",
        base_commit_or_snapshot="snap-1",
        task_description="Repair calculate() in main.py",
        allowed_scope=["main.py"],
        repository_trust="UNTRUSTED",
        resource_budget=ResourceBudget(max_iterations=5, max_runtime=30),
    )


# 1. Valid JSON plan with list fields
def test_valid_json_plan_with_list_fields():
    plan_dict = {
        "objective": "Fix calculate in main.py",
        "files_to_inspect": ["main.py", "test_main.py"],
        "files_to_modify": ["main.py"],
        "implementation_steps": ["change return value"],
        "acceptance_criteria": ["test_main passes"],
        "constraints": ["minimal diff"],
        "risks": ["breaking contract"],
        "expected_tests": ["pytest test_main.py"],
    }
    provider = MockProviderWithResponse(json.dumps(plan_dict))
    events = EventRecorder("test-run-id")
    agent = ArchitectAgent(tools=[], model_provider=provider, events=events)
    plan = agent.plan(_make_task())

    assert isinstance(plan, ArchitectPlan)
    assert plan.objective == "Fix calculate in main.py"
    assert plan.files_to_modify == ["main.py"]
    assert plan.constraints == ["minimal diff"]
    assert plan.risks == ["breaking contract"]
    assert plan.acceptance_criteria == ["test_main passes"]


# 2. List fields incorrectly returned as strings
def test_list_fields_returned_as_strings_normalized():
    plan_dict = {
        "objective": "Fix calculate in main.py",
        "files_to_inspect": ["main.py"],
        "files_to_modify": ["main.py"],
        "implementation_steps": ["step 1"],
        "acceptance_criteria": "test_main.py executes and passes",
        "constraints": "Only main.py may be modified",
        "risks": "Low risk modification",
        "expected_tests": ["test_main.py"],
    }
    provider = MockProviderWithResponse(json.dumps(plan_dict))
    events = EventRecorder("test-run-id")
    agent = ArchitectAgent(tools=[], model_provider=provider, events=events)
    plan = agent.plan(_make_task())

    assert isinstance(plan, ArchitectPlan)
    assert plan.acceptance_criteria == ["test_main.py executes and passes"]
    assert plan.constraints == ["Only main.py may be modified"]
    assert plan.risks == ["Low risk modification"]


# 3. Malformed JSON
def test_malformed_json_fails_closed():
    provider = MockProviderWithResponse("Not valid JSON at all {broken")
    events = EventRecorder("test-run-id")
    agent = ArchitectAgent(tools=[], model_provider=provider, events=events)
    res = agent.plan(_make_task())

    assert res == OperationalResult.MODEL_FAILURE
    event_types = [e["event_type"] for e in events.get_events()]
    assert "ARCHITECT_OUTPUT_PARSE_FAILED" in event_types


# 4. Missing required fields
def test_missing_required_fields_fails_closed():
    # 'objective' is required
    plan_dict = {
        "files_to_modify": ["main.py"],
        "constraints": ["minimal diff"],
    }
    provider = MockProviderWithResponse(json.dumps(plan_dict))
    events = EventRecorder("test-run-id")
    agent = ArchitectAgent(tools=[], model_provider=provider, events=events)
    res = agent.plan(_make_task())

    assert res == OperationalResult.MODEL_FAILURE
    event_types = [e["event_type"] for e in events.get_events()]
    assert "ARCHITECT_SCHEMA_VALIDATION_FAILED" in event_types


# 5. Unexpected fields
def test_unexpected_fields_forbidden_and_fails_closed():
    plan_dict = {
        "objective": "Fix bug",
        "files_to_modify": ["main.py"],
        "unauthorized_extra_field": "dangerous_payload",
    }
    provider = MockProviderWithResponse(json.dumps(plan_dict))
    events = EventRecorder("test-run-id")
    agent = ArchitectAgent(tools=[], model_provider=provider, events=events)
    res = agent.plan(_make_task())

    assert res == OperationalResult.MODEL_FAILURE
    event_types = [e["event_type"] for e in events.get_events()]
    assert "ARCHITECT_SCHEMA_VALIDATION_FAILED" in event_types


# 6. Empty or structurally invalid plans
def test_empty_or_structurally_invalid_plans():
    # Case A: Empty object {}
    provider = MockProviderWithResponse("{}")
    agent = ArchitectAgent(tools=[], model_provider=provider)
    res = agent.plan(_make_task())
    assert res == OperationalResult.MODEL_FAILURE

    # Case B: JSON Array []
    provider = MockProviderWithResponse("[]")
    agent = ArchitectAgent(tools=[], model_provider=provider)
    res = agent.plan(_make_task())
    assert res == OperationalResult.MODEL_FAILURE

    # Case C: JSON Primitive "hello"
    provider = MockProviderWithResponse('"just a string"')
    agent = ArchitectAgent(tools=[], model_provider=provider)
    res = agent.plan(_make_task())
    assert res == OperationalResult.MODEL_FAILURE


# 7. Provider timeout or request failure
def test_provider_timeout_or_request_failure():
    err = ModelProviderError(ModelErrorType.MODEL_TIMEOUT, "Timed out after 60s")
    provider = MockProviderWithResponse(raises_error=err)
    events = EventRecorder("test-run-id")
    agent = ArchitectAgent(tools=[], model_provider=provider, events=events)
    res = agent.plan(_make_task())

    assert res == OperationalResult.MODEL_FAILURE
    event_types = [e["event_type"] for e in events.get_events()]
    assert "MODEL_CALL_FAILED" in event_types


# 8. Confirmation that invalid output never reaches patch application or sandbox execution
def test_invalid_output_never_reaches_patch_or_sandbox():
    provider = MockProviderWithResponse("INVALID_JSON_HERE")
    task = _make_task()

    mock_sandbox = MagicMock()
    orch = Orchestrator(
        run_id="run-invalid-architect-1",
        task_contract=task,
        model_provider=provider,
    )
    orch.sandbox_backend = mock_sandbox
    orch.repo_root = "data/fixtures/repo-cons-1"

    final_state = orch.run()
    assert final_state == RunState.ABORTED

    # Ensure Builder and Sandbox were never called
    assert orch.patch_candidate is None
    mock_sandbox.execute.assert_not_called()


# 9. Confirmation that a failed run cannot receive a VERIFIED verdict
def test_failed_run_cannot_receive_verified_verdict():
    provider = MockProviderWithResponse('{"missing": "required_objective"}')
    task = _make_task()

    orch = Orchestrator(
        run_id="run-invalid-architect-2",
        task_contract=task,
        model_provider=provider,
    )
    orch.repo_root = "data/fixtures/repo-cons-1"

    final_state = orch.run()
    assert final_state == RunState.ABORTED

    receipt = orch.evidence_receipt
    assert receipt is not None
    assert receipt.verdict != VerificationStatus.VERIFIED
    assert receipt.verdict == VerificationStatus.INCONCLUSIVE


# 10. Confirmation that evidence receipt integrity is checked and preserved
def test_evidence_receipt_integrity_preserved():
    provider = MockProviderWithResponse("CORRUPT_OUTPUT")
    task = _make_task()

    orch = Orchestrator(
        run_id="run-invalid-architect-3",
        task_contract=task,
        model_provider=provider,
    )
    orch.repo_root = "data/fixtures/repo-cons-1"

    final_state = orch.run()
    assert final_state == RunState.ABORTED

    receipt = orch.evidence_receipt
    assert receipt is not None
    assert verify_receipt_integrity(receipt) is True
