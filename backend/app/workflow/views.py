"""
Read models for the UI and the execution report. Everything here is derived
from persisted rows; nothing is summarised from memory or assumed. The
lifecycle block (stage status, errors/blockers and the actions the *current
user* may take) is computed on the server so the frontend cannot show a button
whose endpoint would be refused, nor display success the backend never recorded.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.agent_execution import AgentExecution
from app.models.repository import Repository
from app.models.task import Task
from app.models.tool_invocation import ToolInvocation
from app.models.user import User
from app.models.workflow import (
    Deployment, DevelopmentRun, MergeRequest, MrReviewStatus, MrStatus, PlanStatus, ReviewDecision, TaskPlan, ValidationVerdict,
    WorkflowEvent, WorkflowStage as S,
)
from app.rbac import Permission, has_permission
from app.workflow import lifecycle as lc
from app.workflow import qa
from app.workflow.state import IMPLEMENTATION_START_STAGES, PLAN_START_STAGES


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _stale(task: Task, seconds: int) -> bool:
    ts = task.updated_at if task.updated_at.tzinfo else task.updated_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - ts > timedelta(seconds=seconds)


def stage_is_stale(task: Task) -> bool:
    st = S(task.workflow_stage)
    return st.value in ("PLANNING", "IMPLEMENTING", "VALIDATING", "MR_CREATING", "DEPLOYING") and _stale(task, lc.stale_seconds(st))


def plan_status(task_id, db) -> str:
    p = lc.latest_plan(db, task_id)
    return p.status if p else "NOT_STARTED"


def validation_summary_for(run) -> dict | None:
    """Stored explanation of the latest batch; for runs validated before it existed, explain from the stored rows (verdict untouched)."""
    if run is None:
        return None
    if run.validation_summary:
        return run.validation_summary
    if not run.checks:
        return None
    latest = max(c.batch for c in run.checks)
    return qa.explain_legacy([c for c in run.checks if c.batch == latest], verdict=run.validation_verdict)


_HUMAN = {"PLAN_PENDING_APPROVAL": "Plan awaiting Architect approval", "MR_PENDING_REVIEW": "Merge request awaiting Architect review",
          "MR_APPROVED": "Approved - waiting for deployment", "PLAN_REJECTED": "Plan rejected - needs re-planning",
          "PLAN_REVISION_REQUIRED": "Plan revision requested", "MR_REJECTED": "Merge request rejected - needs rework",
          "MR_REVISION_REQUIRED": "Merge request revision requested"}
_ERRORS = {"PLAN_FAILED", "IMPLEMENTATION_FAILED", "VALIDATION_FAILED", "MR_CREATION_FAILED", "DEPLOYMENT_FAILED"}


def attention(task: Task, run, dep, stale: bool) -> dict:
    """What a person must look at. Derived only from persisted state."""
    st = task.workflow_stage
    if st in _HUMAN:
        return {"level": "human_action", "reason": _HUMAN[st]}
    if st in _ERRORS:
        reason = (run.error if run and run.error and st in ("IMPLEMENTATION_FAILED", "VALIDATION_FAILED") else None) or st.replace("_", " ").title()
        return {"level": "error", "reason": reason[:300]}
    if st == "DEPLOYMENT_UNAVAILABLE":
        return {"level": "blocked", "reason": (dep.error if dep and dep.error else "Deployment could not be verified or is not configured")[:300]}
    if st in ("PLANNING", "IMPLEMENTING", "VALIDATING", "MR_CREATING", "DEPLOYING"):
        return {"level": "error" if stale else "running", "reason": "No progress for a long time - the worker may have been lost; it will be marked failed and can be retried" if stale else "Agent working"}
    if st == "READY_FOR_MR" and run and run.validation_verdict == "PARTIAL":
        return {"level": "human_action", "reason": "Validation is PARTIAL - required verification is incomplete"}
    return {"level": None, "reason": None}


def summary_row(db: Session, task: Task, repo_names: dict, users: dict) -> dict:
    run = lc.latest_run(db, task.id)
    mr = lc.latest_mr(db, task.id)
    dep = lc.latest_deployment(db, task.id)
    plan = lc.latest_plan(db, task.id)
    creator = users.get(task.user_id)
    return {
        "id": str(task.id), "title": task.title, "description": task.description, "repository_id": str(task.repository_id),
        "repository_name": repo_names.get(task.repository_id), "branch": task.branch, "status": task.status.value,
        "workflow_stage": task.workflow_stage, "creator": {"id": str(creator.id), "email": creator.email, "full_name": creator.full_name} if creator else None,
        "plan_status": plan.status if plan else "NOT_STARTED",
        "development_status": run.status if run else "NOT_STARTED",
        "validation_verdict": run.validation_verdict if run else "NOT_RUN",
        "validation_headline": (validation_summary_for(run) or {}).get("headline") if run else None,
        "validation_counts": (validation_summary_for(run) or {}).get("counts") if run else None,
        "attention": attention(task, run, dep, stage_is_stale(task)),
        "mr_status": (mr.status if mr else "NOT_CREATED"),
        "mr_review_status": mr.review_status if mr else "NOT_CREATED",
        "deployment_status": (dep.status if dep else ("BLOCKED_PENDING_APPROVAL" if not mr or mr.review_status != MrReviewStatus.APPROVED.value else "READY_FOR_DEPLOYMENT")),
        "created_at": _iso(task.created_at), "updated_at": _iso(task.updated_at),
    }


def allowed_actions(db: Session, task: Task, user: User) -> list[dict]:
    stage = S(task.workflow_stage)
    settings = get_settings()
    acts: list[dict] = []
    repo = db.get(Repository, task.repository_id)
    run = lc.latest_run(db, task.id)
    mr = lc.latest_mr(db, task.id)

    def add(key, label, perm, endpoint, **extra):
        if has_permission(user, perm):
            acts.append({"key": key, "label": label, "method": "POST", "endpoint": f"/api/tasks/{task.id}/{endpoint}", **extra})

    plan_startable = stage in PLAN_START_STAGES or (stage == S.PLANNING and _stale(task, settings.PLAN_STALE_AFTER_SECONDS))
    if plan_startable and lc.planning_blockers(repo) is None:
        label = "Start architecture planning" if stage == S.CREATED else "Re-run architecture planning"
        add("start_planning", label, Permission.AGENT_RUN, "plan", accepts_comment=True)
    if stage == S.PLAN_PENDING_APPROVAL:
        add("approve_plan", "Approve plan", Permission.PLAN_APPROVE, "plan/decision", decision="APPROVED", accepts_comment=True)
        add("request_plan_revision", "Request revision", Permission.PLAN_REJECT, "plan/decision", decision="REVISION_REQUESTED", requires_comment=True)
        add("reject_plan", "Reject plan", Permission.PLAN_REJECT, "plan/decision", decision="REJECTED", requires_comment=True)
    impl_startable = (stage in IMPLEMENTATION_START_STAGES or (stage == S.IMPLEMENTING and _stale(task, settings.DEV_STALE_AFTER_SECONDS))) \
        and lc.approved_plan(db, task.id) is not None
    if impl_startable:
        label = "Start implementation" if stage == S.PLAN_APPROVED else "Re-run implementation"
        add("start_implementation", label, Permission.AGENT_RUN, "implementation", accepts_comment=True)
    if stage in (S.VALIDATION_FAILED, S.READY_FOR_MR) or (stage == S.VALIDATING and stage_is_stale(task)):
        add("run_validation", "Re-run validation", Permission.SANDBOX_EXECUTE, "validation")
    if stage in (S.READY_FOR_MR, S.VALIDATION_FAILED, S.MR_CREATION_FAILED) and run is not None:
        needs_ack = run.validation_verdict in (ValidationVerdict.FAILED.value, ValidationVerdict.NOT_RUN.value, ValidationVerdict.PARTIAL.value)
        add("create_merge_request", "Create commit & merge request", Permission.MR_CREATE, "merge-request",
            requires_acknowledgement=needs_ack, accepts_comment=True)
    if stage == S.MR_PENDING_REVIEW:
        add("approve_mr", "Approve merge request", Permission.MR_APPROVE, "merge-request/decision", decision="APPROVED", accepts_comment=True)
        add("request_mr_revision", "Request revision", Permission.MR_REJECT, "merge-request/decision", decision="REVISION_REQUESTED", requires_comment=True)
        add("reject_mr", "Reject merge request", Permission.MR_REJECT, "merge-request/decision", decision="REJECTED", requires_comment=True)
    if stage in (S.MR_APPROVED, S.DEPLOYMENT_FAILED, S.DEPLOYMENT_UNAVAILABLE):
        add("deploy", "Deploy approved change" if stage == S.MR_APPROVED else "Retry deployment", Permission.DEPLOY_EXECUTE, "deployment")
    return acts


def _stage_block(key, label, owner, status, *, started=None, finished=None, error=None, blockers=None, summary=None, outputs=None):
    return {"key": key, "label": label, "owner": owner, "status": status, "started_at": _iso(started), "finished_at": _iso(finished),
            "error": error, "blockers": blockers or [], "summary": summary, "outputs": outputs or {}}


def lifecycle(db: Session, task: Task) -> list[dict]:
    stage = S(task.workflow_stage)
    repo = db.get(Repository, task.repository_id)
    plan = lc.latest_plan(db, task.id)
    approved = lc.approved_plan(db, task.id)
    run = lc.latest_run(db, task.id)
    mr = lc.latest_mr(db, task.id)
    dep = lc.latest_deployment(db, task.id)
    pd = lc.last_decision(db, task.id, __import__("app.models.workflow", fromlist=["DecisionSubject"]).DecisionSubject.PLAN)
    md = lc.last_decision(db, task.id, __import__("app.models.workflow", fromlist=["DecisionSubject"]).DecisionSubject.MR)
    out = [_stage_block("requirement", "Requirement", "Developer", "COMPLETED", started=task.created_at, finished=task.created_at,
                        summary=task.title or task.description[:120])]

    # Architecture plan
    blockers = [b] if (b := lc.planning_blockers(repo)) and stage == S.CREATED else []
    if plan is None:
        out.append(_stage_block("architecture_plan", "Architecture plan", "Architecture Agent", "BLOCKED" if blockers else "NOT_STARTED", blockers=blockers))
    else:
        st = {PlanStatus.GENERATING.value: "IN_PROGRESS", PlanStatus.FAILED.value: "FAILED"}.get(plan.status, "COMPLETED")
        out.append(_stage_block("architecture_plan", "Architecture plan", "Architecture Agent", st, started=plan.created_at, finished=plan.finished_at,
                                error=plan.error, summary=(plan.plan or {}).get("summary"), outputs={"version": plan.version, "plan_id": str(plan.id)}))
    # Plan approval
    if plan is None or plan.status in (PlanStatus.GENERATING.value, PlanStatus.FAILED.value):
        out.append(_stage_block("plan_approval", "Plan approval", "Architect", "NOT_STARTED"))
    elif plan.status == PlanStatus.PENDING_APPROVAL.value:
        out.append(_stage_block("plan_approval", "Plan approval", "Architect", "PENDING_HUMAN", started=plan.finished_at, summary="Waiting for an Architect to approve, reject or request a revision"))
    else:
        st = "COMPLETED" if approved else "FAILED"
        out.append(_stage_block("plan_approval", "Plan approval", "Architect", st, started=plan.finished_at, finished=pd.created_at if pd else None,
                                summary=f"{plan.status}" + (f": {pd.comment}" if pd and pd.comment else ""),
                                outputs={"decided_by": pd.decided_by_role if pd else None}))
    # Implementation
    if run is None:
        out.append(_stage_block("implementation", "Implementation", "Development Agent", "NOT_STARTED" if approved else "BLOCKED",
                                blockers=[] if approved else ["Requires an Architect-approved plan"]))
    else:
        st = {"RUNNING": "IN_PROGRESS", "FAILED": "FAILED", "NO_CHANGES": "FAILED"}.get(run.status, "COMPLETED")
        out.append(_stage_block("implementation", "Implementation", "Development Agent", st, started=run.created_at, finished=run.finished_at, error=run.error,
                                summary=run.summary, outputs={"run_id": str(run.id), "attempt": run.attempt, "branch": run.branch_name,
                                                              "changed_files": run.changed_files or [], "status": run.status}))
    # Testing
    if run is None or run.status in ("RUNNING", "FAILED", "NO_CHANGES") and not run.checks:
        out.append(_stage_block("testing", "Testing", "QA", "NOT_STARTED"))
    else:
        v = run.validation_verdict
        st = "IN_PROGRESS" if stage == S.VALIDATING else {"PASSED": "COMPLETED", "PARTIAL": "PARTIAL", "FAILED": "FAILED", "NOT_RUN": "FAILED"}[v]
        vs = validation_summary_for(run) or {}
        out.append(_stage_block("testing", "Testing", "QA", st, summary=f"Verdict: {v}. {vs.get('headline') or ''}".strip(),
                                outputs={"verdict": v, "checks": len([c for c in run.checks if c.status != 'UNVERIFIED']), "counts": vs.get("counts")},
                                error=None if v == "PASSED" else (vs.get("headline") or "Not all checks passed or could run; see check details")))
    # Merge request
    if mr is None:
        out.append(_stage_block("merge_request", "Merge request", "Developer", "NOT_STARTED"))
    else:
        st = {MrStatus.CREATING.value: "IN_PROGRESS", MrStatus.CREATION_FAILED.value: "FAILED"}.get(mr.status, "COMPLETED")
        out.append(_stage_block("merge_request", "Merge request", "Developer", st, started=mr.created_at, error=mr.error,
                                summary=f"{mr.status}; remote: {mr.remote_status}", outputs={"mr_id": str(mr.id), "remote_url": mr.remote_url, "commit": mr.commit_sha}))
    # Architect review
    if mr is None or mr.status != MrStatus.OPEN.value:
        out.append(_stage_block("architect_review", "Architect review", "Architect", "NOT_STARTED"))
    elif mr.review_status == MrReviewStatus.PENDING_REVIEW.value:
        out.append(_stage_block("architect_review", "Architect review", "Architect", "PENDING_HUMAN", summary="Waiting for an Architect to review the diff"))
    else:
        st = "COMPLETED" if mr.review_status == MrReviewStatus.APPROVED.value else "FAILED"
        out.append(_stage_block("architect_review", "Architect review", "Architect", st, finished=md.created_at if md else None,
                                summary=mr.review_status + (f": {md.comment}" if md and md.comment else "")))
    # Deployment
    if dep is None:
        ok = mr is not None and mr.review_status == MrReviewStatus.APPROVED.value
        out.append(_stage_block("deployment", "Deployment", "DevOps Agent", "NOT_STARTED" if ok else "BLOCKED",
                                blockers=[] if ok else ["BLOCKED_PENDING_APPROVAL: requires an Architect-approved merge request"],
                                summary="READY_FOR_DEPLOYMENT" if ok else "BLOCKED_PENDING_APPROVAL"))
    else:
        st = {"DEPLOYING": "IN_PROGRESS", "DEPLOYED": "COMPLETED", "UNAVAILABLE": "BLOCKED"}.get(dep.status, "FAILED")
        if dep.status == "DEPLOYED" and dep.verification_level in ("NONE", "COMMAND_ONLY", "HEALTH_ONLY"):
            st = "PARTIAL"
        out.append(_stage_block("deployment", "Deployment", "DevOps Agent", st, started=dep.started_at, finished=dep.finished_at, error=dep.error,
                                summary=dep.status + (f" (verification: {dep.verification_level})" if dep.verification_level else ""),
                                outputs={"deployment_id": str(dep.id), "attempt": dep.attempt, "steps": dep.steps or [], "verification_level": dep.verification_level}))
    return out


def task_detail(db: Session, task: Task, user: User) -> dict:
    lc.recover_if_stale(db, task)
    repos = {task.repository_id: db.get(Repository, task.repository_id).name}
    users = {task.user_id: db.get(User, task.user_id)}
    row = summary_row(db, task, repos, users)
    repo = db.get(Repository, task.repository_id)
    row.update({
        "expected_outcome": task.expected_outcome, "context": task.context,
        "repository": {"id": str(repo.id), "name": repo.name, "url": repo.url, "default_branch": repo.default_branch,
                       "default_branch_source": repo.default_branch_source, "status": repo.status.value,
                       "indexing_status": repo.indexing_status.value, "commit_sha": repo.commit_sha},
        "lifecycle": lifecycle(db, task), "allowed_actions": allowed_actions(db, task, user),
    })
    return row


def plan_dict(p: TaskPlan) -> dict:
    return {"id": str(p.id), "task_id": str(p.task_id), "version": p.version, "status": p.status, "model_name": p.model_name,
            "feedback": p.feedback, "plan": p.plan, "evidence": p.evidence, "error": p.error, "repository_commit_sha": p.repository_commit_sha,
            "created_at": _iso(p.created_at), "finished_at": _iso(p.finished_at)}


def check_dict(c) -> dict:
    return {"id": str(c.id), "batch": c.batch, "name": c.name, "command": c.command, "status": c.status, "exit_code": c.exit_code,
            "output": c.output, "failure_details": c.failure_details, "runner": c.runner,
            "required": c.required, "kind": c.kind, "metrics": c.metrics,
            "started_at": _iso(c.started_at), "finished_at": _iso(c.finished_at)}


def run_dict(r: DevelopmentRun, *, include_diff: bool = True) -> dict:
    latest = max((c.batch for c in r.checks), default=0)
    d = {"id": str(r.id), "task_id": str(r.task_id), "plan_id": str(r.plan_id), "attempt": r.attempt, "status": r.status, "model_name": r.model_name,
         "feedback": r.feedback, "branch_name": r.branch_name, "base_branch": r.base_branch, "base_commit_sha": r.base_commit_sha,
         "files_read": r.files_read or [], "tool_calls": r.tool_calls or [], "edits": r.edits or [], "changed_files": r.changed_files or [],
         "diff_stat": r.diff_stat, "summary": r.summary, "error": r.error, "validation_verdict": r.validation_verdict,
         "commit_sha": r.commit_sha, "commit_message": r.commit_message, "created_at": _iso(r.created_at), "finished_at": _iso(r.finished_at),
         "checks": [check_dict(c) for c in r.checks if c.batch == latest], "check_batches": latest,
         "validation_summary": validation_summary_for(r), "validated_at": _iso(r.validated_at)}
    if include_diff:
        d["diff"] = r.diff
    return d


def mr_dict(m: MergeRequest, run: DevelopmentRun | None) -> dict:
    return {"id": str(m.id), "task_id": str(m.task_id), "run_id": str(m.run_id), "plan_id": str(m.plan_id), "status": m.status,
            "review_status": m.review_status, "title": m.title, "description": m.description, "source_branch": m.source_branch,
            "target_branch": m.target_branch, "commit_sha": m.commit_sha, "validation_verdict": m.validation_verdict,
            "failed_validation_acknowledged": m.failed_validation_acknowledged, "remote_status": m.remote_status, "remote_provider": m.remote_provider,
            "remote_url": m.remote_url, "remote_identifier": m.remote_identifier, "remote_error": m.remote_error, "pushed": m.pushed,
            "error": m.error, "created_at": _iso(m.created_at), "updated_at": _iso(m.updated_at),
            "run": run_dict(run) if run else None}


def deployment_dict(d: Deployment) -> dict:
    return {"id": str(d.id), "task_id": str(d.task_id), "merge_request_id": str(d.merge_request_id), "attempt": d.attempt, "status": d.status,
            "commit_sha": d.commit_sha, "artifact_path": d.artifact_path, "artifact_sha256": d.artifact_sha256, "steps": d.steps or [],
            "health_check": d.health_check, "evidence": d.evidence, "verification_level": d.verification_level, "log": d.log, "error": d.error, "started_at": _iso(d.started_at), "finished_at": _iso(d.finished_at)}


def event_dict(e: WorkflowEvent) -> dict:
    return {"id": str(e.id), "event_type": e.event_type, "from_stage": e.from_stage, "to_stage": e.to_stage, "actor": e.actor_label,
            "message": e.message, "detail": e.detail, "created_at": _iso(e.created_at)}


def build_report(db: Session, task: Task) -> dict:
    """Evidence-based execution report. `verified` sections come from stored evidence; `recommendations` are model output."""
    repo = db.get(Repository, task.repository_id)
    plan = lc.latest_plan(db, task.id)
    approved = lc.approved_plan(db, task.id)
    runs = db.query(DevelopmentRun).filter(DevelopmentRun.task_id == task.id).order_by(DevelopmentRun.attempt).all()
    run = runs[-1] if runs else None
    mr = lc.latest_mr(db, task.id)
    deps = db.query(Deployment).filter(Deployment.task_id == task.id).order_by(Deployment.attempt).all()
    decisions = db.query(ReviewDecision).filter(ReviewDecision.task_id == task.id).order_by(ReviewDecision.created_at).all()
    events = db.query(WorkflowEvent).filter(WorkflowEvent.task_id == task.id).order_by(WorkflowEvent.created_at).all()
    tools = db.query(ToolInvocation).filter(ToolInvocation.task_id == task.id).order_by(ToolInvocation.created_at).all()
    stage = S(task.workflow_stage)
    unresolved = []
    if stage in (S.PLAN_FAILED, S.IMPLEMENTATION_FAILED, S.VALIDATION_FAILED, S.MR_CREATION_FAILED, S.DEPLOYMENT_FAILED, S.DEPLOYMENT_UNAVAILABLE):
        unresolved.append(f"Task is in stage {stage.value}")
    for label, err in (("plan", plan.error if plan else None), ("implementation", run.error if run else None),
                       ("merge request", mr.error if mr else None), ("deployment", deps[-1].error if deps else None)):
        if err:
            unresolved.append(f"{label}: {err}")
    if mr and mr.remote_status != "REMOTE_CREATED":
        unresolved.append(f"No remote merge request exists ({mr.remote_status}): {mr.remote_error}")
    if run and run.validation_verdict in ("FAILED", "NOT_RUN", "PARTIAL"):
        unresolved.append(f"Validation verdict is {run.validation_verdict}")
    checks = [check_dict(c) for c in (run.checks if run else [])]
    return {
        "task_id": str(task.id), "generated_at": _iso(datetime.now(timezone.utc)), "workflow_stage": stage.value,
        "implementation_completed": bool(run and run.status in ("CHANGES_APPLIED", "COMMITTED") and run.changed_files),
        "requirement": {"title": task.title, "description": task.description, "expected_outcome": task.expected_outcome, "context": task.context,
                        "created_at": _iso(task.created_at)},
        "repository": {"name": repo.name, "url": repo.url, "branch": repo.default_branch, "branch_source": repo.default_branch_source,
                       "commit": repo.commit_sha, "indexing_status": repo.indexing_status.value, "indexed_chunks": repo.indexed_chunk_count},
        "verified": {
            "architecture_findings": [{"statement": f["statement"], "evidence": f["evidence"]} for f in ((plan.plan or {}).get("findings", []) if plan else [])],
            "plan_evidence": plan.evidence if plan else None,
            "approved_plan": approved.plan if approved else None,
            "approved_plan_version": approved.version if approved else None,
            "tool_calls": [{"tool": t.tool_name, "status": t.status.value, "input": t.input_summary, "error": t.error, "at": _iso(t.created_at)} for t in tools],
            "files_read": (run.files_read if run else []) or [],
            "files_modified": (run.changed_files if run else []) or [],
            "edits": (run.edits if run else []) or [],
            "git_diff": run.diff if run else None,
            "commit": {"sha": run.commit_sha, "message": run.commit_message, "branch": run.branch_name} if run and run.commit_sha else None,
            "merge_request": mr_dict(mr, None) if mr else None,
            "tests_executed": [c for c in checks if c["status"] not in ("UNVERIFIED",)],
            "validation_verdict": run.validation_verdict if run else "NOT_RUN",
            "architect_decisions": [{"subject": d.subject_type, "decision": d.decision, "comment": d.comment, "by_role": d.decided_by_role, "at": _iso(d.created_at)} for d in decisions],
            "deployments": [deployment_dict(d) for d in deps],
            "agent_stages": [event_dict(e) for e in events],
        },
        "recommendations": {"plan_recommended_approach": (plan.plan or {}).get("recommended_approach") if plan else None,
                            "plan_rationale": (plan.plan or {}).get("rationale") if plan else None,
                            "risks": (plan.plan or {}).get("risks") if plan else None,
                            "note": "Model-authored text; verify against the evidence in the `verified` section."},
        "unverified": {"acceptance_criteria": [c for c in checks if c["status"] == "UNVERIFIED"]},
        "unavailable": [x for x in [
            None if run else "No implementation has run yet",
            None if mr else "No merge request has been created",
            None if deps else "No deployment has been attempted",
        ] if x],
        "unresolved_issues": unresolved,
    }
