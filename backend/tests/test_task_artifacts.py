import uuid


def _create_task(client, repository_id: str, request: str = "Artifact test task."):
    return client.post(
        "/api/tasks",
        json={"repository_id": repository_id, "request": request},
    ).json()


def test_create_task_artifact(client, repository):
    task = _create_task(client, repository["id"])

    response = client.post(
        f"/api/tasks/{task['task_id']}/artifacts",
        json={
            "file_path": "src/investigations/InvestigationPage.tsx",
            "artifact_type": "SOURCE_FILE",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["task_id"] == task["task_id"]
    assert body["file_path"] == "src/investigations/InvestigationPage.tsx"
    assert body["artifact_type"] == "SOURCE_FILE"


def test_create_task_artifact_defaults_type_to_other(client, repository):
    task = _create_task(client, repository["id"])

    response = client.post(
        f"/api/tasks/{task['task_id']}/artifacts",
        json={"file_path": "README.md"},
    )
    assert response.status_code == 201
    assert response.json()["artifact_type"] == "OTHER"


def test_create_task_artifact_rejects_empty_file_path(client, repository):
    task = _create_task(client, repository["id"])

    response = client.post(
        f"/api/tasks/{task['task_id']}/artifacts",
        json={"file_path": "   "},
    )
    assert response.status_code == 422


def test_create_task_artifact_rejects_absolute_path(client, repository):
    task = _create_task(client, repository["id"])

    response = client.post(
        f"/api/tasks/{task['task_id']}/artifacts",
        json={"file_path": "/etc/passwd"},
    )
    assert response.status_code == 422


def test_create_task_artifact_rejects_nonexistent_task(client):
    response = client.post(
        f"/api/tasks/{uuid.uuid4()}/artifacts",
        json={"file_path": "src/foo.py"},
    )
    assert response.status_code == 404


def test_list_task_artifacts(client, repository):
    task = _create_task(client, repository["id"])
    client.post(
        f"/api/tasks/{task['task_id']}/artifacts",
        json={"file_path": "src/a.py"},
    )
    client.post(
        f"/api/tasks/{task['task_id']}/artifacts",
        json={"file_path": "src/b.py"},
    )

    response = client.get(f"/api/tasks/{task['task_id']}/artifacts")
    assert response.status_code == 200
    paths = {a["file_path"] for a in response.json()}
    assert {"src/a.py", "src/b.py"}.issubset(paths)


def test_list_task_artifacts_for_nonexistent_task(client):
    response = client.get(f"/api/tasks/{uuid.uuid4()}/artifacts")
    assert response.status_code == 404


def test_artifact_deleted_when_task_deleted_cascade(client, repository, db_session):
    """Verifies FK cascade: deleting a task deletes its artifacts (no orphans)."""
    task = _create_task(client, repository["id"])
    client.post(
        f"/api/tasks/{task['task_id']}/artifacts",
        json={"file_path": "src/cascade_test.py"},
    )

    from app.models.task import Task
    from app.models.task_artifact import TaskArtifact

    task_id = uuid.UUID(task["task_id"])
    assert db_session.query(TaskArtifact).filter(TaskArtifact.task_id == task_id).count() == 1

    db_session.query(Task).filter(Task.id == task_id).delete()
    db_session.commit()

    assert db_session.query(TaskArtifact).filter(TaskArtifact.task_id == task_id).count() == 0
