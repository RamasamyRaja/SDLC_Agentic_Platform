"""
Graph wiring: LOAD_TASK -> BUILD_CONTEXT -> REASON -> VALIDATE_REASONING ->
DECIDE_ACTION -> [TOOL_EXECUTION if PROPOSE_CHANGE] -> FINALIZE -> END,
with a failure short-circuit after every node that can fail (routes
straight to FINALIZE, per edges.py).

TOOL_EXECUTION (Milestone 7) is conditionally reached — see
edges.py::route_after_decide_action and nodes.py::tool_execution_node for
why only the PROPOSE_CHANGE action triggers it, and why it's a single
bounded pass rather than a multi-round loop back to REASON.

`build_agent_graph()` compiles once (module-level `lru_cache`) and is
reused across requests — building the graph structure is cheap but doesn't
need to be repeated per call; the checkpointer instance in the compiled
graph is shared across threads (thread_id, one per execution, is what
LangGraph uses to key state within a single saver — see service.py).
"""
from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from app.agent.checkpointer import get_checkpointer
from app.agent.edges import route_after_decide_action, route_after_node
from app.agent.nodes import (
    build_context_node,
    decide_action_node,
    finalize_node,
    load_task_node,
    reason_node,
    tool_execution_node,
    validate_reasoning_node,
)
from app.agent.state import AgentState


@lru_cache(maxsize=1)
def build_agent_graph():
    graph = StateGraph(AgentState)

    graph.add_node("LOAD_TASK", load_task_node)
    graph.add_node("BUILD_CONTEXT", build_context_node)
    graph.add_node("REASON", reason_node)
    graph.add_node("VALIDATE_REASONING", validate_reasoning_node)
    graph.add_node("DECIDE_ACTION", decide_action_node)
    graph.add_node("TOOL_EXECUTION", tool_execution_node)
    graph.add_node("FINALIZE", finalize_node)

    graph.add_edge(START, "LOAD_TASK")

    graph.add_conditional_edges(
        "LOAD_TASK", route_after_node, {"continue": "BUILD_CONTEXT", "failed": "FINALIZE"}
    )
    graph.add_conditional_edges(
        "BUILD_CONTEXT", route_after_node, {"continue": "REASON", "failed": "FINALIZE"}
    )
    graph.add_conditional_edges(
        "REASON", route_after_node, {"continue": "VALIDATE_REASONING", "failed": "FINALIZE"}
    )
    graph.add_conditional_edges(
        "VALIDATE_REASONING", route_after_node, {"continue": "DECIDE_ACTION", "failed": "FINALIZE"}
    )
    graph.add_conditional_edges(
        "DECIDE_ACTION", route_after_decide_action, {"tools": "TOOL_EXECUTION", "finalize": "FINALIZE"}
    )
    graph.add_edge("TOOL_EXECUTION", "FINALIZE")
    graph.add_edge("FINALIZE", END)

    return graph.compile(checkpointer=get_checkpointer())
