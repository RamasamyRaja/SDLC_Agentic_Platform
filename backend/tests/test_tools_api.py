import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def _build_local_git_repo(tmp_path: Path, name: str = "api_tools_origin") -> Path:
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
def task_with_repo(client, db_session, tmp_path):
    origin = _build_local_git_repo(tmp_path)
    repo = client.post("/api/repositories", json={"url": f"file://{origin}", "branch": "main"}).json()
    assert client.post(f"/api/repositories/{repo['id']}/onboard", json={}).status_code == 201
    task = client.post(
        "/api/tasks", json={"repository_id": repo["id"], "request": "Delete an investigation"}
    ).json()

    yield {"repo": repo, "task": task}

    from app.models.repository import Repository
    from app.services import workspace_service

    db_session.query(Repository).filter(Repository.id == repo["id"]).delete()
    db_session.commit()
    workspace_service.remove_workspace(uuid.UUID(repo["id"]))


def test_list_tools_endpoint(client):
    response = client.get("/api/tasks/00000000-0000-0000-0000-000000000000/tools")
    assert response.status_code == 200
    body = response.json()
    names = {t["name"] for t in body["tools"]}
    assert names == {"read_file", "search_code", "repository_structure", "modify_file", "git_diff"}


def test_invoke_read_file_via_api(client, task_with_repo):
    task_id = task_with_repo["task"]["task_id"]
    response = client.post(
        f"/api/tasks/{task_id}/tools/read_file",
        json={"input": {"file_path": "src/investigation_service.py"}},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["tool_name"] == "read_file"
    assert "class InvestigationService" in body["output"]["content"]


def test_invoke_search_code_via_api(client, task_with_repo):
    task_id = task_with_repo["task"]["task_id"]
    response = client.post(
        f"/api/tasks/{task_id}/tools/search_code",
        json={"input": {"query": "delete_investigation"}},
    )
    assert response.status_code == 201
    body = response.json()
    assert len(body["output"]["matches"]) == 1


def test_invoke_modify_file_via_api(client, task_with_repo):
    task_id = task_with_repo["task"]["task_id"]
    response = client.post(
        f"/api/tasks/{task_id}/tools/modify_file",
        json={
            "input": {
                "file_path": "src/investigation_service.py",
                "old_content": "class InvestigationService:",
                "new_content": "class Renamed:",
            }
        },
    )
    # Regression: source modification through the generic tool endpoint bypassed the plan-approval gate
    # and wrote straight into the onboarded checkout. It is now refused; the file must be untouched.
    assert response.status_code == 409
    assert "approves the plan" in response.json()["detail"]
    read = client.post(f"/api/tasks/{task_id}/tools/read_file", json={"input": {"file_path": "src/investigation_service.py"}})
    assert "class InvestigationService:" in read.json()["output"]["content"]


def test_invoke_git_diff_via_api(client, task_with_repo):
    task_id = task_with_repo["task"]["task_id"]
    response = client.post(f"/api/tasks/{task_id}/tools/git_diff", json={"input": {}})
    assert response.status_code == 201
    assert response.json()["output"]["summary"] == "No local changes"


def test_invoke_unknown_tool_returns_404(client, task_with_repo):
    task_id = task_with_repo["task"]["task_id"]
    response = client.post(f"/api/tasks/{task_id}/tools/shell_exec", json={"input": {}})
    assert response.status_code == 404


def test_invoke_tool_with_malformed_input_returns_422(client, task_with_repo):
    task_id = task_with_repo["task"]["task_id"]
    response = client.post(f"/api/tasks/{task_id}/tools/read_file", json={"input": {}})
    assert response.status_code == 422


def test_invoke_tool_path_traversal_returns_400(client, task_with_repo):
    task_id = task_with_repo["task"]["task_id"]
    response = client.post(
        f"/api/tasks/{task_id}/tools/read_file",
        json={"input": {"file_path": "../../../etc/passwd"}},
    )
    assert response.status_code == 400


def test_invoke_tool_for_nonexistent_task_returns_404(client):
    response = client.post(
        f"/api/tasks/{uuid.uuid4()}/tools/read_file", json={"input": {"file_path": "a.py"}}
    )
    assert response.status_code == 404


def test_invoke_tool_rejects_mismatched_repository_id(client, task_with_repo):
    """A repository_id in the input that doesn't match the task's own
    repository must be rejected — a user can't use one task's endpoint to
    reach a different repository."""
    task_id = task_with_repo["task"]["task_id"]
    response = client.post(
        f"/api/tasks/{task_id}/tools/read_file",
        json={"input": {"repository_id": str(uuid.uuid4()), "file_path": "a.py"}},
    )
    assert response.status_code == 400


def test_invoke_tool_records_tool_invocation(client, db_session, task_with_repo):
    task_id = task_with_repo["task"]["task_id"]
    client.post(
        f"/api/tasks/{task_id}/tools/read_file",
        json={"input": {"file_path": "src/investigation_service.py"}},
    )

    from app.models.tool_invocation import ToolInvocation

    rows = db_session.query(ToolInvocation).filter(ToolInvocation.task_id == uuid.UUID(task_id)).all()
    assert len(rows) == 1
    assert rows[0].tool_name == "read_file"
    assert rows[0].status.value == "SUCCESS"


def test_invoke_tool_records_failed_invocation(client, db_session, task_with_repo):
    task_id = task_with_repo["task"]["task_id"]
    client.post(
        f"/api/tasks/{task_id}/tools/read_file",
        json={"input": {"file_path": "does/not/exist.py"}},
    )

    from app.models.tool_invocation import ToolInvocation

    rows = db_session.query(ToolInvocation).filter(ToolInvocation.task_id == uuid.UUID(task_id)).all()
    assert len(rows) == 1
    assert rows[0].status.value == "FAILED"
    assert rows[0].error is not None
