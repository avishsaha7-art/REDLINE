from typing import Dict, Any, Optional
from pydantic import BaseModel
from abc import ABC, abstractmethod

from enum import Enum

class ModelErrorType(str, Enum):
    MODEL_CONFIGURATION_ERROR = "MODEL_CONFIGURATION_ERROR"
    MODEL_AUTHENTICATION_ERROR = "MODEL_AUTHENTICATION_ERROR"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    MODEL_TIMEOUT = "MODEL_TIMEOUT"
    MODEL_RATE_LIMIT = "MODEL_RATE_LIMIT"
    MODEL_INVALID_RESPONSE = "MODEL_INVALID_RESPONSE"
    MODEL_PROVIDER_ERROR = "MODEL_PROVIDER_ERROR"
    MODEL_RESOURCE_LIMIT = "MODEL_RESOURCE_LIMIT"

class ModelProviderError(Exception):
    def __init__(self, error_type: ModelErrorType, message: str):
        self.error_type = error_type
        super().__init__(message)

class ModelResponse(BaseModel):
    request_id: Optional[str] = None
    provider: str
    model: str
    response_text: str
    finish_reason: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    latency_ms: Optional[float] = None
    timestamp: float
    provider_request_id: Optional[str] = None

class ModelProvider(ABC):
    @abstractmethod
    def generate(
        self,
        messages: list[Dict[str, Any]],
        *,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        request_id: Optional[str] = None,
    ) -> ModelResponse:
        pass
