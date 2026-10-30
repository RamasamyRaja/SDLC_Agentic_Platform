"""
LangGraph agent orchestration layer (Milestone 6).

Coordinates the existing M1-M5 services into a stateful, observable
workflow: state.py (typed graph state) -> nodes.py (one responsibility
each, all delegating to existing services) -> edges.py (conditional
routing) -> graph.py (wiring) -> service.py (the single entry point:
run_agent_workflow()).

This layer does NOT execute code, run shell commands, modify repository
files, or create pull requests — it produces a structured, declarative
proposed action (see models.py::AgentAction) that a future milestone's
Code Agent would act on. See README "Milestone 6" for the full boundary.
"""
