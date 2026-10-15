import os
import json
import pytest
import shutil
import time
from backend.models.schemas import TaskContract, ResourceBudget, ArchitectPlan, RunState
from backend.orchestrator.orchestrator import Orchestrator
from backend.models.deterministic_provider import DeterministicTestProvider

@pytest.fixture
def repo_root(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "main.py").write_text("a\n", encoding="utf-8")
    return str(repo)

def test_stage7_e2e_pipeline(repo_root):
    # Overwrite os.getcwd for the test context
    old_cwd = os.getcwd()
    os.environ["REDLINE_REPO_ROOT"] = repo_root
    
    try:
        task = TaskContract(
            task_id="t1",
            repository_id="r1",
            base_commit_or_snapshot="1",
            task_description="test",
            allowed_scope=["main.py"],
            resource_budget=ResourceBudget(max_iterations=50)
        )
        
        provider = DeterministicTestProvider()
        orchestrator = Orchestrator("run-1", task, model_provider=provider)
        
        result = orchestrator.run()
        
        # In the original orchestrator, after BUILD succeeds it goes to TEST, then VERIFY, then JUDGE, then VERIFIED
        assert result == RunState.VERIFIED
        events = orchestrator.state_machine.events.get_events()
        event_names = [e["event_type"] for e in events]
        assert "MODEL_CALL_STARTED" in event_names
        assert "PATCH_CANDIDATE_VALIDATED" in event_names
        assert "PATCH_CREATED" in event_names

        
    finally:
        os.environ.pop("REDLINE_REPO_ROOT", None)

def test_live_nebius_model_blocked():
    if "NEBIUS_API_KEY" not in os.environ:
        pytest.skip("BLOCKED: Live model test requires NEBIUS_API_KEY")
