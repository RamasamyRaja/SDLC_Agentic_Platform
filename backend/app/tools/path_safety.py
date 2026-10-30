"""
Path safety for tool-supplied (untrusted, potentially model-generated)
relative file paths.

This is the ONE place a tool-supplied `file_path` string gets turned into
a real filesystem `Path` — every tool that touches a specific file
(`read_file`, `modify_file`) goes through `resolve_safe_relative_path()`.
`search_code` and `repository_structure` instead reuse
`app.analysis.file_discovery.discover_files()` (Milestone 3), which never
follows symlinks and never leaves the workspace root in the first place —
so they don't need this function, but rely on the exact same underlying
guarantee.

Rejected, always:
  - empty/whitespace-only paths
  - absolute paths (POSIX `/...` or Windows `C:\\...` / `\\...`)
  - any path containing a `..` segment
  - a resolved (symlinks followed) target outside the workspace root

The final check — resolving the path and verifying it's still under the
workspace root — is the authoritative one; the earlier string-level
checks exist to fail fast with a clearer error before ever touching the
filesystem, not as the actual security boundary by themselves.
"""
import re
from pathlib import Path

from app.tools.exceptions import PathSecurityError

_WINDOWS_DRIVE_PATTERN = re.compile(r"^[A-Za-z]:[\\/]")


def resolve_safe_relative_path(workspace_root: Path, relative_path: str) -> Path:
    if not relative_path or not relative_path.strip():
        raise PathSecurityError("file_path must not be empty")

    normalized = relative_path.strip()

    if normalized.startswith("/") or normalized.startswith("\\"):
        raise PathSecurityError(f"Absolute paths are not allowed: {relative_path!r}")

    if _WINDOWS_DRIVE_PATTERN.match(normalized):
        raise PathSecurityError(f"Absolute paths are not allowed: {relative_path!r}")

    segments = re.split(r"[\\/]+", normalized)
    if any(segment == ".." for segment in segments):
        raise PathSecurityError(f"Path traversal ('..') is not allowed: {relative_path!r}")

    workspace_resolved = workspace_root.resolve()
    candidate = workspace_resolved / normalized

    try:
        resolved = candidate.resolve(strict=False)
    except OSError as exc:
        raise PathSecurityError(f"Could not resolve path: {relative_path!r}") from exc

    try:
        resolved.relative_to(workspace_resolved)
    except ValueError as exc:
        raise PathSecurityError(
            f"Path escapes the repository workspace: {relative_path!r}"
        ) from exc

    return resolved
