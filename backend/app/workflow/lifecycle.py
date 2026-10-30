"""
Lifecycle services: every state-changing action of the task workflow.

API handlers call the `start_*` / `decide_*` / `create_*` functions (fast,
synchronous, gate-enforcing). Long agent work then runs through the
`execute_*` functions, which own their DB session and are scheduled as
background tasks. Both halves use app.workflow.state.transition(), so a gate
is checked and recorded in exactly one place.

The planning and development agents are LangGraph graphs (same checkpointer
and node discipline as app.agent) whose nodes hand off through persisted rows:
TaskPlan -> DevelopmentRun -> ValidationCheck -> MergeRequest -> Deployment.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.agent.checkpointer import get_checkpointer
from app.core.config import get_settings
from app.core.redaction import redact
from app.core.exceptions import NotFoundError, PermissionDeniedError, ValidationError, WorkflowStateError
from app.db.session import SessionLocal
from app.llm import service as reasoning_service
from app.llm.provider import LLMProvider
from app.models.agent_execution import AgentExecution, AgentExecutionStatus
from app.models.repository import IndexingStatus, Repository, RepositoryStatus
from app.models.task import Task
from app.models.user import User
from app.models.workflow import (
    Decision, DecisionSubject, Deployment, DeploymentStatus, DevelopmentRun, DevRunStatus, MergeRequest,
    MrReviewStatus, MrStatus, PlanStatus, RemoteStatus, ReviewDecision, TaskPlan, ValidationVerdict, WorkflowStage as S,
)
from app.rbac import Permission, has_permission
from app.workflow import deployment as deploy_mod
from app.workflow import development, gitops, planning
from app.workflow.state import (
    IMPLEMENTATION_START_STAGES, PLAN_START_STAGES, lock_task, record_event, recover_stale, transition,
)

logger = logging.getLogger(__name__)

# Tests (and embedders) can install a factory returning an LLMProvider; production resolves Mistral from configuration.
PROVIDER_FACTORY = None


def _resolve_provider(provider: LLMProvider | None) -> LLMProvider:
    if provider is not None:
        return provider
    if PROVIDER_FACTORY is not None:
        return PROVIDER_FACTORY()
    from app.core.exceptions import LLMUnavailableError
    try:
        return reasoning_service.get_mistral_provider()
    except Exception as exc:  # noqa: BLE001 - e.g. MISTRAL_API_KEY not configured
        raise LLMUnavailableError(f"LLM provider unavailable: {exc}") from exc


AGENT_ARCH = "agent:architecture"
AGENT_DEV = "agent:development"
AGENT_QA = "agent:qa"
AGENT_DEVOPS = "agent:devops"


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def get_task_any(db: Session, task_id: uuid.UUID) -> Task:
    """Lifecycle reads are team-wide (an Architect must see a Developer's task)."""
    task = db.get(Task, task_id)
    if task is None:
        raise NotFoundError(f"Task {task_id} not found")
    return task


def _owner(db: Session, task: Task) -> User:
    owner = db.get(User, task.user_id)
    if owner is None:
        raise NotFoundError("The task's creator no longer exists")
    return owner


def _require(user: User, permission: Permission) -> None:
    if not has_permission(user, permission):
        raise PermissionDeniedError(f"Permission required: {permission.value}")


def latest_plan(db: Session, task_id: uuid.UUID) -> TaskPlan | None:
    return db.query(TaskPlan).filter(TaskPlan.task_id == task_id).order_by(TaskPlan.version.desc()).first()


def approved_plan(db: Session, task_id: uuid.UUID) -> TaskPlan | None:
    return (db.query(TaskPlan).filter(TaskPlan.task_id == task_id, TaskPlan.status == PlanStatus.APPROVED.value)
            .order_by(TaskPlan.version.desc()).first())


def latest_run(db: Session, task_id: uuid.UUID) -> DevelopmentRun | None:
    return db.query(DevelopmentRun).filter(DevelopmentRun.task_id == task_id).order_by(DevelopmentRun.attempt.desc()).first()


def latest_mr(db: Session, task_id: uuid.UUID) -> MergeRequest | None:
    return db.query(MergeRequest).filter(MergeRequest.task_id == task_id).order_by(MergeRequest.created_at.desc()).first()


def latest_deployment(db: Session, task_id: uuid.UUID) -> Deployment | None:
    return db.query(Deployment).filter(Deployment.task_id == task_id).order_by(Deployment.attempt.desc()).first()


def last_decision(db: Session, task_id: uuid.UUID, subject: DecisionSubject) -> ReviewDecision | None:
    return (db.query(ReviewDecision).filter(ReviewDecision.task_id == task_id, ReviewDecision.subject_type == subject.value)
            .order_by(ReviewDecision.created_at.desc()).first())


def stale_seconds(stage: S) -> int:
    st = get_settings()
    return {S.PLANNING: st.PLAN_STALE_AFTER_SECONDS, S.IMPLEMENTING: st.DEV_STALE_AFTER_SECONDS, S.VALIDATING: st.VALIDATE_STALE_AFTER_SECONDS,
            S.MR_CREATING: st.MR_STALE_AFTER_SECONDS, S.DEPLOYING: st.DEPLOY_STALE_AFTER_SECONDS}.get(stage, 3600)


def recover_if_stale(db: Session, task: Task) -> Task:
    """A restart kills in-process background work. A task left in an 'agent is working' stage with no progress is failed
    so the existing retry actions become available (previously only planning/implementation were ever recovered)."""
    from app.workflow.state import ACTIVE_STAGES
    stage = S(task.workflow_stage)
    if stage in ACTIVE_STAGES:
        recover_stale(db, task.id, max_age_seconds=stale_seconds(stage))
        db.refresh(task)
    return task


def recover_all_stale(db: Session) -> int:
    from app.workflow.state import ACTIVE_STAGES
    n = 0
    for t in db.query(Task).filter(Task.workflow_stage.in_([s.value for s in ACTIVE_STAGES])).all():
        before = t.workflow_stage
        recover_if_stale(db, t)
        n += before != t.workflow_stage
    return n


# --------------------------------------------------------------------------
# Stage 3: Architecture planning
# --------------------------------------------------------------------------

def planning_blockers(repo: Repository) -> str | None:
    if repo.status != RepositoryStatus.READY:
        return f"The repository is {repo.status.value}; onboard it before planning."
    if repo.indexing_status != IndexingStatus.INDEXED:
        return f"The repository is {repo.indexing_status.value}; index it before planning so the Architecture Agent can read real code."
    return None


def start_planning(db: Session, *, user: User, task_id: uuid.UUID, feedback: str | None = None) -> TaskPlan:
    _require(user, Permission.AGENT_RUN)
    settings = get_settings()
    task = get_task_any(db, task_id)
    recover_stale(db, task_id, max_age_seconds=settings.PLAN_STALE_AFTER_SECONDS)
    db.refresh(task)
    repo = db.get(Repository, task.repository_id)
    blocker = planning_blockers(repo)
    if blocker:
        raise WorkflowStateError(blocker)
    prior_stage = S(task.workflow_stage)
    if feedback is None and prior_stage in (S.PLAN_REJECTED, S.PLAN_REVISION_REQUIRED):
        d = last_decision(db, task_id, DecisionSubject.PLAN)
        feedback = d.comment if d else None
    transition(db, task_id, expect=PLAN_START_STAGES, to=S.PLANNING, actor=user, event_type="planning_started",
               message="Architecture Agent started" + (" (revising after feedback)" if feedback else ""))
    version = (db.query(func.max(TaskPlan.version)).filter(TaskPlan.task_id == task_id).scalar() or 0) + 1
    plan = TaskPlan(task_id=task_id, version=version, status=PlanStatus.GENERATING.value, feedback=feedback,
                    repository_commit_sha=repo.commit_sha, created_by=user.id)
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


class _PlanState(TypedDict, total=False):
    plan_id: str
    status: str
    error: str | None
    error_type: str | None


def _route(state) -> str:
    return "failed" if state.get("status") == "FAILED" else "continue"


def _build_planning_graph():
    def load(state: _PlanState, config) -> dict:
        db: Session = config["configurable"]["db"]
        plan = db.get(TaskPlan, uuid.UUID(state["plan_id"]))
        if plan is None or plan.status != PlanStatus.GENERATING.value:
            return {"status": "FAILED", "error": "Plan row missing or not in GENERATING state", "error_type": "WorkflowStateError"}
        return {"status": "RUNNING"}

    def draft(state: _PlanState, config) -> dict:
        c = config["configurable"]
        db: Session = c["db"]
        plan_row = db.get(TaskPlan, uuid.UUID(state["plan_id"]))
        task = db.get(Task, plan_row.task_id)
        repo = db.get(Repository, task.repository_id)
        owner = _owner(db, task)
        try:
            provider = _resolve_provider(c.get("provider"))
        except Exception as exc:  # noqa: BLE001
            return {"status": "FAILED", "error": f"{exc.__class__.__name__}: {exc}"[:3000], "error_type": exc.__class__.__name__}
        previous = (db.query(TaskPlan).filter(TaskPlan.task_id == task.id, TaskPlan.version < plan_row.version)
                    .order_by(TaskPlan.version.desc()).first())
        prev_summary = (previous.plan or {}).get("summary") if previous else None
        try:
            plan, evidence = planning.generate_plan(db, task=task, repo=repo, owner=owner, feedback=plan_row.feedback,
                                                    previous_summary=prev_summary, provider=provider)
        except Exception as exc:  # noqa: BLE001 - recorded, never swallowed
            db.rollback()
            return {"status": "FAILED", "error": f"{exc.__class__.__name__}: {exc}"[:3000], "error_type": exc.__class__.__name__}
        plan_row.plan = plan.model_dump(mode="json")
        plan_row.evidence = evidence
        plan_row.model_name = provider.model_name
        db.add(plan_row)
        db.commit()
        return {"status": "RUNNING"}

    g = StateGraph(_PlanState)
    g.add_node("LOAD_PLAN", load)
    g.add_node("DRAFT_AND_VERIFY", draft)
    g.add_edge(START, "LOAD_PLAN")
    g.add_conditional_edges("LOAD_PLAN", _route, {"continue": "DRAFT_AND_VERIFY", "failed": END})
    g.add_edge("DRAFT_AND_VERIFY", END)
    return g.compile(checkpointer=get_checkpointer())


_planning_graph = None


def execute_planning(plan_id: uuid.UUID, *, provider: LLMProvider | None = None, db: Session | None = None) -> None:
    """Background entry point (own session unless one is injected, e.g. by tests)."""
    global _planning_graph
    own = db is None
    db = db or SessionLocal()
    try:
        _planning_graph = _planning_graph or _build_planning_graph()
        plan_row = db.get(TaskPlan, plan_id)
        task_id = plan_row.task_id
        final = _planning_graph.invoke({"plan_id": str(plan_id), "status": "RUNNING"},
                                       config={"configurable": {"db": db, "provider": provider, "thread_id": str(uuid.uuid4())}})
        db.expire_all()
        plan_row = db.get(TaskPlan, plan_id)
        from datetime import datetime, timezone
        plan_row.finished_at = datetime.now(timezone.utc)
        if final.get("status") == "FAILED":
            plan_row.status = PlanStatus.FAILED.value
            plan_row.error = final.get("error")
            db.add(plan_row); db.commit()
            _log_execution(db, task_id, "ARCHITECTURE_PLAN", failed=True, error=plan_row.error, model=plan_row.model_name, result=None)
            transition(db, task_id, expect=S.PLANNING, to=S.PLAN_FAILED, actor=AGENT_ARCH, event_type="planning_failed", message=plan_row.error)
            return
        plan_row.status = PlanStatus.PENDING_APPROVAL.value
        db.add(plan_row); db.commit()
        _log_execution(db, task_id, "ARCHITECTURE_PLAN", failed=False, error=None, model=plan_row.model_name, result=plan_row.plan)
        transition(db, task_id, expect=S.PLANNING, to=S.PLAN_PENDING_APPROVAL, actor=AGENT_ARCH, event_type="plan_ready",
                   message="Development plan is ready for Architect approval",
                   detail={"plan_id": str(plan_id), "version": plan_row.version})
    except Exception as exc:  # noqa: BLE001
        logger.exception("Planning crashed for plan %s", plan_id)
        db.rollback()
        _fail_plan(db, plan_id, f"{exc.__class__.__name__}: {exc}")
    finally:
        if own:
            db.close()


def _fail_plan(db: Session, plan_id: uuid.UUID, error: str) -> None:
    plan = db.get(TaskPlan, plan_id)
    if plan and plan.status == PlanStatus.GENERATING.value:
        plan.status, plan.error = PlanStatus.FAILED.value, error[:3000]
        db.add(plan); db.commit()
        try:
            transition(db, plan.task_id, expect=S.PLANNING, to=S.PLAN_FAILED, actor=AGENT_ARCH, event_type="planning_failed", message=error[:500])
        except WorkflowStateError:
            pass


def _log_execution(db: Session, task_id, action: str, *, failed: bool, error: str | None, model: str | None,
                   result: dict | None, changed: list | None = None, validation: dict | None = None, diff: str | None = None) -> None:
    db.add(AgentExecution(
        task_id=task_id, status=AgentExecutionStatus.FAILED if failed else AgentExecutionStatus.COMPLETED, action=action,
        model_name=model, result=result, error=(error or None) and error[:2000], tool_call_count=0, tool_results=[],
        validation=validation, changed_files=changed or [], repair_attempts=0, final_diff=diff,
    ))
    db.commit()


# --------------------------------------------------------------------------
# Stage 4: plan approval gate
# --------------------------------------------------------------------------

def decide_plan(db: Session, *, user: User, task_id: uuid.UUID, decision: Decision, comment: str | None,
                plan_id: uuid.UUID | None = None) -> TaskPlan:
    _require(user, Permission.PLAN_APPROVE if decision == Decision.APPROVED else Permission.PLAN_REJECT)
    if decision != Decision.APPROVED and not (comment and comment.strip()):
        raise ValidationError("A comment explaining the rejection or the requested revision is required")
    get_task_any(db, task_id)
    plan = latest_plan(db, task_id)
    if plan is None or plan.status != PlanStatus.PENDING_APPROVAL.value:
        raise WorkflowStateError("There is no plan awaiting approval")
    if plan_id is not None and plan.id != plan_id:
        raise WorkflowStateError("That plan version is no longer the current one; reload and review the latest plan")
    target_stage, plan_status = {
        Decision.APPROVED: (S.PLAN_APPROVED, PlanStatus.APPROVED),
        Decision.REJECTED: (S.PLAN_REJECTED, PlanStatus.REJECTED),
        Decision.REVISION_REQUESTED: (S.PLAN_REVISION_REQUIRED, PlanStatus.REVISION_REQUIRED),
    }[decision]
    transition(db, task_id, expect=S.PLAN_PENDING_APPROVAL, to=target_stage, actor=user,
               event_type=f"plan_{decision.value.lower()}", message=comment, detail={"plan_id": str(plan.id), "version": plan.version})
    plan = db.get(TaskPlan, plan.id)
    plan.status = plan_status.value
    db.add(plan)
    db.add(ReviewDecision(task_id=task_id, subject_type=DecisionSubject.PLAN.value, subject_id=plan.id, decision=decision.value,
                          comment=comment, decided_by=user.id, decided_by_role=user.role.value))
    db.commit()
    db.refresh(plan)
    return plan


# --------------------------------------------------------------------------
# Stage 5/6: implementation + validation
# --------------------------------------------------------------------------

def start_implementation(db: Session, *, user: User, task_id: uuid.UUID, feedback: str | None = None) -> DevelopmentRun:
    _require(user, Permission.AGENT_RUN)
    settings = get_settings()
    task = get_task_any(db, task_id)
    recover_stale(db, task_id, max_age_seconds=settings.DEV_STALE_AFTER_SECONDS)
    db.refresh(task)
    plan = approved_plan(db, task_id)
    # Defence in depth: the stage table already forbids this, but the gate is also checked against the plan row itself.
    if plan is None:
        raise WorkflowStateError("Implementation cannot start: no Architect-approved plan exists for this task")
    prior = S(task.workflow_stage)
    if feedback is None and prior in (S.MR_REJECTED, S.MR_REVISION_REQUIRED):
        d = last_decision(db, task_id, DecisionSubject.MR)
        feedback = d.comment if d else None
    transition(db, task_id, expect=IMPLEMENTATION_START_STAGES, to=S.IMPLEMENTING, actor=user, event_type="implementation_started",
               message="Development Agent started" + (" (addressing feedback)" if feedback else ""), detail={"plan_id": str(plan.id)})
    attempt = (db.query(func.max(DevelopmentRun.attempt)).filter(DevelopmentRun.task_id == task_id).scalar() or 0) + 1
    run = DevelopmentRun(task_id=task_id, plan_id=plan.id, attempt=attempt, status=DevRunStatus.RUNNING.value, feedback=feedback, created_by=user.id)
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def execute_development(run_id: uuid.UUID, *, provider: LLMProvider | None = None, db: Session | None = None) -> None:
    from datetime import datetime, timezone
    own = db is None
    db = db or SessionLocal()
    settings = get_settings()
    run = db.get(DevelopmentRun, run_id)
    task_id = run.task_id

    def fail(error: str, *, stage_event: str = "implementation_failed") -> None:
        db.rollback()
        r = db.get(DevelopmentRun, run_id)
        r.status = DevRunStatus.FAILED.value if r.status == DevRunStatus.RUNNING.value else r.status
        r.error = redact(error)[:3000]
        r.finished_at = datetime.now(timezone.utc)
        r.summary = development.build_summary(r, []) if r.edits else None
        db.add(r); db.commit()
        _log_execution(db, task_id, "IMPLEMENTATION", failed=True, error=error, model=r.model_name, result=None,
                       changed=r.changed_files, diff=r.diff)
        try:
            transition(db, task_id, expect=S.IMPLEMENTING, to=S.IMPLEMENTATION_FAILED, actor=AGENT_DEV, event_type=stage_event, message=error[:500])
        except WorkflowStateError:
            pass

    try:
        task = db.get(Task, task_id)
        repo = db.get(Repository, task.repository_id)
        owner = _owner(db, task)
        plan_row = db.get(TaskPlan, run.plan_id)
        if plan_row.status != PlanStatus.APPROVED.value:
            return fail("The referenced plan is not approved; refusing to modify source code")
        provider = _resolve_provider(provider)
        run.model_name = provider.model_name
        prior = (db.query(DevelopmentRun).filter(DevelopmentRun.task_id == task_id, DevelopmentRun.attempt < run.attempt)
                 .order_by(DevelopmentRun.attempt.desc()).first())
        notes = development.implement(db, run=run, task=task, repo=repo, owner=owner, plan_row=plan_row, provider=provider,
                                      prior_diff=prior.diff if prior else None)
        development.finalize_diff(db, run)
        if run.status == DevRunStatus.NO_CHANGES.value:
            rejected = "; ".join(f"{e['file_path']}: {e['reason']}" for e in (run.edits or []) if e["status"] == "REJECTED")
            return fail("The Development Agent produced no verified source change (git reports a clean working tree)."
                        + (f" Rejected edits: {rejected}" if rejected else "") + (f" Agent notes: {' | '.join(notes)[:400]}" if notes else ""))
        transition(db, task_id, expect=S.IMPLEMENTING, to=S.VALIDATING, actor=AGENT_DEV, event_type="implementation_applied",
                   message=f"{len(run.changed_files)} file(s) changed in git on {run.branch_name}", detail={"changed_files": run.changed_files})
        plan = planning.ArchitecturePlan.model_validate(plan_row.plan)
        verdict = development.run_validation(db, run, plan)
        repairs = 0
        seen_diffs = {hashlib.sha256((run.diff or "").encode()).hexdigest()}
        while verdict == ValidationVerdict.FAILED and repairs < settings.AGENT_MAX_REPAIR_ATTEMPTS:
            repairs += 1
            failing = "\n".join(f"[{c.name}] {c.failure_details or ''}\n{(c.output or '')[-3000:]}" for c in run.checks
                                if c.batch == max(x.batch for x in run.checks) and c.status in ("FAILED", "TIMED_OUT"))
            try:
                notes += development.repair(db, run=run, task=task, plan_row=plan_row, provider=provider, failure=failing)
            except Exception as exc:  # noqa: BLE001
                notes.append(f"repair attempt {repairs} could not run: {exc}")
                break
            development.finalize_diff(db, run)
            if not run.changed_files:
                break
            digest = hashlib.sha256((run.diff or "").encode()).hexdigest()
            if digest in seen_diffs:
                notes.append(f"repair attempt {repairs} reproduced an earlier change; stopping instead of looping")
                break
            seen_diffs.add(digest)
            verdict = development.run_validation(db, run, plan)
        run.diff_stat = {**(run.diff_stat or {}), "repair_attempts": repairs}
        run.summary = development.build_summary(run, notes)
        run.finished_at = datetime.now(timezone.utc)
        db.add(run); db.commit()
        ok = verdict in (ValidationVerdict.PASSED, ValidationVerdict.PARTIAL)
        _log_execution(db, task_id, "IMPLEMENTATION", failed=False, error=None if ok else f"Validation verdict {verdict.value}",
                       model=run.model_name, result={"summary": run.summary, "branch": run.branch_name},
                       changed=run.changed_files, validation={"runs": [{"name": c.name, "status": c.status, "exit_code": c.exit_code} for c in run.checks]},
                       diff=run.diff)
        transition(db, task_id, expect=S.VALIDATING, to=S.READY_FOR_MR if ok else S.VALIDATION_FAILED, actor=AGENT_QA,
                   event_type="validation_completed", message=f"Validation verdict: {verdict.value}", detail={"verdict": verdict.value, "run_id": str(run.id)})
    except Exception as exc:  # noqa: BLE001
        logger.exception("Development run %s crashed", run_id)
        db.rollback()
        # if we already reached VALIDATING, fall back to VALIDATION_FAILED, else IMPLEMENTATION_FAILED
        t = db.get(Task, task_id)
        if S(t.workflow_stage) == S.VALIDATING:
            r = db.get(DevelopmentRun, run_id); r.error = f"{exc.__class__.__name__}: {exc}"[:3000]; db.add(r); db.commit()
            transition(db, task_id, expect=S.VALIDATING, to=S.VALIDATION_FAILED, actor=AGENT_QA, event_type="validation_failed", message=str(exc)[:500])
        else:
            fail(f"{exc.__class__.__name__}: {exc}")
    finally:
        if own:
            db.close()


def start_validation(db: Session, *, user: User, task_id: uuid.UUID) -> DevelopmentRun:
    _require(user, Permission.SANDBOX_EXECUTE)
    get_task_any(db, task_id)
    run = latest_run(db, task_id)
    if run is None or run.status not in (DevRunStatus.CHANGES_APPLIED.value, DevRunStatus.COMMITTED.value):
        raise WorkflowStateError("There is no applied implementation to validate")
    transition(db, task_id, expect={S.VALIDATION_FAILED, S.READY_FOR_MR}, to=S.VALIDATING, actor=user,
               event_type="validation_started", message="Re-running validation checks")
    return run


def execute_validation(run_id: uuid.UUID, *, db: Session | None = None) -> None:
    own = db is None
    db = db or SessionLocal()
    try:
        run = db.get(DevelopmentRun, run_id)
        plan_row = db.get(TaskPlan, run.plan_id)
        plan = planning.ArchitecturePlan.model_validate(plan_row.plan)
        verdict = development.run_validation(db, run, plan)
        ok = verdict in (ValidationVerdict.PASSED, ValidationVerdict.PARTIAL)
        transition(db, run.task_id, expect=S.VALIDATING, to=S.READY_FOR_MR if ok else S.VALIDATION_FAILED, actor=AGENT_QA,
                   event_type="validation_completed", message=f"Validation verdict: {verdict.value}", detail={"verdict": verdict.value})
    except Exception as exc:  # noqa: BLE001
        logger.exception("Validation crashed")
        db.rollback()
        run = db.get(DevelopmentRun, run_id)
        transition(db, run.task_id, expect=S.VALIDATING, to=S.VALIDATION_FAILED, actor=AGENT_QA, event_type="validation_failed", message=str(exc)[:500])
    finally:
        if own:
            db.close()


# --------------------------------------------------------------------------
# Stage 7: commit + merge request
# --------------------------------------------------------------------------

def _mr_description(db: Session, task: Task, run: DevelopmentRun, plan_row: TaskPlan, extra: str | None) -> str:
    stat = run.diff_stat or {}
    lines = [f"## Requirement\n{task.description}", f"## Approved plan (v{plan_row.version})\n{(plan_row.plan or {}).get('summary', '')}",
             f"## Changes (verified from git)\nBranch `{run.branch_name}` -> `{run.base_branch}`; {len(run.changed_files or [])} file(s), "
             f"+{stat.get('additions', 0)}/-{stat.get('deletions', 0)}"]
    lines += [f"- `{f}`" for f in (run.changed_files or [])]
    latest_batch = max((c.batch for c in run.checks), default=0)
    lines.append(f"## Validation: {run.validation_verdict}")
    for c in run.checks:
        if c.batch == latest_batch:
            lines.append(f"- {c.name}: **{c.status}**" + (f" (exit {c.exit_code})" if c.exit_code is not None else ""))
    if extra:
        lines.append(f"## Developer notes\n{extra}")
    lines.append(f"\n_Created by RAD AI Agent for task {task.id}._")
    return "\n\n".join(lines)


def create_merge_request(db: Session, *, user: User, task_id: uuid.UUID, title: str | None = None, description: str | None = None,
                         acknowledge_validation_risk: bool = False) -> MergeRequest:
    _require(user, Permission.MR_CREATE)
    task = get_task_any(db, task_id)
    run = latest_run(db, task_id)
    plan_row = approved_plan(db, task_id)
    if run is None or plan_row is None or run.status not in (DevRunStatus.CHANGES_APPLIED.value, DevRunStatus.COMMITTED.value):
        raise WorkflowStateError("A merge request needs an applied implementation of an approved plan")
    verdict = ValidationVerdict(run.validation_verdict)
    if verdict in (ValidationVerdict.FAILED, ValidationVerdict.NOT_RUN, ValidationVerdict.PARTIAL) and not acknowledge_validation_risk:
        raise WorkflowStateError(
            f"Validation verdict is {verdict.value}. Fix or re-run validation, or explicitly acknowledge the risk "
            "(acknowledge_validation_risk=true) so the Architect is told the change was submitted without fully passing checks.")
    if run.validated_diff_sha and run.worktree_path and not run.commit_sha:
        now_sha = development.current_diff_sha(Path(run.worktree_path))
        if now_sha and now_sha != run.validated_diff_sha:
            raise WorkflowStateError("The working tree changed after it was validated; the validation result is stale. Re-run validation first.")
    transition(db, task_id, expect={S.READY_FOR_MR, S.VALIDATION_FAILED, S.MR_CREATION_FAILED}, to=S.MR_CREATING, actor=user,
               event_type="mr_creation_started", message="Creating commit and merge request")
    repo = db.get(Repository, task.repository_id)
    settings = get_settings()
    mr = db.query(MergeRequest).filter(MergeRequest.run_id == run.id).one_or_none()
    if mr is None:
        mr = MergeRequest(task_id=task_id, run_id=run.id, plan_id=plan_row.id, title=(title or task.title or task.description[:80])[:300],
                          source_branch=run.branch_name, target_branch=run.base_branch, validation_verdict=run.validation_verdict,
                          failed_validation_acknowledged=acknowledge_validation_risk, created_by=user.id)
        db.add(mr); db.commit(); db.refresh(mr)
    mr.status, mr.error = MrStatus.CREATING.value, None
    mr.failed_validation_acknowledged = acknowledge_validation_risk or mr.failed_validation_acknowledged
    db.add(mr); db.commit()

    def fail(msg: str) -> MergeRequest:
        mr.status, mr.error = MrStatus.CREATION_FAILED.value, msg[:3000]
        db.add(mr); db.commit()
        transition(db, task_id, expect=S.MR_CREATING, to=S.MR_CREATION_FAILED, actor=AGENT_DEVOPS, event_type="mr_creation_failed",
                   message=msg[:500], detail={"local_work_preserved": True, "branch": run.branch_name})
        return mr

    worktree = Path(run.worktree_path or "")
    try:
        if not run.commit_sha:   # idempotent: a retry reuses the existing commit
            message = f"{mr.title}\n\nTask: {task.id}\nPlan: v{plan_row.version}\nValidation: {run.validation_verdict}"
            run.commit_sha = gitops.commit_all(worktree, message)
            run.commit_message = message
        run.status = DevRunStatus.COMMITTED.value
        db.add(run); db.commit()
        mr.commit_sha = run.commit_sha
        mr.description = _mr_description(db, task, run, plan_row, description)
        db.add(mr); db.commit()
    except Exception as exc:  # noqa: BLE001
        return fail(f"Commit failed (local work is preserved in {run.branch_name}): {exc}")

    # ---- remote: push + provider MR (honest about what really happened) ----
    provider, namespace, repo_name = gitops.detect_provider(repo.url)
    token = settings.GIT_PROVIDER_TOKEN
    local_remote = not repo.url.startswith(("http://", "https://", "ssh://", "git@"))
    mr.remote_provider = provider
    if not mr.pushed and (token or local_remote):
        ok, out = gitops.push_branch(worktree, repo.url, mr.source_branch, token=token)
        mr.pushed = ok
        if not ok:
            mr.remote_status, mr.remote_error = RemoteStatus.REMOTE_FAILED.value, f"git push failed: {out}"
    if mr.remote_status != RemoteStatus.REMOTE_FAILED.value:
        if provider is None:
            mr.remote_status = RemoteStatus.REMOTE_UNAVAILABLE.value
            mr.remote_error = ("No supported Git provider (GitHub/GitLab) could be determined for this repository URL; "
                               "no remote merge request was created." + (" The branch was pushed." if mr.pushed else ""))
        elif not token:
            mr.remote_status = RemoteStatus.REMOTE_UNAVAILABLE.value
            mr.remote_error = "GIT_PROVIDER_TOKEN is not configured, so the branch was not pushed and no remote merge request was created."
        elif mr.remote_url is None:
            try:
                remote = gitops.create_remote_mr(provider, namespace, repo_name, token=token, source=mr.source_branch,
                                                 target=mr.target_branch, title=mr.title, description=mr.description or "")
                mr.remote_status, mr.remote_url, mr.remote_identifier, mr.remote_error = (
                    RemoteStatus.REMOTE_CREATED.value, remote.url, remote.identifier, None)
            except gitops.ProviderError as exc:
                mr.remote_status, mr.remote_error = RemoteStatus.REMOTE_FAILED.value, str(exc)
    mr.status = MrStatus.OPEN.value
    mr.review_status = MrReviewStatus.PENDING_REVIEW.value
    db.add(mr); db.commit()
    transition(db, task_id, expect=S.MR_CREATING, to=S.MR_PENDING_REVIEW, actor=user, event_type="mr_created",
               message=f"Merge request opened (remote: {mr.remote_status})", detail={"mr_id": str(mr.id), "commit": mr.commit_sha, "remote_url": mr.remote_url})
    db.refresh(mr)
    return mr


# --------------------------------------------------------------------------
# Stage 8: architect review of the MR
# --------------------------------------------------------------------------

def decide_mr(db: Session, *, user: User, task_id: uuid.UUID, decision: Decision, comment: str | None,
              mr_id: uuid.UUID | None = None) -> MergeRequest:
    _require(user, Permission.MR_APPROVE if decision == Decision.APPROVED else Permission.MR_REJECT)
    if decision != Decision.APPROVED and not (comment and comment.strip()):
        raise ValidationError("A comment explaining the rejection or the requested revision is required")
    get_task_any(db, task_id)
    mr = latest_mr(db, task_id)
    if mr is None or mr.status != MrStatus.OPEN.value or mr.review_status != MrReviewStatus.PENDING_REVIEW.value:
        raise WorkflowStateError("There is no open merge request awaiting review")
    if mr_id is not None and mr.id != mr_id:
        raise WorkflowStateError("That merge request is not the current one")
    stage, review = {
        Decision.APPROVED: (S.MR_APPROVED, MrReviewStatus.APPROVED),
        Decision.REJECTED: (S.MR_REJECTED, MrReviewStatus.REJECTED),
        Decision.REVISION_REQUESTED: (S.MR_REVISION_REQUIRED, MrReviewStatus.REVISION_REQUIRED),
    }[decision]
    transition(db, task_id, expect=S.MR_PENDING_REVIEW, to=stage, actor=user, event_type=f"mr_{decision.value.lower()}", message=comment,
               detail={"mr_id": str(mr.id), "commit": mr.commit_sha})
    mr = db.get(MergeRequest, mr.id)
    mr.review_status = review.value
    db.add(mr)
    db.add(ReviewDecision(task_id=task_id, subject_type=DecisionSubject.MR.value, subject_id=mr.id, decision=decision.value, comment=comment,
                          decided_by=user.id, decided_by_role=user.role.value))
    db.commit()
    db.refresh(mr)
    return mr


# --------------------------------------------------------------------------
# Stage 9: deployment
# --------------------------------------------------------------------------

def start_deployment(db: Session, *, user: User, task_id: uuid.UUID) -> Deployment:
    _require(user, Permission.DEPLOY_EXECUTE)
    task = get_task_any(db, task_id)
    mr = latest_mr(db, task_id)
    repo = db.get(Repository, task.repository_id)
    run = db.get(DevelopmentRun, mr.run_id) if mr else None
    ok, why = deploy_mod.eligibility(mr, run, repo)
    if not ok:
        # record the blocked attempt so the UI/report can show why nothing was deployed
        record_event(db, task_id=task_id, event_type="deployment_blocked", actor=user, message=why)
        raise WorkflowStateError(f"Deployment is blocked: {why}")
    transition(db, task_id, expect={S.MR_APPROVED, S.DEPLOYMENT_FAILED, S.DEPLOYMENT_UNAVAILABLE}, to=S.DEPLOYING, actor=user,
               event_type="deployment_started", message="DevOps Agent started", detail={"commit": mr.commit_sha})
    attempt = (db.query(func.max(Deployment.attempt)).filter(Deployment.task_id == task_id).scalar() or 0) + 1
    dep = Deployment(task_id=task_id, merge_request_id=mr.id, attempt=attempt, status=DeploymentStatus.DEPLOYING.value,
                     commit_sha=mr.commit_sha, created_by=user.id)
    db.add(dep); db.commit(); db.refresh(dep)
    return dep


def execute_deployment(dep_id: uuid.UUID, *, db: Session | None = None) -> None:
    own = db is None
    db = db or SessionLocal()
    try:
        dep = db.get(Deployment, dep_id)
        task = db.get(Task, dep.task_id)
        repo = db.get(Repository, task.repository_id)
        mr = db.get(MergeRequest, dep.merge_request_id)
        status = deploy_mod.execute(db, dep_id=dep_id, task=task, repo=repo, mr=mr)
        stage = {DeploymentStatus.DEPLOYED: S.DEPLOYED, DeploymentStatus.UNAVAILABLE: S.DEPLOYMENT_UNAVAILABLE}.get(status, S.DEPLOYMENT_FAILED)
        db.refresh(dep)
        transition(db, task.id, expect=S.DEPLOYING, to=stage, actor=AGENT_DEVOPS, event_type=f"deployment_{status.value.lower()}", message=dep.error or "Deployment completed",
                   detail={"deployment_id": str(dep.id), "attempt": dep.attempt})
    except Exception as exc:  # noqa: BLE001
        logger.exception("Deployment crashed")
        db.rollback()
        dep = db.get(Deployment, dep_id)
        dep.status, dep.error = DeploymentStatus.DEPLOYMENT_FAILED.value, f"{exc.__class__.__name__}: {exc}"[:3000]
        db.add(dep); db.commit()
        try:
            transition(db, dep.task_id, expect=S.DEPLOYING, to=S.DEPLOYMENT_FAILED, actor=AGENT_DEVOPS, event_type="deployment_failed", message=dep.error[:500])
        except WorkflowStateError:
            pass
    finally:
        if own:
            db.close()
