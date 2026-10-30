"""
Persistent records for the RAD task lifecycle.

Requirement -> Architecture Plan -> Plan Approval -> Implementation ->
Testing -> Merge Request -> Architect Review -> Deployment

Every stage persists its own row(s) and links back to the task (and to the
previous stage's row), so what the UI and the execution report show is
always derived from stored evidence rather than from a free-text summary.

Status vocabularies are plain strings validated by the enums below (stored
as VARCHAR, so adding a value never needs a PostgreSQL ENUM migration).
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, CreatedAtMixin, TimestampMixin, UUIDPrimaryKeyMixin


class WorkflowStage(str, enum.Enum):
    """Overall position of a task in the lifecycle. The single source of truth for gate checks."""

    CREATED = "CREATED"
    PLANNING = "PLANNING"
    PLAN_FAILED = "PLAN_FAILED"
    PLAN_PENDING_APPROVAL = "PLAN_PENDING_APPROVAL"
    PLAN_APPROVED = "PLAN_APPROVED"
    PLAN_REJECTED = "PLAN_REJECTED"
    PLAN_REVISION_REQUIRED = "PLAN_REVISION_REQUIRED"
    IMPLEMENTING = "IMPLEMENTING"
    IMPLEMENTATION_FAILED = "IMPLEMENTATION_FAILED"
    VALIDATING = "VALIDATING"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    READY_FOR_MR = "READY_FOR_MR"
    MR_CREATING = "MR_CREATING"
    MR_CREATION_FAILED = "MR_CREATION_FAILED"
    MR_PENDING_REVIEW = "MR_PENDING_REVIEW"
    MR_APPROVED = "MR_APPROVED"
    MR_REJECTED = "MR_REJECTED"
    MR_REVISION_REQUIRED = "MR_REVISION_REQUIRED"
    DEPLOYING = "DEPLOYING"
    DEPLOYED = "DEPLOYED"
    DEPLOYMENT_FAILED = "DEPLOYMENT_FAILED"
    DEPLOYMENT_UNAVAILABLE = "DEPLOYMENT_UNAVAILABLE"


class PlanStatus(str, enum.Enum):
    GENERATING = "GENERATING"
    FAILED = "FAILED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REVISION_REQUIRED = "REVISION_REQUIRED"
    SUPERSEDED = "SUPERSEDED"


class DevRunStatus(str, enum.Enum):
    RUNNING = "RUNNING"
    FAILED = "FAILED"
    NO_CHANGES = "NO_CHANGES"          # the agent finished but produced no verified modification
    CHANGES_APPLIED = "CHANGES_APPLIED"  # verified modifications exist in the isolated working tree
    COMMITTED = "COMMITTED"            # the verified modifications were committed on the task branch


class CheckStatus(str, enum.Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    DEPENDENCY_MISSING = "DEPENDENCY_MISSING"   # the check could not run: tool/dependency absent in the runner
    BLOCKED = "BLOCKED"                          # the runner itself was unavailable (e.g. Docker not reachable)
    SKIPPED = "SKIPPED"                          # nothing applicable to run - never counted as a pass
    UNVERIFIED = "UNVERIFIED"                    # needs a human (e.g. an acceptance criterion)
    NO_TESTS = "NO_TESTS"                        # the test command ran but collected/executed zero tests - never a pass


class ValidationVerdict(str, enum.Enum):
    NOT_RUN = "NOT_RUN"
    PASSED = "PASSED"      # every REQUIRED check ran and passed (see app.workflow.qa.evaluate)
    PARTIAL = "PARTIAL"    # some checks passed, but required verification is missing/inconclusive (dependency, runner, zero tests, ...)
    FAILED = "FAILED"      # a REQUIRED check failed or timed out


class MrStatus(str, enum.Enum):
    CREATING = "CREATING"
    OPEN = "OPEN"
    CREATION_FAILED = "CREATION_FAILED"


class MrReviewStatus(str, enum.Enum):
    PENDING_REVIEW = "MR_PENDING_REVIEW"
    APPROVED = "MR_APPROVED"
    REJECTED = "MR_REJECTED"
    REVISION_REQUIRED = "MR_REVISION_REQUIRED"


class RemoteStatus(str, enum.Enum):
    NOT_ATTEMPTED = "NOT_ATTEMPTED"
    REMOTE_CREATED = "REMOTE_CREATED"
    REMOTE_FAILED = "REMOTE_FAILED"
    REMOTE_UNAVAILABLE = "REMOTE_UNAVAILABLE"   # no provider credentials / unsupported host


class DeploymentStatus(str, enum.Enum):
    BLOCKED_PENDING_APPROVAL = "BLOCKED_PENDING_APPROVAL"
    READY_FOR_DEPLOYMENT = "READY_FOR_DEPLOYMENT"
    DEPLOYING = "DEPLOYING"
    DEPLOYED = "DEPLOYED"
    DEPLOYMENT_FAILED = "DEPLOYMENT_FAILED"
    UNAVAILABLE = "UNAVAILABLE"                 # no deployment target configured


class DecisionSubject(str, enum.Enum):
    PLAN = "PLAN"
    MR = "MR"


class Decision(str, enum.Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    REVISION_REQUESTED = "REVISION_REQUESTED"


def _uuid_fk(target: str, *, nullable: bool = False, ondelete: str = "CASCADE", index: bool = True):
    return mapped_column(UUID(as_uuid=True), ForeignKey(target, ondelete=ondelete), nullable=nullable, index=index)


class TaskPlan(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One Architecture Agent output. A revision/replan creates a new version; old versions stay for audit."""

    __tablename__ = "task_plans"
    __table_args__ = (UniqueConstraint("task_id", "version", name="uq_task_plans_task_version"),)

    task_id: Mapped[uuid.UUID] = _uuid_fk("tasks.id")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=PlanStatus.GENERATING.value, index=True)
    model_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)  # reviewer feedback this version responds to
    plan: Mapped[dict | None] = mapped_column(JSONB, nullable=True)       # validated ArchitecturePlan
    evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)   # files actually read + chunk hits + verification
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    repository_commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[uuid.UUID | None] = _uuid_fk("users.id", nullable=True, ondelete="SET NULL")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    task: Mapped["Task"] = relationship("Task", back_populates="plans")


class DevelopmentRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One Development Agent execution against an approved plan, in an isolated branch/worktree."""

    __tablename__ = "development_runs"

    task_id: Mapped[uuid.UUID] = _uuid_fk("tasks.id")
    plan_id: Mapped[uuid.UUID] = _uuid_fk("task_plans.id", ondelete="RESTRICT")
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=DevRunStatus.RUNNING.value, index=True)
    model_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    branch_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    base_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    base_commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    worktree_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    files_read: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    tool_calls: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    edits: Mapped[list | None] = mapped_column(JSONB, nullable=True)           # every proposed edit + its outcome
    changed_files: Mapped[list | None] = mapped_column(JSONB, nullable=True)   # verified through git, not claimed
    diff: Mapped[str | None] = mapped_column(Text, nullable=True)
    diff_stat: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    validation_verdict: Mapped[str] = mapped_column(String(16), nullable=False, default=ValidationVerdict.NOT_RUN.value)
    # Explainable result of the LATEST validation batch (required/executed/passed/failed/unresolved checks, exit codes,
    # reasons, acceptance criteria, final status + why). NULL for runs validated before this existed: those are explained
    # on read from their stored check rows and are NOT rewritten.
    validation_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    validated_diff_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)   # sha256 of the diff that was validated
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    commit_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = _uuid_fk("users.id", nullable=True, ondelete="SET NULL")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    task: Mapped["Task"] = relationship("Task", back_populates="development_runs")
    checks: Mapped[list["ValidationCheck"]] = relationship(
        "ValidationCheck", back_populates="run", cascade="all, delete-orphan", order_by="ValidationCheck.created_at"
    )


class ValidationCheck(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "validation_checks"

    task_id: Mapped[uuid.UUID] = _uuid_fk("tasks.id")
    run_id: Mapped[uuid.UUID] = _uuid_fk("development_runs.id")
    batch: Mapped[int] = mapped_column(Integer, nullable=False, default=1)  # which validation pass produced it
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    command: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    runner: Mapped[str | None] = mapped_column(String(24), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # NULL = recorded before checks were classified (legacy row); True/False = required/advisory.
    required: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    kind: Mapped[str | None] = mapped_column(String(24), nullable=True)      # compile | test | build | lint | typecheck | acceptance | ...
    metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)       # e.g. parsed test counts

    run: Mapped[DevelopmentRun] = relationship("DevelopmentRun", back_populates="checks")


class MergeRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    The review record for a task's change. `status` describes MR *creation*;
    `review_status` the Architect's decision; `remote_status` whether a pull
    request really exists on the Git provider. These are deliberately
    separate: a local commit with no provider credentials is OPEN for
    review, but `remote_status` says honestly that no remote MR exists.
    """

    __tablename__ = "merge_requests"
    # One MR per development run: retries can never create a second one for the same commit.
    __table_args__ = (UniqueConstraint("run_id", name="uq_merge_requests_run"),)

    task_id: Mapped[uuid.UUID] = _uuid_fk("tasks.id")
    run_id: Mapped[uuid.UUID] = _uuid_fk("development_runs.id", ondelete="RESTRICT")
    plan_id: Mapped[uuid.UUID] = _uuid_fk("task_plans.id", ondelete="RESTRICT")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default=MrStatus.CREATING.value)
    review_status: Mapped[str] = mapped_column(String(24), nullable=False, default=MrReviewStatus.PENDING_REVIEW.value)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_branch: Mapped[str] = mapped_column(String(255), nullable=False)
    target_branch: Mapped[str] = mapped_column(String(255), nullable=False)
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    validation_verdict: Mapped[str] = mapped_column(String(16), nullable=False, default=ValidationVerdict.NOT_RUN.value)
    failed_validation_acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    remote_status: Mapped[str] = mapped_column(String(24), nullable=False, default=RemoteStatus.NOT_ATTEMPTED.value)
    remote_provider: Mapped[str | None] = mapped_column(String(24), nullable=True)
    remote_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    remote_identifier: Mapped[str | None] = mapped_column(String(128), nullable=True)
    remote_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    pushed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = _uuid_fk("users.id", nullable=True, ondelete="SET NULL")

    task: Mapped["Task"] = relationship("Task", back_populates="merge_requests")


class Deployment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "deployments"

    task_id: Mapped[uuid.UUID] = _uuid_fk("tasks.id")
    merge_request_id: Mapped[uuid.UUID] = _uuid_fk("merge_requests.id", ondelete="RESTRICT")
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=DeploymentStatus.READY_FOR_DEPLOYMENT.value)
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    artifact_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    artifact_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    steps: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    health_check: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Separate pieces of evidence: {"command", "health", "version", "smoke"} each {"status", "detail", ...}.
    evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # NONE | COMMAND_ONLY | HEALTH_ONLY | VERSION_VERIFIED | SMOKE_VERIFIED | FULLY_VERIFIED
    verification_level: Mapped[str | None] = mapped_column(String(24), nullable=True)
    log: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = _uuid_fk("users.id", nullable=True, ondelete="SET NULL")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReviewDecision(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """An Architect's recorded decision on a plan or an MR (append-only audit trail)."""

    __tablename__ = "review_decisions"

    task_id: Mapped[uuid.UUID] = _uuid_fk("tasks.id")
    subject_type: Mapped[str] = mapped_column(String(8), nullable=False)
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    decision: Mapped[str] = mapped_column(String(24), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[uuid.UUID | None] = _uuid_fk("users.id", nullable=True, ondelete="SET NULL")
    decided_by_role: Mapped[str | None] = mapped_column(String(20), nullable=True)


class WorkflowEvent(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Append-only task history: every stage transition and notable action, with actor and timestamp."""

    __tablename__ = "workflow_events"

    task_id: Mapped[uuid.UUID] = _uuid_fk("tasks.id")
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    from_stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    actor_id: Mapped[uuid.UUID | None] = _uuid_fk("users.id", nullable=True, ondelete="SET NULL")
    actor_label: Mapped[str | None] = mapped_column(String(255), nullable=True)  # user email, or the agent name
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
