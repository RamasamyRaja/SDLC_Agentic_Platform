"""
Tool invocation endpoint: POST /api/tasks/{task_id}/tools/{tool_name}.

Deliberately NOT a generic POST /execute — `tool_name` is validated against
the closed ToolRegistry (app.tools.registry), and the request body is
validated against that specific tool's own Pydantic input model before
anything runs. There is no code path here that accepts an arbitrary
shell command or arbitrary Python.

The task_id in the path scopes the call: the tool input's own
`repository_id` must match the task's repository — a user can't use one
task's endpoint to reach a different (even if also owned) repository.
Every tool call, success or failure, is recorded via
app.tools.base.record_tool_invocation (input/output kept small and
non-sensitive — see ToolInvocation's docstring).
"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.rbac import Permission, require_permission
from app.core.exceptions import ValidationError, WorkflowStateError
from app.db.session import get_db
from app.models.user import User
from app.schemas.tools import ToolDescriptor, ToolInvokeRequest, ToolInvokeResponse, ToolListResponse
from app.services.task_service import get_task
from app.tools.base import record_tool_invocation
from app.tools.exceptions import ToolError
from app.tools.registry import list_tools, run_tool

router = APIRouter(prefix="/api/tasks/{task_id}/tools", tags=["tools"])


def _small_input_summary(raw_input: dict) -> dict:
    """Strips anything that could be large/sensitive (e.g. modify_file's
    old_content/new_content) before persisting — keeps only short,
    identifying fields. See ToolInvocation's docstring."""
    allowed_keys = {"repository_id", "file_path", "query", "file_pattern", "start_line", "end_line"}
    return {k: v for k, v in raw_input.items() if k in allowed_keys}


@router.get("", response_model=ToolListResponse)
def list_available_tools(
    current_user: User = Depends(require_permission(Permission.TOOL_READ)),
) -> ToolListResponse:
    return ToolListResponse(
        tools=[ToolDescriptor(name=spec.name, description=spec.description) for spec in list_tools()]
    )


@router.post("/{tool_name}", response_model=ToolInvokeResponse, status_code=201)
def invoke_tool(
    task_id: uuid.UUID,
    tool_name: str,
    payload: ToolInvokeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.TOOL_INVOKE)),
) -> ToolInvokeResponse:
    task = get_task(db, user=current_user, task_id=task_id)

    if tool_name == "modify_file":
        # Source changes are made only by the Development Agent, after an Architect approved the plan, inside an
        # isolated branch/worktree (POST /api/tasks/{id}/implementation). This endpoint would write straight into the
        # onboarded checkout, bypassing both the approval gate and branch isolation.
        raise WorkflowStateError(
            "modify_file is not available through this endpoint. Source changes are made by the Development Agent "
            "after the Architect approves the plan (POST /api/tasks/{task_id}/implementation)."
        )

    raw_repository_id = payload.input.get("repository_id")
    if raw_repository_id is not None and str(raw_repository_id) != str(task.repository_id):
        raise ValidationError(
            "repository_id in the tool input must match this task's repository"
        )
    # Default to the task's own repository if the caller omitted it —
    # convenient, and still always validated against ownership inside the tool.
    tool_input = {**payload.input, "repository_id": str(task.repository_id)}

    input_summary = _small_input_summary(tool_input)

    try:
        output = run_tool(db, user=current_user, tool_name=tool_name, raw_input=tool_input)
    except ToolError as exc:
        record_tool_invocation(
            db, task_id=task_id, tool_name=tool_name, success=False,
            input_summary=input_summary, error=str(exc),
        )
        raise

    record_tool_invocation(
        db, task_id=task_id, tool_name=tool_name, success=True,
        input_summary=input_summary, result_summary=_small_input_summary(output.model_dump(mode="json")),
    )

    return ToolInvokeResponse(tool_name=tool_name, output=output.model_dump(mode="json"))
