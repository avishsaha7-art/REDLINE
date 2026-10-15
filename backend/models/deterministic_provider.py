import time
import json
import hashlib
from typing import Dict, Any, Optional

from backend.models.provider import ModelProvider, ModelResponse, ModelProviderError, ModelErrorType

class DeterministicTestProvider(ModelProvider):
    def __init__(self, predefined_response: str = "", metadata: Optional[Dict[str, Any]] = None):
        self.predefined_response = predefined_response
        self.metadata = metadata or {}
        self.calls = []
        
    def generate(
        self,
        messages: list[Dict[str, Any]],
        *,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        request_id: Optional[str] = None,
    ) -> ModelResponse:
        
        self.calls.append(messages)
        
        if self.predefined_response == "ERROR":
            raise ModelProviderError(ModelErrorType.MODEL_PROVIDER_ERROR, "Mock error")
        
        # Optionally route responses based on the request content if we have predefined routes
        # But usually we just return the predefined_response injected during initialization for tests.
        response_text = self.predefined_response
        
        if not response_text:
            system_msg = messages[0]["content"] if messages else ""
            if "REDLINE Architect" in system_msg:
                response_text = json.dumps({
                    "objective": "test",
                    "files_to_inspect": [],
                    "files_to_modify": ["main.py"],
                    "implementation_steps": [],
                    "acceptance_criteria": [],
                    "constraints": [],
                    "risks": [],
                    "expected_tests": []
                })
            elif "REDLINE Builder" in system_msg:
                diff = "--- a/main.py\n+++ b/main.py\n@@ -1 +1 @@\n-a\n+b\n"
                response_text = json.dumps({
                    "changed_files": ["main.py"],
                    "diff": diff
                })
            elif "REDLINE Judge" in system_msg:
                response_text = json.dumps({
                    "summary": "Deterministic verification verified the changes within scope.",
                    "verified_claims": ["Patch passed deterministic tests"],
                    "failed_claims": [],
                    "evidence_references": [],
                    "limitations": "Deterministic test scope.",
                    "confidence": "HIGH"
                })
            elif "REDLINE Repairer" in system_msg:
                diff = "--- a/main.py\n+++ b/main.py\n@@ -1 +1 @@\n-a\n+b\n"
                response_text = json.dumps({
                    "changed_files": ["main.py"],
                    "diff": diff,
                    "target_failure": "Boundary test failure",
                    "reasoning_summary": "Handled boundary case."
                })
        
        # Check max tokens simple enforcement for oversized output testing
        if max_tokens is not None and len(response_text) > max_tokens * 4: # rough approximation for testing
            raise ModelProviderError(ModelErrorType.MODEL_RESOURCE_LIMIT, "Response exceeded maximum configured tokens.")
            
        return ModelResponse(
            request_id=request_id,
            provider="deterministic-test",
            model=model or "test-model-v1",
            response_text=response_text,
            finish_reason="stop",
            input_tokens=len(str(messages)) // 4,
            output_tokens=len(response_text) // 4,
            latency_ms=1.5,
            timestamp=time.time(),
            provider_request_id=f"test-req-{hashlib.md5(str(messages).encode()).hexdigest()[:8]}"
        )
