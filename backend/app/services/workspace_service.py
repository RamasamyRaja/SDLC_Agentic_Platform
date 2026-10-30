"""
Workspace path management.

Every repository gets an isolated directory under the configured
WORKSPACE_ROOT: WORKSPACE_ROOT/<repository-id>/. This module is the only
place that constructs those paths, so path-traversal protection lives in
exactly one function.
"""
import os
import shutil
import stat
import uuid
from pathlib import Path

from app.core.config import get_settings
from app.core.exceptions import ValidationError

def _remove_readonly_and_retry(func, path, exc_info):
    """Retry deleting a read-only file on Windows."""
    import os
    import stat

    os.chmod(path, stat.S_IWRITE)
    func(path)

def get_workspace_path(repository_id: uuid.UUID) -> Path:
    """
    Return the isolated workspace directory for a repository, guaranteed to
    resolve to a location inside WORKSPACE_ROOT.

    `repository_id` is a UUID (not raw user input), so this mainly guards
    against a misconfigured WORKSPACE_ROOT or unexpected OS path behavior
    rather than a malicious repository_id — but we verify explicitly rather
    than assuming.
    """
    settings = get_settings()
    root = Path(settings.WORKSPACE_ROOT).resolve()
    candidate = (root / str(repository_id)).resolve()

    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValidationError(
            f"Computed workspace path escapes WORKSPACE_ROOT: {candidate}"
        ) from exc

    return candidate


def ensure_clean_workspace(repository_id: uuid.UUID) -> Path:
    """Return the workspace path for a repository, removing any prior contents first."""
    path = get_workspace_path(repository_id)
    if path.exists():
        shutil.rmtree(path, onerror=_remove_readonly_and_retry)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def remove_workspace(repository_id: uuid.UUID) -> None:
    """Safely remove a repository's workspace, if present. No-op if it doesn't exist."""
    path = get_workspace_path(repository_id)
    if path.exists():
        shutil.rmtree(path, onerror=_remove_readonly_and_retry)
