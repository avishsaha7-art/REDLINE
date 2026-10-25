import os
import threading
from typing import Optional

from .provider import ModelProvider, ModelProviderError, ModelErrorType
from .nebius_provider import NebiusProvider
from .freellmapi_provider import FreeLLMAPIProvider
from .deterministic_provider import DeterministicTestProvider

_provider_lock = threading.Lock()
_injected_provider: Optional[ModelProvider] = None


def set_model_provider(provider: Optional[ModelProvider]) -> None:
    """
    Overrides the default model provider instance, primarily used for test fixtures.
    Thread-safe.
    """
    global _injected_provider
    with _provider_lock:
        _injected_provider = provider


def reset_model_provider() -> None:
    """
    Clears any injected model provider override.
    Thread-safe.
    """
    global _injected_provider
    with _provider_lock:
        _injected_provider = None


def get_model_provider(provider_name: Optional[str] = None) -> ModelProvider:
    """
    Resolves and instantiates the authoritative ModelProvider.

    Resolution Policy:
    1. If an injected provider was set via set_model_provider() and no explicit
       provider_name is requested, return the injected provider.
    2. If provider_name or REDLINE_MODEL_PROVIDER is explicitly specified:
       - 'nebius': Requires NEBIUS_API_KEY. Fails closed with MODEL_CONFIGURATION_ERROR if missing.
       - 'freellmapi': Requires FREELLMAPI_API_KEY. Fails closed with MODEL_CONFIGURATION_ERROR if missing.
       - 'deterministic': Returns DeterministicTestProvider.
       - Any unknown value raises MODEL_CONFIGURATION_ERROR.
       *Never* silently falls back to a different provider or to deterministic mock on explicit failure.
    3. If no provider is explicitly specified (unset REDLINE_MODEL_PROVIDER):
       - If NEBIUS_API_KEY is present in environment, returns NebiusProvider.
       - Else if FREELLMAPI_API_KEY is present in environment, returns FreeLLMAPIProvider.
       - Else raises MODEL_CONFIGURATION_ERROR. Explicit REDLINE_MODEL_PROVIDER=deterministic
         is required for offline mock execution.
    """
    global _injected_provider
    with _provider_lock:
        injected = _injected_provider

    if injected is not None and provider_name is None:
        return injected

    target = (provider_name or os.environ.get("REDLINE_MODEL_PROVIDER", "")).strip().lower()

    if target:
        if target == "nebius":
            if not os.environ.get("NEBIUS_API_KEY"):
                raise ModelProviderError(
                    ModelErrorType.MODEL_CONFIGURATION_ERROR,
                    "Nebius provider selected via REDLINE_MODEL_PROVIDER, but NEBIUS_API_KEY is not configured."
                )
            return NebiusProvider()

        elif target == "freellmapi":
            if not os.environ.get("FREELLMAPI_API_KEY"):
                raise ModelProviderError(
                    ModelErrorType.MODEL_CONFIGURATION_ERROR,
                    "FreeLLMAPI provider selected via REDLINE_MODEL_PROVIDER, but FREELLMAPI_API_KEY is not configured."
                )
            return FreeLLMAPIProvider()

        elif target in ("deterministic", "deterministic-test", "mock", "test"):
            return DeterministicTestProvider()

        else:
            raise ModelProviderError(
                ModelErrorType.MODEL_CONFIGURATION_ERROR,
                f"Unknown model provider '{target}'. Supported providers: nebius, freellmapi, deterministic."
            )

    # Unset selection policy: require configured credentials for live providers
    if os.environ.get("NEBIUS_API_KEY"):
        return NebiusProvider()
    elif os.environ.get("FREELLMAPI_API_KEY"):
        return FreeLLMAPIProvider()
    else:
        raise ModelProviderError(
            ModelErrorType.MODEL_CONFIGURATION_ERROR,
            "No model provider configured. Set NEBIUS_API_KEY for Nebius (default), "
            "FREELLMAPI_API_KEY for FreeLLMAPI, or explicitly set "
            "REDLINE_MODEL_PROVIDER=deterministic for offline development/demo execution."
        )
