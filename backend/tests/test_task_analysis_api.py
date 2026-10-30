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
  "dependencies": [],
  "risks": [],
  "uncertainties": [],
  "confidence": 0.85
}"""


def _build_local_git_repo(tmp_path: Path, name: str = "analyze_origin") -> Path:
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
def analyzable_task(client, db_session, tmp_path):
    """A fully onboarded + indexed repository with a task ready to analyze."""
    origin = _build_local_git_repo(tmp_path)
    repo = client.post("/api/repositories", json={"url": f"file://{origin}", "branch": "main"}).json()
    assert client.post(f"/api/repositories/{repo['id']}/onboard", json={}).status_code == 201
    assert client.post(f"/api/repositories/{repo['id']}/index").status_code == 201

    task = client.post(
        "/api/tasks",
        json={"repository_id": repo["id"], "request": "Add a delete button to the Investigations page."},
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


def test_analyze_task_returns_validated_structured_result(client, analyzable_task, monkeypatch):
    _patch_fake_provider(monkeypatch, responses=[VALID_JSON], model="fake-mistral")

    response = client.post(f"/api/tasks/{analyzable_task['task']['task_id']}/analyze")
    assert response.status_code == 201, response.text
    body = response.json()

    assert body["model"] == "fake-mistral"
    assert body["prompt_version"] == "v1"
    assert body["result"]["summary"].startswith("Add a delete button")
    assert body["result"]["confidence"] == 0.85
    # Grounding must have run: the referenced file is real, so grounded=True.
    assert body["result"]["relevant_files"][0]["grounded"] is True


def test_analyze_task_persists_task_analysis_row(client, db_session, analyzable_task, monkeypatch):
    _patch_fake_provider(monkeypatch, responses=[VALID_JSON])

    response = client.post(f"/api/tasks/{analyzable_task['task']['task_id']}/analyze")
    assert response.status_code == 201

    from app.models.task_analysis import TaskAnalysis, TaskAnalysisStatus

    task_id = uuid.UUID(analyzable_task["task"]["task_id"])
    row = db_session.query(TaskAnalysis).filter(TaskAnalysis.task_id == task_id).one()
    assert row.status == TaskAnalysisStatus.COMPLETED
    assert row.result is not None
    assert row.prompt_version == "v1"


def test_analyze_task_flags_hallucinated_file_reference(client, analyzable_task, monkeypatch):
    hallucinated = VALID_JSON.replace("src/investigation_service.py", "src/totally_made_up_file.py")
    _patch_fake_provider(monkeypatch, responses=[hallucinated])

    response = client.post(f"/api/tasks/{analyzable_task['task']['task_id']}/analyze")
    assert response.status_code == 201
    body = response.json()
    assert body["result"]["relevant_files"][0]["grounded"] is False


def test_analyze_task_returns_502_on_provider_failure(client, analyzable_task, monkeypatch):
    from app.llm.provider import LLMProviderError

    _patch_fake_provider(monkeypatch, error=LLMProviderError("simulated outage"))

    response = client.post(f"/api/tasks/{analyzable_task['task']['task_id']}/analyze")
    assert response.status_code == 502


def test_analyze_task_persists_failed_analysis_on_provider_failure(
    client, db_session, analyzable_task, monkeypatch
):
    from app.llm.provider import LLMProviderError

    _patch_fake_provider(monkeypatch, error=LLMProviderError("simulated outage"))

    client.post(f"/api/tasks/{analyzable_task['task']['task_id']}/analyze")

    from app.models.task_analysis import TaskAnalysis, TaskAnalysisStatus

    task_id = uuid.UUID(analyzable_task["task"]["task_id"])
    row = db_session.query(TaskAnalysis).filter(TaskAnalysis.task_id == task_id).one()
    assert row.status == TaskAnalysisStatus.FAILED
    assert row.error is not None


def test_analyze_task_returns_502_after_exhausting_retries(client, analyzable_task, monkeypatch):
    _patch_fake_provider(monkeypatch, responses=["bad", "still bad", "nope"])

    response = client.post(f"/api/tasks/{analyzable_task['task']['task_id']}/analyze")
    assert response.status_code == 502


def test_analyze_task_not_found(client, monkeypatch):
    _patch_fake_provider(monkeypatch, responses=[VALID_JSON])
    response = client.post(f"/api/tasks/{uuid.uuid4()}/analyze")
    assert response.status_code == 404


def test_analyze_task_never_exposes_raw_provider_response_directly(client, analyzable_task, monkeypatch):
    """The API response must be the validated schema, not raw provider text."""
    _patch_fake_provider(monkeypatch, responses=[VALID_JSON])
    response = client.post(f"/api/tasks/{analyzable_task['task']['task_id']}/analyze")
    body = response.json()
    assert set(body.keys()) == {"task_id", "model", "prompt_version", "result"}
