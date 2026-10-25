import os
from typing import Dict, Any, Optional, List

from .provider import ModelResponse, ModelProviderError, ModelErrorType
from .openai_compatible_provider import OpenAICompatibleProvider


class FreeLLMAPIProvider(OpenAICompatibleProvider):
    """
    FreeLLMAPI local OpenAI-compatible gateway inference provider.
    Inherits from OpenAICompatibleProvider with local gateway defaults,
    strict loopback/private host boundary isolation, and bounded response limits.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        default_model: Optional[str] = None,
        max_response_bytes: Optional[int] = None,
        allowed_hostnames: Optional[List[str]] = None,
        timeout_seconds: float = 60.0,
        require_api_key: bool = True,
        allowed_ports: Optional[List[int]] = None,
        allowed_schemes: Optional[List[str]] = None,
    ):
        resolved_key = api_key or os.environ.get("FREELLMAPI_API_KEY")
        resolved_url = base_url or os.environ.get("FREELLMAPI_BASE_URL", "http://127.0.0.1:3001/v1")
        clean_url = (resolved_url or "").rstrip("/")
        if clean_url:
            from urllib.parse import urlparse
            p = urlparse(clean_url)
            if not p.path or p.path == "/":
                clean_url = f"{clean_url}/v1"

        resolved_model = default_model or os.environ.get("FREELLMAPI_MODEL", "auto")

        limit_str = os.environ.get("FREELLMAPI_MAX_RESPONSE_BYTES", "1048576")
        if max_response_bytes is not None:
            resolved_bytes = max_response_bytes
        else:
            try:
                resolved_bytes = int(limit_str)
            except ValueError:
                resolved_bytes = -1

        if resolved_bytes <= 0:
            raise ModelProviderError(
                ModelErrorType.MODEL_CONFIGURATION_ERROR,
                "FREELLMAPI_MAX_RESPONSE_BYTES must be a positive integer."
            )

        if allowed_hostnames is not None:
            approved = allowed_hostnames
        else:
            approved = ["localhost", "127.0.0.1", "::1"]
            if os.environ.get("REDLINE_CONTAINERIZED") == "1" or os.environ.get("REDLINE_IN_CONTAINER") == "1":
                approved.append("host.docker.internal")
            extra = os.environ.get("FREELLMAPI_APPROVED_HOSTS")
            if extra:
                approved = approved + [h.strip().lower() for h in extra.split(",") if h.strip()]

        if allowed_ports is not None:
            approved_ports = allowed_ports
        else:
            approved_ports = [3001]
            extra_ports = os.environ.get("FREELLMAPI_APPROVED_PORTS")
            if extra_ports:
                try:
                    approved_ports = approved_ports + [int(p.strip()) for p in extra_ports.split(",") if p.strip()]
                except ValueError:
                    pass

        if allowed_schemes is not None:
            approved_schemes = allowed_schemes
        else:
            approved_schemes = ["http", "https"]

        super().__init__(
            api_key=resolved_key,
            base_url=clean_url,
            default_model=resolved_model,
            max_response_bytes=resolved_bytes,
            timeout_seconds=timeout_seconds,
            provider_name="freellmapi",
            allowed_hostnames=approved,
            require_api_key=require_api_key,
            allowed_ports=approved_ports,
            allowed_schemes=approved_schemes,
        )
