"""
ToolInvocation model.

One row per tool call — whether made explicitly via
POST /api/tasks/{task_id}/tools/{tool_name} or automatically by the
LangGraph TOOL_EXECUTION node (Milestone 7). Deliberately separate from
AgentExecution (Milestone 6), which represents one full graph run, not a
single tool call — a task can have zero AgentExecutions and several
ToolInvocations (explicit tool use) or vice versa.

`input_summary` is intentionally small and non-sensitive: for read_file,
just the file path and line range, never file content; for modify_file,
the file path and byte-length of old/new content, never the actual text.
The goal is enough to understand "what was attempted", never a duplicate
copy of repository content.
"""
import enum
import uuid

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ToolInvocationStatus(str, enum.Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class ToolInvocation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tool_invocations"

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    tool_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    status: Mapped[ToolInvocationStatus] = mapped_column(
        Enum(ToolInvocationStatus, name="tool_invocation_status"), nullable=False
    )
    # Small, non-sensitive metadata only — never full file content. See
    # module docstring.
    input_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    result_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    task: Mapped["Task"] = relationship("Task")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<ToolInvocation id={self.id} tool_name={self.tool_name!r} status={self.status}>"
