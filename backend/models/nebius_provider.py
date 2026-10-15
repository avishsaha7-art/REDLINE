import os
from typing import Dict, Any, Optional, List

from .provider import ModelResponse, ModelProviderError, ModelErrorType
from .openai_compatible_provider import OpenAICompatibleProvider


class NebiusProvider(OpenAICompatibleProvider):
    """
    Nebius Token Factory inference provider.
    Inherits from OpenAICompatibleProvider with Token Factory defaults,
    strict credential boundary isolation, port/scheme validation, and response limit validation.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        default_model: Optional[str] = None,
        max_response_bytes: Optional[int] = None,
        allowed_hostnames: Optional[List[str]] = None,
        timeout_seconds: float = 60.0,
        allowed_ports: Optional[List[int]] = None,
        allowed_schemes: Optional[List[str]] = None,
    ):
        resolved_key = api_key or os.environ.get("NEBIUS_API_KEY")
        resolved_url = base_url or os.environ.get("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1/")
        resolved_model = default_model or os.environ.get("NEBIUS_MODEL")

        limit_str = os.environ.get("NEBIUS_MAX_RESPONSE_BYTES", "1048576")
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
                "NEBIUS_MAX_RESPONSE_BYTES must be a positive integer."
            )

        if allowed_hostnames is not None:
            approved = allowed_hostnames
        else:
            approved = ["api.tokenfactory.nebius.com"]
            extra = os.environ.get("NEBIUS_APPROVED_HOSTS")
            if extra:
                approved = approved + [h.strip().lower() for h in extra.split(",") if h.strip()]

        if allowed_ports is not None:
            approved_ports = allowed_ports
        else:
            approved_ports = [443]
            extra_ports = os.environ.get("NEBIUS_APPROVED_PORTS")
            if extra_ports:
                try:
                    approved_ports.extend([int(p.strip()) for p in extra_ports.split(",") if p.strip()])
                except ValueError:
                    pass

        if allowed_schemes is not None:
            approved_schemes = allowed_schemes
        else:
            approved_schemes = ["https"]
            extra_schemes = os.environ.get("NEBIUS_APPROVED_SCHEMES")
            if extra_schemes:
                approved_schemes.extend([s.strip().lower() for s in extra_schemes.split(",") if s.strip()])

        super().__init__(
            api_key=resolved_key,
            base_url=resolved_url,
            default_model=resolved_model,
            max_response_bytes=resolved_bytes,
            timeout_seconds=timeout_seconds,
            provider_name="nebius",
            allowed_hostnames=approved,
            allowed_ports=approved_ports,
            allowed_schemes=approved_schemes,
        )
