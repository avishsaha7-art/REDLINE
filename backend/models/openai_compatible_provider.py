import os
import re
import time
import requests
import json
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse

from .provider import ModelProvider, ModelResponse, ModelProviderError, ModelErrorType


class OpenAICompatibleProvider(ModelProvider):
    """
    Shared base adapter for OpenAI-compatible HTTP inference providers.

    Provides:
    - Standardized POST /chat/completions interaction.
    - Strict base URL validation: rejects userinfo, malformed/ambiguous hosts,
      unsupported schemes, invalid/unexpected ports, and raw/integer IPs.
    - Explicitly disabled automatic HTTP redirects (allow_redirects=False) to prevent SSRF
      and credential leaking across boundaries.
    - Strict response-byte limits via streaming inspection.
    - Standardized error classification into ModelErrorType.
    - Robust secret redaction across all exception strings.
    - Accurate provider and model provenance tracking.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        default_model: Optional[str] = None,
        max_response_bytes: Optional[int] = None,
        timeout_seconds: float = 60.0,
        provider_name: str = "openai-compatible",
        allowed_hostnames: Optional[List[str]] = None,
        require_api_key: bool = True,
        allowed_ports: Optional[List[int]] = None,
        allowed_schemes: Optional[List[str]] = None,
    ):
        self.api_key = api_key
        self.base_url = (base_url or "").rstrip("/")
        self.default_model = default_model
        self.timeout_seconds = timeout_seconds
        self.provider_name = provider_name
        self.allowed_hostnames = allowed_hostnames
        self.require_api_key = require_api_key
        self.allowed_ports = allowed_ports
        self.allowed_schemes = allowed_schemes

        if max_response_bytes is not None:
            self.max_response_bytes = max_response_bytes
        else:
            self.max_response_bytes = 1048576  # 1MB default safety ceiling

        if self.max_response_bytes <= 0:
            raise ModelProviderError(
                ModelErrorType.MODEL_CONFIGURATION_ERROR,
                f"max_response_bytes must be a positive integer for {self.provider_name}."
            )

    def _validate_destination(self) -> None:
        """
        Validates that the target base_url is well-formed HTTP/HTTPS and conforms
        to the allowed hostnames, schemes, and ports policy if configured.
        Rejects userinfo, malformed/ambiguous hosts, raw/integer IPs, and out-of-policy ports.
        Prevents credential leakage, SSRF, and ambiguous destination routing.
        """
        if not self.base_url:
            raise ModelProviderError(
                ModelErrorType.MODEL_CONFIGURATION_ERROR,
                f"Base URL is not configured for {self.provider_name}."
            )

        # Disallow raw control characters, backslashes, or whitespace in base URL
        if any(c in self.base_url for c in ("\r", "\n", "\t", " ", "\\")):
            raise ModelProviderError(
                ModelErrorType.MODEL_CONFIGURATION_ERROR,
                f"Malformed base URL for {self.provider_name}: contains invalid characters or whitespace."
            )

        parsed = urlparse(self.base_url)

        # Reject userinfo (e.g. user:pass@host)
        if "@" in parsed.netloc or parsed.username is not None or parsed.password is not None:
            raise ModelProviderError(
                ModelErrorType.MODEL_CONFIGURATION_ERROR,
                f"URL userinfo (username/password) is not permitted in base URL for {self.provider_name}."
            )

        # Disallow query parameters or URL fragments
        if parsed.query or parsed.fragment:
            raise ModelProviderError(
                ModelErrorType.MODEL_CONFIGURATION_ERROR,
                f"URL query parameters and fragments are not permitted in base URL for {self.provider_name}."
            )

        # Scheme validation
        allowed_schemes = self.allowed_schemes or ("http", "https")
        if parsed.scheme not in allowed_schemes:
            raise ModelProviderError(
                ModelErrorType.MODEL_CONFIGURATION_ERROR,
                f"Invalid base URL scheme '{parsed.scheme}' for {self.provider_name}. Allowed schemes: {allowed_schemes}"
            )

        # Hostname presence
        raw_hostname = parsed.hostname
        if not raw_hostname:
            raise ModelProviderError(
                ModelErrorType.MODEL_CONFIGURATION_ERROR,
                f"Invalid base URL: missing hostname for {self.provider_name}: '{self.base_url}'"
            )

        # Check for ambiguous or deceptive hostname formats (leading/trailing dots, spaces)
        if raw_hostname != raw_hostname.strip() or raw_hostname.startswith(".") or raw_hostname.endswith("."):
            raise ModelProviderError(
                ModelErrorType.MODEL_CONFIGURATION_ERROR,
                f"Malformed hostname representation for {self.provider_name}: '{raw_hostname}'"
            )

        # Reject raw integer, hex, octal, or short-form IP representations
        if raw_hostname.isdigit():
            raise ModelProviderError(
                ModelErrorType.MODEL_CONFIGURATION_ERROR,
                f"Ambiguous raw integer IP representation is not allowed: '{raw_hostname}'"
            )
        if re.match(r"^0x[0-9a-fA-F]+$", raw_hostname):
            raise ModelProviderError(
                ModelErrorType.MODEL_CONFIGURATION_ERROR,
                f"Ambiguous hex IP representation is not allowed: '{raw_hostname}'"
            )
        dotted_parts = raw_hostname.split(".")
        if len(dotted_parts) in (2, 3) and all(p.isdigit() for p in dotted_parts):
            raise ModelProviderError(
                ModelErrorType.MODEL_CONFIGURATION_ERROR,
                f"Ambiguous short-form IP representation is not allowed: '{raw_hostname}'"
            )
        if len(dotted_parts) == 4 and any(p.isdigit() and len(p) > 1 and p.startswith("0") for p in dotted_parts):
            raise ModelProviderError(
                ModelErrorType.MODEL_CONFIGURATION_ERROR,
                f"Ambiguous octal IP representation is not allowed: '{raw_hostname}'"
            )

        # Hostname allowlist validation
        if self.allowed_hostnames is not None:
            hostname_lower = raw_hostname.lower()
            allowed = [h.lower() for h in self.allowed_hostnames]
            if hostname_lower not in allowed:
                raise ModelProviderError(
                    ModelErrorType.MODEL_CONFIGURATION_ERROR,
                    f"Credential destination policy blocked: Hostname '{hostname_lower}' is not in approved destinations for {self.provider_name}: {allowed}"
                )

        # Port validation
        try:
            port = parsed.port
        except ValueError as e:
            raise ModelProviderError(
                ModelErrorType.MODEL_CONFIGURATION_ERROR,
                f"Invalid port in base URL for {self.provider_name}: {e}"
            )

        if port is not None:
            if not (1 <= port <= 65535):
                raise ModelProviderError(
                    ModelErrorType.MODEL_CONFIGURATION_ERROR,
                    f"Port {port} is out of valid range (1-65535) for {self.provider_name}."
                )
            if self.allowed_ports is not None and port not in self.allowed_ports:
                raise ModelProviderError(
                    ModelErrorType.MODEL_CONFIGURATION_ERROR,
                    f"Unexpected port {port} for {self.provider_name}. Permitted ports: {self.allowed_ports}"
                )
        else:
            if self.allowed_ports is not None:
                default_scheme_port = 443 if parsed.scheme == "https" else 80
                if default_scheme_port not in self.allowed_ports:
                    raise ModelProviderError(
                        ModelErrorType.MODEL_CONFIGURATION_ERROR,
                        f"Default port {default_scheme_port} for scheme '{parsed.scheme}' is not permitted for {self.provider_name}: {self.allowed_ports}"
                    )

    def _redact_secrets(self, text: str) -> str:
        """
        Redacts the API key from any output, exception, or log message.
        """
        if not text:
            return ""
        if self.api_key and self.api_key in text:
            return text.replace(self.api_key, "[REDACTED_API_KEY]")
        return text

    def generate(
        self,
        messages: list[Dict[str, Any]],
        *,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        request_id: Optional[str] = None,
    ) -> ModelResponse:
        """
        Issues an OpenAI-compatible chat completion request with strict safety boundaries.
        Explicitly disables HTTP redirects (allow_redirects=False).
        """
        if self.require_api_key and not self.api_key:
            raise ModelProviderError(
                ModelErrorType.MODEL_CONFIGURATION_ERROR,
                f"{self.provider_name} API key is not configured."
            )

        self._validate_destination()

        active_model = model or self.default_model
        if not active_model:
            raise ModelProviderError(
                ModelErrorType.MODEL_CONFIGURATION_ERROR,
                f"No model specified or configured for {self.provider_name}."
            )

        endpoint = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json"
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload: Dict[str, Any] = {
            "model": active_model,
            "messages": messages,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        start_time = time.time()

        try:
            response = requests.post(
                endpoint,
                json=payload,
                headers=headers,
                timeout=self.timeout_seconds,
                stream=True,
                allow_redirects=False,
            )
        except requests.exceptions.Timeout:
            raise ModelProviderError(
                ModelErrorType.MODEL_TIMEOUT,
                f"Request to {self.provider_name} API timed out after {self.timeout_seconds}s."
            )
        except requests.exceptions.ConnectionError:
            raise ModelProviderError(
                ModelErrorType.MODEL_UNAVAILABLE,
                f"{self.provider_name} API is currently unreachable."
            )
        except requests.exceptions.RequestException as e:
            redacted_err = self._redact_secrets(str(e))
            raise ModelProviderError(
                ModelErrorType.MODEL_PROVIDER_ERROR,
                f"Request error: {redacted_err}"
            )

        latency_ms = (time.time() - start_time) * 1000

        # Disallow HTTP 3xx redirects explicitly to prevent credential leaks and SSRF
        if 300 <= response.status_code < 400:
            response.close()
            raise ModelProviderError(
                ModelErrorType.MODEL_PROVIDER_ERROR,
                f"{self.provider_name} API returned unexpected redirect (HTTP {response.status_code}). Redirects are disallowed."
            )

        if response.status_code in (401, 403):
            raise ModelProviderError(
                ModelErrorType.MODEL_AUTHENTICATION_ERROR,
                f"{self.provider_name} authentication failed."
            )
        elif response.status_code == 429:
            raise ModelProviderError(
                ModelErrorType.MODEL_RATE_LIMIT,
                f"{self.provider_name} rate limit exceeded."
            )
        elif response.status_code in (502, 503, 504):
            raise ModelProviderError(
                ModelErrorType.MODEL_UNAVAILABLE,
                f"{self.provider_name} service is unavailable (HTTP {response.status_code})."
            )
        elif response.status_code != 200:
            redacted_text = self._redact_secrets(response.text)
            raise ModelProviderError(
                ModelErrorType.MODEL_PROVIDER_ERROR,
                f"{self.provider_name} API returned status {response.status_code}: {redacted_text}"
            )

        # Stream response content to enforce bounded byte size ceiling
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
            raise ModelProviderError(
                ModelErrorType.MODEL_INVALID_RESPONSE,
                f"Failed to parse {self.provider_name} JSON response."
            )

        if "choices" not in data or not data["choices"]:
            raise ModelProviderError(
                ModelErrorType.MODEL_INVALID_RESPONSE,
                f"{self.provider_name} response missing 'choices'."
            )

        choice = data["choices"][0]
        message = choice.get("message", {})
        content = message.get("content", "")

        usage = data.get("usage", {})

        return ModelResponse(
            request_id=request_id,
            provider=self.provider_name,
            model=active_model,
            response_text=content,
            finish_reason=choice.get("finish_reason"),
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            latency_ms=latency_ms,
            timestamp=time.time(),
            provider_request_id=data.get("id")
        )
