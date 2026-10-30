import pytest

from app.core.exceptions import LLMOutputValidationError, LLMUnavailableError
from app.llm.fake_provider import FakeLLMProvider
from app.llm.provider import LLMProviderError
from app.llm.service import _complete_with_bounded_retries

VALID_JSON = """{
  "summary": "Add a delete button to the Investigations page.",
  "understanding": {"goal": "Delete investigations", "affected_area": "UI"},
  "relevant_files": [],
  "affected_symbols": [],
  "implementation_plan": [],
  "dependencies": [],
  "risks": [],
  "uncertainties": [],
  "confidence": 0.8
}"""


def test_service_returns_valid_result_on_first_try():
    provider = FakeLLMProvider(responses=[VALID_JSON])
    result = _complete_with_bounded_retries(
        provider, system_prompt="s", user_prompt="u", max_retries=2,
        temperature=0.2, max_output_tokens=500, timeout_seconds=10,
    )
    assert result.summary.startswith("Add a delete button")
    assert len(provider.requests) == 1


def test_service_retries_on_invalid_json_then_succeeds():
    provider = FakeLLMProvider(responses=["not json", VALID_JSON])
    result = _complete_with_bounded_retries(
        provider, system_prompt="s", user_prompt="u", max_retries=2,
        temperature=0.2, max_output_tokens=500, timeout_seconds=10,
    )
    assert result.confidence == 0.8
    assert len(provider.requests) == 2
    # The retry prompt must reference the validation error, not resend the
    # original prompt verbatim.
    assert "validation" in provider.requests[1].user_prompt.lower()


def test_service_retries_on_schema_violation_then_succeeds():
    invalid_schema = '{"summary": "ok", "confidence": 5.0}'  # confidence out of range
    provider = FakeLLMProvider(responses=[invalid_schema, VALID_JSON])
    result = _complete_with_bounded_retries(
        provider, system_prompt="s", user_prompt="u", max_retries=2,
        temperature=0.2, max_output_tokens=500, timeout_seconds=10,
    )
    assert result.confidence == 0.8


def test_service_raises_after_exhausting_retries():
    provider = FakeLLMProvider(responses=["bad", "still bad", "nope"])
    with pytest.raises(LLMOutputValidationError):
        _complete_with_bounded_retries(
            provider, system_prompt="s", user_prompt="u", max_retries=2,
            temperature=0.2, max_output_tokens=500, timeout_seconds=10,
        )
    assert len(provider.requests) == 3  # initial + 2 retries, never more


def test_service_does_not_retry_on_provider_error():
    """A provider-level failure (auth/timeout/rate-limit) should fail
    immediately as LLMUnavailableError, not burn retry attempts on a
    corrected prompt that can't fix a transport problem."""
    provider = FakeLLMProvider(error=LLMProviderError("simulated timeout"))
    with pytest.raises(LLMUnavailableError):
        _complete_with_bounded_retries(
            provider, system_prompt="s", user_prompt="u", max_retries=2,
            temperature=0.2, max_output_tokens=500, timeout_seconds=10,
        )
    assert len(provider.requests) == 1


def test_service_respects_zero_max_retries():
    provider = FakeLLMProvider(responses=["bad"])
    with pytest.raises(LLMOutputValidationError):
        _complete_with_bounded_retries(
            provider, system_prompt="s", user_prompt="u", max_retries=0,
            temperature=0.2, max_output_tokens=500, timeout_seconds=10,
        )
    assert len(provider.requests) == 1
