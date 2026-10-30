"""
TaskAnalysis model.

Persists the outcome of one reasoning run (Milestone 5) against a task —
the model used, the prompt contract version, status, and the validated
structured result as JSONB. PostgreSQL remains the source of truth; this
does NOT duplicate the (already bounded) context sent to the model, only
the result, keeping storage proportional to output size rather than
context size.

One-to-many with Task deliberately: analysis can be re-run (e.g. after the
repository is re-indexed), and prior results stay available for comparison
rather than being overwritten.
"""
import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class TaskAnalysisStatus(str, enum.Enum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class TaskAnalysis(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "task_analyses"

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[TaskAnalysisStatus] = mapped_column(
        Enum(TaskAnalysisStatus, name="task_analysis_status"), nullable=False
    )
    # The validated ReasoningResult, as JSON — present when status=COMPLETED.
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # A clean, non-sensitive error message — present when status=FAILED.
    error: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    task: Mapped["Task"] = relationship("Task")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<TaskAnalysis id={self.id} task_id={self.task_id} status={self.status}>"
