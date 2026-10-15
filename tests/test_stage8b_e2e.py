import json
import pytest

from backend.models.schemas import TaskContract, ResourceBudget, ArchitectPlan
from backend.agents.builder import BuilderAgent
from backend.models.deterministic_provider import DeterministicTestProvider
from backend.verification.patch_validation import validate_patch
from backend.sandbox.client import SandboxClient
from backend.sandbox.models import SandboxPolicy, ExecutionRequest
from backend.verification.observer import DeterministicVerificationObserver
from backend.verification.policy import DeterministicVerificationPolicy
from backend.verification.models import VerificationStatus, RegressionSummary, InvariantEvaluation, InvariantResultStatus

def test_minimal_e2e_verification(tmp_path):
    # 1. Task
    task = TaskContract(
        task_id="t1", repository_id="r1", base_commit_or_snapshot="snap",
        task_description="Build a feature", allowed_scope=["main.py"],
        resource_budget=ResourceBudget()
    )
    
    # 2. Architect
    plan = ArchitectPlan(objective="do it", files_to_modify=["main.py"])
    
    # 3. Builder
    diff = "--- a/main.py\n+++ b/main.py\n@@ -1 +1 @@\n-a\n+b\n"
    payload = json.dumps({"changed_files": ["main.py"], "diff": diff})
    provider = DeterministicTestProvider(payload)
    builder = BuilderAgent(tools=[], model_provider=provider)
    patch = builder.build(task, plan, "repo content")
    
    # 4. Patch validation
    assert validate_patch(patch, task) is True
    
    # 5. Sandbox policy
    policy = SandboxPolicy(allowed_commands=["python"])
    client = SandboxClient(str(tmp_path), policy)
    
    # 6. Execution (We just use TRUSTED_DEVELOPMENT for testing E2E locally)
    with open(tmp_path / "test_main.py", "w") as f:
        f.write("print('1 passed')\n")
        
    from backend.sandbox.backend import LocalDevelopmentBackend
    backend = LocalDevelopmentBackend(policy)
    req = ExecutionRequest(
        command=["python", "test_main.py"],
        working_directory=str(tmp_path),
        repository_trust="TRUSTED_DEVELOPMENT"
    )
    res = backend.execute(req, "run-1")
    
    # 7. Observer
    observer = DeterministicVerificationObserver()
    structured_obs = observer.observe_execution(res, str(tmp_path), "snap_hash", patch.diff_sha256)
    
    # 8. Test observation
    test_summary = observer.observe_tests(res)
    assert test_summary.passed == 1
    
    # 9. Invariant evaluation
    inv = InvariantEvaluation(
        invariant_id="inv1", description="desc", result=InvariantResultStatus.PASS,
        failure_reason="", evidence_hash="ev1"
    )
    
    # 10. Verification policy
    v_policy = DeterministicVerificationPolicy()
    verdict = v_policy.evaluate(
        repository_snapshot_hash="snap_hash",
        patch_hash=patch.diff_sha256,
        structured_observation=structured_obs,
        test_summary=test_summary,
        regression_summary=RegressionSummary(),
        invariants=[inv],
        security_aggregation=None,
        oracle_results=[],
        counterexamples=[]
    )
    
    # 11. VerificationResult
    assert verdict.status == VerificationStatus.VERIFIED
    assert verdict.test_summary.passed == 1
    assert verdict.repository_snapshot_hash == "snap_hash"
