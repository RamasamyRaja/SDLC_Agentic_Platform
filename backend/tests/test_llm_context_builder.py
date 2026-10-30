import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def _build_local_git_repo(tmp_path: Path, name: str = "ctx_origin") -> Path:
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
def indexed_repository_for_context(client, db_session, tmp_path):
    origin = _build_local_git_repo(tmp_path)
    repo = client.post("/api/repositories", json={"url": f"file://{origin}", "branch": "main"}).json()
    assert client.post(f"/api/repositories/{repo['id']}/onboard", json={}).status_code == 201
    assert client.post(f"/api/repositories/{repo['id']}/index").status_code == 201

    yield repo

    from app.models.repository import Repository
    from app.retrieval.embeddings import get_embedding_provider
    from app.retrieval.milvus_client import MilvusVectorStore
    from app.services import workspace_service

    MilvusVectorStore(dimension=get_embedding_provider().dimension).delete_by_repository(repo["id"])
    db_session.query(Repository).filter(Repository.id == repo["id"]).delete()
    db_session.commit()
    workspace_service.remove_workspace(uuid.UUID(repo["id"]))


def test_context_builder_combines_structural_and_retrieved_context(
    client, db_session, indexed_repository_for_context
):
    from app.llm.context_builder import build_reasoning_input
    from app.models.task import Task
    from app.services.repository_service import get_repository
    from app.services.task_service import create_task
    from app.schemas.task import TaskCreate
    from app.api.deps import get_current_user
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        user = get_current_user(db, None)
        repository = get_repository(db, user=user, repository_id=uuid.UUID(indexed_repository_for_context["id"]))
        task = create_task(
            db, user=user,
            payload=TaskCreate(repository_id=repository.id, request="Delete an investigation"),
        )

        context = build_reasoning_input(db, user=user, task=task, repository=repository)

        assert context.task.id == str(task.id)
        assert context.repository.id == str(repository.id)
        # Structural context comes from M3 (via M4's CodeChunk index).
        assert len(context.structural_context) > 0
        # Semantic context comes from M4 retrieval.
        assert len(context.retrieved_context) > 0
        # Source metadata (file paths) must be preserved, not stripped.
        assert all(s.file_path for s in context.structural_context)
        assert all(c.file_path for c in context.retrieved_context)
    finally:
        db.query(Task).filter(Task.repository_id == uuid.UUID(indexed_repository_for_context["id"])).delete()
        db.commit()
        db.close()


def test_context_builder_enforces_retrieved_chunk_limit(
    client, db_session, indexed_repository_for_context, monkeypatch
):
    from app.core import config as config_module
    from app.llm.context_builder import build_reasoning_input
    from app.models.task import Task
    from app.services.repository_service import get_repository
    from app.services.task_service import create_task
    from app.schemas.task import TaskCreate
    from app.api.deps import get_current_user
    from app.db.session import SessionLocal

    settings = config_module.get_settings()
    monkeypatch.setattr(settings, "LLM_MAX_RETRIEVED_CHUNKS", 1)

    db = SessionLocal()
    try:
        user = get_current_user(db, None)
        repository = get_repository(db, user=user, repository_id=uuid.UUID(indexed_repository_for_context["id"]))
        task = create_task(
            db, user=user,
            payload=TaskCreate(repository_id=repository.id, request="Delete an investigation"),
        )
        context = build_reasoning_input(db, user=user, task=task, repository=repository)
        assert len(context.retrieved_context) <= 1
    finally:
        db.query(Task).filter(Task.repository_id == uuid.UUID(indexed_repository_for_context["id"])).delete()
        db.commit()
        db.close()


def test_context_builder_enforces_structural_symbol_limit(
    client, db_session, indexed_repository_for_context, monkeypatch
):
    from app.core import config as config_module
    from app.llm.context_builder import build_reasoning_input
    from app.models.task import Task
    from app.services.repository_service import get_repository
    from app.services.task_service import create_task
    from app.schemas.task import TaskCreate
    from app.api.deps import get_current_user
    from app.db.session import SessionLocal

    settings = config_module.get_settings()
    monkeypatch.setattr(settings, "LLM_MAX_STRUCTURAL_SYMBOLS", 1)

    db = SessionLocal()
    try:
        user = get_current_user(db, None)
        repository = get_repository(db, user=user, repository_id=uuid.UUID(indexed_repository_for_context["id"]))
        task = create_task(
            db, user=user,
            payload=TaskCreate(repository_id=repository.id, request="Delete an investigation"),
        )
        context = build_reasoning_input(db, user=user, task=task, repository=repository)
        assert len(context.structural_context) <= 1
    finally:
        db.query(Task).filter(Task.repository_id == uuid.UUID(indexed_repository_for_context["id"])).delete()
        db.commit()
        db.close()


def test_context_builder_handles_unindexed_repository_gracefully(client, db_session, repository):
    """A repository with no index yet should produce empty retrieved_context
    rather than raising — reasoning can still proceed on structural context
    alone (or note the uncertainty in the model's own output)."""
    from app.llm.context_builder import build_reasoning_input
    from app.models.task import Task
    from app.services.repository_service import get_repository
    from app.services.task_service import create_task
    from app.schemas.task import TaskCreate
    from app.api.deps import get_current_user
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        user = get_current_user(db, None)
        repo_obj = get_repository(db, user=user, repository_id=uuid.UUID(repository["id"]))
        task = create_task(
            db, user=user,
            payload=TaskCreate(repository_id=repo_obj.id, request="Some request"),
        )
        context = build_reasoning_input(db, user=user, task=task, repository=repo_obj)
        assert context.retrieved_context == []
    finally:
        db.query(Task).filter(Task.repository_id == uuid.UUID(repository["id"])).delete()
        db.commit()
        db.close()
