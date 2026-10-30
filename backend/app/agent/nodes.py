"""
Graph nodes. Each node has one responsibility and delegates the actual
work to an existing M1-M5 service - none of these nodes reimplement
retrieval, LLM calling, or grounding logic.

Every node follows the same failure discipline: catch the specific,
already-established domain exceptions (NotFoundError, OwnershipError,
LLMUnavailableError, ...), record status="FAILED", error_type
(the exception class name), and a human-readable message in errors -
then return early. Nothing is re-raised from inside a node; edges.py
routes a failed state straight to FINALIZE so the workflow always
terminates cleanly and FINALIZE is always the one place that persists
the terminal AgentExecution row. run_agent_workflow() in service.py is
what re-raises the ORIGINAL exception type afterward (mapped back via
error_type), so the API layer's existing exception handlers (404/403/
502/etc.) keep working exactly as they do for every other endpoint.
"""
import uuid

from langchain_core.runnables import RunnableConfig

from app.agent.models import AgentAction
from app.agent.state import AgentState
from app.core.config import get_settings
from app.core.exceptions import (
    LLMOutputValidationError,
    LLMUnavailableError,
    NotFoundError,
    OwnershipError,
    ValidationError,
)
from app.llm import service as reasoning_service
from app.llm.schemas import ReasoningResult
from app.models.task_analysis import TaskAnalysisStatus
from app.services.repository_service import get_repository
from app.services.task_service import get_task

# Exception types a node is expected to catch and turn into a failed
# state (rather than let propagate out of the graph invocation itself).
_KNOWN_FAILURE_TYPES = (
    NotFoundError,
    OwnershipError,
    ValidationError,
    LLMUnavailableError,
    LLMOutputValidationError,
)


def _record_failure(state: AgentState, stage: str, exc: Exception) -> dict:
    return {
        "stage": stage,
        "status": "FAILED",
        "error_type": exc.__class__.__name__,
        "errors": state.get("errors", []) + [f"{stage}: {exc.__class__.__name__}: {exc}"],
    }


def load_task_node(state: AgentState, config: RunnableConfig) -> dict:
    """Validates the task and its repository exist and are owned by the
    current user - fails fast, before any context-building or LLM cost is
    incurred, exactly like every other endpoint's ownership check."""
    configurable = config["configurable"]
    db = configurable["db"]
    user = configurable["user"]

    try:
        task = get_task(db, user=user, task_id=uuid.UUID(state["task_id"]))
        repository = get_repository(db, user=user, repository_id=task.repository_id)
    except _KNOWN_FAILURE_TYPES as exc:
        return _record_failure(state, "LOAD_TASK", exc)

    return {
        "stage": "LOAD_TASK",
        "status": "RUNNING",
        "repository_id": str(repository.id),
        "task_description": task.description,
        "errors": state.get("errors", []),
    }


def build_context_node(state: AgentState, config: RunnableConfig) -> dict:
    """
    Verifies the repository is in a state reasoning can actually use, and
    surfaces indexing status into state for observability/DECIDE_ACTION.

    Deliberately does NOT construct the structural/semantic context itself
    - that stays inside the existing, atomic
    app.llm.context_builder.build_reasoning_input() (Milestone 5), called
    wholesale from the REASON node below via reasoning_service.
    analyze_task(). Splitting that function's internals across two graph
    nodes would mean re-implementing part of Milestone 5 here; this node's
    job is readiness-checking only, which is a genuinely separate concern.
    """
    configurable = config["configurable"]
    db = configurable["db"]
    user = configurable["user"]

    try:
        repository = get_repository(db, user=user, repository_id=uuid.UUID(state["repository_id"]))
    except _KNOWN_FAILURE_TYPES as exc:
        return _record_failure(state, "BUILD_CONTEXT", exc)

    return {
        "stage": "BUILD_CONTEXT",
        "indexing_status": repository.indexing_status.value,
        "errors": state.get("errors", []),
    }


def reason_node(state: AgentState, config: RunnableConfig) -> dict:
    """
    Calls the existing Milestone 5 reasoning pipeline wholesale
    (context build -> prompt -> Mistral call with bounded retry ->
    grounding) and persists the result via the same helper the M5 API
    endpoint uses (reasoning_service.persist_task_analysis) - no
    retrieval, prompting, validation, or grounding logic is duplicated
    here.
    """
    configurable = config["configurable"]
    db = configurable["db"]
    user = configurable["user"]
    provider = configurable.get("provider")

    task_id = uuid.UUID(state["task_id"])

    try:
        result, _context, model_name = reasoning_service.analyze_task(
            db, user=user, task_id=task_id, provider=provider
        )
    except _KNOWN_FAILURE_TYPES as exc:
        reasoning_service.persist_task_analysis(
            db, task_id=task_id, model_name="unknown", status=TaskAnalysisStatus.FAILED, error=str(exc)
        )
        return _record_failure(state, "REASON", exc)

    reasoning_service.persist_task_analysis(
        db, task_id=task_id, model_name=model_name, status=TaskAnalysisStatus.COMPLETED, result=result
    )

    return {
        "stage": "REASON",
        "reasoning_result": result.model_dump(mode="json"),
        "model_name": model_name,
        "errors": state.get("errors", []),
    }


def validate_reasoning_node(state: AgentState) -> dict:
    """
    Basic sanity check on the already-validated-and-grounded
    ReasoningResult (Pydantic validation and grounding both already
    happened inside analyze_task() - this node only checks the result is
    present and re-parses cleanly, as a defensive guard before
    DECIDE_ACTION reads specific fields off it).
    """
    raw = state.get("reasoning_result")
    if raw is None:
        exc = ValidationError("No reasoning result available to validate")
        return _record_failure(state, "VALIDATE_REASONING", exc)

    try:
        ReasoningResult.model_validate(raw)
    except Exception as exc:  # noqa: BLE001 - any re-validation failure is a hard stop here
        return _record_failure(state, "VALIDATE_REASONING", exc)

    return {"stage": "VALIDATE_REASONING", "errors": state.get("errors", [])}


def decide_action_node(state: AgentState) -> dict:
    """
    Deterministic, rule-based action selection - NOT another LLM call.
    Reads the already-grounded ReasoningResult and applies a simple,
    explicit policy:

      - any relevant_files/affected_symbols entry failed grounding
        -> REQUEST_APPROVAL (don't auto-propose against a claim that
           doesn't check out against the supplied repository context)
      - confidence below AGENT_MIN_CONFIDENCE_FOR_AUTO_PROPOSE
        -> REQUEST_APPROVAL
      - a non-empty implementation_plan and nothing above triggered
        -> PROPOSE_CHANGE
      - otherwise -> COMPLETE (nothing concrete enough to propose)
    """
    settings = get_settings()
    result = ReasoningResult.model_validate(state["reasoning_result"])

    any_ungrounded = any(f.grounded is False for f in result.relevant_files) or any(
        s.grounded is False for s in result.affected_symbols
    )

    if any_ungrounded or result.confidence < settings.AGENT_MIN_CONFIDENCE_FOR_AUTO_PROPOSE:
        action = AgentAction.REQUEST_APPROVAL
    elif result.implementation_plan:
        action = AgentAction.PROPOSE_CHANGE
    else:
        action = AgentAction.COMPLETE

    return {"stage": "DECIDE_ACTION", "action": action.value, "errors": state.get("errors", [])}


def tool_execution_node(state: AgentState, config: RunnableConfig) -> dict:
    """
    Milestone 7: a single, BOUNDED, read-only tool-gathering pass — not a
    multi-round agentic loop. Only reached when DECIDE_ACTION selected
    PROPOSE_CHANGE (see edges.py::route_after_decide_action).

    Reasoning: Milestone 5's ReasoningResult schema does not include
    literal new file content for the model to write (no code-generation
    step exists yet — see README "Milestone 7" for why this is a
    deliberate scope boundary, not an oversight), so this node cannot
    safely auto-invoke modify_file with real content. Instead it calls
    read_file (via the tool registry, never a raw filesystem call) on
    each grounded target_files entry named in the plan, bounded by
    AGENT_MAX_TOOL_CALLS, and records what it found. modify_file/
    search_code/repository_structure/git_diff remain fully available via
    the tool registry and the explicit
    POST /api/tasks/{task_id}/tools/{tool_name} endpoint for real use —
    this node deliberately does not call them automatically without a
    concrete reason to.

    Individual tool failures (e.g. a named file doesn't actually exist)
    are recorded in `tool_results` but do NOT fail the workflow — a
    read-only observation gap is not a workflow-breaking error.
    """
    from app.core.config import get_settings
    from app.tools.base import record_tool_invocation
    from app.tools.exceptions import ToolError
    from app.tools.filesystem import read_file
    from app.tools.models import ReadFileInput

    configurable = config["configurable"]
    db = configurable["db"]
    user = configurable["user"]
    settings = get_settings()

    task_id = uuid.UUID(state["task_id"])
    repository_id = uuid.UUID(state["repository_id"])
    result = ReasoningResult.model_validate(state["reasoning_result"])

    target_files: list[str] = []
    seen: set[str] = set()
    for step in result.implementation_plan:
        for file_path in step.target_files:
            if file_path not in seen:
                seen.add(file_path)
                target_files.append(file_path)

    tool_results: list[dict] = []
    call_count = 0
    limit_reached = False

    for file_path in target_files:
        if call_count >= settings.AGENT_MAX_TOOL_CALLS:
            limit_reached = True
            break

        call_count += 1
        try:
            output = read_file(
                db, user=user, input_data=ReadFileInput(repository_id=repository_id, file_path=file_path)
            )
            tool_results.append(
                {
                    "tool": "read_file",
                    "file_path": file_path,
                    "success": True,
                    "total_lines": output.total_lines,
                }
            )
            record_tool_invocation(
                db,
                task_id=task_id,
                tool_name="read_file",
                success=True,
                input_summary={"file_path": file_path},
                result_summary={"total_lines": output.total_lines, "truncated": output.truncated},
            )
        except ToolError as exc:
            tool_results.append({"tool": "read_file", "file_path": file_path, "success": False, "error": str(exc)})
            record_tool_invocation(
                db,
                task_id=task_id,
                tool_name="read_file",
                success=False,
                input_summary={"file_path": file_path},
                error=str(exc),
            )

    return {
        "stage": "TOOL_EXECUTION",
        "tool_call_count": call_count,
        "tool_results": tool_results,
        "tool_limit_reached": limit_reached,
        "errors": state.get("errors", []),
    }


def finalize_node(state: AgentState) -> dict:
    """Terminal node - always reached, whether the run succeeded or
    failed. Sets the final status; AgentExecution persistence happens in
    service.py after graph.invoke() returns, using this final state."""
    final_status = state.get("status") or "RUNNING"
    if final_status != "FAILED":
        final_status = "COMPLETED"
    return {"stage": "FINALIZE", "status": final_status, "errors": state.get("errors", [])}
