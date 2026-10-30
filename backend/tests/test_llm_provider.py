import pytest

from app.llm.fake_provider import FakeLLMProvider
from app.llm.mistral_provider import MistralProvider
from app.llm.provider import LLMAuthenticationError, LLMCompletionRequest, LLMProviderError


def test_mistral_provider_requires_api_key():
    with pytest.raises(LLMAuthenticationError):
        MistralProvider(api_key="", model="mistral-large-latest")


def test_mistral_provider_initializes_with_key():
    provider = MistralProvider(api_key="dummy-key", model="mistral-large-latest")
    assert provider.model_name == "mistral-large-latest"


def test_mistral_provider_wraps_transport_failure_as_provider_error():
    """A real call with a dummy key must fail cleanly as LLMProviderError,
    never an unhandled exception — this exercises the actual SDK/transport
    path (fails due to network/auth in this environment), not a mock."""
    provider = MistralProvider(api_key="dummy-key-for-test", model="mistral-large-latest")
    request = LLMCompletionRequest(
        system_prompt="test",
        user_prompt="test",
        temperature=0.2,
        max_output_tokens=50,
        timeout_seconds=5,
    )
    with pytest.raises(LLMProviderError):
        provider.complete(request)


def test_fake_provider_returns_programmed_response():
    provider = FakeLLMProvider(responses=["hello"])
    request = LLMCompletionRequest(
        system_prompt="s", user_prompt="u", temperature=0.2, max_output_tokens=50, timeout_seconds=5
    )
    response = provider.complete(request)
    assert response.text == "hello"
    assert response.model == "fake-model"


def test_fake_provider_records_requests():
    provider = FakeLLMProvider(responses=["a", "b"])
    request = LLMCompletionRequest(
        system_prompt="s", user_prompt="u1", temperature=0.2, max_output_tokens=50, timeout_seconds=5
    )
    provider.complete(request)
    assert len(provider.requests) == 1
    assert provider.requests[0].user_prompt == "u1"


def test_fake_provider_raises_programmed_error():
    error = LLMProviderError("boom")
    provider = FakeLLMProvider(error=error)
    request = LLMCompletionRequest(
        system_prompt="s", user_prompt="u", temperature=0.2, max_output_tokens=50, timeout_seconds=5
    )
    with pytest.raises(LLMProviderError, match="boom"):
        provider.complete(request)


def test_fake_provider_raises_when_responses_exhausted():
    provider = FakeLLMProvider(responses=["only one"])
    request = LLMCompletionRequest(
        system_prompt="s", user_prompt="u", temperature=0.2, max_output_tokens=50, timeout_seconds=5
    )
    provider.complete(request)
    with pytest.raises(LLMProviderError):
        provider.complete(request)
