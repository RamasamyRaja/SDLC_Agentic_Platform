"""
Checkpointer factory.

DECISION (documented per the milestone spec's requirement to justify the
checkpointing choice): this milestone uses LangGraph's in-memory
`MemorySaver` by default, NOT `langgraph-checkpoint-postgres`, even though
the Postgres-backed saver is installed and available.

WHY: `PostgresSaver` manages its own tables via a `.setup()` call that runs
its own bundled SQL migrations, entirely OUTSIDE Alembic. This project's
established principle (every milestone so far) is "the database must
remain migration-driven — never require manual table creation" (see
README, and every prior milestone's Alembic verification). Wiring in
`PostgresSaver` today would mean either (a) silently creating
unmanaged tables the first time the app runs, which breaks that
principle, or (b) hand-writing an Alembic migration that duplicates
LangGraph's own internal schema — fragile, since that schema is
LangGraph's implementation detail and could change between versions.

Given the workflow in this milestone executes synchronously within a
single request (same pattern as onboarding/indexing/analyze — see those
milestones), `MemorySaver` is sufficient for what checkpointing actually
buys here: mid-run state inspection during that single execution (used by
tests via `get_state_history`), not cross-request resumption. The
durable, cross-request record of a workflow run is `AgentExecution`
(app/models/agent_execution.py) — a normal, Alembic-migrated table — which
is what `GET /api/tasks/{id}/run/{execution_id}` actually reads.

UPGRADE PATH: `get_checkpointer()` is the only place this decision lives.
Swapping to `PostgresSaver` later means: (1) resolving the Alembic-vs-
`.setup()` tension above (e.g. by vendoring LangGraph's migration SQL into
a real Alembic migration, or calling `.setup()` in a controlled startup
step and documenting that exception explicitly), and (2) changing only
this function — no changes to graph.py, nodes.py, or service.py, since
they depend on `Checkpointer` (the langgraph-checkpoint base type), not on
`MemorySaver` specifically.
"""
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver


def get_checkpointer() -> BaseCheckpointSaver:
    return MemorySaver()
