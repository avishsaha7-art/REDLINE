from backend.models.attack import AttackCandidate
from backend.models.attack_execution import AttackExecutionRequest

def validate_attack_for_execution(
    run_id: str,
    task_id: str,
    snapshot_hash: str,
    patch_hash: str,
    candidate: AttackCandidate
) -> AttackExecutionRequest:
    # Validate preconditions (length checks are in Pydantic)
    
    # We only map allowed, bounded strategies to execution
    allowed_strategies = [
        "TEST_CASE", "FUNCTION_INPUT", "MALFORMED_INPUT",
        "INVARIANT_CHECK", "SECURITY_CASE", "MUTATION_CASE",
        "METAMORPHIC_CASE"
    ]
    if candidate.execution_strategy not in allowed_strategies:
        raise ValueError(f"Invalid execution strategy: {candidate.execution_strategy}")

    req = AttackExecutionRequest(
        run_id=run_id,
        task_id=task_id,
        snapshot_hash=snapshot_hash,
        patch_hash=patch_hash,
        attack_fingerprint=candidate.deterministic_fingerprint,
        attack_type=candidate.attack_type,
        target=candidate.target,
        input=candidate.input_specification,
        strategy=candidate.execution_strategy,
        oracle=candidate.oracle_type,
        resource_policy=candidate.resource_budget,
        isolation_policy=candidate.isolation_requirements
    )
    return req
