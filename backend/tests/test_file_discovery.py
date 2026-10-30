from pathlib import Path

import pytest

from app.analysis.file_discovery import discover_files


def test_discover_files_finds_source_files(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1")
    (tmp_path / "src" / "b.java").write_text("class B {}")

    discovered = discover_files(tmp_path)
    relative_paths = {f.relative_path for f in discovered}
    assert relative_paths == {"src/a.py", "src/b.java"}


def test_discover_files_ignores_configured_directories(tmp_path: Path):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "junk.js").write_text("ignored")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("ignored")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "cache.pyc").write_bytes(b"\x00")
    (tmp_path / "keep.py").write_text("x = 1")

    discovered = discover_files(tmp_path)
    relative_paths = {f.relative_path for f in discovered}
    assert relative_paths == {"keep.py"}


def test_discover_files_reports_file_size(tmp_path: Path):
    content = b"x" * 500
    (tmp_path / "sized.py").write_bytes(content)

    discovered = discover_files(tmp_path)
    assert len(discovered) == 1
    assert discovered[0].size_bytes == 500


def test_discover_files_raises_for_nonexistent_root(tmp_path: Path):
    with pytest.raises(ValueError):
        discover_files(tmp_path / "does-not-exist")


def test_discover_files_skips_symlinks_escaping_root(tmp_path: Path):
    outside = tmp_path.parent / f"outside-{tmp_path.name}.py"
    outside.write_text("should never be read")
    try:
        (tmp_path / "escape.py").symlink_to(outside)
        discovered = discover_files(tmp_path)
        relative_paths = {f.relative_path for f in discovered}
        assert "escape.py" not in relative_paths
    finally:
        outside.unlink(missing_ok=True)
