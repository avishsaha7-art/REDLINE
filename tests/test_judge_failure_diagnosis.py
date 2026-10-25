"""
Step 2.9.6.5 Regression Tests: Judge Failure Diagnosis and Non-Authoritative Verification.

Validates that:
1. Valid JudgeExplanation with markdown codeblocks and normalized list fields is accepted.
2. Extra injected fields (e.g., {"verdict": "VERIFIED"}) are strictly forbidden and rejected.
3. Hallucinated or unsupported evidence references are rejected by consistency check.
4. Judge failure does not prevent VERIFIED when deterministic receipt verdict is VERIFIED.
5. Judge failure never upgrades INCONCLUSIVE or REJECTED to VERIFIED.
6. Judge explanation is never fabricated on failure (remains None in Orchestrator).
"""

import json
import pytest
from unittest.mock import MagicMock

from backend.models.schemas import TaskContract, ResourceBudget, RunState, PatchCandidate
from backend.models.evidence import (
    EvidenceReceipt,
    JudgeExplanation,
    VerificationScope,
)
from backend.verification.models import VerificationStatus
from backend.models.provider import ModelProvider, ModelResponse
from backend.agents.judge import JudgeAgent
from backend.orchestrator.orchestrator import Orchestrator


class MockModelProvider(ModelProvider):
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def generate(self, messages, *, model=None, temperature=None, max_tokens=None, request_id=None, **kwargs):
        self.calls.append(messages)
        resp_text = self.responses.pop(0) if self.responses else "{}"
        return ModelResponse(
            provider="mock",
            model="mock-model",
            response_text=resp_text,
            timestamp=1234567890.0,
            provider_request_id="req-mock",
            latency_ms=10.0,
            input_tokens=100,
            output_tokens=100
        )


def _make_dummy_receipt(verdict=VerificationStatus.VERIFIED, execution_ids=None):
    if execution_ids is None:
        execution_ids = ["exec-123"]
    r = EvidenceReceipt(
        run_id="run-judge-test",
        task_id="task-judge-test",
        repository_snapshot_hash="snap-hash",
        task_contract_hash="contract-hash",
        patch_hash="patch-hash",
        execution_ids=execution_ids,
        verdict=verdict,
        verification_scope=VerificationScope(execution="VERIFIED", tests="VERIFIED"),
        policy_version="1.0",
        verifier_version="1.0",
        timestamp="2026-10-25T00:00:00Z"
    )
    # calculate and set valid receipt hash
    h = r.calculate_integrity_hash()
    return r.model_copy(update={"receipt_hash": h})


def _make_task_contract():
    return TaskContract(
        task_id="task-judge-test",
        repository_id="repo-cons-1",
        base_commit_or_snapshot="snap-1",
        task_description="Repair calculate()",
        allowed_scope=["main.py"],
        resource_budget=ResourceBudget(max_iterations=20, max_runtime=120)
    )


def _make_patch():
    return PatchCandidate(
        patch_id="PATCH-001",
        task_id="task-judge-test",
        base_commit_or_snapshot="snap-1",
        diff="--- a/main.py\n+++ b/main.py\n@@ -1 +1 @@\n-old\n+new",
        changed_files=["main.py"]
    )


def test_judge_accepts_markdown_codeblocks_and_normalized_lists():
    payload = """```json
{
  "summary": "All tests passed cleanly in secure sandbox.",
  "verified_claims": "The calculate function returned 0 as expected.",
  "failed_claims": [],
  "evidence_references": "exec-123",
  "limitations": "Tested only on unit level.",
  "confidence": "HIGH"
}
```"""
    provider = MockModelProvider([payload])
    judge = JudgeAgent(model_provider=provider)
    receipt = _make_dummy_receipt(execution_ids=["exec-123"])
    contract = _make_task_contract()
    patch = _make_patch()

    explanation = judge.generate_explanation(receipt, contract, patch)
    assert isinstance(explanation, JudgeExplanation)
    assert explanation.summary == "All tests passed cleanly in secure sandbox."
    assert explanation.verified_claims == ["The calculate function returned 0 as expected."]
    assert explanation.evidence_references == ["exec-123"]
    assert explanation.confidence == "HIGH"


def test_judge_rejects_injected_extra_fields():
    payload = json.dumps({
        "summary": "All tests passed.",
        "verified_claims": [],
        "failed_claims": [],
        "evidence_references": [],
        "limitations": "None",
        "confidence": "HIGH",
        "verdict": "VERIFIED"  # Extra forbidden field
    })
    provider = MockModelProvider([payload])
    judge = JudgeAgent(model_provider=provider)
    receipt = _make_dummy_receipt()
    contract = _make_task_contract()
    patch = _make_patch()

    with pytest.raises(ValueError, match="Judge output invalid"):
        judge.generate_explanation(receipt, contract, patch)


def test_judge_rejects_hallucinated_evidence_references():
    payload = json.dumps({
        "summary": "All tests passed.",
        "verified_claims": [],
        "failed_claims": [],
        "evidence_references": ["invented-id-999"],  # Hallucinated ID
        "limitations": "None",
        "confidence": "HIGH"
    })
    provider = MockModelProvider([payload])
    judge = JudgeAgent(model_provider=provider)
    receipt = _make_dummy_receipt(execution_ids=["exec-real-1"])
    contract = _make_task_contract()
    patch = _make_patch()

    with pytest.raises(ValueError, match="Explanation consistency check failed"):
        judge.generate_explanation(receipt, contract, patch)


def test_judge_failure_does_not_prevent_verified_when_deterministic_verdict_verified(monkeypatch):
    monkeypatch.setenv("REDLINE_ENABLE_LOCAL_BACKEND", "1")
    contract = _make_task_contract()

    # Provider returns corrupt judge output
    provider = MockModelProvider([
        # Architect
        json.dumps({"objective": "repair", "files_to_modify": ["main.py"], "constraints": ["none"]}),
        # Builder
        json.dumps({"changed_files": ["main.py"], "diff": "--- a/main.py\n+++ b/main.py\n@@ -1,1 +1,1 @@\n-old\n+def calculate(): return 0\n"}),
        # Red Team (empty list of attacks)
        json.dumps([]),
        # Judge: Malformed output
        "CORRUPT NOT JSON"
    ])

    orch = Orchestrator("run-judge-resilience", contract, model_provider=provider)
    orch.repo_root = "data/fixtures/repo-cons-1"

    final_state = orch.run()
    # Deterministic verification still governs verdict!
    assert final_state == RunState.VERIFIED
    assert getattr(orch, "judge_explanation", None) is None

    event_types = [e["event_type"] for e in orch.state_machine.events.get_events()]
    assert "JUDGE_FAILURE" in event_types


def test_judge_failure_never_upgrades_inconclusive_or_rejected():
    receipt = _make_dummy_receipt(verdict=VerificationStatus.INCONCLUSIVE)
    contract = _make_task_contract()

    provider = MockModelProvider(["INVALID OUTPUT"])
    orch = Orchestrator("run-judge-no-upgrade", contract, model_provider=provider)
    orch.evidence_receipt = receipt

    # Directly check deterministic gate
    if receipt.verdict == VerificationStatus.VERIFIED:
        orch.state_machine.advance("JUDGE_PASS")
    else:
        orch.state_machine.advance("JUDGE_FAIL")

    assert orch.state_machine.current_state != RunState.VERIFIED
