"""
Task endpoints.

Creating a task records the requirement and, when the repository is onboarded
and indexed, immediately starts the Architecture Agent in the background. The
task then waits at the Architect's plan-approval gate - nothing touches source
code before that (see app.workflow.state / app.api.workflow).

Reads are team-wide so that every role in the lifecycle (Architect, Viewer, ...)
can see the tasks it has to review; writes are permission-gated per action.
"""
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.orm import Session

from app.core.exceptions import WorkflowStateError
from app.db.session import get_db
from app.models.repository import Repository
from app.models.task import Task, TaskStatus
from app.models.user import User
from app.rbac import Permission, require_permission
from app.schemas.task import TaskCreate, TaskCreateResponse, TaskStatusResponse, TaskStatusUpdate
from app.services import task_service
from app.workflow import lifecycle, views

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.post("", response_model=TaskCreateResponse, status_code=201)
def create_task(
    payload: TaskCreate,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.TASK_CREATE)),
) -> TaskCreateResponse:
    task = task_service.create_task(db, user=current_user, payload=payload)
    started, blocker = False, None
    try:
        plan = lifecycle.start_planning(db, user=current_user, task_id=task.id)
        background.add_task(lifecycle.execute_planning, plan.id)
        started = True
    except WorkflowStateError as exc:   # e.g. repository not yet indexed: the task is still created
        blocker = str(exc)
        lifecycle.record_event(db, task_id=task.id, event_type="planning_blocked", actor="system", message=blocker)
    db.refresh(task)
    return TaskCreateResponse(task_id=task.id, repository_id=task.repository_id, status=task.status,
                              workflow_stage=task.workflow_stage, planning_started=started, planning_blocker=blocker)


@router.get("")
def list_tasks(
    repository_id: uuid.UUID | None = Query(default=None),
    status: TaskStatus | None = Query(default=None),
    workflow_stage: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.TASK_READ)),
) -> list[dict]:
    q = db.query(Task)
    if repository_id is not None:
        q = q.filter(Task.repository_id == repository_id)
    if status is not None:
        q = q.filter(Task.status == status)
    if workflow_stage is not None:
        q = q.filter(Task.workflow_stage == workflow_stage)
    tasks = q.order_by(Task.created_at.desc()).all()
    repo_names = {r.id: r.name for r in db.query(Repository).filter(Repository.id.in_({t.repository_id for t in tasks})).all()} if tasks else {}
    users = {u.id: u for u in db.query(User).filter(User.id.in_({t.user_id for t in tasks})).all()} if tasks else {}
    return [{**views.summary_row(db, t, repo_names, users), "user_id": str(t.user_id)} for t in tasks]


@router.get("/summary")
def tasks_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.TASK_READ)),
) -> dict:
    """Workflow health computed from persisted state only (nothing hardcoded). Declared before /{task_id}."""
    tasks = db.query(Task).order_by(Task.updated_at.desc()).all()
    repo_names = {r.id: r.name for r in db.query(Repository).filter(Repository.id.in_({t.repository_id for t in tasks})).all()} if tasks else {}
    for t in tasks:
        lifecycle.recover_if_stale(db, t)
    rows = [views.summary_row(db, t, repo_names, {}) for t in tasks]
    validation = {"PASSED": 0, "PARTIAL": 0, "FAILED": 0, "NOT_RUN": 0}
    deployment = {"DEPLOYED": 0, "DEPLOYMENT_FAILED": 0, "DEPLOYMENT_UNAVAILABLE": 0, "NOT_DEPLOYED": 0}
    levels = {"human_action": 0, "error": 0, "blocked": 0, "running": 0}
    needs = []
    for r in rows:
        validation[r["validation_verdict"]] = validation.get(r["validation_verdict"], 0) + 1
        deployment[r["workflow_stage"] if r["workflow_stage"] in deployment else "NOT_DEPLOYED"] += 1
        lvl = r["attention"]["level"]
        if lvl:
            levels[lvl] = levels.get(lvl, 0) + 1
        if lvl in ("human_action", "error", "blocked"):
            needs.append({"id": r["id"], "title": r["title"], "repository_name": r["repository_name"], "workflow_stage": r["workflow_stage"],
                          "level": lvl, "reason": r["attention"]["reason"], "updated_at": r["updated_at"]})
    return {"total": len(rows), "validation": validation, "deployment": deployment, "attention": levels,
            "completed": deployment["DEPLOYED"], "needs_attention": needs[:20]}


@router.get("/{task_id}")
def get_task(
    task_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.TASK_READ)),
) -> dict:
    task = lifecycle.get_task_any(db, task_id)
    return {**views.task_detail(db, task, current_user), "user_id": str(task.user_id)}


@router.patch("/{task_id}/status", response_model=TaskStatusResponse)
def update_task_status(
    task_id: uuid.UUID,
    payload: TaskStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.TASK_WRITE)),
) -> TaskStatusResponse:
    """Legacy coarse status. It cannot move the lifecycle: every gate reads `workflow_stage`, which this never changes."""
    task = task_service.update_task_status(
        db, user=current_user, task_id=task_id, new_status=payload.status
    )
    return TaskStatusResponse.model_validate(task)
