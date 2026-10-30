import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def _build_local_git_repo(tmp_path: Path, name: str) -> Path:
    origin = tmp_path / name
    origin.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=origin, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=origin, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=origin, check=True)

    (origin / "secret.py").write_text(f"SECRET_FOR_{name.upper()} = True\n")

    subprocess.run(["git", "add", "."], cwd=origin, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=origin, check=True, capture_output=True)
    return origin


@pytest.fixture()
def two_repos(client, db_session, tmp_path):
    origin_a = _build_local_git_repo(tmp_path, "repo_a")
    origin_b = _build_local_git_repo(tmp_path, "repo_b")

    repo_a = client.post("/api/repositories", json={"url": f"file://{origin_a}", "branch": "main"}).json()
    repo_b = client.post("/api/repositories", json={"url": f"file://{origin_b}", "branch": "main"}).json()
    assert client.post(f"/api/repositories/{repo_a['id']}/onboard", json={}).status_code == 201
    assert client.post(f"/api/repositories/{repo_b['id']}/onboard", json={}).status_code == 201

    yield {"a": repo_a, "b": repo_b}

    from app.models.repository import Repository
    from app.services import workspace_service

    for repo in (repo_a, repo_b):
        db_session.query(Repository).filter(Repository.id == repo["id"]).delete()
        workspace_service.remove_workspace(uuid.UUID(repo["id"]))
    db_session.commit()


def _user(db_session):
    from app.api.deps import get_current_user

    return get_current_user(db_session, None)


def test_read_file_cannot_read_across_repositories(db_session, two_repos):
    """Repository A's tools must never access Repository B's files —
    read_file for repo A can only ever see repo A's own secret.py."""
    from app.tools.filesystem import read_file
    from app.tools.models import ReadFileInput

    output_a = read_file(
        db_session, user=_user(db_session),
        input_data=ReadFileInput(repository_id=uuid.UUID(two_repos["a"]["id"]), file_path="secret.py"),
    )
    assert "REPO_A" in output_a.content
    assert "REPO_B" not in output_a.content

    output_b = read_file(
        db_session, user=_user(db_session),
        input_data=ReadFileInput(repository_id=uuid.UUID(two_repos["b"]["id"]), file_path="secret.py"),
    )
    assert "REPO_B" in output_b.content
    assert "REPO_A" not in output_b.content


def test_search_code_does_not_leak_across_repositories(db_session, two_repos):
    from app.tools.models import SearchCodeInput
    from app.tools.search import search_code

    output = search_code(
        db_session, user=_user(db_session),
        input_data=SearchCodeInput(repository_id=uuid.UUID(two_repos["a"]["id"]), query="SECRET_FOR"),
    )
    assert len(output.matches) == 1
    assert "REPO_A" in output.matches[0].text
    assert "REPO_B" not in output.matches[0].text


def test_repository_structure_does_not_leak_across_repositories(db_session, two_repos):
    from app.tools.models import RepositoryStructureInput
    from app.tools.tree import repository_structure

    output_a = repository_structure(
        db_session, user=_user(db_session),
        input_data=RepositoryStructureInput(repository_id=uuid.UUID(two_repos["a"]["id"])),
    )
    paths_a = {e.path for e in output_a.entries}
    assert "secret.py" in paths_a

    output_b = repository_structure(
        db_session, user=_user(db_session),
        input_data=RepositoryStructureInput(repository_id=uuid.UUID(two_repos["b"]["id"])),
    )
    paths_b = {e.path for e in output_b.entries}
    assert "secret.py" in paths_b

    # Same relative filename in both, but each call only ever touches its
    # own repository's workspace — verified by content, not just paths.
    assert paths_a == paths_b  # both repos have the same relative structure...
    # ...but the actual file content differs (checked in test_read_file_cannot_read_across_repositories)


def test_modify_file_cannot_write_across_repositories(db_session, two_repos):
    """Modifying repo A must never affect repo B's copy of a
    similarly-named file."""
    from app.tools.filesystem import modify_file, read_file
    from app.tools.models import ModifyFileInput, ReadFileInput

    modify_file(
        db_session, user=_user(db_session),
        input_data=ModifyFileInput(
            repository_id=uuid.UUID(two_repos["a"]["id"]), file_path="secret.py",
            old_content="SECRET_FOR_REPO_A = True", new_content="SECRET_FOR_REPO_A = False",
        ),
    )

    output_b = read_file(
        db_session, user=_user(db_session),
        input_data=ReadFileInput(repository_id=uuid.UUID(two_repos["b"]["id"]), file_path="secret.py"),
    )
    assert "SECRET_FOR_REPO_B = True" in output_b.content  # untouched
