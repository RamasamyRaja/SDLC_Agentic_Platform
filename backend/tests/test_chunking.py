import shutil
from pathlib import Path

from app.analysis.service import analyze_repository
from app.retrieval.chunking import build_chunks_for_file, chunk_repository
from app.retrieval.models import ChunkType

FIXTURES = Path(__file__).parent / "fixtures"


def test_build_chunks_for_file_produces_class_and_method_chunks():
    content = (FIXTURES / "python_sample" / "investigation_service.py").read_text()
    from app.analysis.models import SupportedLanguage
    from app.analysis.tree_sitter.languages import python as py_lang
    from app.analysis.tree_sitter.parser import parse_source

    parsed = parse_source(content.encode(), SupportedLanguage.PYTHON)
    extraction = py_lang.extract(parsed.root_node, content.encode(), "investigation_service.py")

    chunks = build_chunks_for_file(
        repository_document_id="doc-1",
        file_path="investigation_service.py",
        language="python",
        file_content=content,
        classes=extraction.classes,
        functions=extraction.functions,
    )

    types = {c.chunk_type for c in chunks}
    assert ChunkType.CLASS in types
    assert ChunkType.METHOD in types

    class_chunk = next(c for c in chunks if c.chunk_type == ChunkType.CLASS)
    assert class_chunk.symbol_name == "InvestigationService"
    assert "class InvestigationService" in class_chunk.content

    method_chunk = next(c for c in chunks if c.chunk_type == ChunkType.METHOD)
    assert method_chunk.symbol_name == "InvestigationService.delete_investigation"
    assert "def delete_investigation" in method_chunk.content


def test_build_chunks_for_file_falls_back_to_whole_file_when_no_symbols():
    chunks = build_chunks_for_file(
        repository_document_id="doc-2",
        file_path="README.md",
        language=None,
        file_content="# Hello\nSome docs.",
        classes=[],
        functions=[],
    )
    assert len(chunks) == 1
    assert chunks[0].chunk_type == ChunkType.FILE
    assert chunks[0].symbol_name is None
    assert chunks[0].content == "# Hello\nSome docs."


def test_chunk_content_hash_reflects_content():
    chunks = build_chunks_for_file(
        repository_document_id="doc-3",
        file_path="a.py",
        language="python",
        file_content="x = 1",
        classes=[],
        functions=[],
    )
    import hashlib

    expected = hashlib.sha256("x = 1".encode()).hexdigest()
    assert chunks[0].content_hash == expected


def test_chunk_content_is_truncated_to_max_chars(monkeypatch):
    from app.core import config as config_module

    settings = config_module.get_settings()
    monkeypatch.setattr(settings, "CHUNK_MAX_CHARS", 5)

    chunks = build_chunks_for_file(
        repository_document_id="doc-4",
        file_path="a.py",
        language="python",
        file_content="0123456789",
        classes=[],
        functions=[],
    )
    assert len(chunks[0].content) == 5


def test_chunk_repository_end_to_end(tmp_path: Path):
    (tmp_path / "src").mkdir()
    shutil.copy(FIXTURES / "python_sample" / "investigation_service.py", tmp_path / "src")
    shutil.copy(FIXTURES / "java_sample" / "InvestigationService.java", tmp_path / "src")

    analysis = analyze_repository(tmp_path, repository_id="r1", commit_sha="abc")
    doc_ids = {f.path: f"doc-{i}" for i, f in enumerate(analysis.files)}
    contents = {
        f.path: (tmp_path / f.path).read_text()
        for f in analysis.files
        if f.status.value == "ANALYZED"
    }

    chunks = chunk_repository(analysis, document_ids_by_path=doc_ids, file_contents_by_path=contents)

    assert len(chunks) == 4  # 2 classes + 2 methods
    file_paths = {c.file_path for c in chunks}
    assert file_paths == {"src/investigation_service.py", "src/InvestigationService.java"}
