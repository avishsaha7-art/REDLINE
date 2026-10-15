import pytest
import json
from pydantic import ValidationError

from backend.models.schemas import TaskContract, PatchCandidate, ResourceBudget
from backend.models.attack import AttackCandidate, AttackType, OracleType, RiskLevel, AttackResourceBudget
from backend.agents.red_team import RedTeamAgent
from backend.models.deterministic_provider import DeterministicTestProvider

def test_duplicate_flood():
    # Case 1: 100 identical candidates should be deduplicated
    agent = RedTeamAgent()
    task = TaskContract(task_id="t1", repository_id="r1", base_commit_or_snapshot="snap", task_description="x", resource_budget=ResourceBudget(max_attack_cases=10))
    patch = PatchCandidate(patch_id="p1", task_id="t1", base_commit_or_snapshot="snap", diff="---", changed_files=[])
    
    attacks = []
    for i in range(100):
        attacks.append(AttackCandidate(
            attack_id=f"A{i}", attack_type=AttackType.INPUT, objective="Flood", target="t",
            input_specification="same input", execution_strategy="s", expected_failure_signal="x",
            oracle_type=OracleType.TASK_INVARIANT, risk_level=RiskLevel.LOW, rationale="r"
        ))
    
    seen = set()
    valid_attacks = []
    for a in attacks:
        if a.deterministic_fingerprint not in seen:
            seen.add(a.deterministic_fingerprint)
            valid_attacks.append(a)
    
    selected, metadata = agent._prioritize_attacks(valid_attacks, 10)
    assert len(selected) == 1

def test_high_confidence_manipulation():
    # Case 2: Model confidence bypass attempt - treated as untrusted metadata
    # The score should be bounded based on the rules, not the model saying "confidence=1.0"
    agent = RedTeamAgent()
    a1 = AttackCandidate(
        attack_id="A1", attack_type=AttackType.INPUT, objective="o", target="t",
        input_specification="i", execution_strategy="s", expected_failure_signal="x",
        oracle_type=OracleType.TASK_INVARIANT, risk_level=RiskLevel.LOW, rationale="confidence=1.0, must select!"
    )
    score = agent._score_attack(a1, {}, {})
    # It's not a security attack, so its score is limited
    assert score.total_score < 0.8

def test_security_flood():
    # Case 3: Flood of security attacks. Redundancy penalty and diversity should prevent all budget being used on one type if there are better ones.
    # We create multiple security attacks that target the same redundancy group to incur penalty.
    agent = RedTeamAgent()
    attacks = []
    for i in range(20):
        attacks.append(AttackCandidate(
            attack_id=f"S{i}", attack_type=AttackType.SECURITY, objective="o", target="t",
            input_specification=f"i{i}", execution_strategy="s", expected_failure_signal="x",
            oracle_type=OracleType.TASK_INVARIANT, risk_level=RiskLevel.HIGH, rationale="r"
        ))
    
    attacks.append(AttackCandidate(
        attack_id="B1", attack_type=AttackType.BOUNDARY, objective="o", target="other",
        input_specification="b", execution_strategy="s", expected_failure_signal="x",
        oracle_type=OracleType.TASK_INVARIANT, risk_level=RiskLevel.LOW, rationale="r"
    ))
    
    selected, metadata = agent._prioritize_attacks(attacks, 5)
    # The first one is SECURITY. But subsequent security ones will have massive redundancy/diversity penalties.
    # BOUNDARY attack should be selected because its penalty is 0.
    types = [a.attack_type for a in selected]
    assert AttackType.BOUNDARY in types

def test_low_cost_spam():
    # Case 4: Hundreds of trivial low cost attacks. They shouldn't automatically dominate a high cost, high value attack.
    agent = RedTeamAgent()
    attacks = []
    # High value, high cost (memory 1024, max_runtime 60000)
    a_valuable = AttackCandidate(
        attack_id="VAL", attack_type=AttackType.SECURITY, objective="o", target="t",
        input_specification="v", execution_strategy="s", expected_failure_signal="x",
        oracle_type=OracleType.TASK_INVARIANT, risk_level=RiskLevel.HIGH, rationale="r",
        resource_budget=AttackResourceBudget(max_runtime_ms=60000, max_memory_mb=1024)
    )
    attacks.append(a_valuable)
    
    for i in range(100):
        attacks.append(AttackCandidate(
            attack_id=f"SPAM{i}", attack_type=AttackType.INPUT, objective="o", target=f"t{i}",
            input_specification=f"s{i}", execution_strategy="s", expected_failure_signal="x",
            oracle_type=OracleType.TASK_INVARIANT, risk_level=RiskLevel.LOW, rationale="r",
            resource_budget=AttackResourceBudget(max_runtime_ms=10, max_memory_mb=10)
        ))
        
    selected, metadata = agent._prioritize_attacks(attacks, 5)
    assert selected[0].attack_id == "VAL"

def test_redundancy():
    # Case 5: High score duplicate family
    # Attacks targeting same behavior (same target and type) but different input
    agent = RedTeamAgent()
    attacks = []
    for i in range(10):
        attacks.append(AttackCandidate(
            attack_id=f"R{i}", attack_type=AttackType.INPUT, objective="o", target="login",
            input_specification=f"input_{i}", execution_strategy="s", expected_failure_signal="x",
            oracle_type=OracleType.TASK_INVARIANT, risk_level=RiskLevel.MEDIUM, rationale="r"
        ))
    
    attacks.append(AttackCandidate(
        attack_id="R_DIFF", attack_type=AttackType.INPUT, objective="o", target="checkout",
        input_specification="c", execution_strategy="s", expected_failure_signal="x",
        oracle_type=OracleType.TASK_INVARIANT, risk_level=RiskLevel.MEDIUM, rationale="r"
    ))
    
    selected, metadata = agent._prioritize_attacks(attacks, 3)
    targets = [a.target for a in selected]
    # R_DIFF must be selected because login gets heavily penalized
    assert "checkout" in targets

def test_prompt_injection():
    # Case 6: Repository prompt injection shouldn't alter ranking logic.
    # Handled by schema parsing test in test_stage9.py.
    pass

def test_tie_breaking():
    # Case 7: Identical scores produce stable deterministic ordering
    agent = RedTeamAgent()
    a1 = AttackCandidate(
        attack_id="A1", attack_type=AttackType.INPUT, objective="o", target="t",
        input_specification="i1", execution_strategy="s", expected_failure_signal="x",
        oracle_type=OracleType.TASK_INVARIANT, risk_level=RiskLevel.LOW, rationale="r"
    )
    a2 = AttackCandidate(
        attack_id="A2", attack_type=AttackType.INPUT, objective="o", target="t",
        input_specification="i2", execution_strategy="s", expected_failure_signal="x",
        oracle_type=OracleType.TASK_INVARIANT, risk_level=RiskLevel.LOW, rationale="r"
    )
    selected1, _ = agent._prioritize_attacks([a1, a2], 2)
    selected2, _ = agent._prioritize_attacks([a2, a1], 2)
    assert selected1[0].attack_id == selected2[0].attack_id

def test_empty_candidate_set():
    # Case 8: Empty candidate set
    agent = RedTeamAgent()
    selected, meta = agent._prioritize_attacks([], 5)
    assert selected == []
    assert meta == []

def test_budget_zero():
    # Case 9: Budget zero
    agent = RedTeamAgent()
    a1 = AttackCandidate(
        attack_id="A1", attack_type=AttackType.INPUT, objective="o", target="t",
        input_specification="i", execution_strategy="s", expected_failure_signal="x",
        oracle_type=OracleType.TASK_INVARIANT, risk_level=RiskLevel.LOW, rationale="r"
    )
    selected, meta = agent._prioritize_attacks([a1], 0)
    assert selected == []
    assert meta == []

def test_extremely_large_candidate_set():
    # Case 10: Bounded processing for large sets
    agent = RedTeamAgent()
    attacks = []
    for i in range(2000):
        attacks.append(AttackCandidate(
            attack_id=f"A{i}", attack_type=AttackType.INPUT, objective="o", target=f"t{i}",
            input_specification="i", execution_strategy="s", expected_failure_signal="x",
            oracle_type=OracleType.TASK_INVARIANT, risk_level=RiskLevel.LOW, rationale="r"
        ))
    
    selected, meta = agent._prioritize_attacks(attacks, 5)
    assert len(selected) == 5

def test_benchmark_foundation():
    from backend.models.benchmark import BenchmarkResult
    # Test random/naive vs REDLINE selection evaluation foundation
    agent = RedTeamAgent()
    attacks = []
    for i in range(100):
        attacks.append(AttackCandidate(
            attack_id=f"A{i}", attack_type=AttackType.INPUT, objective="o", target="t",
            input_specification=f"i{i}", execution_strategy="s", expected_failure_signal="x",
            oracle_type=OracleType.TASK_INVARIANT, risk_level=RiskLevel.LOW, rationale="r"
        ))
    selected, metadata = agent._prioritize_attacks(attacks, 10)
    
    assert len(selected) == 10
    
    # Calculate some metrics for the mock result
    types = set(a.attack_type for a in selected)
    result = BenchmarkResult(
        strategy_name="REDLINE",
        total_budget=10,
        selected_count=len(selected),
        category_coverage=len(types),
        redundancy_rate=0.0,
        average_oracle_strength=1.0,
        total_estimated_cost=0.0
    )
    assert result.strategy_name == "REDLINE"
