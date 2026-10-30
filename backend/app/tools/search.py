"""
search_code — repository-scoped, Python-based text search.

Reuses `app.analysis.file_discovery.discover_files()` (Milestone 3)
exactly as-is: it already skips ignored directories, never follows
symlinks, and only ever returns paths verified to be inside the workspace
root. This tool adds nothing to that boundary — it only reads files
`discover_files` already confirmed are safe, and only up to
TOOL_MAX_FILE_SIZE_BYTES each.

Deliberately NOT backed by an unrestricted system `grep` — a plain Python
substring scan keeps this tool's behavior fully within the same
process/permission boundary as everything else here (no subprocess).
"""
import fnmatch

from sqlalchemy.orm import Session

from app.analysis.file_discovery import discover_files
from app.core.config import get_settings
from app.models.user import User
from app.tools.base import get_onboarded_workspace
from app.tools.models import SearchCodeInput, SearchCodeOutput, SearchMatch


def search_code(db: Session, *, user: User, input_data: SearchCodeInput) -> SearchCodeOutput:
    settings = get_settings()
    workspace = get_onboarded_workspace(db, user=user, repository_id=input_data.repository_id)

    max_results = input_data.max_results or settings.TOOL_MAX_SEARCH_RESULTS
    max_results = min(max_results, settings.TOOL_MAX_SEARCH_RESULTS)
    query_lower = input_data.query.lower()

    matches: list[SearchMatch] = []
    truncated = False

    for discovered in discover_files(workspace):
        if len(matches) >= max_results:
            truncated = True
            break

        if input_data.file_pattern and not fnmatch.fnmatch(discovered.relative_path, input_data.file_pattern):
            continue

        if discovered.size_bytes > settings.TOOL_MAX_FILE_SIZE_BYTES:
            continue  # too large to scan — skip, don't fail the whole search

        try:
            text = discovered.absolute_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue  # unreadable/binary — skip, don't fail the whole search

        for line_number, line in enumerate(text.splitlines(), start=1):
            if query_lower in line.lower():
                matches.append(
                    SearchMatch(file=discovered.relative_path, line=line_number, text=line.strip()[:500])
                )
                if len(matches) >= max_results:
                    truncated = True
                    break

    return SearchCodeOutput(matches=matches, truncated=truncated)
