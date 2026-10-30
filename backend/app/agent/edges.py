"""
Conditional edge routing.

`route_after_node` is reused after every node that can fail: if the node
just set status="FAILED", skip straight to FINALIZE (which still runs, so
the workflow always terminates cleanly and a terminal AgentExecution
record is always produced) rather than continuing down the happy path
with a now-invalid state.

`route_after_decide_action` (Milestone 7) routes to the bounded
TOOL_EXECUTION node only when DECIDE_ACTION selected PROPOSE_CHANGE — see
nodes.py::tool_execution_node for why only that action triggers it.
"""
from typing import Literal

from app.agent.state import AgentState

NodeOutcome = Literal["continue", "failed"]


def route_after_node(state: AgentState) -> NodeOutcome:
    return "failed" if state.get("status") == "FAILED" else "continue"


DecideActionOutcome = Literal["tools", "finalize"]


def route_after_decide_action(state: AgentState) -> DecideActionOutcome:
    if state.get("status") == "FAILED":
        return "finalize"
    return "tools" if state.get("action") == "PROPOSE_CHANGE" else "finalize"
