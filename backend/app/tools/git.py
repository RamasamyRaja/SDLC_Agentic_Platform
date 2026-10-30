"""
git_diff — inspects LOCAL, uncommitted changes in a repository's
workspace (tracked-file modifications via `git diff`, plus untracked new
files listed by name). Reuses GitPython (already a project dependency,
via app.services.git_service) — never shells out to a raw `git` command
string, and never commits, pushes, or touches the remote.
"""
import git
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.user import User
from app.tools.base import get_onboarded_workspace
from app.tools.models import GitDiffInput, GitDiffOutput


def git_diff(db: Session, *, user: User, input_data: GitDiffInput) -> GitDiffOutput:
    settings = get_settings()
    workspace = get_onboarded_workspace(db, user=user, repository_id=input_data.repository_id)

    repo = git.Repo(workspace)

    numstat_output = repo.git.diff("--numstat")
    additions = 0
    deletions = 0
    changed_files: list[str] = []
    for line in numstat_output.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added, removed, file_path = parts
        changed_files.append(file_path)
        if added.isdigit():
            additions += int(added)
        if removed.isdigit():
            deletions += int(removed)

    untracked = list(repo.untracked_files)
    files_changed = changed_files + [f for f in untracked if f not in changed_files]

    diff_text = repo.git.diff()
    truncated = len(diff_text) > settings.TOOL_MAX_DIFF_CHARS
    if truncated:
        diff_text = diff_text[: settings.TOOL_MAX_DIFF_CHARS]

    summary = (
        f"{len(files_changed)} file(s) changed, {additions} addition(s), {deletions} deletion(s)"
        if files_changed
        else "No local changes"
    )

    return GitDiffOutput(
        files_changed=files_changed,
        additions=additions,
        deletions=deletions,
        diff_text=diff_text,
        summary=summary,
        truncated=truncated,
    )
