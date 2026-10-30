"""
MistralProvider: the real `LLMProvider` implementation, backed by the
official `mistralai` Python SDK.

CAPABILITIES ACTUALLY USED (inspected against the installed SDK version —
see README "Milestone 5" for how this was verified, not assumed):
  - `client.chat.complete(..., response_format={"type": "json_object"})`:
    Mistral's JSON mode. This *guarantees the response is valid JSON*, but
    — per Mistral's own documented behavior — does NOT guarantee it matches
    any particular schema. That's why service.py still runs full Pydantic
    validation on every response; JSON mode is a floor (parseable JSON),
    not a substitute for schema validation. (Mistral also offers a
    `"json_schema"` response-format mode on some models, which *does*
    enforce a schema — not used here, to keep this provider working
    uniformly across whichever MISTRAL_MODEL is configured, rather than
    depending on per-model schema-mode support.)
  - `temperature`, `max_tokens`, `timeout_ms`: passed straight through,
    all confirmed present on the SDK's `chat.complete` signature.
  - Bounded retries are NOT implemented inside this provider — that's
    service.py's job (LLM_MAX_RETRIES), since a retry here needs to revise
    the *prompt* (asking the model to fix a validation error), which this
    provider has no visibility into.
"""
import logging

from mistralai.client import Mistral

from app.core.config import get_settings
from app.llm.provider import (
    LLMAuthenticationError,
    LLMCompletionRequest,
    LLMCompletionResponse,
    LLMProvider,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
)

logger = logging.getLogger(__name__)


class MistralProvider(LLMProvider):
    def __init__(self, api_key: str, model: str, base_url: str | None = None) -> None:
        if not api_key:
            raise LLMAuthenticationError("MISTRAL_API_KEY is not configured")
        self._model = model
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["server_url"] = base_url
        self._client = Mistral(**client_kwargs)

    @property
    def model_name(self) -> str:
        return self._model

    def complete(self, request: LLMCompletionRequest) -> LLMCompletionResponse:
        response_format = {"type": "json_object"} if request.json_mode else None

        try:
            response = self._client.chat.complete(
                model=self._model,
                messages=[
                    {"role": "system", "content": request.system_prompt},
                    {"role": "user", "content": request.user_prompt},
                ],
                temperature=request.temperature,
                max_tokens=request.max_output_tokens,
                timeout_ms=request.timeout_seconds * 1000,
                response_format=response_format,
            )
        except TimeoutError as exc:
            raise LLMTimeoutError(f"Mistral request timed out after {request.timeout_seconds}s") from exc
        except Exception as exc:  # noqa: BLE001 - any transport/SDK failure becomes a clean provider error
            status = getattr(exc, "status_code", None)
            if status == 401:
                raise LLMAuthenticationError(f"Mistral authentication failed: {exc}") from exc
            if status == 429:
                raise LLMRateLimitError(f"Mistral rate limit exceeded: {exc}") from exc
            raise LLMProviderError(f"Mistral request failed: {exc.__class__.__name__}: {exc}") from exc

        if not response.choices:
            raise LLMProviderError("Mistral returned no choices")

        content = response.choices[0].message.content
        if isinstance(content, list):
            # Some SDK versions can return content as a list of content
            # blocks rather than a plain string — normalize defensively.
            content = "".join(getattr(part, "text", "") for part in content)

        return LLMCompletionResponse(text=content or "", model=self._model)


def get_mistral_provider() -> MistralProvider:
    settings = get_settings()
    return MistralProvider(
        api_key=settings.MISTRAL_API_KEY,
        model=settings.MISTRAL_MODEL,
        base_url=settings.MISTRAL_BASE_URL,
    )
