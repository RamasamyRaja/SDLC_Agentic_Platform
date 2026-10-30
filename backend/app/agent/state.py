"""
Typed LangGraph state.

Deliberately a thin, JSON-serializable TypedDict — no database sessions,
no ORM objects, no full repository content, no secrets. Non-serializable
runtime dependencies (the DB session, the current user, an optional
injected LLM provider) are passed via LangGraph's `config["configurable"]`
instead (see checkpointer.py / graph.py) — they're never part of state, so
they're never at risk of being written to a checkpoint.

`reasoning_result` holds the (already-validated, already-grounded)
ReasoningResult as a plain dict — bounded in size by Milestone 5's own
context limits (LLM_MAX_*), not arbitrary repository text.

`tool_results` (Milestone 7) holds small summaries only (e.g. a file path
and truncated snippet) — never full file content, and bounded by
AGENT_MAX_TOOL_CALLS. See app/agent/nodes.py::tool_execution_node.
"""
from typing import TypedDict


class AgentState(TypedDict, total=False):
    # Identifiers (input)
    task_id: str
    repository_id: str

    # Populated by LOAD_TASK
    task_description: str

    # Populated by BUILD_CONTEXT
    indexing_status: str

    # Populated by REASON
    reasoning_result: dict | None
    model_name: str | None

    # Populated by DECIDE_ACTION
    action: str | None

    # Populated by TOOL_EXECUTION (Milestone 7) — bounded read-only
    # gathering pass, see app/agent/nodes.py::tool_execution_node.
    tool_call_count: int
    tool_results: list[dict]  # small summaries only, never full file content
    tool_limit_reached: bool

    # Workflow bookkeeping
    stage: str
    status: str  # AgentExecutionStatus value
    errors: list[str]
    error_type: str | None  # exception class name, for accurate re-raising in service.py
