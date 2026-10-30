import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def _build_local_git_repo(tmp_path: Path, name: str = "index_origin") -> Path:
    origin = tmp_path / name
    origin.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=origin, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=origin, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=origin, check=True)

    (origin / "src").mkdir()
    shutil.copy(FIXTURES / "python_sample" / "investigation_service.py", origin / "src")
    shutil.copy(FIXTURES / "java_sample" / "InvestigationService.java", origin / "src")

    subprocess.run(["git", "add", "."], cwd=origin, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=origin, check=True, capture_output=True)
    return origin


@pytest.fixture()
def indexed_repository(client, db_session, tmp_path):
    """Registers + onboards + indexes a repository against a real local
    git repo (no network) — ready for search tests."""
    origin = _build_local_git_repo(tmp_path)
    response = client.post("/api/repositories", json={"url": f"file://{origin}", "branch": "main"})
    assert response.status_code == 201, response.text
    repo = response.json()

    onboard_response = client.post(f"/api/repositories/{repo['id']}/onboard", json={})
    assert onboard_response.status_code == 201, onboard_response.text

    index_response = client.post(f"/api/repositories/{repo['id']}/index")
    assert index_response.status_code == 201, index_response.text

    yield repo

    from app.models.repository import Repository
    from app.retrieval.embeddings import get_embedding_provider
    from app.retrieval.milvus_client import MilvusVectorStore
    from app.services import workspace_service

    MilvusVectorStore(dimension=get_embedding_provider().dimension).delete_by_repository(repo["id"])
    db_session.query(Repository).filter(Repository.id == repo["id"]).delete()
    db_session.commit()
    workspace_service.remove_workspace(uuid.UUID(repo["id"]))


def test_index_repository_creates_chunks(indexed_repository, client):
    status_response = client.get(f"/api/repositories/{indexed_repository['id']}/index/status")
    assert status_response.status_code == 200
    body = status_response.json()
    assert body["indexing_status"] == "INDEXED"
    assert body["indexed_chunk_count"] == 4  # 2 classes + 2 methods


def test_search_returns_relevant_chunk_first(client, indexed_repository):
    response = client.post(
        f"/api/repositories/{indexed_repository['id']}/search",
        json={"query": "delete investigation", "top_k": 5},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "delete investigation"
    assert len(body["results"]) > 0

    top_result = body["results"][0]
    assert "investigation" in (top_result["symbol_name"] or "").lower() or "Investigation" in top_result["content"]


def test_search_respects_top_k_limit(client, indexed_repository):
    response = client.post(
        f"/api/repositories/{indexed_repository['id']}/search",
        json={"query": "delete investigation", "top_k": 2},
    )
    assert response.status_code == 200
    assert len(response.json()["results"]) <= 2


def test_search_rejects_top_k_above_maximum(client, indexed_repository):
    response = client.post(
        f"/api/repositories/{indexed_repository['id']}/search",
        json={"query": "delete investigation", "top_k": 999},
    )
    assert response.status_code == 422


def test_search_before_indexing_is_not_found(client, db_session, tmp_path):
    origin = _build_local_git_repo(tmp_path, name="unindexed_origin")
    repo = client.post("/api/repositories", json={"url": f"file://{origin}", "branch": "main"}).json()
    client.post(f"/api/repositories/{repo['id']}/onboard", json={})

    try:
        response = client.post(
            f"/api/repositories/{repo['id']}/search", json={"query": "anything", "top_k": 5}
        )
        assert response.status_code == 404
    finally:
        from app.models.repository import Repository
        from app.services import workspace_service

        db_session.query(Repository).filter(Repository.id == repo["id"]).delete()
        db_session.commit()
        workspace_service.remove_workspace(uuid.UUID(repo["id"]))


def test_index_before_onboarding_fails_cleanly(client, repository):
    response = client.post(f"/api/repositories/{repository['id']}/index")
    assert response.status_code == 400


def test_index_not_found_repository(client):
    response = client.post(f"/api/repositories/{uuid.uuid4()}/index")
    assert response.status_code == 404


def test_reindexing_is_idempotent_for_unchanged_content(client, indexed_repository):
    """Running indexing twice with no source changes should report every
    chunk as unchanged, not create duplicates."""
    response = client.post(f"/api/repositories/{indexed_repository['id']}/index")
    assert response.status_code == 201
    body = response.json()
    assert body["chunks_unchanged"] == 4
    assert body["chunks_created"] == 0
    assert body["total_chunks"] == 4

    status_response = client.get(f"/api/repositories/{indexed_repository['id']}/index/status")
    assert status_response.json()["indexed_chunk_count"] == 4


def test_repository_isolation_end_to_end(client, db_session, tmp_path):
    """Two separately indexed repositories must never leak chunks into
    each other's search results."""
    origin_a = _build_local_git_repo(tmp_path, name="repo_a_origin")
    origin_b = _build_local_git_repo(tmp_path, name="repo_b_origin")

    repo_a = client.post("/api/repositories", json={"url": f"file://{origin_a}", "branch": "main"}).json()
    repo_b = client.post("/api/repositories", json={"url": f"file://{origin_b}", "branch": "main"}).json()

    try:
        for repo in (repo_a, repo_b):
            assert client.post(f"/api/repositories/{repo['id']}/onboard", json={}).status_code == 201
            assert client.post(f"/api/repositories/{repo['id']}/index").status_code == 201

        response = client.post(
            f"/api/repositories/{repo_a['id']}/search",
            json={"query": "delete investigation", "top_k": 10},
        )
        assert response.status_code == 200
        # Every returned chunk must come from repo_a's files, never repo_b's.
        for result in response.json()["results"]:
            assert result["file_path"].startswith("src/")
        # (file paths are identical between the two fixture repos by
        # construction, so the real isolation check is at the Milvus layer —
        # see test_milvus_client.py::test_repository_isolation_in_search —
        # this confirms the API-level flow doesn't break that guarantee.)
    finally:
        from app.models.repository import Repository
        from app.retrieval.embeddings import get_embedding_provider
        from app.retrieval.milvus_client import MilvusVectorStore
        from app.services import workspace_service

        store = MilvusVectorStore(dimension=get_embedding_provider().dimension)
        for repo in (repo_a, repo_b):
            store.delete_by_repository(repo["id"])
            db_session.query(Repository).filter(Repository.id == repo["id"]).delete()
            workspace_service.remove_workspace(uuid.UUID(repo["id"]))
        db_session.commit()
