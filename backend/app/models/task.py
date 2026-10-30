"""
Task model.

Represents a user's natural-language software change request against a
specific repository. This milestone only tracks the request and a coarse
lifecycle status — LangGraph execution state (retries, checkpoints, node
transitions, etc.) is introduced in Milestone 6 and lives on separate
Execution* tables, not here.
"""
import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class TaskStatus(str, enum.Enum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# Coarse, Milestone-2-level state machine. LangGraph-driven execution will
# have its own, more detailed transitions later; this only governs what the
# public API is allowed to do via PATCH /api/tasks/{id}/status.
ALLOWED_TASK_STATUS_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PENDING: {TaskStatus.QUEUED, TaskStatus.CANCELLED},
    TaskStatus.QUEUED: {TaskStatus.RUNNING, TaskStatus.CANCELLED},
    TaskStatus.RUNNING: {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.COMPLETED: set(),
    TaskStatus.FAILED: set(),
    TaskStatus.CANCELLED: set(),
}


class Task(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tasks"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    branch: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # --- RAD lifecycle ---------------------------------------------------
    # What the client expects once the requirement is delivered, and any
    # extra context (e.g. pasted requirement document text).
    expected_outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    context: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Overall lifecycle position (see app.models.workflow.WorkflowStage). The
    # coarse `status` above predates the lifecycle and is kept for
    # compatibility; every approval gate is enforced from `workflow_stage`.
    workflow_stage: Mapped[str] = mapped_column(String(32), nullable=False, default="CREATED", server_default="CREATED", index=True)

    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, name="task_status"),
        nullable=False,
        default=TaskStatus.PENDING,
        index=True,
    )

    user: Mapped["User"] = relationship("User", back_populates="tasks")
    repository: Mapped["Repository"] = relationship("Repository", back_populates="tasks")
    artifacts: Mapped[list["TaskArtifact"]] = relationship(
        "TaskArtifact",
        back_populates="task",
        cascade="all, delete-orphan",
    )
    plans: Mapped[list["TaskPlan"]] = relationship(
        "TaskPlan", back_populates="task", cascade="all, delete-orphan", order_by="TaskPlan.version"
    )
    development_runs: Mapped[list["DevelopmentRun"]] = relationship(
        "DevelopmentRun", back_populates="task", cascade="all, delete-orphan", order_by="DevelopmentRun.attempt"
    )
    merge_requests: Mapped[list["MergeRequest"]] = relationship(
        "MergeRequest", back_populates="task", cascade="all, delete-orphan", order_by="MergeRequest.created_at"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<Task id={self.id} status={self.status}>"
