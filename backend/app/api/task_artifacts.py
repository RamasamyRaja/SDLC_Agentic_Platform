"""
Task artifact endpoints.

Nested under /api/tasks/{task_id}/artifacts since an artifact only makes
sense in the context of a task.
"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.rbac import Permission, require_permission
from app.db.session import get_db
from app.models.user import User
from app.schemas.task_artifact import TaskArtifactCreate, TaskArtifactResponse
from app.services import task_artifact_service

router = APIRouter(prefix="/api/tasks/{task_id}/artifacts", tags=["task-artifacts"])


@router.post("", response_model=TaskArtifactResponse, status_code=201)
def create_task_artifact(
    task_id: uuid.UUID,
    payload: TaskArtifactCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.TASK_WRITE)),
) -> TaskArtifactResponse:
    artifact = task_artifact_service.create_task_artifact(
        db, user=current_user, task_id=task_id, payload=payload
    )
    return TaskArtifactResponse.model_validate(artifact)


@router.get("", response_model=list[TaskArtifactResponse])
def list_task_artifacts(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.TASK_READ)),
) -> list[TaskArtifactResponse]:
    artifacts = task_artifact_service.list_task_artifacts(db, user=current_user, task_id=task_id)
    return [TaskArtifactResponse.model_validate(a) for a in artifacts]
