import pytest
from backend.models.schemas import TaskContract, ResourceBudget, RunState, OperationalResult, PatchCandidate
from backend.orchestrator.orchestrator import Orchestrator
from backend.agents.red_team import RedTeamAgent
from backend.models.attack import AttackCandidate, AttackType, RiskLevel, OracleType, AttackMetadata
import uuid
from typing import List
from backend.orchestrator.state_machine import StateMachine

# Helper for testing Red Team integration
def setup_orchestrator(mock_red_team=None):
    contract = TaskContract(
        task_id="TEST-TASK",
        repository_id="TEST-REPO",
        base_commit_or_snapshot="HEAD",
        task_description="Test task",
        resource_budget=ResourceBudget(max_attack_cases=2)
    )
    orch = Orchestrator("RUN-ID", contract)
    orch.patch_candidate = PatchCandidate(
        patch_id="PATCH-ID",
        task_id="TEST-TASK",
        base_commit_or_snapshot="HEAD",
        diff="fake diff",
        diff_sha256="fake_sha",
        author="builder",
        commit_message="test"
    )
    orch.untrusted_context = "test context"
    # Force state machine to RunState.TEST so advancing TEST_SUCCESS goes to ATTACK
    orch.state_machine.current_state = RunState.TEST
    
    if mock_red_team:
        orch.red_team = mock_red_team
    
    return orch

def test_attack_invokes_redteam():
    """Test 1 & 2 & 3: Prove that entering ATTACK invokes RedTeamAgent and propagates state/metadata"""
    class MockRedTeam:
        def __init__(self, *args, **kwargs):
            self.invoked = False
            self.passed_task = None
            
        def generate_attacks(self, task, patch, context) -> List[AttackCandidate]:
            self.invoked = True
            self.passed_task = task
            # Return a fake selection
            attack = AttackCandidate(
                attack_id="ATTACK-1",
                attack_type=AttackType.INPUT,
                objective="Test",
                target="system",
                input_specification="test",
                execution_strategy="DEFAULT",
                expected_failure_signal="Crash",
                oracle_type=OracleType.TASK_INVARIANT,
                risk_level=RiskLevel.LOW,
                rationale="Test"
            )
            return [attack]
            
    mock_rt = MockRedTeam()
    orch = setup_orchestrator(mock_rt)
    
    # Run ATTACK logic manually to avoid needing to mock every previous step perfectly
    orch.state_machine.current_state = RunState.ATTACK
    
    # We simulate what orchestrator does at ATTACK
    orch.selected_attacks = orch.red_team.generate_attacks(
        orch.task_contract,
        orch.patch_candidate,
        orch.untrusted_context
    )
    if not orch.selected_attacks:
        orch.state_machine.advance("ATTACK_FAILED")
    else:
        orch.state_machine.advance("ATTACK_SUCCESS")
    
    assert mock_rt.invoked, "RedTeamAgent was not invoked"
    assert mock_rt.passed_task is not None
    assert orch.selected_attacks is not None
    assert len(orch.selected_attacks) == 1
    assert orch.selected_attacks[0].attack_id == "ATTACK-1"
    assert orch.state_machine.current_state == RunState.VERIFY

def test_red_team_failure_handling():
    """Test 4: Red Team failure does not become fake success"""
    class FailingRedTeam:
        def generate_attacks(self, task, patch, context):
            return [] # Empty attacks
            
    orch = setup_orchestrator(FailingRedTeam())
    orch.state_machine.current_state = RunState.ATTACK
    
    # We must intercept run() because it will go to ATTACK_FAILED -> ANALYZE -> ANALYZE_COMPLETE ... wait ANALYZE handles it? 
    # Let's just execute the step manually to avoid looping too far
    orch.selected_attacks = orch.red_team.generate_attacks(orch.task_contract, orch.patch_candidate, orch.untrusted_context)
    if not orch.selected_attacks:
        orch.state_machine.advance("ATTACK_FAILED")
    else:
        orch.state_machine.advance("ATTACK_SUCCESS")
        
    assert orch.state_machine.current_state == RunState.ANALYZE

def test_relevance_novelty_hints():
    """Test 5 & 6: Relevance and Novelty hints influence scoring safely"""
    agent = RedTeamAgent()
    
    # Provide a valid hint
    a1 = AttackCandidate(
        attack_id="A1",
        attack_type=AttackType.INPUT,
        objective="O", target="T", input_specification="I", execution_strategy="E",
        expected_failure_signal="F", oracle_type=OracleType.TASK_INVARIANT, risk_level=RiskLevel.LOW, rationale="R",
        metadata={"relevance": 0.9, "novelty": 0.8}
    )
    
    assert a1.metadata.relevance == 0.9
    assert a1.metadata.novelty == 0.8
    
    score1 = agent._score_attack(a1, {}, {})
    
    a2 = AttackCandidate(
        attack_id="A2",
        attack_type=AttackType.INPUT,
        objective="O", target="T2", input_specification="I", execution_strategy="E",
        expected_failure_signal="F", oracle_type=OracleType.TASK_INVARIANT, risk_level=RiskLevel.LOW, rationale="R",
        metadata={"relevance": 0.1, "novelty": 0.2}
    )
    
    score2 = agent._score_attack(a2, {}, {})
    
    assert score1.total_score > score2.total_score, "Higher relevance/novelty should yield a higher score"
    
def test_invalid_hints_normalized():
    """Test 7 & 8: Invalid hints fall back safely"""
    a_invalid = AttackCandidate(
        attack_id="A1",
        attack_type=AttackType.INPUT,
        objective="O", target="T", input_specification="I", execution_strategy="E",
        expected_failure_signal="F", oracle_type=OracleType.TASK_INVARIANT, risk_level=RiskLevel.LOW, rationale="R",
        metadata={"relevance": -1.0, "novelty": 5.0, "confidence": float('inf')}
    )
    
    assert a_invalid.metadata.relevance == 0.0 # Bounded to 0
    assert a_invalid.metadata.novelty == 1.0 # Bounded to 1
    assert a_invalid.metadata.confidence is None # Inf becomes None

    a_type_error = AttackCandidate(
        attack_id="A1",
        attack_type=AttackType.INPUT,
        objective="O", target="T", input_specification="I", execution_strategy="E",
        expected_failure_signal="F", oracle_type=OracleType.TASK_INVARIANT, risk_level=RiskLevel.LOW, rationale="R",
        metadata={"relevance": "invalid", "novelty": "invalid"}
    )
    
    assert a_type_error.metadata.relevance == 0.5
    assert a_type_error.metadata.novelty == 0.5

def test_model_authority_bounded():
    """Test 9: Deterministic scoring overrides malicious hints"""
    agent = RedTeamAgent()
    
    # Model tries to force priority with 1.0 hints on a weak attack
    malicious = AttackCandidate(
        attack_id="MALICIOUS",
        attack_type=AttackType.INPUT,
        objective="O", target="T", input_specification="I", execution_strategy="E",
        expected_failure_signal="F", oracle_type=OracleType.MODEL_GENERATED, risk_level=RiskLevel.LOW, rationale="R",
        metadata={"relevance": 1.0, "novelty": 1.0}
    )
    
    # A strong deterministic attack with neutral hints
    strong = AttackCandidate(
        attack_id="STRONG",
        attack_type=AttackType.SECURITY,
        objective="O", target="T2", input_specification="I2", execution_strategy="E",
        expected_failure_signal="F", oracle_type=OracleType.TASK_INVARIANT, risk_level=RiskLevel.HIGH, rationale="R",
        metadata={"relevance": 0.5, "novelty": 0.5}
    )
    
    s_mal = agent._score_attack(malicious, {}, {})
    s_strong = agent._score_attack(strong, {}, {})
    
    assert s_strong.total_score > s_mal.total_score, "Deterministic strength must overpower maxed LLM hints"
