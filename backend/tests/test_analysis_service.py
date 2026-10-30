import shutil
from pathlib import Path

from app.analysis.models import FileAnalysisStatus
from app.analysis.service import analyze_repository

FIXTURES = Path(__file__).parent / "fixtures"


def _build_mixed_repo(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    shutil.copy(FIXTURES / "python_sample" / "investigation_service.py", tmp_path / "src")
    shutil.copy(FIXTURES / "java_sample" / "InvestigationService.java", tmp_path / "src")
    shutil.copy(FIXTURES / "typescript_sample" / "investigation.ts", tmp_path / "src")

    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "ignored.js").write_text("should never be scanned")

    (tmp_path / "src" / "broken.py").write_text("def broken(:\n    pass")
    (tmp_path / "README.md").write_text("# not a source file")

    return tmp_path


def test_analyze_repository_end_to_end(tmp_path: Path):
    root = _build_mixed_repo(tmp_path)
    analysis = analyze_repository(root, repository_id="repo-1", commit_sha="deadbeef")

    assert analysis.repository_id == "repo-1"
    assert analysis.commit_sha == "deadbeef"
    assert {lang.value for lang in analysis.languages} == {"python", "java", "typescript"}

    statuses = {f.path: f.status for f in analysis.files}
    assert statuses["src/investigation_service.py"] == FileAnalysisStatus.ANALYZED
    assert statuses["src/InvestigationService.java"] == FileAnalysisStatus.ANALYZED
    assert statuses["src/investigation.ts"] == FileAnalysisStatus.ANALYZED
    assert statuses["src/broken.py"] == FileAnalysisStatus.PARSE_ERROR
    assert statuses["README.md"] == FileAnalysisStatus.SKIPPED_UNSUPPORTED
    assert "node_modules/ignored.js" not in statuses  # pruned entirely, not just skipped

    assert analysis.files_analyzed_count == 3
    assert len(analysis.parse_errors) == 1
    assert analysis.parse_errors[0].file == "src/broken.py"

    class_names = {c.name for c in analysis.classes}
    assert "InvestigationService" in class_names

    symbol_names = {s.name for s in analysis.symbols}
    assert "deleteInvestigation" in symbol_names
    assert "delete_investigation" in symbol_names


def test_analyze_repository_respects_file_size_limit(tmp_path: Path, monkeypatch):
    from app.core import config as config_module

    (tmp_path / "big.py").write_text("x = 1\n" * 10)

    original_get_settings = config_module.get_settings
    settings = original_get_settings()
    monkeypatch.setattr(settings, "ANALYSIS_MAX_FILE_SIZE_BYTES", 5)

    analysis = analyze_repository(tmp_path, repository_id="repo-2", commit_sha=None)
    statuses = {f.path: f.status for f in analysis.files}
    assert statuses["big.py"] == FileAnalysisStatus.SKIPPED_TOO_LARGE


def test_analyze_repository_produces_dependency_edges_from_imports(tmp_path: Path):
    (tmp_path / "a.py").write_text("import os\n")
    analysis = analyze_repository(tmp_path, repository_id="repo-3", commit_sha=None)

    assert len(analysis.dependencies) == 1
    assert analysis.dependencies[0].from_file == "a.py"
    assert analysis.dependencies[0].target == "os"
