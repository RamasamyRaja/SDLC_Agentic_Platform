"""
Safe file operations for the Development Agent, rooted at an *isolated worktree*
(never at the onboarded checkout).

Every model-supplied path goes through app.tools.path_safety (no absolute
paths, no "..", resolved target must stay inside the root). On top of that:
protected files (secrets, lockfiles, .git, dependency directories) can never
be touched, symlinks are never written through, and sizes are bounded.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

from app.core.config import get_settings
from app.tools.exceptions import (
    AmbiguousModificationError,
    FileTooLargeError,
    ModificationNotFoundError,
    PathSecurityError,
    ToolFileNotFoundError,
    ToolInputValidationError,
)
from app.tools.path_safety import resolve_safe_relative_path

_PROTECTED_NAMES = {
    ".env", ".env.local", ".env.production", ".env.development", "package-lock.json", "pnpm-lock.yaml",
    "yarn.lock", "poetry.lock", "pipfile.lock", "id_rsa", "id_ed25519", ".npmrc", ".pypirc", ".netrc",
}
_PROTECTED_SUFFIXES = (".pem", ".key", ".p12", ".pfx")


def is_protected_path(path: str) -> bool:
    normalized = path.replace("\\", "/").strip().lower()
    parts = [p for p in normalized.split("/") if p]
    if not parts:
        return True
    name = parts[-1]
    return (
        name in _PROTECTED_NAMES
        or name.startswith(".env.")
        or name.endswith(_PROTECTED_SUFFIXES)
        or ".git" in parts
        or "node_modules" in parts
    )


def _guard(root: Path, rel: str) -> Path:
    if is_protected_path(rel):
        raise PathSecurityError(f"Path is protected and cannot be read or modified by the agent: {rel!r}")
    target = resolve_safe_relative_path(root, rel)
    # refuse to operate through symlinks (even ones that point inside the tree)
    probe = root.resolve()
    for segment in Path(rel).parts:
        probe = probe / segment
        if probe.is_symlink():
            raise PathSecurityError(f"Symlinks are not followed: {rel!r}")
    return target


def read_text(root: Path, rel: str) -> str:
    settings = get_settings()
    target = _guard(root, rel)
    if not target.exists():
        raise ToolFileNotFoundError(f"File not found: {rel}")
    if not target.is_file():
        raise PathSecurityError(f"Not a regular file: {rel}")
    size = target.stat().st_size
    if size > settings.TOOL_MAX_FILE_SIZE_BYTES:
        raise FileTooLargeError(f"File exceeds {settings.TOOL_MAX_FILE_SIZE_BYTES} bytes: {rel}")
    try:
        return target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ToolInputValidationError(f"{rel}: not valid UTF-8 text") from exc


def _atomic_write(target: Path, content: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f"{target.name}.tmp-{uuid.uuid4().hex[:8]}")
    try:
        tmp.write_text(content, encoding="utf-8")
        if target.exists():
            os.chmod(tmp, target.stat().st_mode & 0o7777)
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)


def replace_once(root: Path, rel: str, old: str, new: str) -> None:
    """Replace exactly one occurrence of `old`; refuse when absent or ambiguous."""
    if not old:
        raise ToolInputValidationError("old_content must not be empty")
    original = read_text(root, rel)
    n = original.count(old)
    if n == 0:
        raise ModificationNotFoundError(f"old_content was not found in {rel}")
    if n > 1:
        raise AmbiguousModificationError(f"old_content occurs {n} times in {rel}")
    _atomic_write(_guard(root, rel), original.replace(old, new, 1))


def create_file(root: Path, rel: str, content: str) -> None:
    """Create a NEW file; never overwrites."""
    settings = get_settings()
    target = _guard(root, rel)
    if target.exists():
        raise ToolInputValidationError(f"{rel} already exists; use an edit instead of creating it")
    if len(content.encode("utf-8")) > settings.TOOL_MAX_FILE_SIZE_BYTES:
        raise FileTooLargeError(f"New file exceeds {settings.TOOL_MAX_FILE_SIZE_BYTES} bytes: {rel}")
    parent = target.parent
    # every existing ancestor must be inside the root and not a symlink (resolve already checked containment)
    _atomic_write(target, content)
