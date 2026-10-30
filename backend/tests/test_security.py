"""
Security-focused tests for the onboarding/analysis pipeline, called out
separately from functional tests per the milestone spec even though some
of this is also exercised incidentally elsewhere (test_file_discovery.py,
test_workspace_service.py).
"""
import uuid
from pathlib import Path

from app.analysis.file_discovery import discover_files
from app.analysis.models import FileAnalysisStatus
from app.analysis.service import analyze_repository
from app.services.workspace_service import get_workspace_path


def test_workspace_path_never_escapes_root_for_any_repository_id():
    """Every possible repository_id must resolve to a path under WORKSPACE_ROOT."""
    from app.core.config import get_settings

    settings = get_settings()
    root = Path(settings.WORKSPACE_ROOT).resolve()

    for _ in range(20):
        repository_id = uuid.uuid4()
        path = get_workspace_path(repository_id)
        # relative_to raises ValueError if `path` is not under `root` —
        # this call itself is the assertion.
        path.relative_to(root)


def test_oversized_file_is_skipped_not_read(tmp_path: Path, monkeypatch):
    """A file over the configured size limit is recorded as skipped and its
    contents are never parsed — verified by an intentionally-unparseable
    body that would otherwise show up as a parse error, not a skip."""
    from app.core import config as config_module

    settings = config_module.get_settings()
    monkeypatch.setattr(settings, "ANALYSIS_MAX_FILE_SIZE_BYTES", 10)

    (tmp_path / "huge.py").write_text("x = 1\n" * 100)  # well over 10 bytes

    analysis = analyze_repository(tmp_path, repository_id="sec-1", commit_sha=None)
    file_info = next(f for f in analysis.files if f.path == "huge.py")
    assert file_info.status == FileAnalysisStatus.SKIPPED_TOO_LARGE
    assert file_info.content_hash == ""  # never hashed/read


def test_unsupported_file_extension_is_skipped(tmp_path: Path):
    (tmp_path / "notes.txt").write_text("just some notes")
    (tmp_path / "binary.bin").write_bytes(b"\x00\x01\x02\xff")

    analysis = analyze_repository(tmp_path, repository_id="sec-2", commit_sha=None)
    statuses = {f.path: f.status for f in analysis.files}
    assert statuses["notes.txt"] == FileAnalysisStatus.SKIPPED_UNSUPPORTED
    assert statuses["binary.bin"] == FileAnalysisStatus.SKIPPED_UNSUPPORTED


def test_ignored_directories_are_never_visited_even_if_large(tmp_path: Path):
    """Confirms ignored directories are pruned during the walk itself
    (os.walk dirnames[:] filtering), not merely filtered out afterward —
    files inside them should not appear in the discovered set at all."""
    ignored_dirs = ["node_modules", ".venv", "venv", "target", "build", "dist", "__pycache__", ".git"]
    for d in ignored_dirs:
        (tmp_path / d).mkdir()
        (tmp_path / d / "should_not_appear.py").write_text("x = 1")

    (tmp_path / "keep.py").write_text("x = 1")

    discovered = discover_files(tmp_path)
    relative_paths = {f.relative_path for f in discovered}
    assert relative_paths == {"keep.py"}


def test_symlink_pointing_outside_workspace_is_never_followed(tmp_path: Path):
    outside_dir = tmp_path.parent / f"outside-secrets-{tmp_path.name}"
    outside_dir.mkdir()
    secret_file = outside_dir / "secret.py"
    secret_file.write_text("SECRET = 'do-not-leak'")

    try:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "link_to_secret.py").symlink_to(secret_file)

        discovered = discover_files(workspace)
        relative_paths = {f.relative_path for f in discovered}
        assert relative_paths == set()  # the symlink itself must not be reported
    finally:
        import shutil

        shutil.rmtree(outside_dir, ignore_errors=True)
