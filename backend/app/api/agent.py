"""
Agent workflow endpoints: run the LangGraph orchestration for a task, and
inspect a past run. Never exposes raw exceptions, secrets, or unbounded
repository content — only the structured AgentExecutionResult/record.
"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agent import service as agent_service
from app.core.exceptions import WorkflowStateError
from app.schemas.agent import AgentRunRequest
from app.rbac import Permission, require_permission
from app.db.session import get_db
from app.models.user import User
from app.schemas.agent import AgentExecutionDetailResponse, AgentRunResponse

router = APIRouter(prefix="/api/tasks/{task_id}", tags=["agent"])


@router.post("/run", response_model=AgentRunResponse, status_code=201)
def run_agent_workflow(
    task_id: uuid.UUID,
    payload: AgentRunRequest = AgentRunRequest(),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.AGENT_RUN)),
) -> AgentRunResponse:
    if payload.execute_changes:
        raise WorkflowStateError(
            "Direct execution is disabled. Source changes are made only through the task lifecycle: the Architect approves "
            "the plan, then POST /api/tasks/{task_id}/implementation runs the Development Agent in an isolated branch."
        )
    result = agent_service.run_agent_workflow(db, user=current_user, task_id=task_id)
    return AgentRunResponse(
        execution_id=result.execution_id, task_id=result.task_id, status=result.status, action=result.action,
        model_name=result.model_name, reasoning_result=result.reasoning_result, errors=result.errors,
        tool_call_count=result.tool_call_count, tool_results=result.tool_results,
    )


@router.get("/run/{execution_id}", response_model=AgentExecutionDetailResponse)
def get_agent_execution(
    task_id: uuid.UUID,
    execution_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.AGENT_READ)),
) -> AgentExecutionDetailResponse:
    execution = agent_service.get_execution(
        db, user=current_user, task_id=task_id, execution_id=execution_id
    )
    return AgentExecutionDetailResponse.model_validate(execution)
