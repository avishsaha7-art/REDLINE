import os
import time
import requests
import json
from typing import Dict, Any, Optional
from .provider import ModelProvider, ModelResponse, ModelProviderError, ModelErrorType

class NebiusProvider(ModelProvider):
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, default_model: Optional[str] = None, max_response_bytes: Optional[int] = None):
        self.api_key = api_key or os.environ.get("NEBIUS_API_KEY")
        self.base_url = base_url or os.environ.get("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1/")
        self.default_model = default_model or os.environ.get("NEBIUS_MODEL")
        
        limit_str = os.environ.get("NEBIUS_MAX_RESPONSE_BYTES", "1048576") # Default 1MB
        if max_response_bytes is not None:
            self.max_response_bytes = max_response_bytes
        else:
            try:
                self.max_response_bytes = int(limit_str)
            except ValueError:
                self.max_response_bytes = -1
                
        if self.max_response_bytes <= 0:
            raise ModelProviderError(ModelErrorType.MODEL_CONFIGURATION_ERROR, "NEBIUS_MAX_RESPONSE_BYTES must be a positive integer.")
        
    def generate(
        self,
        messages: list[Dict[str, Any]],
        *,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        request_id: Optional[str] = None,
    ) -> ModelResponse:
        
        if not self.api_key:
            raise ModelProviderError(ModelErrorType.MODEL_CONFIGURATION_ERROR, "Nebius API key is not configured.")
        
        active_model = model or self.default_model
        if not active_model:
            raise ModelProviderError(ModelErrorType.MODEL_CONFIGURATION_ERROR, "No model specified or configured for Nebius.")
            
        endpoint = self.base_url.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": active_model,
            "messages": messages,
        }
        
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        start_time = time.time()
        
        try:
            response = requests.post(endpoint, json=payload, headers=headers, timeout=60, stream=True)
        except requests.exceptions.Timeout:
            raise ModelProviderError(ModelErrorType.MODEL_TIMEOUT, "Request to Nebius API timed out.")
        except requests.exceptions.ConnectionError:
            raise ModelProviderError(ModelErrorType.MODEL_UNAVAILABLE, "Nebius API is currently unreachable.")
        except requests.exceptions.RequestException as e:
            raise ModelProviderError(ModelErrorType.MODEL_PROVIDER_ERROR, f"Request error: {str(e)}")
            
        latency_ms = (time.time() - start_time) * 1000
        
        if response.status_code == 401 or response.status_code == 403:
            raise ModelProviderError(ModelErrorType.MODEL_AUTHENTICATION_ERROR, "Nebius authentication failed.")
        elif response.status_code == 429:
            raise ModelProviderError(ModelErrorType.MODEL_RATE_LIMIT, "Nebius rate limit exceeded.")
        elif response.status_code != 200:
            raise ModelProviderError(ModelErrorType.MODEL_PROVIDER_ERROR, f"Nebius API returned status {response.status_code}: {response.text}")
            
        content_bytes = bytearray()
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                content_bytes.extend(chunk)
                if len(content_bytes) > self.max_response_bytes:
                    response.close()
                    raise ModelProviderError(
                        ModelErrorType.MODEL_RESOURCE_LIMIT,
                        f"Response exceeded maximum configured size of {self.max_response_bytes} bytes."
                    )
        
        try:
            data = json.loads(content_bytes.decode('utf-8'))
        except Exception:
            raise ModelProviderError(ModelErrorType.MODEL_INVALID_RESPONSE, "Failed to parse Nebius JSON response.")
            
        if "choices" not in data or not data["choices"]:
            raise ModelProviderError(ModelErrorType.MODEL_INVALID_RESPONSE, "Nebius response missing 'choices'.")
            
        choice = data["choices"][0]
        message = choice.get("message", {})
        content = message.get("content", "")
        
        usage = data.get("usage", {})
        
        return ModelResponse(
            request_id=request_id,
            provider="nebius",
            model=active_model,
            response_text=content,
            finish_reason=choice.get("finish_reason"),
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            latency_ms=latency_ms,
            timestamp=time.time(),
            provider_request_id=data.get("id")
        )
