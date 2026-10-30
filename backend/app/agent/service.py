"""
AgentService: the single entry point for running the LangGraph workflow.

run_agent_workflow(task_id) -> compiles/reuses the graph (graph.py) ->
invokes it with a fresh AgentState and the DB session/user/optional LLM
provider passed via config["configurable"] (never through state - see
state.py) -> persists a terminal AgentExecution row -> returns an
AgentExecutionResult, or re-raises the original M1-M5 exception type if
the workflow failed, so the API layer's existing exception handlers
(app/api/errors.py) map it to the same HTTP status every other endpoint
uses for that failure.
"""
import uuid

from sqlalchemy.orm import Session

from app.agent.graph import build_agent_graph
from app.agent.models import AgentAction, AgentExecutionResult, AgentExecutionStatus
from app.agent.state import AgentState
from app.core.exceptions import (
    LLMOutputValidationError,
    LLMUnavailableError,
    NotFoundError,
    OwnershipError,
    ValidationError,
)
from app.llm.provider import LLMProvider
from app.llm.schemas import ReasoningResult
from app.models.agent_execution import AgentExecution
from app.models.agent_execution import AgentExecutionStatus as DBExecutionStatus
from app.models.task import Task
from app.models.user import User

# Maps a state["error_type"] string (the failing exception's class name)
# back to the actual exception class, so the original error type/HTTP
# mapping is preserved end-to-end rather than collapsing every failure to
# one generic "workflow failed" error.
_ERROR_TYPE_REGISTRY: dict[str, type[Exception]] = {
    "NotFoundError": NotFoundError,
    "OwnershipError": OwnershipError,
    "ValidationError": ValidationError,
    "LLMUnavailableError": LLMUnavailableError,
    "LLMOutputValidationError": LLMOutputValidationError,
}


def run_agent_workflow(
    db: Session,
    *,
    user: User,
    task_id: uuid.UUID,
    provider: LLMProvider | None = None,
) -> AgentExecutionResult:
    graph = build_agent_graph()

    execution_id = uuid.uuid4()
    initial_state: AgentState = {
        "task_id": str(task_id),
        "stage": "START",
        "status": "RUNNING",
        "errors": [],
    }
    config = {
        "configurable": {"db": db, "user": user, "provider": provider, "thread_id": str(execution_id)}
    }

    final_state: AgentState = graph.invoke(initial_state, config=config)

    status = final_state.get("status", "FAILED")
    errors = final_state.get("errors", [])
    reasoning_result_raw = final_state.get("reasoning_result")
    reasoning_result = ReasoningResult.model_validate(reasoning_result_raw) if reasoning_result_raw else None
    action = AgentAction(final_state["action"]) if final_state.get("action") else None
    model_name = final_state.get("model_name")

    db_status = DBExecutionStatus.COMPLETED if status == "COMPLETED" else DBExecutionStatus.FAILED
    execution = AgentExecution(
        id=execution_id,
        task_id=task_id,
        status=db_status,
        action=action.value if action else None,
        model_name=model_name,
        result=reasoning_result.model_dump(mode="json") if reasoning_result else None,
        error="; ".join(errors) if errors else None,
        tool_call_count=final_state.get("tool_call_count"),
        tool_results=final_state.get("tool_results"),
    )
    # If LOAD_TASK failed because task_id itself doesn't exist, there is no
    # valid task row to attach an AgentExecution to (FK constraint) — skip
    # persistence in that specific case rather than crash on an IntegrityError.
    # Every other failure/success path has a real task, so this stays a
    # narrow, well-understood exception rather than a broad try/except.
    task_exists = db.get(Task, task_id) is not None
    if task_exists:
        db.add(execution)
        db.commit()

    if status == "FAILED":
        error_type_name = final_state.get("error_type")
        exc_class = _ERROR_TYPE_REGISTRY.get(error_type_name, ValidationError)
        message = errors[-1] if errors else "Agent workflow failed"
        raise exc_class(message)

    return AgentExecutionResult(
        execution_id=execution_id,
        task_id=task_id,
        status=AgentExecutionStatus.COMPLETED,
        action=action,
        reasoning_result=reasoning_result,
        model_name=model_name,
        errors=errors,
        tool_call_count=final_state.get("tool_call_count") or 0,
        tool_results=final_state.get("tool_results") or [],
    )


def get_execution(db: Session, *, user: User, task_id: uuid.UUID, execution_id: uuid.UUID) -> AgentExecution:
    """Retrieves a persisted AgentExecution, verifying it belongs to a task
    the current user owns (via the same ownership check every other
    endpoint uses)."""
    from app.services.task_service import get_task

    get_task(db, user=user, task_id=task_id)  # raises NotFoundError/OwnershipError if not owned

    execution = db.get(AgentExecution, execution_id)
    if execution is None or execution.task_id != task_id:
        raise NotFoundError(f"Execution {execution_id} not found for task {task_id}")
    return execution
