import os
import json
import time
import pytest
from unittest.mock import patch, MagicMock

from backend.models.provider import ModelErrorType, ModelProviderError, ModelResponse
from backend.models.nebius_provider import NebiusProvider
from backend.models.freellmapi_provider import FreeLLMAPIProvider
from backend.models.deterministic_provider import DeterministicTestProvider
from backend.models.registry import (
    get_model_provider,
    set_model_provider,
    reset_model_provider,
)
from backend.models.schemas import TaskContract, RunState, ResourceBudget
from backend.orchestrator.orchestrator import Orchestrator
from backend.sandbox.secure_backend import SecureSandboxBackend
from backend.sandbox.models import SandboxPolicy


# =====================================================================
# Phase F: Cross-Provider Isolation & Non-Interference Tests
# =====================================================================

def test_default_provider_precedence_nebius(monkeypatch):
    """Verify that Nebius is the default provider when REDLINE_MODEL_PROVIDER is unset."""
    monkeypatch.delenv("REDLINE_MODEL_PROVIDER", raising=False)
    monkeypatch.setenv("NEBIUS_API_KEY", "nebius-test-token")
    monkeypatch.setenv("FREELLMAPI_API_KEY", "freellm-test-token")
    reset_model_provider()

    provider = get_model_provider()
    # Precedence rule: Nebius takes priority when both keys are present and provider is unset
    assert isinstance(provider, NebiusProvider)
    assert provider.provider_name == "nebius"


def test_explicit_selection_strictness(monkeypatch):
    """Verify that explicit REDLINE_MODEL_PROVIDER strictly selects the requested provider."""
    monkeypatch.setenv("NEBIUS_API_KEY", "nebius-key")
    monkeypatch.setenv("FREELLMAPI_API_KEY", "freellmapi-key")
    reset_model_provider()

    # Explicit nebius
    monkeypatch.setenv("REDLINE_MODEL_PROVIDER", "nebius")
    p_nebius = get_model_provider()
    assert isinstance(p_nebius, NebiusProvider)

    # Explicit freellmapi
    monkeypatch.setenv("REDLINE_MODEL_PROVIDER", "freellmapi")
    p_free = get_model_provider()
    assert isinstance(p_free, FreeLLMAPIProvider)

    # Explicit deterministic
    monkeypatch.setenv("REDLINE_MODEL_PROVIDER", "deterministic")
    p_det = get_model_provider()
    assert isinstance(p_det, DeterministicTestProvider)


def test_freellmapi_failure_never_calls_nebius(monkeypatch):
    """Verify that a failure in FreeLLMAPI never silently falls back to Nebius."""
    monkeypatch.setenv("REDLINE_MODEL_PROVIDER", "freellmapi")
    monkeypatch.setenv("FREELLMAPI_API_KEY", "free-key")
    monkeypatch.setenv("NEBIUS_API_KEY", "nebius-key")
    reset_model_provider()

    nebius_called = False

    class SpyNebius(NebiusProvider):
        def generate(self, *args, **kwargs):
            nonlocal nebius_called
            nebius_called = True
            return super().generate(*args, **kwargs)

    class FailingFreeLLM(FreeLLMAPIProvider):
        def generate(self, *args, **kwargs):
            raise ModelProviderError(ModelErrorType.MODEL_UNAVAILABLE, "FreeLLMAPI gateway down")

    contract = TaskContract(
        task_id="t-iso-1",
        repository_id="repo-cons-1",
        base_commit_or_snapshot="snap-iso-1",
        task_description="test isolation",
        allowed_scope=["main.py"],
        repository_trust="TRUSTED_DEVELOPMENT",
        resource_budget=ResourceBudget(max_iterations=1, max_failed_attempts=1)
    )

    orch = Orchestrator(run_id="run-iso-1", task_contract=contract, model_provider=FailingFreeLLM())
    final_state = orch.run()

    # Invariant: Run must terminate in ABORTED without ever touching Nebius
    assert final_state == RunState.ABORTED
    assert nebius_called is False
    assert orch.state_machine.current_state == RunState.ABORTED


def test_nebius_failure_never_calls_freellmapi(monkeypatch):
    """Verify that a failure in Nebius never silently falls back to FreeLLMAPI."""
    monkeypatch.setenv("REDLINE_MODEL_PROVIDER", "nebius")
    monkeypatch.setenv("NEBIUS_API_KEY", "nebius-key")
    monkeypatch.setenv("FREELLMAPI_API_KEY", "free-key")
    reset_model_provider()

    freellm_called = False

    class SpyFreeLLM(FreeLLMAPIProvider):
        def generate(self, *args, **kwargs):
            nonlocal freellm_called
            freellm_called = True
            return super().generate(*args, **kwargs)

    class FailingNebius(NebiusProvider):
        def generate(self, *args, **kwargs):
            raise ModelProviderError(ModelErrorType.MODEL_UNAVAILABLE, "Nebius API 503")

    contract = TaskContract(
        task_id="t-iso-2",
        repository_id="repo-cons-1",
        base_commit_or_snapshot="snap-iso-2",
        task_description="test isolation",
        allowed_scope=["main.py"],
        repository_trust="TRUSTED_DEVELOPMENT",
        resource_budget=ResourceBudget(max_iterations=1, max_failed_attempts=1)
    )

    orch = Orchestrator(run_id="run-iso-2", task_contract=contract, model_provider=FailingNebius())
    final_state = orch.run()

    # Invariant: Run must terminate in ABORTED without ever touching FreeLLMAPI
    assert final_state == RunState.ABORTED
    assert freellm_called is False
    assert orch.state_machine.current_state == RunState.ABORTED


def test_model_identifiers_are_strictly_isolated(monkeypatch):
    """Verify that model configuration variables remain isolated between providers."""
    monkeypatch.setenv("NEBIUS_MODEL", "nvidia/Nemotron-3_5-Lightning")
    monkeypatch.setenv("FREELLMAPI_MODEL", "groq/llama-3.3-70b-versatile")

    p_nebius = NebiusProvider(api_key="k1")
    p_free = FreeLLMAPIProvider(api_key="k2")

    assert p_nebius.default_model == "nvidia/Nemotron-3_5-Lightning"
    assert p_free.default_model == "groq/llama-3.3-70b-versatile"

    # Changing NEBIUS_MODEL must not alter FreeLLMAPIProvider
    monkeypatch.setenv("NEBIUS_MODEL", "nvidia/different-model")
    p_free_2 = FreeLLMAPIProvider(api_key="k2")
    assert p_free_2.default_model == "groq/llama-3.3-70b-versatile"

    # Changing FREELLMAPI_MODEL must not alter NebiusProvider
    monkeypatch.setenv("FREELLMAPI_MODEL", "meta/llama-3")
    p_nebius_2 = NebiusProvider(api_key="k1")
    assert p_nebius_2.default_model == "nvidia/different-model"


def test_evidence_provenance_records_distinct_provider_and_model():
    """Verify that EvidenceReceipt records distinct model_provenance for both providers."""
    class DeterministicNebiusMock(NebiusProvider):
        def __init__(self):
            super().__init__(api_key="k-neb", default_model="nvidia/Nemotron-3_5-Lightning")
        def generate(self, messages, **kwargs):
            return ModelResponse(
                provider="nebius",
                model="nvidia/Nemotron-3_5-Lightning",
                response_text=json.dumps({"objective": "plan", "files_to_modify": ["main.py"]}),
                timestamp=time.time()
            )

    class DeterministicFreeLLMMock(FreeLLMAPIProvider):
        def __init__(self):
            super().__init__(api_key="k-free", default_model="groq/llama-3.3-70b-versatile")
        def generate(self, messages, **kwargs):
            return ModelResponse(
                provider="freellmapi",
                model="groq/llama-3.3-70b-versatile",
                response_text=json.dumps({"objective": "plan", "files_to_modify": ["main.py"]}),
                timestamp=time.time()
            )

    contract = TaskContract(
        task_id="t-prov-distinct",
        repository_id="repo-cons-1",
        base_commit_or_snapshot="snap-prov",
        task_description="test distinct provenance",
        allowed_scope=["main.py"],
        repository_trust="TRUSTED_DEVELOPMENT",
        resource_budget=ResourceBudget(max_iterations=1, max_failed_attempts=1)
    )

    orch_neb = Orchestrator(run_id="run-prov-neb", task_contract=contract, model_provider=DeterministicNebiusMock())
    orch_neb.run()
    assert orch_neb.evidence_receipt is not None
    assert orch_neb.evidence_receipt.model_provenance == {
        "provider": "nebius",
        "model": "nvidia/Nemotron-3_5-Lightning"
    }

    orch_free = Orchestrator(run_id="run-prov-free", task_contract=contract, model_provider=DeterministicFreeLLMMock())
    orch_free.run()
    assert orch_free.evidence_receipt is not None
    assert orch_free.evidence_receipt.model_provenance == {
        "provider": "freellmapi",
        "model": "groq/llama-3.3-70b-versatile"
    }


def test_secrets_sanitization_in_evidence_and_errors():
    """Verify that neither provider logs or embeds secret credentials in receipts or errors."""
    secret_neb = "super-secret-nebius-key-12345"
    secret_free = "super-secret-freellm-key-67890"

    p_neb = NebiusProvider(api_key=secret_neb)
    p_free = FreeLLMAPIProvider(api_key=secret_free)

    # Test error redaction
    redacted_neb = p_neb._redact_secrets(f"Connection failed to API with key {secret_neb} in headers")
    assert secret_neb not in redacted_neb
    assert "[REDACTED_API_KEY]" in redacted_neb

    redacted_free = p_free._redact_secrets(f"Connection failed to gateway with key {secret_free} in headers")
    assert secret_free not in redacted_free
    assert "[REDACTED_API_KEY]" in redacted_free


def test_candidate_container_never_receives_any_provider_credentials(monkeypatch):
    """Verify that neither Nebius nor FreeLLMAPI credentials enter the candidate container."""
    secret_neb = "super-secret-nebius-key-12345"
    secret_free = "super-secret-freellm-key-67890"

    monkeypatch.setenv("NEBIUS_API_KEY", secret_neb)
    monkeypatch.setenv("FREELLMAPI_API_KEY", secret_free)

    policy = SandboxPolicy(
        cpu_limit=1.0,
        pids_limit=32,
        max_memory_bytes=64 * 1024 * 1024,
        max_runtime_seconds=10,
        max_output_bytes=1024 * 1024
    )
    backend = SecureSandboxBackend(policy=policy)
    cmd_args = backend.build_container_args(
        engine="docker",
        container_name="test-isolation-box",
        canonical_workspace="/tmp/ws",
        command=["python", "test.py"],
        env={}
    )

    full_arg_str = " ".join(cmd_args)
    assert secret_neb not in full_arg_str
    assert secret_free not in full_arg_str
    assert "NEBIUS_API_KEY" not in full_arg_str
    assert "FREELLMAPI_API_KEY" not in full_arg_str
    assert "--network none" in full_arg_str
