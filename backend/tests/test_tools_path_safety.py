from pathlib import Path

import pytest

from app.tools.exceptions import PathSecurityError
from app.tools.path_safety import resolve_safe_relative_path


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1")
    return tmp_path


def test_valid_relative_path_resolves_inside_workspace(workspace):
    resolved = resolve_safe_relative_path(workspace, "src/a.py")
    assert resolved == (workspace / "src" / "a.py").resolve()


def test_rejects_empty_path(workspace):
    with pytest.raises(PathSecurityError):
        resolve_safe_relative_path(workspace, "")


def test_rejects_whitespace_only_path(workspace):
    with pytest.raises(PathSecurityError):
        resolve_safe_relative_path(workspace, "   ")


@pytest.mark.parametrize(
    "bad_path",
    [
        "../../secret",
        "../../../etc/passwd",
        "../outside.txt",
        "src/../../outside.txt",
    ],
)
def test_rejects_path_traversal(workspace, bad_path):
    with pytest.raises(PathSecurityError):
        resolve_safe_relative_path(workspace, bad_path)


@pytest.mark.parametrize(
    "bad_path",
    [
        "/etc/passwd",
        "/absolute/path",
        "C:\\Windows\\System32",
        "c:/Windows/System32",
        "\\\\server\\share",
    ],
)
def test_rejects_absolute_paths(workspace, bad_path):
    with pytest.raises(PathSecurityError):
        resolve_safe_relative_path(workspace, bad_path)


def test_rejects_symlink_escaping_workspace(tmp_path):
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()
    outside = tmp_path / "outside_secret.txt"
    outside.write_text("secret")

    try:
        (workspace_dir / "link").symlink_to(outside)
        with pytest.raises(PathSecurityError):
            resolve_safe_relative_path(workspace_dir, "link")
    finally:
        outside.unlink(missing_ok=True)


def test_allows_symlink_pointing_inside_workspace(tmp_path):
    """A symlink is only rejected if it escapes the workspace — one that
    resolves to another location still inside the workspace is fine."""
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()
    real_file = workspace_dir / "real.py"
    real_file.write_text("x = 1")

    (workspace_dir / "link.py").symlink_to(real_file)
    resolved = resolve_safe_relative_path(workspace_dir, "link.py")
    assert resolved == real_file.resolve()
