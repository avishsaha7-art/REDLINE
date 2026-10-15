import pytest
import json
from typing import Optional
from backend.models.schemas import TaskContract, PatchCandidate, RunState, ResourceBudget
from backend.models.evidence import EvidenceReceipt, JudgeExplanation, verify_receipt_integrity, VerificationScope
from backend.evidence.builder import EvidenceAggregator
from backend.verification.models import VerificationResult, VerificationStatus, TestResultSummary, RegressionSummary
from backend.agents.judge import JudgeAgent
from backend.orchestrator.orchestrator import Orchestrator

class MockResponse:
    def __init__(self, text):
        self.response_text = text
        self.provider = "mock"
        self.model = "mock"
        self.provider_request_id = "req1"
        self.request_id = "req2"
        self.latency_ms = 100
        self.input_tokens = 10
        self.output_tokens = 10

class MockModelProvider:
    def __init__(self, responses=None):
        self.responses = responses or []
        
    def generate(self, prompt, system=None, **kwargs):
        if self.responses:
            return MockResponse(self.responses.pop(0))
        return MockResponse("{}")
        
def create_dummy_receipt():
    contract = TaskContract(
        task_id="T1",
        repository_id="R1",
        base_commit_or_snapshot="COMMIT1",
        task_description="Test Task",
        allowed_scope=["main.py"],
    )
    patch = PatchCandidate(
        patch_id="P1",
        task_id="T1",
        base_commit_or_snapshot="COMMIT1",
        diff="--- a/main.py\n+++ b/main.py\n+print('hello')"
    )
    result = VerificationResult(
        verification_id="V1",
        verifier_version="1.0",
        verified_scope="test_scope",
        status=VerificationStatus.VERIFIED,
        policy_version="1.0",
        repository_snapshot_hash="HASH1",
        patch_hash="HASH2",
        test_summary=TestResultSummary(executed=1, passed=1),
        regression_summary=RegressionSummary(),
        security_aggregation=None,
        invariants=[],
        oracle_results=[],
        counterexamples=[]
    )
    
    agg = EvidenceAggregator(contract)
    receipt = agg.build_receipt(
        run_id="RUN1",
        patch=patch,
        verification_result=result,
        attacks=[],
        model_provenance={"model": "test"},
        sandbox_provenance={"backend": "local"}
    )
    return receipt, contract, patch

from unittest import mock

@mock.patch("backend.evidence.builder.datetime")
def test_evidence_receipt_hash_determinism(mock_datetime):
    mock_datetime.datetime.utcnow.return_value.isoformat.return_value = "2026-01-01T00:00:00Z"
    receipt1, _, _ = create_dummy_receipt()
    receipt2, _, _ = create_dummy_receipt()
    assert receipt1.receipt_hash == receipt2.receipt_hash
    assert verify_receipt_integrity(receipt1)

def test_evidence_receipt_integrity_tampering():
    receipt, _, _ = create_dummy_receipt()
    assert verify_receipt_integrity(receipt)
    
    # Tamper with verdict (using model_copy since it's frozen)
    tampered_receipt = receipt.model_copy(update={"verdict": VerificationStatus.REJECTED})
    # model_copy keeps the same receipt_hash but the actual contents changed
    assert not verify_receipt_integrity(tampered_receipt)
    
    # Tamper with scope
    tampered_scope = receipt.model_copy(update={
        "verification_scope": VerificationScope(execution="EXECUTED", tests="TAMPERED")
    })
    assert not verify_receipt_integrity(tampered_scope)
    
def test_judge_agent_isolation_and_parsing():
    receipt, contract, patch = create_dummy_receipt()
    
    # Mock LLM returning valid explanation
    valid_json = json.dumps({
        "summary": "Passed all tests.",
        "verified_claims": [],
        "failed_claims": [],
        "evidence_references": [],
        "limitations": "None",
        "confidence": "High"
    })
    
    provider = MockModelProvider([valid_json])
    judge = JudgeAgent(model_provider=provider)
    
    explanation = judge.generate_explanation(receipt, contract, patch)
    assert explanation.summary == "Passed all tests."

def test_judge_agent_rejects_extra_fields():
    receipt, contract, patch = create_dummy_receipt()
    
    # Mock LLM returning valid explanation but trying to override verdict
    invalid_json = json.dumps({
        "summary": "Passed all tests.",
        "verified_claims": [],
        "failed_claims": [],
        "evidence_references": [],
        "limitations": "None",
        "confidence": "High",
        "verdict": "VERIFIED" # Malicious injection
    })
    
    provider = MockModelProvider([invalid_json])
    judge = JudgeAgent(model_provider=provider)
    
    # Pydantic forbid extra fields
    with pytest.raises(Exception):
        judge.generate_explanation(receipt, contract, patch)

def test_judge_agent_missing_fields():
    receipt, contract, patch = create_dummy_receipt()
    
    # Mock LLM returning wrong payload
    invalid_json = json.dumps({
        "summary": "Passed all tests."
    })
    
    provider = MockModelProvider([invalid_json])
    judge = JudgeAgent(model_provider=provider)
    
    with pytest.raises(ValueError, match="Judge output invalid"):
        judge.generate_explanation(receipt, contract, patch)

def test_orchestrator_stage11_e2e():
    contract = TaskContract(
        task_id="T1",
        repository_id="R1",
        base_commit_or_snapshot="COMMIT1",
        task_description="Test Task",
        allowed_scope=["main.py"],
        resource_budget=ResourceBudget(max_iterations=20)
    )
    provider = MockModelProvider([
        # Architect
        json.dumps({"objective": "...", "rationale": "...", "files_to_modify": ["main.py"], "instructions": "..."}),
        # Builder
        json.dumps({"changed_files": ["main.py"], "diff": "--- a/main.py\n+++ b/main.py\n@@ -1,1 +1,2 @@\n+print('hello')"}),
        # Judge
        json.dumps({
            "summary": "pass",
            "verified_claims": [],
            "failed_claims": [],
            "evidence_references": [],
            "limitations": "None",
            "confidence": "High"
        })
    ])
    
    orch = Orchestrator("RUN1", contract, model_provider=provider)
    
    # Mock the Judge generation to not fail on ID mismatch due to static mock
    original_generate = orch.judge.generate_explanation
    def fake_generate(receipt, contract, patch):
        return JudgeExplanation(
            summary="pass",
            verified_claims=[],
            failed_claims=[],
            evidence_references=[],
            limitations="None",
            confidence="High"
        )
    orch.judge.generate_explanation = fake_generate
    
    final_state = orch.run()
    assert final_state == RunState.VERIFIED
    assert hasattr(orch, "evidence_receipt")
    assert orch.evidence_receipt is not None
    assert verify_receipt_integrity(orch.evidence_receipt)
    assert hasattr(orch, "judge_explanation")
    assert orch.judge_explanation.summary == "pass"
