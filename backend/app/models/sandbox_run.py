import enum
import uuid
from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin

class SandboxRunStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    BLOCKED = "BLOCKED"

class SandboxRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sandbox_runs"
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    repository_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True)
    command: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[SandboxRunStatus] = mapped_column(Enum(SandboxRunStatus, name="sandbox_run_status"), nullable=False)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stdout: Mapped[str | None] = mapped_column(Text, nullable=True)
    stderr: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    task: Mapped["Task"] = relationship("Task")
    repository: Mapped["Repository"] = relationship("Repository")
