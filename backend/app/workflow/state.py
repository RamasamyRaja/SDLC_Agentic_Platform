"""
The lifecycle state machine.

Every gate in the product is enforced from here, on the server:

* `transition()` takes a row lock on the task and performs a compare-and-set
  from an expected stage. Two concurrent "start implementation" requests (or a
  retry after a timeout) therefore cannot both win - the loser gets a 409 and
  nothing is duplicated.
* The transition table is the only definition of what may follow what. In
  particular nothing leads to IMPLEMENTING except PLAN_APPROVED (first run),
  or a later MR/validation rejection of an *already approved* plan, so the
  Development Agent can never start before the Architect approved a plan.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, WorkflowStateError
from app.models.task import Task
from app.models.user import User
from app.models.workflow import WorkflowEvent, WorkflowStage as S

TRANSITIONS: dict[S, frozenset[S]] = {
    S.CREATED: frozenset({S.PLANNING}),
    S.PLANNING: frozenset({S.PLAN_PENDING_APPROVAL, S.PLAN_FAILED}),
    S.PLAN_FAILED: frozenset({S.PLANNING}),
    S.PLAN_PENDING_APPROVAL: frozenset({S.PLAN_APPROVED, S.PLAN_REJECTED, S.PLAN_REVISION_REQUIRED}),
    S.PLAN_REJECTED: frozenset({S.PLANNING}),
    S.PLAN_REVISION_REQUIRED: frozenset({S.PLANNING}),
    S.PLAN_APPROVED: frozenset({S.IMPLEMENTING}),
    S.IMPLEMENTING: frozenset({S.VALIDATING, S.IMPLEMENTATION_FAILED}),
    S.IMPLEMENTATION_FAILED: frozenset({S.IMPLEMENTING}),
    S.VALIDATING: frozenset({S.READY_FOR_MR, S.VALIDATION_FAILED}),
    S.VALIDATION_FAILED: frozenset({S.VALIDATING, S.IMPLEMENTING, S.MR_CREATING}),
    S.READY_FOR_MR: frozenset({S.VALIDATING, S.IMPLEMENTING, S.MR_CREATING}),
    S.MR_CREATING: frozenset({S.MR_PENDING_REVIEW, S.MR_CREATION_FAILED}),
    S.MR_CREATION_FAILED: frozenset({S.MR_CREATING, S.IMPLEMENTING}),
    S.MR_PENDING_REVIEW: frozenset({S.MR_APPROVED, S.MR_REJECTED, S.MR_REVISION_REQUIRED}),
    S.MR_APPROVED: frozenset({S.DEPLOYING}),
    S.MR_REJECTED: frozenset({S.IMPLEMENTING}),
    S.MR_REVISION_REQUIRED: frozenset({S.IMPLEMENTING}),
    S.DEPLOYING: frozenset({S.DEPLOYED, S.DEPLOYMENT_FAILED, S.DEPLOYMENT_UNAVAILABLE}),
    S.DEPLOYMENT_FAILED: frozenset({S.DEPLOYING}),
    S.DEPLOYMENT_UNAVAILABLE: frozenset({S.DEPLOYING}),
    S.DEPLOYED: frozenset(),
}

# Stages that mean "an agent is working right now", and where a crashed worker should land.
ACTIVE_STAGES: dict[S, S] = {
    S.PLANNING: S.PLAN_FAILED,
    S.IMPLEMENTING: S.IMPLEMENTATION_FAILED,
    S.VALIDATING: S.VALIDATION_FAILED,
    S.MR_CREATING: S.MR_CREATION_FAILED,
    S.DEPLOYING: S.DEPLOYMENT_FAILED,
}

# Stages from which the Development Agent may legitimately be started. Every one of them is
# downstream of a plan that an Architect approved.
IMPLEMENTATION_START_STAGES = frozenset({
    S.PLAN_APPROVED, S.IMPLEMENTATION_FAILED, S.VALIDATION_FAILED, S.READY_FOR_MR,
    S.MR_CREATION_FAILED, S.MR_REJECTED, S.MR_REVISION_REQUIRED,
})

PLAN_START_STAGES = frozenset({S.CREATED, S.PLAN_FAILED, S.PLAN_REJECTED, S.PLAN_REVISION_REQUIRED})

# Stages after (and including) plan approval: the plan row is frozen.
POST_APPROVAL_STAGES = frozenset(set(S) - {
    S.CREATED, S.PLANNING, S.PLAN_FAILED, S.PLAN_PENDING_APPROVAL, S.PLAN_REJECTED, S.PLAN_REVISION_REQUIRED,
})


def _stage(value: str | S) -> S:
    return value if isinstance(value, S) else S(value)


def actor_label(actor: User | str | None) -> str | None:
    if actor is None:
        return None
    return actor if isinstance(actor, str) else actor.email


def record_event(
    db: Session,
    *,
    task_id: uuid.UUID,
    event_type: str,
    actor: User | str | None = None,
    message: str | None = None,
    detail: dict | None = None,
    from_stage: str | None = None,
    to_stage: str | None = None,
    commit: bool = True,
) -> WorkflowEvent:
    event = WorkflowEvent(
        task_id=task_id,
        event_type=event_type,
        from_stage=from_stage,
        to_stage=to_stage,
        actor_id=actor.id if isinstance(actor, User) else None,
        actor_label=actor_label(actor),
        message=message,
        detail=detail,
    )
    db.add(event)
    if commit:
        db.commit()
    return event


def lock_task(db: Session, task_id: uuid.UUID) -> Task:
    """SELECT ... FOR UPDATE: serialises every lifecycle change for one task."""
    task = db.query(Task).filter(Task.id == task_id).with_for_update().populate_existing().one_or_none()
    if task is None:
        raise NotFoundError(f"Task {task_id} not found")
    return task


def transition(
    db: Session,
    task_id: uuid.UUID,
    *,
    expect: frozenset[S] | set[S] | S,
    to: S,
    actor: User | str | None,
    event_type: str,
    message: str | None = None,
    detail: dict | None = None,
) -> Task:
    """Atomically move a task `expect` -> `to`, or raise WorkflowStateError (409)."""
    expected = {expect} if isinstance(expect, S) else set(expect)
    task = lock_task(db, task_id)
    current = _stage(task.workflow_stage)
    if current not in expected:
        db.rollback()
        raise WorkflowStateError(
            f"Action not allowed while the task is in stage {current.value}; "
            f"expected one of: {', '.join(sorted(s.value for s in expected))}"
        )
    if to not in TRANSITIONS[current]:
        db.rollback()
        raise WorkflowStateError(f"Illegal lifecycle transition {current.value} -> {to.value}")
    task.workflow_stage = to.value
    db.add(task)
    record_event(
        db, task_id=task.id, event_type=event_type, actor=actor, message=message,
        detail=detail, from_stage=current.value, to_stage=to.value, commit=False,
    )
    db.commit()
    db.refresh(task)
    return task


def recover_stale(db: Session, task_id: uuid.UUID, *, max_age_seconds: int) -> Task:
    """
    If a task sits in an "agent is working" stage for longer than `max_age_seconds`
    the worker died (process restart, crash). Mark that attempt failed so the user
    can retry, instead of leaving the task stuck forever.
    """
    task = lock_task(db, task_id)
    current = _stage(task.workflow_stage)
    failed = ACTIVE_STAGES.get(current)
    updated = task.updated_at if task.updated_at.tzinfo else task.updated_at.replace(tzinfo=timezone.utc)
    if failed is not None and datetime.now(timezone.utc) - updated > timedelta(seconds=max_age_seconds):
        task.workflow_stage = failed.value
        record_event(
            db, task_id=task.id, event_type="stale_run_recovered", actor="system",
            message=f"No progress for {max_age_seconds}s in {current.value}; the worker was lost. Marked as failed so it can be retried.",
            from_stage=current.value, to_stage=failed.value, commit=False,
        )
        db.commit()
        db.refresh(task)
    else:
        db.rollback()
    return task
