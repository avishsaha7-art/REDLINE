import pytest
import os
import json
import requests
from backend.models.provider import ModelErrorType, ModelProviderError, ModelResponse
from backend.models.nebius_provider import NebiusProvider
from backend.models.schemas import TaskContract, ArchitectPlan, OperationalResult
from backend.agents.architect import ArchitectAgent
from backend.orchestrator.events import EventRecorder

class MockStreamingResponse:
    def __init__(self, data_bytes, status_code=200):
        self.data_bytes = data_bytes
        self.status_code = status_code
        self.text = ""
        
    def iter_content(self, chunk_size=8192):
        for i in range(0, len(self.data_bytes), chunk_size):
            yield self.data_bytes[i:i+chunk_size]
            
    def close(self):
        pass

# Test 1 - below limit
def test_below_limit(monkeypatch):
    data = {"id": "1", "choices": [{"message": {"content": "ok"}}]}
    data_bytes = json.dumps(data).encode("utf-8")
    def mock_post(*args, **kwargs):
        return MockStreamingResponse(data_bytes)
    monkeypatch.setattr(requests, "post", mock_post)
    
    provider = NebiusProvider(api_key="secret", default_model="model", max_response_bytes=len(data_bytes) + 10)
    resp = provider.generate([{"role": "user", "content": "hi"}])
    assert resp.response_text == "ok"

# Test 2 - exactly at limit
def test_exactly_at_limit(monkeypatch):
    data = {"id": "1", "choices": [{"message": {"content": "ok"}}]}
    data_bytes = json.dumps(data).encode("utf-8")
    def mock_post(*args, **kwargs):
        return MockStreamingResponse(data_bytes)
    monkeypatch.setattr(requests, "post", mock_post)
    
    provider = NebiusProvider(api_key="secret", default_model="model", max_response_bytes=len(data_bytes))
    resp = provider.generate([{"role": "user", "content": "hi"}])
    assert resp.response_text == "ok"

# Test 3 - one byte over limit
def test_one_byte_over_limit(monkeypatch):
    data = {"id": "1", "choices": [{"message": {"content": "ok"}}]}
    data_bytes = json.dumps(data).encode("utf-8")
    def mock_post(*args, **kwargs):
        return MockStreamingResponse(data_bytes)
    monkeypatch.setattr(requests, "post", mock_post)
    
    provider = NebiusProvider(api_key="secret", default_model="model", max_response_bytes=len(data_bytes) - 1)
    with pytest.raises(ModelProviderError) as exc_info:
        provider.generate([{"role": "user", "content": "hi"}])
    assert exc_info.value.error_type == ModelErrorType.MODEL_RESOURCE_LIMIT

# Test 4 - multibyte Unicode
def test_multibyte_unicode(monkeypatch):
    data = {"id": "1", "choices": [{"message": {"content": "😀"}}]}
    json_str = json.dumps(data, ensure_ascii=False)
    data_bytes = json_str.encode("utf-8") # '😀' is 4 bytes
    def mock_post(*args, **kwargs):
        return MockStreamingResponse(data_bytes)
    monkeypatch.setattr(requests, "post", mock_post)
    
    # Character count of json string would be smaller than byte count
    # Prove that byte count is used
    char_count = len(json_str)
    byte_count = len(data_bytes)
    assert byte_count > char_count
    
    # Set limit to char_count, which is less than byte_count, so it should fail
    provider = NebiusProvider(api_key="secret", default_model="model", max_response_bytes=char_count)
    with pytest.raises(ModelProviderError) as exc_info:
        provider.generate([{"role": "user", "content": "hi"}])
    assert exc_info.value.error_type == ModelErrorType.MODEL_RESOURCE_LIMIT

# Test 5 - malformed config
def test_malformed_config_zero():
    with pytest.raises(ModelProviderError) as exc_info:
        NebiusProvider(api_key="secret", default_model="model", max_response_bytes=0)
    assert exc_info.value.error_type == ModelErrorType.MODEL_CONFIGURATION_ERROR

def test_malformed_config_negative():
    with pytest.raises(ModelProviderError) as exc_info:
        NebiusProvider(api_key="secret", default_model="model", max_response_bytes=-10)
    assert exc_info.value.error_type == ModelErrorType.MODEL_CONFIGURATION_ERROR

def test_malformed_config_env(monkeypatch):
    monkeypatch.setenv("NEBIUS_MAX_RESPONSE_BYTES", "notanumber")
    with pytest.raises(ModelProviderError) as exc_info:
        NebiusProvider(api_key="secret", default_model="model")
    assert exc_info.value.error_type == ModelErrorType.MODEL_CONFIGURATION_ERROR

# Test 6 - extremely large configured value (validation)
def test_extremely_large_config(monkeypatch):
    # Should not crash on large value, but it should be tested
    limit = 100 * 1024 * 1024  # 100MB
    provider = NebiusProvider(api_key="secret", default_model="model", max_response_bytes=limit)
    assert provider.max_response_bytes == limit

# Test 7 - rejected response does not reach agent
def test_rejected_response_agent(monkeypatch):
    oversized_data = {"id": "1", "choices": [{"message": {"content": "x" * 2000}}]}
    data_bytes = json.dumps(oversized_data).encode("utf-8")
    
    def mock_post(*args, **kwargs):
        return MockStreamingResponse(data_bytes)
    monkeypatch.setattr(requests, "post", mock_post)
    
    provider = NebiusProvider(api_key="secret", default_model="model", max_response_bytes=1000)
    events = EventRecorder("run-1")
    agent = ArchitectAgent(tools=[], model_provider=provider, events=events)
    task = TaskContract(task_id="1", repository_id="1", base_commit_or_snapshot="1", task_description="1")
    
    res = agent.plan(task)
    assert res == OperationalResult.MODEL_FAILURE
    
    # Test 8 - rejected response is not persisted in evidence
    event_list = events.get_events()
    assert len(event_list) == 2
    assert event_list[0]["event_type"] == "MODEL_CALL_STARTED"
    assert event_list[1]["event_type"] == "MODEL_CALL_FAILED"
    assert event_list[1]["details"]["error"] == ModelErrorType.MODEL_RESOURCE_LIMIT
    
    # Verify the oversized data is nowhere in the events
    events_json = json.dumps(event_list)
    assert "x" * 2000 not in events_json

# Test 9 - secret isolation
def test_secret_isolation(monkeypatch):
    data = {"id": "1", "choices": [{"message": {"content": "ok"}}]}
    data_bytes = json.dumps(data).encode("utf-8")
    
    def mock_post(*args, **kwargs):
        return MockStreamingResponse(data_bytes)
    monkeypatch.setattr(requests, "post", mock_post)
    
    secret_key = "SECRET_API_KEY_NEVER_LOG_THIS"
    provider = NebiusProvider(api_key=secret_key, default_model="model", max_response_bytes=10)
    
    with pytest.raises(ModelProviderError) as exc_info:
        provider.generate([{"role": "user", "content": "hi"}])
        
    error_msg = str(exc_info.value)
    assert secret_key not in error_msg
    assert exc_info.value.error_type == ModelErrorType.MODEL_RESOURCE_LIMIT
