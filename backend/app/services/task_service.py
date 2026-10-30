"""
Task service.

Handles create/retrieve/list/status-update for Task records. Creating a
task here only persists it — it never starts LangGraph or any agent
execution (that begins in Milestone 6).
"""
import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import InvalidStatusTransitionError, NotFoundError, OwnershipError
from app.models.task import ALLOWED_TASK_STATUS_TRANSITIONS, Task, TaskStatus
from app.models.user import User
from app.schemas.task import TaskCreate
from app.services.repository_service import get_repository


def create_task(db: Session, *, user: User, payload: TaskCreate) -> Task:
    # Repositories are a shared team resource for the task lifecycle (an Architect must be able to
    # review what a Developer submitted), so any task author may target any existing repository.
    from app.models.repository import Repository
    repository = db.get(Repository, payload.repository_id)
    if repository is None:
        raise NotFoundError(f"Repository {payload.repository_id} not found")

    task = Task(
        user_id=user.id,
        repository_id=repository.id,
        title=payload.title,
        description=payload.request,
        branch=payload.branch or repository.default_branch,
        expected_outcome=payload.expected_outcome,
        context=payload.context,
        status=TaskStatus.PENDING,
        workflow_stage="CREATED",
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def get_task(db: Session, *, user: User, task_id: uuid.UUID) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise NotFoundError(f"Task {task_id} not found")
    if task.user_id != user.id:
        raise OwnershipError(f"User does not have access to task {task_id}")
    return task


def list_tasks(
    db: Session,
    *,
    user: User,
    repository_id: uuid.UUID | None = None,
    status: TaskStatus | None = None,
) -> list[Task]:
    query = db.query(Task).filter(Task.user_id == user.id)
    if repository_id is not None:
        query = query.filter(Task.repository_id == repository_id)
    if status is not None:
        query = query.filter(Task.status == status)
    return query.order_by(Task.created_at.desc()).all()


def update_task_status(db: Session, *, user: User, task_id: uuid.UUID, new_status: TaskStatus) -> Task:
    task = get_task(db, user=user, task_id=task_id)

    allowed_next_statuses = ALLOWED_TASK_STATUS_TRANSITIONS.get(task.status, set())
    if new_status not in allowed_next_statuses:
        raise InvalidStatusTransitionError(
            f"Cannot transition task {task_id} from {task.status.value} to {new_status.value}"
        )

    task.status = new_status
    db.add(task)
    db.commit()
    db.refresh(task)
    return task
