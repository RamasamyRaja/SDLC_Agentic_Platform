import uuid


def test_create_task(client, repository):
    response = client.post(
        "/api/tasks",
        json={
            "repository_id": repository["id"],
            "request": "Add a delete button to the Investigations page.",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["repository_id"] == repository["id"]
    assert body["status"] == "PENDING"
    assert "task_id" in body


def test_create_task_rejects_empty_request(client, repository):
    response = client.post(
        "/api/tasks",
        json={"repository_id": repository["id"], "request": "   "},
    )
    assert response.status_code == 422


def test_create_task_rejects_nonexistent_repository(client):
    response = client.post(
        "/api/tasks",
        json={"repository_id": str(uuid.uuid4()), "request": "Do something useful."},
    )
    assert response.status_code == 404


def test_get_task(client, repository):
    created = client.post(
        "/api/tasks",
        json={"repository_id": repository["id"], "request": "Fix the flaky test."},
    ).json()

    response = client.get(f"/api/tasks/{created['task_id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == created["task_id"]
    assert body["description"] == "Fix the flaky test."


def test_get_task_not_found(client):
    response = client.get(f"/api/tasks/{uuid.uuid4()}")
    assert response.status_code == 404


def test_list_tasks_filters_by_repository(client, repository):
    client.post(
        "/api/tasks",
        json={"repository_id": repository["id"], "request": "Task for filtering test."},
    )

    response = client.get("/api/tasks", params={"repository_id": repository["id"]})
    assert response.status_code == 200
    tasks = response.json()
    assert len(tasks) >= 1
    assert all(t["repository_id"] == repository["id"] for t in tasks)


def test_task_status_transition_pending_to_queued(client, repository):
    created = client.post(
        "/api/tasks",
        json={"repository_id": repository["id"], "request": "Task for status transition test."},
    ).json()
    task_id = created["task_id"]

    response = client.patch(f"/api/tasks/{task_id}/status", json={"status": "QUEUED"})
    assert response.status_code == 200
    assert response.json()["status"] == "QUEUED"


def test_task_status_transition_invalid_is_rejected(client, repository):
    created = client.post(
        "/api/tasks",
        json={"repository_id": repository["id"], "request": "Task for invalid transition test."},
    ).json()
    task_id = created["task_id"]

    # PENDING -> COMPLETED is not an allowed direct transition.
    response = client.patch(f"/api/tasks/{task_id}/status", json={"status": "COMPLETED"})
    assert response.status_code == 400


def test_task_status_transition_full_happy_path(client, repository):
    created = client.post(
        "/api/tasks",
        json={"repository_id": repository["id"], "request": "Task for happy path test."},
    ).json()
    task_id = created["task_id"]

    for target in ("QUEUED", "RUNNING", "COMPLETED"):
        response = client.patch(f"/api/tasks/{task_id}/status", json={"status": target})
        assert response.status_code == 200, response.text
        assert response.json()["status"] == target

    # COMPLETED is terminal — no further transitions allowed.
    response = client.patch(f"/api/tasks/{task_id}/status", json={"status": "RUNNING"})
    assert response.status_code == 400
