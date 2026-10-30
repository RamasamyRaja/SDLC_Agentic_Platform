"""
Report list/detail for the Reports page. Built from persisted lifecycle
evidence (see app.workflow.views.build_report for the full structured report
at GET /api/tasks/{id}/report). A report is only "complete" when the change
was actually deployed; a plan alone, or an unmerged change, never reads as done.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models.repository import Repository
from app.models.task import Task
from app.models.user import User
from app.rbac import Permission, require_permission
from app.schemas.report import ReportResponse
from app.workflow import lifecycle as lc
from app.workflow import views

router = APIRouter(prefix="/api/reports", tags=["reports"])

_FAILED = {"PLAN_FAILED", "IMPLEMENTATION_FAILED", "VALIDATION_FAILED", "MR_CREATION_FAILED", "MR_REJECTED", "PLAN_REJECTED",
           "DEPLOYMENT_FAILED", "DEPLOYMENT_UNAVAILABLE"}


def _row(db: Session, t: Task) -> ReportResponse:
    full = views.build_report(db, t)
    repo = db.get(Repository, t.repository_id)
    v = full["verified"]
    stage = t.workflow_stage
    status = "complete" if stage == "DEPLOYED" else "failed" if stage in _FAILED else "pending" if stage == "CREATED" else "running"
    plan = lc.latest_plan(db, t.id)
    summary = (plan.plan or {}).get("summary") if plan and plan.plan else None
    changed = len(v["files_modified"])
    outcome = {
        "DEPLOYED": "Deployed from the approved commit.",
        "DEPLOYMENT_UNAVAILABLE": "Approved, but no deployment target or health check is configured; not verified as deployed.",
    }.get(stage, f"In progress: {stage.replace('_', ' ').lower()}. Implementation completed: {'yes' if full['implementation_completed'] else 'no'}.")
    return ReportResponse(
        id=str(t.id), taskId=str(t.id), taskTitle=t.title or t.description[:80], repositoryId=str(t.repository_id),
        repositoryName=repo.name if repo else str(t.repository_id), status=status, generatedAt=t.updated_at, updatedAt=t.updated_at,
        taskSummary=t.description, repositoryContext=f"{repo.url} on {repo.default_branch} ({repo.default_branch_source})" if repo else "",
        analysisSummary=summary or "No architecture plan has been produced yet.",
        agentSummary=(f"Plan v{full['verified']['approved_plan_version']} approved." if v["approved_plan"] else "No approved plan."),
        retrievedContextSummary=f"{len((v['plan_evidence'] or {}).get('files_read', []))} source file(s) read and "
                                f"{(v['plan_evidence'] or {}).get('verification', {}).get('verified_quotes', 0)} evidence quote(s) verified by the Architecture Agent.",
        toolsUsed=sorted({x["tool"] for x in v["tool_calls"]}),
        executionResults=f"Stage {stage}; {changed} file(s) verifiably changed; validation verdict {v['validation_verdict']}; "
                         f"MR {(v['merge_request'] or {}).get('status', 'NOT_CREATED')}.",
        warnings=[x for x in full["unresolved_issues"] if x.startswith(("Validation", "No remote"))],
        errors=[x for x in full["unresolved_issues"] if not x.startswith(("Validation", "No remote"))],
        finalOutcome=outcome,
    )


@router.get("", response_model=list[ReportResponse])
def list_reports(db: Session = Depends(get_db), current_user: User = Depends(require_permission(Permission.AGENT_READ))):
    return [_row(db, t) for t in db.query(Task).order_by(Task.updated_at.desc()).all()]


@router.get("/{report_id}", response_model=ReportResponse)
def get_report(report_id: str, db: Session = Depends(get_db), current_user: User = Depends(require_permission(Permission.AGENT_READ))):
    for t in db.query(Task).all():
        if str(t.id) == report_id:
            return _row(db, t)
    raise NotFoundError("Report not found")
