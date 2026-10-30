"""
TaskArtifact model.

Identifies a repository file relevant to a task (e.g. a file the Code Agent
is expected to touch). At this milestone this is just a repository-relative
file path plus light metadata — it intentionally does NOT reference a
RepositoryDocument, since repository indexing/document tracking belongs to
Milestone 4. That link can be added later without breaking this table.
"""
import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, CreatedAtMixin, UUIDPrimaryKeyMixin


class ArtifactType(str, enum.Enum):
    SOURCE_FILE = "SOURCE_FILE"
    TEST_FILE = "TEST_FILE"
    CONFIG_FILE = "CONFIG_FILE"
    DOCUMENTATION = "DOCUMENTATION"
    OTHER = "OTHER"


class TaskArtifact(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "task_artifacts"

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Repository-relative path, e.g. "src/investigations/InvestigationPage.tsx".
    # Not validated against an actual repository yet — that requires the
    # Milestone 3 onboarding/workspace step.
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)

    artifact_type: Mapped[ArtifactType] = mapped_column(
        Enum(ArtifactType, name="task_artifact_type"),
        nullable=False,
        default=ArtifactType.OTHER,
    )

    # Free-form note on why this artifact is relevant to the task
    # (e.g. "primary file to modify", "referenced by controller").
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    task: Mapped["Task"] = relationship("Task", back_populates="artifacts")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<TaskArtifact id={self.id} file_path={self.file_path!r}>"
