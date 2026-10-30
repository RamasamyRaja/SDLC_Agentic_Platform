"""
Code Agent tool layer (Milestone 7).

Gives the agent controlled, workspace-bounded capabilities: read a file,
search source code, inspect repository structure, modify a file (single,
unambiguous, textual replacement), and inspect a local Git diff. Nothing
here executes arbitrary code, shell commands, or model-generated
functions — see README "Milestone 7" for the full boundary.

base.py (Tool protocol) -> filesystem.py / search.py / tree.py / git.py
(the five tool implementations) -> registry.py (name -> Tool lookup,
input/output validation) -> app/agent/nodes.py::tool_execution_node
(the one place the LangGraph workflow calls into this package) and
app/api/tools.py (the one place the API calls into this package).
"""
