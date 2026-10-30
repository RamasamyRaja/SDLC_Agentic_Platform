"""
Task artifact service.

Handles create/retrieve/list for TaskArtifact records. Does not perform any
code analysis — a file path is accepted as-is (validated for shape only, in
the Pydantic schema layer). Connecting artifacts to real indexed repository
documents is Milestone 4+ work.
"""
import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.task_artifact import TaskArtifact
from app.models.user import User
from app.schemas.task_artifact import TaskArtifactCreate
from app.services.task_service import get_task


def create_task_artifact(
    db: Session, *, user: User, task_id: uuid.UUID, payload: TaskArtifactCreate
) -> TaskArtifact:
    # Ensures the task exists AND belongs to this user before an artifact
    # can be attached to it.
    task = get_task(db, user=user, task_id=task_id)

    artifact = TaskArtifact(
        task_id=task.id,
        file_path=payload.file_path,
        artifact_type=payload.artifact_type,
        notes=payload.notes,
    )
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    return artifact


def list_task_artifacts(db: Session, *, user: User, task_id: uuid.UUID) -> list[TaskArtifact]:
    task = get_task(db, user=user, task_id=task_id)
    return (
        db.query(TaskArtifact)
        .filter(TaskArtifact.task_id == task.id)
        .order_by(TaskArtifact.created_at.desc())
        .all()
    )


def get_task_artifact(
    db: Session, *, user: User, task_id: uuid.UUID, artifact_id: uuid.UUID
) -> TaskArtifact:
    task = get_task(db, user=user, task_id=task_id)
    artifact = db.get(TaskArtifact, artifact_id)
    if artifact is None or artifact.task_id != task.id:
        raise NotFoundError(f"Artifact {artifact_id} not found for task {task_id}")
    return artifact
