# Test-only settings: use the isolated test database.
import os

os.environ["POSTGRES_HOST"] = "localhost"
os.environ["POSTGRES_PORT"] = "15432"
os.environ["POSTGRES_DB"] = "ai_swe_agent_test"
os.environ.pop("DATABASE_URL", None)

# Compatibility for legacy tests without JWT headers.
os.environ["AUTH_ALLOW_DEV_USER_FALLBACK"] = "true"
import pytest
from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def repository(client: TestClient, db_session):
    """Creates a repository via the real API and deletes it (cascades to
    tasks/artifacts) after the test, keeping the dev database tidy."""
    response = client.post(
        "/api/repositories",
        json={"url": "https://github.com/example/milestone2-fixture-repo", "branch": "main"},
    )
    assert response.status_code == 201, response.text
    body = response.json()

    yield body

    from app.models.repository import Repository

    db_session.query(Repository).filter(Repository.id == body["id"]).delete()
    db_session.commit()
