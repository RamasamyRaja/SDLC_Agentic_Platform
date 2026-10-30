"""
Shared helper used by every tool: resolves a repository the current user
owns AND has actually been onboarded (workspace exists on disk) — reusing
the exact same ownership check (`repository_service.get_repository`) every
other endpoint in this project uses, so tool calls can never bypass
repository ownership.
"""
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.models.user import User
from app.services.repository_service import get_repository


def get_onboarded_workspace(db: Session, *, user: User, repository_id: uuid.UUID) -> Path:
    """
    Returns the workspace path for a repository the user owns. Raises
    ValidationError (-> 400) if the repository has never been onboarded —
    same error used by onboarding_service/retrieval_service for the
    equivalent "not ready yet" case, so tool failures stay consistent with
    the rest of the API. Raises NotFoundError/OwnershipError (via
    get_repository) exactly as every other service does.
    """
    repository = get_repository(db, user=user, repository_id=repository_id)

    if repository.workspace_path is None:
        raise ValidationError(
            f"Repository {repository_id} has not been onboarded yet — POST /onboard first"
        )

    workspace_path = Path(repository.workspace_path)
    if not workspace_path.exists():
        raise ValidationError(
            f"Repository {repository_id}'s workspace no longer exists on disk — re-run /onboard"
        )

    return workspace_path


def record_tool_invocation(
    db: Session,
    *,
    task_id: uuid.UUID,
    tool_name: str,
    success: bool,
    input_summary: dict | None = None,
    result_summary: dict | None = None,
    error: str | None = None,
) -> "ToolInvocation":
    """
    Persists one ToolInvocation row. Used by BOTH the explicit
    POST /api/tasks/{task_id}/tools/{tool_name} endpoint and the automated
    TOOL_EXECUTION graph node — one recording path, not two. `input_summary`
    /`result_summary` must already be small, non-sensitive metadata (see
    ToolInvocation's docstring) — this function does not itself redact
    anything, so callers are responsible for never passing full file
    content here.
    """
    from app.models.tool_invocation import ToolInvocation, ToolInvocationStatus

    row = ToolInvocation(
        task_id=task_id,
        tool_name=tool_name,
        status=ToolInvocationStatus.SUCCESS if success else ToolInvocationStatus.FAILED,
        input_summary=input_summary,
        result_summary=result_summary,
        error=error[:2000] if error else None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
