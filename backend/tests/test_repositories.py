import uuid


def test_create_repository_derives_name_from_url(client, db_session):
    response = client.post(
        "/api/repositories",
        json={"url": "https://github.com/example/my-cool-project", "branch": "develop"},
    )
    assert response.status_code == 201, response.text
    body = response.json()

    try:
        assert body["name"] == "my-cool-project"
        assert body["default_branch"] == "develop"
        assert body["status"] == "PENDING"
        assert body["workspace_path"] is None
        assert "id" in body and "user_id" in body
    finally:
        from app.models.repository import Repository

        db_session.query(Repository).filter(Repository.id == body["id"]).delete()
        db_session.commit()


def test_create_repository_defaults_branch_to_main(client, db_session):
    response = client.post(
        "/api/repositories",
        json={"url": "https://github.com/example/no-branch-specified"},
    )
    assert response.status_code == 201, response.text
    body = response.json()

    try:
        assert body["default_branch"] == "main"
    finally:
        from app.models.repository import Repository

        db_session.query(Repository).filter(Repository.id == body["id"]).delete()
        db_session.commit()


def test_create_repository_rejects_invalid_url(client):
    response = client.post("/api/repositories", json={"url": "not-a-valid-url"})
    assert response.status_code == 422


def test_get_repository(client, repository):
    response = client.get(f"/api/repositories/{repository['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == repository["id"]


def test_get_repository_not_found(client):
    response = client.get(f"/api/repositories/{uuid.uuid4()}")
    assert response.status_code == 404


def test_list_repositories_includes_created_repository(client, repository):
    response = client.get("/api/repositories")
    assert response.status_code == 200
    ids = [r["id"] for r in response.json()]
    assert repository["id"] in ids
