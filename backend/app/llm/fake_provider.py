"""
FakeLLMProvider: a deterministic, offline `LLMProvider` used by the test
suite (see README "Milestone 5" testing strategy — real Mistral calls are
never made by the normal test suite, only an optional, clearly separated
real-provider smoke test that skips cleanly when MISTRAL_API_KEY is unset).

Not used by the application at runtime — only ever constructed directly by
tests, which inject it into `ReasoningService` instead of the real
provider.
"""
from app.llm.provider import (
    LLMCompletionRequest,
    LLMCompletionResponse,
    LLMProvider,
    LLMProviderError,
)


class FakeLLMProvider(LLMProvider):
    """Returns a pre-programmed response (or raises a pre-programmed
    error) regardless of the request — full control for tests."""

    def __init__(
        self,
        responses: list[str] | None = None,
        *,
        model: str = "fake-model",
        error: Exception | None = None,
    ) -> None:
        self._responses = list(responses or [])
        self._model = model
        self._error = error
        self.requests: list[LLMCompletionRequest] = []  # inspectable by tests

    @property
    def model_name(self) -> str:
        return self._model

    def complete(self, request: LLMCompletionRequest) -> LLMCompletionResponse:
        self.requests.append(request)
        if self._error is not None:
            raise self._error
        if not self._responses:
            raise LLMProviderError("FakeLLMProvider has no more programmed responses")
        text = self._responses.pop(0)
        return LLMCompletionResponse(text=text, model=self._model)
