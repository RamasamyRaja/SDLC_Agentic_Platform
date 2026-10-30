from app.agent.state import AgentState


def test_agent_state_accepts_minimal_valid_construction():
    state: AgentState = {"task_id": "t1", "stage": "START", "status": "RUNNING", "errors": []}
    assert state["task_id"] == "t1"
    assert state["status"] == "RUNNING"


def test_agent_state_is_total_false_allows_partial_dicts():
    """AgentState is a partial (total=False) TypedDict — nodes return
    partial updates, not the full state, so this must be allowed."""
    partial: AgentState = {"stage": "REASON"}
    assert partial["stage"] == "REASON"


def test_agent_state_supports_all_documented_fields():
    state: AgentState = {
        "task_id": "t1",
        "repository_id": "r1",
        "task_description": "do something",
        "indexing_status": "INDEXED",
        "reasoning_result": {"summary": "s"},
        "model_name": "fake-model",
        "action": "PROPOSE_CHANGE",
        "stage": "FINALIZE",
        "status": "COMPLETED",
        "errors": [],
        "error_type": None,
    }
    assert state["status"] == "COMPLETED"
    assert state["action"] == "PROPOSE_CHANGE"
