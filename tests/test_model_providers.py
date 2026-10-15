import os
import json
import pytest
import requests
from unittest.mock import patch, MagicMock

from backend.models.provider import ModelErrorType, ModelProviderError, ModelResponse
from backend.models.openai_compatible_provider import OpenAICompatibleProvider
from backend.models.nebius_provider import NebiusProvider
from backend.models.freellmapi_provider import FreeLLMAPIProvider
from backend.models.deterministic_provider import DeterministicTestProvider
from backend.models.registry import (
    get_model_provider,
    set_model_provider,
    reset_model_provider,
)
from backend.models.schemas import TaskContract, OperationalResult
from backend.agents.architect import ArchitectAgent
from backend.agents.builder import BuilderAgent
from backend.agents.repairer import RepairerAgent
from backend.orchestrator.events import EventRecorder


class MockStreamingResponse:
    def __init__(self, data_bytes: bytes, status_code: int = 200, text: str = ""):
        self.data_bytes = data_bytes
        self.status_code = status_code
        self.text = text or (data_bytes.decode("utf-8", errors="replace") if data_bytes else "")

    def iter_content(self, chunk_size: int = 8192):
        for i in range(0, len(self.data_bytes), chunk_size):
            yield self.data_bytes[i:i + chunk_size]

    def close(self):
        pass


# =====================================================================
# Phase 3 Tests: Registry & Provider Selection
# =====================================================================

def test_registry_explicit_nebius_success(monkeypatch):
    monkeypatch.setenv("REDLINE_MODEL_PROVIDER", "nebius")
    monkeypatch.setenv("NEBIUS_API_KEY", "test-nebius-key")
    reset_model_provider()

    provider = get_model_provider()
    assert isinstance(provider, NebiusProvider)
    assert provider.provider_name == "nebius"
    assert provider.api_key == "test-nebius-key"


def test_registry_explicit_nebius_missing_key_fails_closed(monkeypatch):
    monkeypatch.setenv("REDLINE_MODEL_PROVIDER", "nebius")
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    reset_model_provider()

    with pytest.raises(ModelProviderError) as exc_info:
        get_model_provider()
    assert exc_info.value.error_type == ModelErrorType.MODEL_CONFIGURATION_ERROR
    assert "Nebius provider selected" in str(exc_info.value)


def test_registry_explicit_freellmapi_success(monkeypatch):
    monkeypatch.setenv("REDLINE_MODEL_PROVIDER", "freellmapi")
    monkeypatch.setenv("FREELLMAPI_API_KEY", "test-freellmapi-key")
    reset_model_provider()

    provider = get_model_provider()
    assert isinstance(provider, FreeLLMAPIProvider)
    assert provider.provider_name == "freellmapi"
    assert provider.api_key == "test-freellmapi-key"


def test_registry_explicit_freellmapi_missing_key_fails_closed(monkeypatch):
    monkeypatch.setenv("REDLINE_MODEL_PROVIDER", "freellmapi")
    monkeypatch.delenv("FREELLMAPI_API_KEY", raising=False)
    reset_model_provider()

    with pytest.raises(ModelProviderError) as exc_info:
        get_model_provider()
    assert exc_info.value.error_type == ModelErrorType.MODEL_CONFIGURATION_ERROR
    assert "FreeLLMAPI provider selected" in str(exc_info.value)


def test_registry_explicit_deterministic(monkeypatch):
    monkeypatch.setenv("REDLINE_MODEL_PROVIDER", "deterministic")
    reset_model_provider()

    provider = get_model_provider()
    assert isinstance(provider, DeterministicTestProvider)


def test_registry_unknown_provider_fails_closed(monkeypatch):
    monkeypatch.setenv("REDLINE_MODEL_PROVIDER", "unsupported-provider")
    reset_model_provider()

    with pytest.raises(ModelProviderError) as exc_info:
        get_model_provider()
    assert exc_info.value.error_type == ModelErrorType.MODEL_CONFIGURATION_ERROR
    assert "Unknown model provider 'unsupported-provider'" in str(exc_info.value)


def test_registry_unset_prefers_nebius_if_configured(monkeypatch):
    monkeypatch.delenv("REDLINE_MODEL_PROVIDER", raising=False)
    monkeypatch.setenv("NEBIUS_API_KEY", "test-nebius-key")
    monkeypatch.delenv("FREELLMAPI_API_KEY", raising=False)
    reset_model_provider()

    provider = get_model_provider()
    assert isinstance(provider, NebiusProvider)


def test_registry_unset_prefers_freellmapi_if_nebius_unset(monkeypatch):
    monkeypatch.delenv("REDLINE_MODEL_PROVIDER", raising=False)
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    monkeypatch.setenv("FREELLMAPI_API_KEY", "test-freellmapi-key")
    reset_model_provider()

    provider = get_model_provider()
    assert isinstance(provider, FreeLLMAPIProvider)


def test_registry_unset_defaults_to_deterministic(monkeypatch):
    monkeypatch.delenv("REDLINE_MODEL_PROVIDER", raising=False)
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    monkeypatch.delenv("FREELLMAPI_API_KEY", raising=False)
    reset_model_provider()

    provider = get_model_provider()
    assert isinstance(provider, DeterministicTestProvider)


def test_registry_injected_override():
    mock_prov = DeterministicTestProvider(predefined_response="custom")
    set_model_provider(mock_prov)
    try:
        assert get_model_provider() is mock_prov
    finally:
        reset_model_provider()


# =====================================================================
# Phase 1 & 2 Tests: OpenAI Compatible Provider & Parsing
# =====================================================================

def test_valid_openai_compatible_response_parsing(monkeypatch):
    payload = {
        "id": "chatcmpl-test-123",
        "choices": [
            {
                "message": {"content": "Generated completion text"},
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": 15,
            "completion_tokens": 8
        }
    }
    data_bytes = json.dumps(payload).encode("utf-8")

    def mock_post(*args, **kwargs):
        return MockStreamingResponse(data_bytes, status_code=200)

    monkeypatch.setattr(requests, "post", mock_post)

    provider = FreeLLMAPIProvider(
        api_key="test-key",
        base_url="http://localhost:3001/v1",
        default_model="auto"
    )

    resp = provider.generate([{"role": "user", "content": "hello"}], request_id="client-req-1")
    assert resp.response_text == "Generated completion text"
    assert resp.provider == "freellmapi"
    assert resp.model == "auto"
    assert resp.finish_reason == "stop"
    assert resp.input_tokens == 15
    assert resp.output_tokens == 8
    assert resp.provider_request_id == "chatcmpl-test-123"
    assert resp.request_id == "client-req-1"
    assert resp.latency_ms is not None and resp.latency_ms >= 0


def test_openai_compatible_missing_choices(monkeypatch):
    payload = {"id": "chatcmpl-123", "choices": []}
    data_bytes = json.dumps(payload).encode("utf-8")

    def mock_post(*args, **kwargs):
        return MockStreamingResponse(data_bytes, status_code=200)

    monkeypatch.setattr(requests, "post", mock_post)

    provider = FreeLLMAPIProvider(api_key="test-key")
    with pytest.raises(ModelProviderError) as exc_info:
        provider.generate([{"role": "user", "content": "hi"}])
    assert exc_info.value.error_type == ModelErrorType.MODEL_INVALID_RESPONSE
    assert "missing 'choices'" in str(exc_info.value)


def test_openai_compatible_malformed_json(monkeypatch):
    data_bytes = b"This is clearly not JSON content {{"

    def mock_post(*args, **kwargs):
        return MockStreamingResponse(data_bytes, status_code=200)

    monkeypatch.setattr(requests, "post", mock_post)

    provider = FreeLLMAPIProvider(api_key="test-key")
    with pytest.raises(ModelProviderError) as exc_info:
        provider.generate([{"role": "user", "content": "hi"}])
    assert exc_info.value.error_type == ModelErrorType.MODEL_INVALID_RESPONSE
    assert "Failed to parse" in str(exc_info.value)


def test_http_401_and_403_authentication_error(monkeypatch):
    for code in (401, 403):
        def mock_post(*args, **kwargs):
            return MockStreamingResponse(b"Forbidden", status_code=code, text="Forbidden")

        monkeypatch.setattr(requests, "post", mock_post)

        provider = FreeLLMAPIProvider(api_key="invalid-key")
        with pytest.raises(ModelProviderError) as exc_info:
            provider.generate([{"role": "user", "content": "hi"}])
        assert exc_info.value.error_type == ModelErrorType.MODEL_AUTHENTICATION_ERROR


def test_http_429_rate_limit(monkeypatch):
    def mock_post(*args, **kwargs):
        return MockStreamingResponse(b"Rate limit reached", status_code=429, text="Rate limit reached")

    monkeypatch.setattr(requests, "post", mock_post)

    provider = FreeLLMAPIProvider(api_key="test-key")
    with pytest.raises(ModelProviderError) as exc_info:
        provider.generate([{"role": "user", "content": "hi"}])
    assert exc_info.value.error_type == ModelErrorType.MODEL_RATE_LIMIT


def test_http_500_provider_error(monkeypatch):
    def mock_post(*args, **kwargs):
        return MockStreamingResponse(b"Internal Server Error", status_code=500, text="Internal Server Error")

    monkeypatch.setattr(requests, "post", mock_post)

    provider = FreeLLMAPIProvider(api_key="test-key")
    with pytest.raises(ModelProviderError) as exc_info:
        provider.generate([{"role": "user", "content": "hi"}])
    assert exc_info.value.error_type == ModelErrorType.MODEL_PROVIDER_ERROR
    assert "returned status 500" in str(exc_info.value)


def test_http_502_503_504_gateway_unavailable(monkeypatch):
    for code in (502, 503, 504):
        def mock_post(*args, **kwargs):
            return MockStreamingResponse(b"Service Unavailable", status_code=code, text="Service Unavailable")

        monkeypatch.setattr(requests, "post", mock_post)

        provider = FreeLLMAPIProvider(api_key="test-key")
        with pytest.raises(ModelProviderError) as exc_info:
            provider.generate([{"role": "user", "content": "hi"}])
        assert exc_info.value.error_type == ModelErrorType.MODEL_UNAVAILABLE
        assert f"HTTP {code}" in str(exc_info.value)


def test_timeout_and_connection_error_mapping(monkeypatch):
    # Timeout
    def mock_timeout(*args, **kwargs):
        raise requests.exceptions.Timeout("Connection timed out")

    monkeypatch.setattr(requests, "post", mock_timeout)
    provider = FreeLLMAPIProvider(api_key="test-key")
    with pytest.raises(ModelProviderError) as exc_info:
        provider.generate([{"role": "user", "content": "hi"}])
    assert exc_info.value.error_type == ModelErrorType.MODEL_TIMEOUT

    # Connection Error (e.g. gateway not running)
    def mock_conn_err(*args, **kwargs):
        raise requests.exceptions.ConnectionError("Connection refused on port 3001")

    monkeypatch.setattr(requests, "post", mock_conn_err)
    with pytest.raises(ModelProviderError) as exc_info:
        provider.generate([{"role": "user", "content": "hi"}])
    assert exc_info.value.error_type == ModelErrorType.MODEL_UNAVAILABLE


def test_response_byte_limit_enforced(monkeypatch):
    oversized = {"id": "1", "choices": [{"message": {"content": "x" * 2000}}]}
    data_bytes = json.dumps(oversized).encode("utf-8")

    def mock_post(*args, **kwargs):
        return MockStreamingResponse(data_bytes, status_code=200)

    monkeypatch.setattr(requests, "post", mock_post)

    provider = FreeLLMAPIProvider(api_key="test-key", max_response_bytes=500)
    with pytest.raises(ModelProviderError) as exc_info:
        provider.generate([{"role": "user", "content": "hi"}])
    assert exc_info.value.error_type == ModelErrorType.MODEL_RESOURCE_LIMIT


# =====================================================================
# Security & Destination Isolation Tests
# =====================================================================

def test_secret_redaction_in_exceptions(monkeypatch):
    secret_key = "sk-super-secret-production-token"

    def mock_post(*args, **kwargs):
        return MockStreamingResponse(
            f"Error with key {secret_key}".encode("utf-8"),
            status_code=500,
            text=f"Error with key {secret_key}"
        )

    monkeypatch.setattr(requests, "post", mock_post)

    provider = FreeLLMAPIProvider(api_key=secret_key)
    with pytest.raises(ModelProviderError) as exc_info:
        provider.generate([{"role": "user", "content": "hi"}])

    msg = str(exc_info.value)
    assert secret_key not in msg
    assert "[REDACTED_API_KEY]" in msg


def test_credential_destination_isolation_nebius():
    # Nebius must reject localhost or arbitrary foreign destinations
    provider_foreign = NebiusProvider(
        api_key="secret-nebius-token",
        base_url="https://evil-harvesting-site.com/v1"
    )
    with pytest.raises(ModelProviderError) as exc_info:
        provider_foreign.generate([{"role": "user", "content": "hi"}])
    assert exc_info.value.error_type == ModelErrorType.MODEL_CONFIGURATION_ERROR
    assert "Credential destination policy blocked" in str(exc_info.value)

    # Nebius must also reject local gateway URLs to prevent credential crossing
    provider_local = NebiusProvider(
        api_key="secret-nebius-token",
        base_url="http://localhost:3001/v1"
    )
    with pytest.raises(ModelProviderError) as exc_info:
        provider_local.generate([{"role": "user", "content": "hi"}])
    assert exc_info.value.error_type == ModelErrorType.MODEL_CONFIGURATION_ERROR


def test_credential_destination_isolation_freellmapi():
    # FreeLLMAPI must reject external non-loopback destinations by default
    provider_external = FreeLLMAPIProvider(
        api_key="secret-free-token",
        base_url="https://api.tokenfactory.nebius.com/v1"
    )
    with pytest.raises(ModelProviderError) as exc_info:
        provider_external.generate([{"role": "user", "content": "hi"}])
    assert exc_info.value.error_type == ModelErrorType.MODEL_CONFIGURATION_ERROR
    assert "Credential destination policy blocked" in str(exc_info.value)


def test_credential_env_separation(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "nebius-only-key")
    monkeypatch.delenv("FREELLMAPI_API_KEY", raising=False)

    # FreeLLMAPI must not read Nebius key
    provider = FreeLLMAPIProvider()
    assert provider.api_key is None

    # Nebius must not read FreeLLMAPI key
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    monkeypatch.setenv("FREELLMAPI_API_KEY", "freellmapi-only-key")
    nebius = NebiusProvider()
    assert nebius.api_key is None


# =====================================================================
# Provenance & Telemetry Tests
# =====================================================================

def test_provenance_and_agent_telemetry(monkeypatch):
    data = {"id": "req-999", "choices": [{"message": {"content": "{}"}}]}
    data_bytes = json.dumps(data).encode("utf-8")

    def mock_post(*args, **kwargs):
        return MockStreamingResponse(data_bytes, status_code=200)

    monkeypatch.setattr(requests, "post", mock_post)

    provider = FreeLLMAPIProvider(api_key="test-key")
    events = EventRecorder("test-run-1")

    # ArchitectAgent telemetry
    architect = ArchitectAgent(tools=[], model_provider=provider, events=events)
    task = TaskContract(task_id="t1", repository_id="r1", base_commit_or_snapshot="h1", task_description="desc")
    architect.plan(task)

    event_list = events.get_events()
    start_events = [e for e in event_list if e.get("event_type") == "MODEL_CALL_STARTED"]
    assert len(start_events) >= 1
    assert start_events[0]["details"]["provider"] == "freellmapi"

    # BuilderAgent telemetry
    events_builder = EventRecorder("test-run-2")
    builder = BuilderAgent(tools=[], model_provider=provider, events=events_builder)
    builder.build(task, MagicMock(files_to_modify=["a.py"]), {})
    b_start = [e for e in events_builder.get_events() if e.get("event_type") == "MODEL_CALL_STARTED"]
    assert len(b_start) >= 1
    assert b_start[0]["details"]["provider"] == "freellmapi"

    # RepairerAgent telemetry
    from backend.models.schemas import PatchCandidate
    events_repairer = EventRecorder("test-run-3")
    repairer = RepairerAgent(tools=[], model_provider=provider, events=events_repairer)
    patch_cand = PatchCandidate(
        patch_id="p1",
        task_id="t1",
        base_commit_or_snapshot="h1",
        diff="--- a/a.py\n+++ b/a.py\n@@ -1 +1 @@\n-a\n+b\n"
    )
    repairer.repair(task, patch_cand, "counterexample text")
    r_start = [e for e in events_repairer.get_events() if e.get("event_type") == "MODEL_CALL_STARTED"]
    assert len(r_start) >= 1
    assert r_start[0]["details"]["provider"] == "freellmapi"


def test_orchestrator_receipt_provenance():
    from backend.orchestrator.orchestrator import Orchestrator
    provider = FreeLLMAPIProvider(api_key="test-key")
    contract = TaskContract(
        task_id="t1",
        repository_id="r1",
        base_commit_or_snapshot="h1",
        task_description="test"
    )
    orch = Orchestrator(run_id="run-test", task_contract=contract, model_provider=provider)
    assert orch.model_provider is provider


def test_freellmapi_offline_behavior_fails_safely(monkeypatch):
    def mock_conn_fail(*args, **kwargs):
        raise requests.exceptions.ConnectionError("Connection refused: 127.0.0.1:3001")

    monkeypatch.setattr(requests, "post", mock_conn_fail)
    provider = FreeLLMAPIProvider(api_key="local-test-key")

    with pytest.raises(ModelProviderError) as exc_info:
        provider.generate([{"role": "user", "content": "hello"}])

    assert exc_info.value.error_type == ModelErrorType.MODEL_UNAVAILABLE
    assert "freellmapi API is currently unreachable." in str(exc_info.value)


# =====================================================================
# Step 2.3 Hardening Tests: Finding 1 (Disallow HTTP Redirects)
# =====================================================================

@pytest.mark.parametrize("status_code", [301, 302, 303, 307, 308])
def test_redirects_disabled_and_sanitized(monkeypatch, status_code):
    redirect_target = "https://evil-harvesting-site.com/intercept"
    secret_key = "secret-token-do-not-leak"

    closed = False

    class MockRedirectResponse:
        def __init__(self):
            self.status_code = status_code
            self.headers = {"Location": redirect_target}
            self.text = f"Redirecting to {redirect_target}"

        def close(self):
            nonlocal closed
            closed = True

    calls = []

    def mock_post(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        assert kwargs.get("allow_redirects") is False
        return MockRedirectResponse()

    monkeypatch.setattr(requests, "post", mock_post)

    provider = FreeLLMAPIProvider(api_key=secret_key, base_url="http://localhost:3001/v1")

    with pytest.raises(ModelProviderError) as exc_info:
        provider.generate([{"role": "user", "content": "hi"}])

    assert exc_info.value.error_type == ModelErrorType.MODEL_PROVIDER_ERROR
    error_msg = str(exc_info.value)
    # Check that error is sanitized: no redirect target, no credentials, no response body
    assert redirect_target not in error_msg
    assert secret_key not in error_msg
    assert "unexpected redirect" in error_msg
    # Ensure response was closed
    assert closed is True
    # Ensure only 1 request was made and never sent credentials to redirect destination
    assert len(calls) == 1
    assert calls[0]["args"][0] == "http://localhost:3001/v1/chat/completions"


# =====================================================================
# Step 2.3 Hardening Tests: Finding 2 (Harden Base URL Validation)
# =====================================================================

def test_url_userinfo_rejected():
    userinfo_urls = [
        "http://user:password@localhost:3001/v1",
        "http://user@localhost:3001/v1",
        "https://user:pass@api.tokenfactory.nebius.com/v1",
        "https://api.tokenfactory.nebius.com:secret@attacker.com/v1",
    ]
    for url in userinfo_urls:
        provider = OpenAICompatibleProvider(api_key="key", base_url=url, default_model="m")
        with pytest.raises(ModelProviderError) as exc_info:
            provider.generate([{"role": "user", "content": "hi"}])
        assert exc_info.value.error_type == ModelErrorType.MODEL_CONFIGURATION_ERROR
        assert "userinfo" in str(exc_info.value).lower()


def test_malformed_and_deceptive_urls_rejected():
    malformed_urls = [
        "http://localhost\\attacker.com/v1",      # backslash
        "http://localhost:3001/v1?query=param",   # query params
        "http://localhost:3001/v1#fragment",      # fragment
        "https://api.tokenfactory.nebius.com.attacker.com/v1",  # deceptive domain suffix
        "https://api.tokenfactory.nebius.com./v1", # trailing dot
        "https://.api.tokenfactory.nebius.com/v1", # leading dot
        "http:///v1",                             # missing host
        "ftp://localhost:3001/v1",                 # unsupported scheme
        "http://localhost:3001 /v1",              # whitespace
    ]
    for url in malformed_urls:
        provider = NebiusProvider(api_key="key", base_url=url, default_model="m")
        with pytest.raises(ModelProviderError) as exc_info:
            provider.generate([{"role": "user", "content": "hi"}])
        assert exc_info.value.error_type == ModelErrorType.MODEL_CONFIGURATION_ERROR


def test_invalid_and_unexpected_ports():
    invalid_ports = [
        "http://localhost:abc/v1",     # non-numeric
        "http://localhost:70000/v1",   # out of range (>65535)
        "http://localhost:0/v1",       # port 0
        "http://localhost:-80/v1",     # negative port
    ]
    for url in invalid_ports:
        provider = FreeLLMAPIProvider(api_key="key", base_url=url)
        with pytest.raises(ModelProviderError) as exc_info:
            provider.generate([{"role": "user", "content": "hi"}])
        assert exc_info.value.error_type == ModelErrorType.MODEL_CONFIGURATION_ERROR

    # Unexpected port for Nebius (only 443 permitted by policy)
    nebius_wrong_port = NebiusProvider(
        api_key="key",
        base_url="https://api.tokenfactory.nebius.com:8443/v1"
    )
    with pytest.raises(ModelProviderError) as exc_info:
        nebius_wrong_port.generate([{"role": "user", "content": "hi"}])
    assert exc_info.value.error_type == ModelErrorType.MODEL_CONFIGURATION_ERROR
    assert "Unexpected port" in str(exc_info.value)

    # Unexpected port for FreeLLMAPI when explicitly restricted
    freellm_restricted = FreeLLMAPIProvider(
        api_key="key",
        base_url="http://localhost:9000/v1",
        allowed_ports=[3001]
    )
    with pytest.raises(ModelProviderError) as exc_info:
        freellm_restricted.generate([{"role": "user", "content": "hi"}])
    assert exc_info.value.error_type == ModelErrorType.MODEL_CONFIGURATION_ERROR
    assert "Unexpected port" in str(exc_info.value)


def test_raw_integer_hex_octal_ips_rejected():
    ambiguous_ips = [
        "http://2130706433:3001/v1",   # dword / integer IP for 127.0.0.1
        "http://0x7f000001:3001/v1",   # hex IP
        "http://0177.0.0.1:3001/v1",   # octal IP
        "http://127.1:3001/v1",        # short-form dotted IP
    ]
    for url in ambiguous_ips:
        provider = FreeLLMAPIProvider(api_key="key", base_url=url)
        with pytest.raises(ModelProviderError) as exc_info:
            provider.generate([{"role": "user", "content": "hi"}])
        assert exc_info.value.error_type == ModelErrorType.MODEL_CONFIGURATION_ERROR
        assert "Ambiguous" in str(exc_info.value) or "blocked" in str(exc_info.value)


def test_nebius_scheme_policy_enforcement():
    # Nebius strictly requires https
    provider_http = NebiusProvider(
        api_key="key",
        base_url="http://api.tokenfactory.nebius.com/v1"
    )
    with pytest.raises(ModelProviderError) as exc_info:
        provider_http.generate([{"role": "user", "content": "hi"}])
    assert exc_info.value.error_type == ModelErrorType.MODEL_CONFIGURATION_ERROR
    assert "Invalid base URL scheme" in str(exc_info.value)
