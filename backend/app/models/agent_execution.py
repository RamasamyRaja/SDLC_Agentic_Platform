"""
AgentExecution model.

Deliberately minimal, per the milestone spec's "do not prematurely
implement the complete execution subsystem" — this is the single table
that represents one LangGraph workflow run: which task, what status, what
declarative action was decided, the (already-validated, already-grounded)
reasoning result, and an error message on failure. Future milestones may
expand this into execution_steps / step_logs / tool_calls / code_changes
as those capabilities are actually built — not introduced speculatively
here.

This table (not LangGraph's own checkpointer) is the durable, cross-request
record of a run — see app/agent/checkpointer.py's docstring for why
LangGraph's checkpointing itself uses an in-memory saver in this milestone.
"""
import enum
import uuid

from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AgentExecutionStatus(str, enum.Enum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class AgentExecution(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "agent_executions"

    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    status: Mapped[AgentExecutionStatus] = mapped_column(
        Enum(AgentExecutionStatus, name="agent_execution_status"), nullable=False
    )
    # AgentAction value (e.g. "PROPOSE_CHANGE") — nullable, since a failed
    # run never reaches DECIDE_ACTION.
    action: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # The validated ReasoningResult, as JSON — present when status=COMPLETED.
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    # --- Milestone 7: bounded tool-gathering summary for this run ---
    # Small summaries only (file path + line count / truncated error
    # message), the same shape TOOL_EXECUTION returns in state — never
    # full file content. Individual tool calls are ALSO recorded, one row
    # each, in ToolInvocation — this column is a per-run summary, not a
    # duplicate of that table.
    tool_call_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tool_results: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    validation: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    changed_files: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    repair_attempts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    final_diff: Mapped[str | None] = mapped_column(Text, nullable=True)

    task: Mapped["Task"] = relationship("Task")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<AgentExecution id={self.id} task_id={self.task_id} status={self.status}>"
