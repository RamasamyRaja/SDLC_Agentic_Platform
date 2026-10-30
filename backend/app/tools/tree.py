"""
repository_structure — a bounded, deterministic view of the repository
tree, reusing `discover_files()` (Milestone 3) for the same safe,
symlink-free, ignore-dir-respecting file walk `search_code` uses.

Directories are derived from the parent paths of discovered files (so a
directory that's empty of any non-ignored file never appears — there's
nothing useful to show for it). Entries are sorted deterministically
(directories and files together, alphabetically by path) and capped by
both max_depth (path segment count) and max_entries.
"""
from sqlalchemy.orm import Session

from app.analysis.file_discovery import discover_files
from app.core.config import get_settings
from app.models.user import User
from app.tools.base import get_onboarded_workspace
from app.tools.models import RepositoryStructureInput, RepositoryStructureOutput, TreeEntry


def repository_structure(
    db: Session, *, user: User, input_data: RepositoryStructureInput
) -> RepositoryStructureOutput:
    settings = get_settings()
    workspace = get_onboarded_workspace(db, user=user, repository_id=input_data.repository_id)

    max_depth = input_data.max_depth or settings.TOOL_MAX_TREE_DEPTH
    max_depth = min(max_depth, settings.TOOL_MAX_TREE_DEPTH)
    max_entries = input_data.max_entries or settings.TOOL_MAX_TREE_ENTRIES
    max_entries = min(max_entries, settings.TOOL_MAX_TREE_ENTRIES)

    directory_paths: set[str] = set()
    file_paths: set[str] = set()

    for discovered in discover_files(workspace):
        parts = discovered.relative_path.split("/")

        # Ancestor directories within max_depth are always shown, even if
        # the file itself is deeper — a directory shouldn't disappear just
        # because none of its direct children fit under the depth limit.
        for depth in range(1, min(len(parts), max_depth + 1)):
            directory_paths.add("/".join(parts[:depth]))

        if len(parts) > max_depth:
            continue  # the file itself is too deep to list, but its
            # ancestor directories (added above) still are.

        file_paths.add(discovered.relative_path)

    all_entries = sorted(
        [TreeEntry(path=p, type="dir") for p in directory_paths]
        + [TreeEntry(path=p, type="file") for p in file_paths],
        key=lambda e: e.path,
    )

    truncated = len(all_entries) > max_entries
    return RepositoryStructureOutput(entries=all_entries[:max_entries], truncated=truncated)
