"""
Safe, recursive source-file discovery for a cloned repository workspace.

Responsibilities:
  - walk the workspace directory, skipping configured ignore-directory names
    anywhere in the tree (.git, node_modules, venv, build output, ...).
  - never follow symlinks that would escape the workspace root.
  - return repository-relative paths only (never absolute host paths) so
    nothing downstream can leak or depend on the host filesystem layout.
  - flag files over the configured size limit rather than reading them.

This module does not decide what's "supported" for parsing — that's the
language registry's job (`app.analysis.tree_sitter.registry.detect_language`).
It just discovers files safely and reports their size.
"""
import fnmatch
import os
from dataclasses import dataclass
from pathlib import Path

from app.core.config import get_settings


@dataclass
class DiscoveredFile:
    relative_path: str  # POSIX-style, relative to the workspace root
    absolute_path: Path
    size_bytes: int


def discover_files(workspace_root: Path) -> list[DiscoveredFile]:
    """
    Recursively discover files under `workspace_root`, skipping ignored
    directories. Raises ValueError if `workspace_root` does not exist or is
    not a directory — callers are expected to have already established the
    workspace via the Git/workspace service.
    """
    settings = get_settings()
    ignored_dir_names = settings.analysis_ignored_dir_names
    ignored_files = settings.analysis_ignored_file_patterns

    workspace_root = workspace_root.resolve()
    if not workspace_root.is_dir():
        raise ValueError(f"Workspace root does not exist or is not a directory: {workspace_root}")

    discovered: list[DiscoveredFile] = []

    for dirpath, dirnames, filenames in os.walk(workspace_root, followlinks=False):
        # Prune ignored directories in-place so os.walk never descends into them.
        dirnames[:] = [d for d in dirnames if d not in ignored_dir_names]

        current_dir = Path(dirpath)
        for filename in filenames:
            if any(fnmatch.fnmatch(filename, pat) for pat in ignored_files):
                continue   # generated / minified / bundled: not parsed, not embedded
            absolute_path = current_dir / filename

            # Skip symlinks entirely — we never want to parse or hash a
            # target that might live outside the workspace root.
            if absolute_path.is_symlink():
                continue

            try:
                resolved = absolute_path.resolve()
                resolved.relative_to(workspace_root)
            except (OSError, ValueError):
                # Escapes the workspace root, or is otherwise unresolvable — skip.
                continue

            try:
                size_bytes = absolute_path.stat().st_size
            except OSError:
                continue

            relative_path = absolute_path.relative_to(workspace_root).as_posix()
            discovered.append(
                DiscoveredFile(relative_path=relative_path, absolute_path=absolute_path, size_bytes=size_bytes)
            )

    return discovered
