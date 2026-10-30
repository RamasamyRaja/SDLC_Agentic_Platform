"""
ReasoningService: the single entry point for the reasoning layer.

analyze_task(task_id) -> load task/repository -> build bounded context
(context_builder.py, consuming M3 via M4's CodeChunk index + M4 retrieval
directly) -> call the LLM provider -> parse + validate the JSON response
against ReasoningResult (bounded retry on failure) -> ground the result
against the supplied context -> return.

This service does NOT execute anything — no code changes, no test runs, no
PR creation. It produces analysis only. See README "Milestone 5" for the
full responsibility boundary.
"""
import logging
import uuid

import pydantic
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import LLMOutputValidationError, LLMUnavailableError
from app.llm.context_builder import build_reasoning_input
from app.llm.grounding import ground_result
from app.llm.mistral_provider import get_mistral_provider
from app.llm.parsing import JSONExtractionError, extract_json
from app.llm.prompts import PROMPT_VERSION, build_retry_prompt, build_system_prompt, build_user_prompt
from app.llm.provider import LLMCompletionRequest, LLMProvider, LLMProviderError
from app.llm.schemas import ReasoningInput, ReasoningResult
from app.models.task_analysis import TaskAnalysis, TaskAnalysisStatus
from app.models.user import User
from app.services.repository_service import get_repository
from app.services.task_service import get_task

logger = logging.getLogger(__name__)


def persist_task_analysis(
    db: Session,
    *,
    task_id: uuid.UUID,
    model_name: str,
    status: TaskAnalysisStatus,
    result: ReasoningResult | None = None,
    error: str | None = None,
) -> TaskAnalysis:
    """
    Persists one TaskAnalysis row. Extracted here (rather than left inline
    in the API router) specifically so both the Milestone 5 API endpoint
    (app/api/task_analysis.py) and the Milestone 6 agent REASON node
    (app/agent/nodes.py) persist analysis results through the exact same
    path — no duplicated persistence logic between the two call sites.
    """
    row = TaskAnalysis(
        task_id=task_id,
        model_name=model_name,
        prompt_version=PROMPT_VERSION,
        status=status,
        result=result.model_dump(mode="json") if result is not None else None,
        error=error[:2000] if error else None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def analyze_task(
    db: Session,
    *,
    user: User,
    task_id: uuid.UUID,
    provider: LLMProvider | None = None,
) -> tuple[ReasoningResult, ReasoningInput, str]:
    """
    Runs the full reasoning pipeline for a task. Returns
    (grounded_result, context_used, model_name) — the context is returned
    too so callers (the API layer, tests) can inspect exactly what was sent
    without a second context-build.

    `provider` is injectable for tests (FakeLLMProvider); defaults to the
    real Mistral provider via configuration.
    """
    settings = get_settings()

    task = get_task(db, user=user, task_id=task_id)
    repository = get_repository(db, user=user, repository_id=task.repository_id)

    if provider is None:
        try:
            provider = get_mistral_provider()
        except Exception as exc:  # noqa: BLE001 - any provider construction failure is "unavailable"
            raise LLMUnavailableError(f"LLM provider unavailable: {exc}") from exc

    context = build_reasoning_input(db, user=user, task=task, repository=repository)

    system_prompt = build_system_prompt()
    user_prompt = build_user_prompt(context)

    result = _complete_with_bounded_retries(
        provider,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_retries=settings.LLM_MAX_RETRIES,
        temperature=settings.LLM_TEMPERATURE,
        max_output_tokens=settings.LLM_MAX_OUTPUT_TOKENS,
        timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
    )

    grounded = ground_result(result, context)
    return grounded, context, provider.model_name


def _complete_with_bounded_retries(
    provider: LLMProvider,
    *,
    system_prompt: str,
    user_prompt: str,
    max_retries: int,
    temperature: float,
    max_output_tokens: int,
    timeout_seconds: int,
) -> ReasoningResult:
    attempt = 0
    last_error: Exception | None = None
    last_raw_text: str | None = None
    current_user_prompt = user_prompt

    while attempt <= max_retries:
        request = LLMCompletionRequest(
            system_prompt=system_prompt,
            user_prompt=current_user_prompt,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            timeout_seconds=timeout_seconds,
        )
        try:
            response = provider.complete(request)
        except LLMProviderError as exc:
            # A provider-level failure (auth/timeout/rate-limit/transport)
            # is not something a corrected prompt can fix — fail immediately
            # rather than burning retries on it.
            raise LLMUnavailableError(str(exc)) from exc

        last_raw_text = response.text

        try:
            payload = extract_json(response.text)
            result = ReasoningResult.model_validate(payload)
            return result
        except (JSONExtractionError, pydantic.ValidationError) as exc:
            last_error = exc
            logger.warning("LLM output validation failed (attempt %d): %s", attempt + 1, exc)
            current_user_prompt = build_retry_prompt(previous_response=response.text, validation_error=str(exc))
            attempt += 1

    raise LLMOutputValidationError(
        f"Model output failed validation after {max_retries + 1} attempt(s): {last_error}. "
        f"Last raw response: {(last_raw_text or '')[:500]}"
    )
