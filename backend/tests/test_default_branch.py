"""Regression tests for default-branch discovery (repos whose default is `master`, e.g. torvalds/linux)."""
import subprocess

import pytest

from app.models.repository import Repository
from app.services import git_service


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(cwd)})


def _remote_with_branch(tmp_path, branch):
    bare = tmp_path / f"{branch}.git"
    work = tmp_path / f"w-{branch}"
    work.mkdir()
    _git(work, "init", "-b", branch)
    (work / "a.txt").write_text("x")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "init")
    _git(tmp_path, "clone", "--bare", str(work), str(bare))
    return str(bare)


@pytest.mark.parametrize("branch", ["main", "master", "trunk"])
def test_resolves_actual_remote_default_branch(tmp_path, branch):
    url = _remote_with_branch(tmp_path, branch)
    assert git_service.resolve_remote_default_branch(url) == branch


def test_unreachable_remote_returns_none_not_main(tmp_path):
    assert git_service.resolve_remote_default_branch(str(tmp_path / "nope.git")) is None


def test_remote_branch_exists(tmp_path):
    url = _remote_with_branch(tmp_path, "master")
    assert git_service.remote_branch_exists(url, "master") is True
    assert git_service.remote_branch_exists(url, "main") is False


def test_live_linux_kernel_default_branch_is_master():
    """Real network check (ls-remote only; nothing is cloned or indexed)."""
    got = git_service.resolve_remote_default_branch("https://github.com/torvalds/linux")
    if got is None:
        pytest.skip("github.com not reachable from this environment")
    assert got == "master"


def test_create_repository_records_discovered_branch(client, db_session, monkeypatch):
    monkeypatch.setattr(git_service, "resolve_remote_default_branch", lambda url: "master")
    r = client.post("/api/repositories", json={"url": "https://github.com/example/linux-like"})
    assert r.status_code == 201, r.text
    body = r.json()
    try:
        assert body["default_branch"] == "master" and body["default_branch_source"] == "remote_head"
        assert body["status"] == "PENDING"                      # creation never clones or indexes
        assert body["indexing_status"] in ("NOT_INDEXED", None) and not body.get("indexed_chunk_count")
    finally:
        db_session.query(Repository).filter(Repository.id == body["id"]).delete()
        db_session.commit()


def test_explicit_branch_is_verified_and_recorded_as_user_specified(client, db_session, monkeypatch):
    monkeypatch.setattr(git_service, "remote_branch_exists", lambda url, b, default=True: True)
    r = client.post("/api/repositories", json={"url": "https://github.com/example/explicit", "branch": "develop"})
    assert r.status_code == 201, r.text
    body = r.json()
    try:
        assert body["default_branch"] == "develop" and body["default_branch_source"] == "user_specified"
    finally:
        db_session.query(Repository).filter(Repository.id == body["id"]).delete()
        db_session.commit()


def test_explicit_missing_branch_is_rejected(client, monkeypatch):
    monkeypatch.setattr(git_service, "remote_branch_exists", lambda url, b, default=True: False)
    r = client.post("/api/repositories", json={"url": "https://github.com/example/explicit2", "branch": "nonexistent"})
    assert r.status_code in (400, 404, 409, 422), r.text


def test_undiscoverable_remote_falls_back_and_says_so(client, db_session, monkeypatch):
    monkeypatch.setattr(git_service, "resolve_remote_default_branch", lambda url: None)
    r = client.post("/api/repositories", json={"url": "https://github.com/example/private-ish"})
    assert r.status_code == 201, r.text
    body = r.json()
    try:
        assert body["default_branch_source"] == "fallback"
    finally:
        db_session.query(Repository).filter(Repository.id == body["id"]).delete()
        db_session.commit()
