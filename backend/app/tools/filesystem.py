"""
read_file and modify_file — the two tools that touch a single, specific,
model-supplied path. Both go through
app.tools.path_safety.resolve_safe_relative_path() for the workspace-
boundary check described in that module's docstring.

modify_file is the most security-sensitive operation in this milestone
(per the spec): it requires an unambiguous, single occurrence of
`old_content` in the target file before writing anything, refuses to
guess when the match is ambiguous or absent, and writes atomically
(write to a temp file in the same directory, then `os.replace` — which is
atomic on POSIX, so a crash mid-write can never leave the target file
half-written).
"""
import os
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.user import User
from app.tools.base import get_onboarded_workspace
from app.tools.exceptions import (
    AmbiguousModificationError,
    FileTooLargeError,
    ModificationNotFoundError,
    PathSecurityError,
    ToolFileNotFoundError,
    ToolInputValidationError,
)
from app.tools.models import ModifyFileInput, ModifyFileOutput, ReadFileInput, ReadFileOutput
from app.tools.path_safety import resolve_safe_relative_path


def _read_text_or_raise(path: Path, *, context: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ToolInputValidationError(f"{context}: file is not valid UTF-8 text") from exc


def read_file(db: Session, *, user: User, input_data: ReadFileInput) -> ReadFileOutput:
    settings = get_settings()
    workspace = get_onboarded_workspace(db, user=user, repository_id=input_data.repository_id)
    target = resolve_safe_relative_path(workspace, input_data.file_path)

    if not target.exists():
        raise ToolFileNotFoundError(f"File not found: {input_data.file_path}")
    if not target.is_file():
        raise PathSecurityError(f"Not a regular file: {input_data.file_path}")

    size = target.stat().st_size
    if size > settings.TOOL_MAX_FILE_SIZE_BYTES:
        raise FileTooLargeError(
            f"File exceeds TOOL_MAX_FILE_SIZE_BYTES "
            f"({size} > {settings.TOOL_MAX_FILE_SIZE_BYTES} bytes): {input_data.file_path}"
        )

    text = _read_text_or_raise(target, context=input_data.file_path)
    lines = text.splitlines()
    total_lines = len(lines)

    start_line = input_data.start_line or 1
    end_line = input_data.end_line or total_lines
    end_line = min(end_line, total_lines) if total_lines else start_line

    selected = lines[start_line - 1 : end_line] if total_lines else []
    content = "\n".join(selected)

    truncated = len(content) > settings.TOOL_MAX_FILE_SIZE_BYTES
    if truncated:
        content = content[: settings.TOOL_MAX_FILE_SIZE_BYTES]

    return ReadFileOutput(
        path=input_data.file_path,
        start_line=start_line,
        end_line=end_line,
        content=content,
        truncated=truncated,
        total_lines=total_lines,
    )


def modify_file(db: Session, *, user: User, input_data: ModifyFileInput) -> ModifyFileOutput:
    settings = get_settings()
    workspace = get_onboarded_workspace(db, user=user, repository_id=input_data.repository_id)
    target = resolve_safe_relative_path(workspace, input_data.file_path)

    if not target.exists():
        raise ModificationNotFoundError(f"File not found: {input_data.file_path}")
    if not target.is_file():
        raise PathSecurityError(f"Not a regular file: {input_data.file_path}")

    size = target.stat().st_size
    if size > settings.TOOL_MAX_FILE_SIZE_BYTES:
        raise FileTooLargeError(
            f"File exceeds TOOL_MAX_FILE_SIZE_BYTES "
            f"({size} > {settings.TOOL_MAX_FILE_SIZE_BYTES} bytes): {input_data.file_path}"
        )

    original_content = _read_text_or_raise(target, context=input_data.file_path)

    occurrences = original_content.count(input_data.old_content)
    if occurrences == 0:
        raise ModificationNotFoundError(
            f"old_content was not found in {input_data.file_path} — refusing to modify"
        )
    if occurrences > 1:
        raise AmbiguousModificationError(
            f"old_content occurs {occurrences} times in {input_data.file_path} — "
            f"refusing to guess which occurrence to replace"
        )

    new_full_content = original_content.replace(input_data.old_content, input_data.new_content, 1)

    # Atomic write: write to a temp file in the same directory, then
    # os.replace (atomic on POSIX) — a crash mid-write can never leave the
    # target file partially written.
    tmp_path = target.with_name(f"{target.name}.tmp-{uuid.uuid4().hex[:8]}")
    try:
        tmp_path.write_text(new_full_content, encoding="utf-8")
        os.replace(tmp_path, target)
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)

    return ModifyFileOutput(
        path=input_data.file_path,
        success=True,
        bytes_changed=len(new_full_content.encode("utf-8")) - len(original_content.encode("utf-8")),
        message="File updated successfully",
    )
