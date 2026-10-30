"""
LLMProvider abstraction.

Nothing outside this module (and mistral_provider.py) should import the
Mistral SDK directly — app/llm/service.py depends only on this interface,
so the concrete provider is swappable and trivially fakeable in tests.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


class LLMProviderError(Exception):
    """Base class for provider-level failures (auth, timeout, rate limit,
    unreachable, malformed transport response). Never raised for a
    structurally-invalid-but-successfully-returned response — that's a
    validation failure, handled separately in service.py."""


class LLMAuthenticationError(LLMProviderError):
    """Missing or invalid API key."""


class LLMTimeoutError(LLMProviderError):
    """The provider did not respond within LLM_TIMEOUT_SECONDS."""


class LLMRateLimitError(LLMProviderError):
    """The provider rejected the request due to rate limiting."""


@dataclass
class LLMCompletionRequest:
    system_prompt: str
    user_prompt: str
    temperature: float
    max_output_tokens: int
    timeout_seconds: int
    # Requests JSON-mode output from providers that support it (see
    # mistral_provider.py). Providers that don't support any structured
    # output mode still receive this — service.py's Pydantic validation is
    # the real enforcement layer either way, per the "robust JSON
    # extraction + Pydantic validation" fallback the spec calls for.
    json_mode: bool = True


@dataclass
class LLMCompletionResponse:
    text: str
    model: str


class LLMProvider(ABC):
    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @abstractmethod
    def complete(self, request: LLMCompletionRequest) -> LLMCompletionResponse: ...
