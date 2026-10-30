"""
Declarative agent models: the action enum, execution status, and the
Pydantic result schema returned by the API / stored (as JSON) on
AgentExecution.result.
"""
import enum
import uuid

from pydantic import BaseModel, Field

from app.llm.schemas import ReasoningResult


class AgentAction(str, enum.Enum):
    """
    Declarative-only, per the milestone spec — the graph decides WHICH of
    these fits, but never executes any of them itself:

    ANALYZE            - not enough was determined yet to propose anything concrete
    RETRIEVE           - more/different context is needed before reasoning can proceed
    PROPOSE_CHANGE      - a concrete implementation plan is ready for a future Code Agent
    REQUEST_APPROVAL     - reasoning succeeded but confidence/grounding is too low to
                            auto-propose; a human should review before proceeding
    COMPLETE               - analysis is complete and needs no further agent action
    """

    ANALYZE = "ANALYZE"
    RETRIEVE = "RETRIEVE"
    PROPOSE_CHANGE = "PROPOSE_CHANGE"
    REQUEST_APPROVAL = "REQUEST_APPROVAL"
    COMPLETE = "COMPLETE"


class AgentExecutionStatus(str, enum.Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class AgentExecutionResult(BaseModel):
    """The structured result returned by POST/GET .../run — never a raw
    exception, never unbounded repository content."""

    execution_id: uuid.UUID
    task_id: uuid.UUID
    status: AgentExecutionStatus
    action: AgentAction | None = None
    reasoning_result: ReasoningResult | None = None
    model_name: str | None = None
    errors: list[str] = Field(default_factory=list)
    # Milestone 7: bounded tool-gathering summary (see
    # app/agent/nodes.py::tool_execution_node) — empty unless action was
    # PROPOSE_CHANGE.
    tool_call_count: int = 0
    tool_results: list[dict] = Field(default_factory=list)
