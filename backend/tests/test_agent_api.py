import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"

VALID_JSON = """{
  "summary": "Add a delete button to the Investigations page.",
  "understanding": {"goal": "Delete investigations", "affected_area": "UI"},
  "relevant_files": [{"file_path": "src/investigation_service.py", "reason": "core logic", "confidence": 0.9}],
  "affected_symbols": [],
  "implementation_plan": [{"step": 1, "description": "Add a button", "target_files": ["src/investigation_service.py"]}],
  "dependencies": [], "risks": [], "uncertainties": [], "confidence": 0.9
}"""


def _build_local_git_repo(tmp_path: Path, name: str = "api_agent_origin") -> Path:
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
def runnable_task_api(client, db_session, tmp_path):
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


def _patch_fake_provider(monkeypatch, **kwargs):
    from app.llm.fake_provider import FakeLLMProvider

    fake = FakeLLMProvider(**kwargs)
    monkeypatch.setattr("app.llm.service.get_mistral_provider", lambda: fake)
    return fake


def test_run_endpoint_returns_structured_result(client, runnable_task_api, monkeypatch):
    _patch_fake_provider(monkeypatch, responses=[VALID_JSON], model="fake-mistral")

    response = client.post(f"/api/tasks/{runnable_task_api['task']['task_id']}/run")
    assert response.status_code == 201, response.text
    body = response.json()

    assert body["status"] == "COMPLETED"
    assert body["action"] == "PROPOSE_CHANGE"
    assert body["model_name"] == "fake-mistral"
    assert "execution_id" in body


def test_run_endpoint_never_exposes_raw_exception_details(client, runnable_task_api, monkeypatch):
    from app.llm.provider import LLMProviderError

    _patch_fake_provider(monkeypatch, error=LLMProviderError("simulated outage with sensitive detail"))

    response = client.post(f"/api/tasks/{runnable_task_api['task']['task_id']}/run")
    assert response.status_code == 502
    body = response.json()
    assert "traceback" not in str(body).lower()


def test_run_endpoint_not_found_for_unknown_task(client, monkeypatch):
    _patch_fake_provider(monkeypatch, responses=[VALID_JSON])
    response = client.post(f"/api/tasks/{uuid.uuid4()}/run")
    assert response.status_code == 404


def test_get_execution_status_endpoint(client, runnable_task_api, monkeypatch):
    _patch_fake_provider(monkeypatch, responses=[VALID_JSON])

    run_response = client.post(f"/api/tasks/{runnable_task_api['task']['task_id']}/run")
    execution_id = run_response.json()["execution_id"]

    response = client.get(f"/api/tasks/{runnable_task_api['task']['task_id']}/run/{execution_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == execution_id
    assert body["status"] == "COMPLETED"
    assert body["action"] == "PROPOSE_CHANGE"


def test_get_execution_status_not_found_for_unknown_execution(client, runnable_task_api):
    response = client.get(f"/api/tasks/{runnable_task_api['task']['task_id']}/run/{uuid.uuid4()}")
    assert response.status_code == 404


def test_run_endpoint_result_is_grounded(client, runnable_task_api, monkeypatch):
    _patch_fake_provider(monkeypatch, responses=[VALID_JSON])
    response = client.post(f"/api/tasks/{runnable_task_api['task']['task_id']}/run")
    body = response.json()
    assert body["reasoning_result"]["relevant_files"][0]["grounded"] is True
