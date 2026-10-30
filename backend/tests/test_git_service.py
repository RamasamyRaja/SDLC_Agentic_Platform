import subprocess
from pathlib import Path

import pytest

from app.core.exceptions import BranchNotFoundError, RepositoryCloneError
from app.services.git_service import clone_repository, get_current_commit_sha


def _init_local_repo(path: Path, *, branch: str = "main") -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", branch], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    (path / "README.md").write_text("hello")
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True)


def test_clone_repository_succeeds_for_valid_local_repo(tmp_path: Path):
    origin = tmp_path / "origin"
    _init_local_repo(origin)

    dest = tmp_path / "cloned"
    repo = clone_repository(f"file://{origin}", dest, branch="main")

    assert (dest / "README.md").exists()
    sha = get_current_commit_sha(repo)
    assert sha is not None
    assert len(sha) == 40


def test_clone_repository_raises_branch_not_found(tmp_path: Path):
    origin = tmp_path / "origin"
    _init_local_repo(origin)

    dest = tmp_path / "cloned"
    with pytest.raises(BranchNotFoundError):
        clone_repository(f"file://{origin}", dest, branch="does-not-exist")


def test_clone_repository_raises_clone_error_for_nonexistent_remote(tmp_path: Path):
    dest = tmp_path / "cloned"
    with pytest.raises(RepositoryCloneError):
        clone_repository("file:///tmp/definitely-does-not-exist-repo-xyz", dest)
