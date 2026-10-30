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

VALID_JSON_LOW_CONFIDENCE = """{
  "summary": "Not fully sure what to do here.",
  "understanding": {"goal": "Delete investigations", "affected_area": "UI"},
  "relevant_files": [], "affected_symbols": [],
  "implementation_plan": [{"step": 1, "description": "Maybe do this", "target_files": []}],
  "dependencies": [], "risks": [], "uncertainties": ["Not sure this is the right file"], "confidence": 0.1
}"""

VALID_JSON_NO_PLAN = """{
  "summary": "Nothing to change.",
  "understanding": {"goal": "Investigate", "affected_area": "none"},
  "relevant_files": [], "affected_symbols": [], "implementation_plan": [],
  "dependencies": [], "risks": [], "uncertainties": [], "confidence": 0.9
}"""


def _build_local_git_repo(tmp_path: Path, name: str = "svc_origin") -> Path:
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


def test_run_agent_workflow_proposes_change_for_high_confidence_grounded_plan(
    db_session, runnable_task
):
    from app.agent.models import AgentAction, AgentExecutionStatus
    from app.agent.service import run_agent_workflow
    from app.api.deps import get_current_user
    from app.llm.fake_provider import FakeLLMProvider

    user = get_current_user(db_session, None)
    provider = FakeLLMProvider(responses=[VALID_JSON_PROPOSE], model="fake-mistral")

    result = run_agent_workflow(
        db_session, user=user, task_id=uuid.UUID(runnable_task["task"]["task_id"]), provider=provider
    )

    assert result.status == AgentExecutionStatus.COMPLETED
    assert result.action == AgentAction.PROPOSE_CHANGE
    assert result.model_name == "fake-mistral"
    assert result.reasoning_result.relevant_files[0].grounded is True


def test_run_agent_workflow_requests_approval_for_low_confidence(db_session, runnable_task):
    from app.agent.models import AgentAction
    from app.agent.service import run_agent_workflow
    from app.api.deps import get_current_user
    from app.llm.fake_provider import FakeLLMProvider

    user = get_current_user(db_session, None)
    provider = FakeLLMProvider(responses=[VALID_JSON_LOW_CONFIDENCE])

    result = run_agent_workflow(
        db_session, user=user, task_id=uuid.UUID(runnable_task["task"]["task_id"]), provider=provider
    )
    assert result.action == AgentAction.REQUEST_APPROVAL


def test_run_agent_workflow_completes_when_nothing_to_propose(db_session, runnable_task):
    from app.agent.models import AgentAction
    from app.agent.service import run_agent_workflow
    from app.api.deps import get_current_user
    from app.llm.fake_provider import FakeLLMProvider

    user = get_current_user(db_session, None)
    provider = FakeLLMProvider(responses=[VALID_JSON_NO_PLAN])

    result = run_agent_workflow(
        db_session, user=user, task_id=uuid.UUID(runnable_task["task"]["task_id"]), provider=provider
    )
    assert result.action == AgentAction.COMPLETE


def test_run_agent_workflow_persists_agent_execution(db_session, runnable_task):
    from app.agent.service import run_agent_workflow
    from app.api.deps import get_current_user
    from app.llm.fake_provider import FakeLLMProvider
    from app.models.agent_execution import AgentExecution, AgentExecutionStatus as DBStatus

    user = get_current_user(db_session, None)
    provider = FakeLLMProvider(responses=[VALID_JSON_PROPOSE])

    result = run_agent_workflow(
        db_session, user=user, task_id=uuid.UUID(runnable_task["task"]["task_id"]), provider=provider
    )

    row = db_session.get(AgentExecution, result.execution_id)
    assert row is not None
    assert row.status == DBStatus.COMPLETED
    assert row.action == "PROPOSE_CHANGE"
    assert row.result is not None


def test_run_agent_workflow_raises_not_found_for_nonexistent_task(db_session):
    from app.agent.service import run_agent_workflow
    from app.api.deps import get_current_user
    from app.core.exceptions import NotFoundError
    from app.llm.fake_provider import FakeLLMProvider

    user = get_current_user(db_session, None)
    provider = FakeLLMProvider(responses=[VALID_JSON_PROPOSE])

    with pytest.raises(NotFoundError):
        run_agent_workflow(db_session, user=user, task_id=uuid.uuid4(), provider=provider)


def test_run_agent_workflow_raises_llm_unavailable_on_provider_failure(db_session, runnable_task):
    from app.agent.service import run_agent_workflow
    from app.api.deps import get_current_user
    from app.core.exceptions import LLMUnavailableError
    from app.llm.fake_provider import FakeLLMProvider
    from app.llm.provider import LLMProviderError

    user = get_current_user(db_session, None)
    provider = FakeLLMProvider(error=LLMProviderError("simulated outage"))

    with pytest.raises(LLMUnavailableError):
        run_agent_workflow(
            db_session, user=user, task_id=uuid.UUID(runnable_task["task"]["task_id"]), provider=provider
        )


def test_run_agent_workflow_raises_output_validation_error_after_retries_exhausted(
    db_session, runnable_task
):
    from app.agent.service import run_agent_workflow
    from app.api.deps import get_current_user
    from app.core.exceptions import LLMOutputValidationError
    from app.llm.fake_provider import FakeLLMProvider

    user = get_current_user(db_session, None)
    provider = FakeLLMProvider(responses=["bad", "still bad", "nope"])

    with pytest.raises(LLMOutputValidationError):
        run_agent_workflow(
            db_session, user=user, task_id=uuid.UUID(runnable_task["task"]["task_id"]), provider=provider
        )


def test_run_agent_workflow_persists_failed_execution_on_llm_failure(db_session, runnable_task):
    from app.agent.service import run_agent_workflow
    from app.api.deps import get_current_user
    from app.core.exceptions import LLMUnavailableError
    from app.llm.fake_provider import FakeLLMProvider
    from app.llm.provider import LLMProviderError
    from app.models.agent_execution import AgentExecution, AgentExecutionStatus as DBStatus

    user = get_current_user(db_session, None)
    provider = FakeLLMProvider(error=LLMProviderError("simulated outage"))
    task_id = uuid.UUID(runnable_task["task"]["task_id"])

    with pytest.raises(LLMUnavailableError):
        run_agent_workflow(db_session, user=user, task_id=task_id, provider=provider)

    row = db_session.query(AgentExecution).filter(AgentExecution.task_id == task_id, AgentExecution.action.is_distinct_from("ARCHITECTURE_PLAN")).one()
    assert row.status == DBStatus.FAILED
    assert row.error is not None


def test_get_execution_returns_persisted_execution(db_session, runnable_task):
    from app.agent.service import get_execution, run_agent_workflow
    from app.api.deps import get_current_user
    from app.llm.fake_provider import FakeLLMProvider

    user = get_current_user(db_session, None)
    provider = FakeLLMProvider(responses=[VALID_JSON_PROPOSE])
    task_id = uuid.UUID(runnable_task["task"]["task_id"])

    result = run_agent_workflow(db_session, user=user, task_id=task_id, provider=provider)
    execution = get_execution(db_session, user=user, task_id=task_id, execution_id=result.execution_id)

    assert execution.id == result.execution_id
    assert execution.action == "PROPOSE_CHANGE"


def test_get_execution_not_found_for_unknown_execution_id(db_session, runnable_task):
    from app.agent.service import get_execution
    from app.api.deps import get_current_user
    from app.core.exceptions import NotFoundError

    user = get_current_user(db_session, None)
    task_id = uuid.UUID(runnable_task["task"]["task_id"])

    with pytest.raises(NotFoundError):
        get_execution(db_session, user=user, task_id=task_id, execution_id=uuid.uuid4())
