"""
Optional real-provider smoke test.

Skips cleanly (does not fail the suite) when MISTRAL_API_KEY is not set —
per the spec, the normal test suite must never require real credentials.
This is the one test file that talks to the actual Mistral API when
credentials ARE available; every other LLM-layer test uses FakeLLMProvider.
"""
import os

import pytest

from app.llm.mistral_provider import MistralProvider
from app.llm.parsing import extract_json
from app.llm.provider import LLMCompletionRequest
from app.llm.schemas import ReasoningResult

MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY")

pytestmark = pytest.mark.skipif(
    not MISTRAL_API_KEY, reason="MISTRAL_API_KEY not set — skipping real Mistral smoke test"
)


def test_real_mistral_structured_output_smoke_test():
    """
    Sends one tiny, controlled request to the real Mistral API and
    validates the response against ReasoningResult. Never modifies any
    repository, never uses a real repository_id.
    """
    from app.core.config import get_settings

    settings = get_settings()
    provider = MistralProvider(api_key=MISTRAL_API_KEY, model=settings.MISTRAL_MODEL)

    system_prompt = (
        "You are a test assistant. Respond with ONLY a JSON object matching "
        "this exact shape: "
        '{"summary": "<string>", "understanding": {"goal": "<string>", '
        '"affected_area": "<string>"}, "relevant_files": [], '
        '"affected_symbols": [], "implementation_plan": [], "dependencies": [], '
        '"risks": [], "uncertainties": [], "confidence": <number 0-1>}'
    )
    user_prompt = (
        "Task: add a health check endpoint to a FastAPI app. "
        "No repository context is available. Produce your structured analysis."
    )

    request = LLMCompletionRequest(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0.2,
        max_output_tokens=500,
        timeout_seconds=30,
    )

    response = provider.complete(request)
    payload = extract_json(response.text)
    result = ReasoningResult.model_validate(payload)

    assert result.summary
    assert 0.0 <= result.confidence <= 1.0
