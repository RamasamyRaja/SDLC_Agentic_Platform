import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def _build_local_git_repo(tmp_path: Path, name: str = "node_origin") -> Path:
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
def onboarded_repo_and_task(client, db_session, tmp_path):
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


def _config(db, user, provider=None):
    return {"configurable": {"db": db, "user": user, "provider": provider}}


def test_load_task_node_populates_state(onboarded_repo_and_task, db_session):
    from app.agent.nodes import load_task_node
    from app.api.deps import get_current_user

    user = get_current_user(db_session, None)
    state = {"task_id": onboarded_repo_and_task["task"]["task_id"], "errors": []}

    result = load_task_node(state, _config(db_session, user))

    assert result["stage"] == "LOAD_TASK"
    assert result["status"] == "RUNNING"
    assert result["repository_id"] == onboarded_repo_and_task["repo"]["id"]
    assert result["task_description"] == "Delete an investigation"


def test_load_task_node_fails_cleanly_for_nonexistent_task(db_session):
    from app.agent.nodes import load_task_node
    from app.api.deps import get_current_user

    user = get_current_user(db_session, None)
    state = {"task_id": str(uuid.uuid4()), "errors": []}

    result = load_task_node(state, _config(db_session, user))

    assert result["status"] == "FAILED"
    assert result["error_type"] == "NotFoundError"
    assert len(result["errors"]) == 1


def test_build_context_node_surfaces_indexing_status(onboarded_repo_and_task, db_session):
    from app.agent.nodes import build_context_node
    from app.api.deps import get_current_user

    user = get_current_user(db_session, None)
    state = {"repository_id": onboarded_repo_and_task["repo"]["id"], "errors": []}

    result = build_context_node(state, _config(db_session, user))

    assert result["stage"] == "BUILD_CONTEXT"
    assert result["indexing_status"] == "INDEXED"


def test_reason_node_persists_and_returns_result(onboarded_repo_and_task, db_session):
    from app.agent.nodes import reason_node
    from app.api.deps import get_current_user
    from app.llm.fake_provider import FakeLLMProvider
    from app.models.task_analysis import TaskAnalysis

    valid_json = """{
      "summary": "test", "understanding": {"goal": "g", "affected_area": "a"},
      "relevant_files": [], "affected_symbols": [], "implementation_plan": [],
      "dependencies": [], "risks": [], "uncertainties": [], "confidence": 0.9
    }"""
    provider = FakeLLMProvider(responses=[valid_json])
    user = get_current_user(db_session, None)
    state = {"task_id": onboarded_repo_and_task["task"]["task_id"], "errors": []}

    result = reason_node(state, _config(db_session, user, provider))

    assert result["stage"] == "REASON"
    assert result["reasoning_result"]["confidence"] == 0.9

    task_id = uuid.UUID(onboarded_repo_and_task["task"]["task_id"])
    row = db_session.query(TaskAnalysis).filter(TaskAnalysis.task_id == task_id).one()
    assert row.result is not None


def test_reason_node_fails_cleanly_on_provider_error(onboarded_repo_and_task, db_session):
    from app.agent.nodes import reason_node
    from app.api.deps import get_current_user
    from app.llm.fake_provider import FakeLLMProvider
    from app.llm.provider import LLMProviderError

    provider = FakeLLMProvider(error=LLMProviderError("simulated outage"))
    user = get_current_user(db_session, None)
    state = {"task_id": onboarded_repo_and_task["task"]["task_id"], "errors": []}

    result = reason_node(state, _config(db_session, user, provider))

    assert result["status"] == "FAILED"
    assert result["error_type"] == "LLMUnavailableError"


def test_validate_reasoning_node_passes_for_valid_result():
    from app.agent.nodes import validate_reasoning_node

    state = {
        "reasoning_result": {
            "summary": "s", "understanding": {"goal": "g", "affected_area": "a"},
            "relevant_files": [], "affected_symbols": [], "implementation_plan": [],
            "dependencies": [], "risks": [], "uncertainties": [], "confidence": 0.8,
        },
        "errors": [],
    }
    result = validate_reasoning_node(state)
    assert result["stage"] == "VALIDATE_REASONING"
    assert "status" not in result or result.get("status") != "FAILED"


def test_validate_reasoning_node_fails_when_result_missing():
    from app.agent.nodes import validate_reasoning_node

    result = validate_reasoning_node({"reasoning_result": None, "errors": []})
    assert result["status"] == "FAILED"


def test_decide_action_node_proposes_change_for_high_confidence_grounded_plan():
    from app.agent.nodes import decide_action_node

    state = {
        "reasoning_result": {
            "summary": "s", "understanding": {"goal": "g", "affected_area": "a"},
            "relevant_files": [{"file_path": "a.py", "reason": "r", "confidence": 0.9, "grounded": True}],
            "affected_symbols": [],
            "implementation_plan": [{"step": 1, "description": "do it", "target_files": ["a.py"]}],
            "dependencies": [], "risks": [], "uncertainties": [], "confidence": 0.9,
        },
        "errors": [],
    }
    result = decide_action_node(state)
    assert result["action"] == "PROPOSE_CHANGE"


def test_decide_action_node_requests_approval_for_low_confidence():
    from app.agent.nodes import decide_action_node

    state = {
        "reasoning_result": {
            "summary": "s", "understanding": {"goal": "g", "affected_area": "a"},
            "relevant_files": [], "affected_symbols": [],
            "implementation_plan": [{"step": 1, "description": "do it", "target_files": []}],
            "dependencies": [], "risks": [], "uncertainties": [], "confidence": 0.2,
        },
        "errors": [],
    }
    result = decide_action_node(state)
    assert result["action"] == "REQUEST_APPROVAL"


def test_decide_action_node_requests_approval_for_ungrounded_reference():
    from app.agent.nodes import decide_action_node

    state = {
        "reasoning_result": {
            "summary": "s", "understanding": {"goal": "g", "affected_area": "a"},
            "relevant_files": [{"file_path": "fake.py", "reason": "r", "confidence": 0.9, "grounded": False}],
            "affected_symbols": [],
            "implementation_plan": [{"step": 1, "description": "do it", "target_files": []}],
            "dependencies": [], "risks": [], "uncertainties": [], "confidence": 0.9,
        },
        "errors": [],
    }
    result = decide_action_node(state)
    assert result["action"] == "REQUEST_APPROVAL"


def test_decide_action_node_completes_when_no_plan():
    from app.agent.nodes import decide_action_node

    state = {
        "reasoning_result": {
            "summary": "s", "understanding": {"goal": "g", "affected_area": "a"},
            "relevant_files": [], "affected_symbols": [], "implementation_plan": [],
            "dependencies": [], "risks": [], "uncertainties": [], "confidence": 0.9,
        },
        "errors": [],
    }
    result = decide_action_node(state)
    assert result["action"] == "COMPLETE"


def test_finalize_node_sets_completed_when_not_failed():
    from app.agent.nodes import finalize_node

    result = finalize_node({"status": "RUNNING", "errors": []})
    assert result["status"] == "COMPLETED"


def test_finalize_node_preserves_failed_status():
    from app.agent.nodes import finalize_node

    result = finalize_node({"status": "FAILED", "errors": ["boom"]})
    assert result["status"] == "FAILED"
