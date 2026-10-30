import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def _build_local_git_repo(tmp_path: Path) -> Path:
    """Creates a real local git repository (with fixture source files
    committed) that can be cloned via a file:// URL — no network required."""
    origin = tmp_path / "onboard_origin"
    origin.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=origin, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=origin, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=origin, check=True)

    (origin / "src").mkdir()
    shutil.copy(FIXTURES / "python_sample" / "investigation_service.py", origin / "src")
    shutil.copy(FIXTURES / "java_sample" / "InvestigationService.java", origin / "src")
    (origin / "node_modules").mkdir()
    (origin / "node_modules" / "ignored.js").write_text("should never be scanned")

    subprocess.run(["git", "add", "."], cwd=origin, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=origin, check=True, capture_output=True)
    return origin


@pytest.fixture()
def onboarding_repository(client, db_session, tmp_path):
    """Registers a repository pointing at a real local git repo (no network)."""
    origin = _build_local_git_repo(tmp_path)
    response = client.post(
        "/api/repositories",
        json={"url": f"file://{origin}", "branch": "main"},
    )
    assert response.status_code == 201, response.text
    body = response.json()

    yield body

    from app.models.repository import Repository
    from app.services import workspace_service

    db_session.query(Repository).filter(Repository.id == body["id"]).delete()
    db_session.commit()
    workspace_service.remove_workspace(uuid.UUID(body["id"]))


def test_onboard_repository_end_to_end(client, onboarding_repository):
    repository_id = onboarding_repository["id"]

    response = client.post(f"/api/repositories/{repository_id}/onboard", json={})
    assert response.status_code == 201, response.text
    body = response.json()

    assert body["status"] == "READY"
    assert body["commit_sha"] is not None and len(body["commit_sha"]) == 40
    assert set(body["languages"]) == {"python", "java"}
    assert body["files_analyzed"] == 2
    assert body["parse_error_count"] == 0

    class_names = {c["name"] for c in body["classes"]}
    assert "InvestigationService" in class_names


def test_onboard_repository_persists_workspace_path(client, db_session, onboarding_repository):
    repository_id = onboarding_repository["id"]
    client.post(f"/api/repositories/{repository_id}/onboard", json={})

    from app.models.repository import Repository

    repo_row = db_session.get(Repository, uuid.UUID(repository_id))
    assert repo_row.workspace_path is not None
    assert Path(repo_row.workspace_path).exists()
    assert (Path(repo_row.workspace_path) / "src").exists()


def test_get_analysis_summary_after_onboarding(client, onboarding_repository):
    repository_id = onboarding_repository["id"]
    client.post(f"/api/repositories/{repository_id}/onboard", json={})

    response = client.get(f"/api/repositories/{repository_id}/analysis")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "READY"
    assert body["files_analyzed_count"] == 2
    assert set(body["detected_languages"]) == {"python", "java"}


def test_get_analysis_summary_before_onboarding_is_not_found(client, onboarding_repository):
    repository_id = onboarding_repository["id"]
    response = client.get(f"/api/repositories/{repository_id}/analysis")
    assert response.status_code == 404


def test_get_documents_after_onboarding(client, onboarding_repository):
    repository_id = onboarding_repository["id"]
    client.post(f"/api/repositories/{repository_id}/onboard", json={})

    response = client.get(f"/api/repositories/{repository_id}/documents")
    assert response.status_code == 200
    documents = response.json()
    paths = {d["file_path"] for d in documents}
    assert paths == {"src/investigation_service.py", "src/InvestigationService.java"}
    assert all(d["analysis_status"] == "ANALYZED" for d in documents)
    assert all(d["content_hash"] for d in documents)


def test_onboard_repository_with_invalid_url_fails_cleanly(client, db_session):
    response = client.post(
        "/api/repositories",
        json={"url": "https://github.com/example/definitely-does-not-exist-repo-xyz-123", "branch": "main"},
    )
    repository_id = response.json()["id"]

    try:
        onboard_response = client.post(f"/api/repositories/{repository_id}/onboard", json={})
        assert onboard_response.status_code == 422

        analysis_response = client.get(f"/api/repositories/{repository_id}/analysis")
        # Not onboarded successfully -> still treated as "not onboarded yet"
        assert analysis_response.status_code == 404
    finally:
        from app.models.repository import Repository

        db_session.query(Repository).filter(Repository.id == repository_id).delete()
        db_session.commit()


def test_onboard_repository_not_found(client):
    response = client.post(f"/api/repositories/{uuid.uuid4()}/onboard", json={})
    assert response.status_code == 404
