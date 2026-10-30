"""
Git operations, isolated behind one service so route handlers and the
onboarding orchestrator never call GitPython/git directly.

Only supports: clone, checkout branch, read commit SHA, remove workspace.
Deliberately does NOT execute any repository-provided command (build/test
scripts, hooks, etc.) — that's the Milestone 8 Docker sandbox's job, under
much stricter isolation than a plain clone.
"""
import logging
import os
import re
import subprocess
from pathlib import Path

import git
from git import GitCommandError

from app.core.config import get_settings
from app.core.exceptions import BranchNotFoundError, RepositoryCloneError

logger = logging.getLogger(__name__)


def clone_repository(url: str, destination: Path, *, branch: str | None = None) -> git.Repo:
    """
    Clone `url` into `destination` (which must already exist as an empty/
    absent directory — see workspace_service.ensure_clean_workspace).

    If `branch` is given, clones directly onto that branch. Raises
    `RepositoryCloneError` for network/auth/URL failures, and
    `BranchNotFoundError` specifically when the branch doesn't exist on the
    remote (detected via GitPython's error message, since the git CLI does
    not give a distinct exit code for it).
    """
    settings = get_settings()
    kwargs = {"depth": 1}  # shallow clone: we only need the current tree + latest commit SHA
    if branch:
        kwargs["branch"] = branch

    
    try:
        command = ["git", "clone", "--depth", "1"]
        if branch:
            command.extend(["--branch", branch])
        command.extend(["--", url, str(destination)])

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=settings.GIT_CLONE_TIMEOUT_SECONDS,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            check=False,
        )

        if result.returncode != 0:
            message = (result.stderr or result.stdout or "Git clone failed").strip()
            if branch and (
                f"Remote branch {branch} not found" in message
                or "not found in upstream" in message
                or "did not match any" in message
            ):
                raise BranchNotFoundError(
                    f"Branch '{branch}' not found in repository {url}"
                )
            raise RepositoryCloneError(
                f"Failed to clone repository {url}: {message[:500]}"
            )

        repo = git.Repo(str(destination))

    except subprocess.TimeoutExpired as exc:
        raise RepositoryCloneError(
            f"Cloning repository {url} exceeded the timeout of "
            f"{settings.GIT_CLONE_TIMEOUT_SECONDS} seconds"
        ) from exc
    except (BranchNotFoundError, RepositoryCloneError):
        raise
    except Exception as exc:  # noqa: BLE001
        raise RepositoryCloneError(
            f"Failed to clone repository {url}: {exc}"
        ) from exc


    return repo



def resolve_remote_default_branch(url: str) -> str | None:
    """Resolve the advertised default branch from the remote HEAD symref.

    Returns None when the server does not advertise a symbolic HEAD or the
    remote cannot be queried. Never assumes that the branch is named main.
    """
    settings = get_settings()
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--symref", url, "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=settings.GIT_DISCOVERY_TIMEOUT_SECONDS,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except (subprocess.SubprocessError, OSError) as exc:
        logger.warning("Could not resolve remote default branch for %s: %s", url, exc)
        return None

    match = re.search(r"^ref:\s+refs/heads/(\S+)\s+HEAD\s*$", result.stdout, re.MULTILINE)
    return match.group(1) if match else None


def remote_branch_exists(url: str, branch: str, *, default: bool = True) -> bool:
    """True/False when the remote answers; `default` when it cannot be queried (private/unreachable)."""
    settings = get_settings()
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--heads", url, f"refs/heads/{branch}"],
            check=True, capture_output=True, text=True, timeout=settings.GIT_DISCOVERY_TIMEOUT_SECONDS,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except (subprocess.SubprocessError, OSError):
        return default
    return bool(result.stdout.strip())


def get_current_commit_sha(repo: git.Repo) -> str | None:
    try:
        return repo.head.commit.hexsha
    except (ValueError, AttributeError) as exc:
        logger.warning("Could not determine commit SHA: %s", exc)
        return None


def get_default_branch_name(repo: git.Repo) -> str | None:
    try:
        return repo.active_branch.name
    except TypeError:
        # Detached HEAD (can happen with shallow clones of a tag/SHA) — no
        # named branch to report, which is fine; the commit SHA is what matters.
        return None
