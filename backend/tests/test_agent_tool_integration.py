import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"

VALID_JSON_PROPOSE = """{
  "summary": "Add a delete button to the Investigations page.",
  "understanding": {"goal": "Delete investigations", "affected_area": "UI"},
  "relevant_files": [{"file_path": "src/investigation_service.py", "reason": "core logic", "confidence": 0.9}],
  "affected_symbols": [],
  "implementation_plan": [{"step": 1, "description": "Add a button", "target_files": ["src/investigation_service.py"]}],
  "dependencies": [], "risks": [], "uncertainties": [], "confidence": 0.9
}"""

VALID_JSON_NO_PLAN = """{
  "summary": "Nothing to change.",
  "understanding": {"goal": "Investigate", "affected_area": "none"},
  "relevant_files": [], "affected_symbols": [], "implementation_plan": [],
  "dependencies": [], "risks": [], "uncertainties": [], "confidence": 0.9
}"""

VALID_JSON_PROPOSE_MISSING_FILE = """{
  "summary": "Plan references a file that does not actually exist.",
  "understanding": {"goal": "g", "affected_area": "a"},
  "relevant_files": [{"file_path": "src/investigation_service.py", "reason": "r", "confidence": 0.9}],
  "affected_symbols": [],
  "implementation_plan": [{"step": 1, "description": "d", "target_files": ["does/not/exist.py"]}],
  "dependencies": [], "risks": [], "uncertainties": [], "confidence": 0.9
}"""


def _build_local_git_repo(tmp_path: Path, name: str = "tool_graph_origin") -> Path:
    origin = tmp_path / name
    origin.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=origin, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=origin, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=origin, check=True)

    (origin / "src").mkdir()
    shutil.copy(FIXTURES / "python_sample" / "investigation_service.py", origin / "src")

    subprocess.run(["git", "add", "."], cwd=origin, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=origin, check=True, capture_output=True)
    return origin


@pytest.fixture()
def runnable_task(client, db_session, tmp_path):
    origin = _build_local_git_repo(tmp_path)
    repo = client.post("/api/repositories", json={"url": f"file://{origin}", "branch": "main"}).json()
    assert client.post(f"/api/repositories/{repo['id']}/onboard", json={}).status_code == 201
    assert client.post(f"/api/repositories/{repo['id']}/index").status_code == 201
    task = client.post(
        "/api/tasks", json={"repository_id": repo["id"], "request": "Delete an investigation"}
    ).json()

    yield {"repo": repo, "task": task}

    from app.models.repository import Repository
    from app.retrieval.embeddings import get_embedding_provider
    from app.retrieval.milvus_client import MilvusVectorStore
    from app.services import workspace_service

    MilvusVectorStore(dimension=get_embedding_provider().dimension).delete_by_repository(repo["id"])
    db_session.query(Repository).filter(Repository.id == repo["id"]).delete()
    db_session.commit()
    workspace_service.remove_workspace(uuid.UUID(repo["id"]))


def test_tool_execution_runs_for_propose_change(db_session, runnable_task):
    from app.agent.service import run_agent_workflow
    from app.api.deps import get_current_user
    from app.llm.fake_provider import FakeLLMProvider

    user = get_current_user(db_session, None)
    provider = FakeLLMProvider(responses=[VALID_JSON_PROPOSE])

    result = run_agent_workflow(
        db_session, user=user, task_id=uuid.UUID(runnable_task["task"]["task_id"]), provider=provider
    )

    assert result.action.value == "PROPOSE_CHANGE"
    assert result.tool_call_count == 1
    assert result.tool_results[0]["tool"] == "read_file"
    assert result.tool_results[0]["success"] is True
    assert result.tool_results[0]["file_path"] == "src/investigation_service.py"


def test_tool_execution_skipped_for_complete_action(db_session, runnable_task):
    from app.agent.service import run_agent_workflow
    from app.api.deps import get_current_user
    from app.llm.fake_provider import FakeLLMProvider

    user = get_current_user(db_session, None)
    provider = FakeLLMProvider(responses=[VALID_JSON_NO_PLAN])

    result = run_agent_workflow(
        db_session, user=user, task_id=uuid.UUID(runnable_task["task"]["task_id"]), provider=provider
    )

    assert result.action.value == "COMPLETE"
    assert result.tool_call_count == 0
    assert result.tool_results == []


def test_tool_execution_records_failure_for_missing_file_without_failing_workflow(
    db_session, runnable_task
):
    """A plan referencing a nonexistent file should record a failed
    read_file attempt but NOT fail the overall workflow — a read-only
    observation gap is not a workflow-breaking error."""
    from app.agent.service import run_agent_workflow
    from app.api.deps import get_current_user
    from app.llm.fake_provider import FakeLLMProvider

    user = get_current_user(db_session, None)
    provider = FakeLLMProvider(responses=[VALID_JSON_PROPOSE_MISSING_FILE])

    result = run_agent_workflow(
        db_session, user=user, task_id=uuid.UUID(runnable_task["task"]["task_id"]), provider=provider
    )

    assert result.status.value == "COMPLETED"
    assert result.tool_call_count == 1
    assert result.tool_results[0]["success"] is False


def test_tool_execution_respects_agent_max_tool_calls(db_session, runnable_task, monkeypatch):
    from app.core import config as config_module
    from app.agent.service import run_agent_workflow
    from app.api.deps import get_current_user
    from app.llm.fake_provider import FakeLLMProvider

    settings = config_module.get_settings()
    monkeypatch.setattr(settings, "AGENT_MAX_TOOL_CALLS", 0)

    user = get_current_user(db_session, None)
    provider = FakeLLMProvider(responses=[VALID_JSON_PROPOSE])

    result = run_agent_workflow(
        db_session, user=user, task_id=uuid.UUID(runnable_task["task"]["task_id"]), provider=provider
    )

    assert result.tool_call_count == 0
    assert result.tool_results == []


def test_tool_execution_persists_tool_invocation_row(db_session, runnable_task):
    from app.agent.service import run_agent_workflow
    from app.api.deps import get_current_user
    from app.llm.fake_provider import FakeLLMProvider
    from app.models.tool_invocation import ToolInvocation

    user = get_current_user(db_session, None)
    provider = FakeLLMProvider(responses=[VALID_JSON_PROPOSE])
    task_id = uuid.UUID(runnable_task["task"]["task_id"])

    run_agent_workflow(db_session, user=user, task_id=task_id, provider=provider)

    rows = db_session.query(ToolInvocation).filter(ToolInvocation.task_id == task_id).all()
    assert len(rows) == 1
    assert rows[0].tool_name == "read_file"
    assert rows[0].status.value == "SUCCESS"


def test_agent_execution_persists_tool_results_summary(db_session, runnable_task):
    from app.agent.service import run_agent_workflow
    from app.api.deps import get_current_user
    from app.llm.fake_provider import FakeLLMProvider
    from app.models.agent_execution import AgentExecution

    user = get_current_user(db_session, None)
    provider = FakeLLMProvider(responses=[VALID_JSON_PROPOSE])

    result = run_agent_workflow(
        db_session, user=user, task_id=uuid.UUID(runnable_task["task"]["task_id"]), provider=provider
    )

    row = db_session.get(AgentExecution, result.execution_id)
    assert row.tool_call_count == 1
    assert row.tool_results is not None
