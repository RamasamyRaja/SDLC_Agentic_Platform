"""
Task lifecycle endpoints. Every route checks its permission on the server and
then lets app.workflow.lifecycle enforce the stage gate; the Angular UI only
renders the `allowed_actions` the backend computed for the current user.
"""
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models.user import User
from app.models.workflow import Decision, DevelopmentRun, WorkflowEvent
from app.rbac import Permission, has_permission, require_permission
from app.workflow import lifecycle as lc
from app.workflow import views

router = APIRouter(prefix="/api/tasks/{task_id}", tags=["workflow"])
read = Depends(require_permission(Permission.TASK_READ))


class FeedbackBody(BaseModel):
    feedback: str | None = Field(default=None, max_length=5000)


class DecisionBody(BaseModel):
    decision: Decision
    comment: str | None = Field(default=None, max_length=5000)
    plan_id: uuid.UUID | None = None   # optimistic check: the version the reviewer actually read
    mr_id: uuid.UUID | None = None


class MrBody(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=10_000)
    acknowledge_validation_risk: bool = False


# ---- planning ----------------------------------------------------------
@router.post("/plan", status_code=202)
def start_plan(task_id: uuid.UUID, background: BackgroundTasks, body: FeedbackBody = FeedbackBody(), db: Session = Depends(get_db),
               user: User = Depends(require_permission(Permission.AGENT_RUN))) -> dict:
    plan = lc.start_planning(db, user=user, task_id=task_id, feedback=body.feedback)
    background.add_task(lc.execute_planning, plan.id)
    return {"plan_id": str(plan.id), "version": plan.version, "workflow_stage": lc.get_task_any(db, task_id).workflow_stage}


@router.get("/plan")
def get_plan(task_id: uuid.UUID, db: Session = Depends(get_db), user: User = read) -> dict:
    lc.get_task_any(db, task_id)
    plan = lc.latest_plan(db, task_id)
    if plan is None:
        raise NotFoundError("No plan has been generated for this task yet")
    return views.plan_dict(plan)


@router.get("/plans")
def list_plans(task_id: uuid.UUID, db: Session = Depends(get_db), user: User = read) -> list[dict]:
    from app.models.workflow import TaskPlan
    lc.get_task_any(db, task_id)
    return [views.plan_dict(p) for p in db.query(TaskPlan).filter(TaskPlan.task_id == task_id).order_by(TaskPlan.version.desc()).all()]


@router.post("/plan/decision")
def decide_plan(task_id: uuid.UUID, body: DecisionBody, db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.TASK_READ))) -> dict:
    plan = lc.decide_plan(db, user=user, task_id=task_id, decision=body.decision, comment=body.comment, plan_id=body.plan_id)
    return views.plan_dict(plan)


# ---- implementation + validation ---------------------------------------
@router.post("/implementation", status_code=202)
def start_implementation(task_id: uuid.UUID, background: BackgroundTasks, body: FeedbackBody = FeedbackBody(), db: Session = Depends(get_db),
                         user: User = Depends(require_permission(Permission.AGENT_RUN))) -> dict:
    run = lc.start_implementation(db, user=user, task_id=task_id, feedback=body.feedback)
    background.add_task(lc.execute_development, run.id)
    return {"run_id": str(run.id), "attempt": run.attempt, "workflow_stage": lc.get_task_any(db, task_id).workflow_stage}


@router.get("/development-runs")
def list_runs(task_id: uuid.UUID, db: Session = Depends(get_db), user: User = read) -> list[dict]:
    lc.get_task_any(db, task_id)
    rows = db.query(DevelopmentRun).filter(DevelopmentRun.task_id == task_id).order_by(DevelopmentRun.attempt.desc()).all()
    return [views.run_dict(r, include_diff=False) for r in rows]


@router.get("/development-runs/{run_id}")
def get_run(task_id: uuid.UUID, run_id: uuid.UUID, db: Session = Depends(get_db), user: User = read) -> dict:
    run = db.get(DevelopmentRun, run_id)
    if run is None or run.task_id != task_id:
        raise NotFoundError("Development run not found")
    return views.run_dict(run)


@router.post("/validation", status_code=202)
def run_validation(task_id: uuid.UUID, background: BackgroundTasks, db: Session = Depends(get_db),
                   user: User = Depends(require_permission(Permission.SANDBOX_EXECUTE))) -> dict:
    run = lc.start_validation(db, user=user, task_id=task_id)
    background.add_task(lc.execute_validation, run.id)
    return {"run_id": str(run.id), "workflow_stage": lc.get_task_any(db, task_id).workflow_stage}


# ---- merge request -------------------------------------------------------
@router.post("/merge-request", status_code=201)
def create_mr(task_id: uuid.UUID, body: MrBody = MrBody(), db: Session = Depends(get_db),
              user: User = Depends(require_permission(Permission.MR_CREATE))) -> dict:
    mr = lc.create_merge_request(db, user=user, task_id=task_id, title=body.title, description=body.description,
                                 acknowledge_validation_risk=body.acknowledge_validation_risk)
    return views.mr_dict(mr, db.get(DevelopmentRun, mr.run_id))


@router.get("/merge-request")
def get_mr(task_id: uuid.UUID, db: Session = Depends(get_db), user: User = read) -> dict:
    lc.get_task_any(db, task_id)
    mr = lc.latest_mr(db, task_id)
    if mr is None:
        raise NotFoundError("No merge request exists for this task")
    return views.mr_dict(mr, db.get(DevelopmentRun, mr.run_id))


@router.post("/merge-request/decision")
def decide_mr(task_id: uuid.UUID, body: DecisionBody, db: Session = Depends(get_db), user: User = Depends(require_permission(Permission.TASK_READ))) -> dict:
    mr = lc.decide_mr(db, user=user, task_id=task_id, decision=body.decision, comment=body.comment, mr_id=body.mr_id)
    return views.mr_dict(mr, None)


# ---- deployment ----------------------------------------------------------
@router.post("/deployment", status_code=202)
def deploy(task_id: uuid.UUID, background: BackgroundTasks, db: Session = Depends(get_db),
           user: User = Depends(require_permission(Permission.DEPLOY_EXECUTE))) -> dict:
    dep = lc.start_deployment(db, user=user, task_id=task_id)
    background.add_task(lc.execute_deployment, dep.id)
    return {"deployment_id": str(dep.id), "attempt": dep.attempt, "workflow_stage": lc.get_task_any(db, task_id).workflow_stage}


@router.get("/deployment")
def get_deployment(task_id: uuid.UUID, db: Session = Depends(get_db), user: User = read) -> dict:
    lc.get_task_any(db, task_id)
    dep = lc.latest_deployment(db, task_id)
    if dep is None:
        mr = lc.latest_mr(db, task_id)
        approved = bool(mr and mr.review_status == "MR_APPROVED")
        return {"status": "READY_FOR_DEPLOYMENT" if approved else "BLOCKED_PENDING_APPROVAL", "steps": [], "attempt": 0,
                "error": None if approved else "Deployment requires an Architect-approved merge request."}
    return views.deployment_dict(dep)


# ---- history + report -----------------------------------------------------
@router.get("/events")
def events(task_id: uuid.UUID, db: Session = Depends(get_db), user: User = read) -> list[dict]:
    lc.get_task_any(db, task_id)
    return [views.event_dict(e) for e in db.query(WorkflowEvent).filter(WorkflowEvent.task_id == task_id).order_by(WorkflowEvent.created_at).all()]


@router.get("/report")
def report(task_id: uuid.UUID, db: Session = Depends(get_db), user: User = read) -> dict:
    return views.build_report(db, lc.get_task_any(db, task_id))
