"""
Chunking: turns a repository's analyzed source into meaningful chunks
(class bodies, function/method bodies) using Milestone 3's Tree-sitter
structural analysis for boundaries — not arbitrary fixed-size string
splitting.

This module CONSUMES Milestone 3's output (`RepositoryAnalysis` /
`ClassInfo` / `FunctionInfo`, produced by `app.analysis.service.
analyze_repository`) rather than re-implementing any parsing itself. A file
with no extracted classes/functions (unsupported language, parse error, or
genuinely no top-level symbols) falls back to a single whole-file chunk, so
every discovered, readable file still contributes at least one chunk.
"""
import hashlib

from app.analysis.models import ClassInfo, FunctionInfo, RepositoryAnalysis
from app.core.config import get_settings
from app.retrieval.models import ChunkCandidate, ChunkType


def _hash_content(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _extract_lines(source_lines: list[str], start_line: int, end_line: int, max_chars: int) -> str:
    """1-indexed, inclusive line range -> joined text, truncated to max_chars."""
    start_idx = max(start_line - 1, 0)
    end_idx = min(end_line, len(source_lines))
    text = "\n".join(source_lines[start_idx:end_idx])
    return text[:max_chars]


def build_chunks_for_file(
    *,
    repository_document_id: str,
    file_path: str,
    language: str | None,
    file_content: str,
    classes: list[ClassInfo],
    functions: list[FunctionInfo],
) -> list[ChunkCandidate]:
    """
    Build chunks for a single file, given the classes/functions Milestone
    3's analysis already extracted for it (both lists are expected to be
    pre-filtered to this file's entries — see `chunk_repository`).
    """
    settings = get_settings()
    max_chars = settings.CHUNK_MAX_CHARS
    source_lines = file_content.splitlines()

    chunks: list[ChunkCandidate] = []

    for cls in classes:
        end_line = cls.end_line if cls.end_line >= cls.line else cls.line
        content = _extract_lines(source_lines, cls.line, end_line, max_chars)
        chunks.append(
            ChunkCandidate(
                repository_document_id=repository_document_id,
                file_path=file_path,
                language=language,
                chunk_type=ChunkType.CLASS,
                symbol_name=cls.name,
                start_line=cls.line,
                end_line=end_line,
                content=content,
                content_hash=_hash_content(content),
            )
        )

    for fn in functions:
        end_line = fn.end_line if fn.end_line >= fn.line else fn.line
        content = _extract_lines(source_lines, fn.line, end_line, max_chars)
        chunk_type = ChunkType.METHOD if fn.enclosing_class else ChunkType.FUNCTION
        # Qualify method chunk symbol names with their class for readability
        # in search results (e.g. "InvestigationService.deleteInvestigation").
        symbol_name = f"{fn.enclosing_class}.{fn.name}" if fn.enclosing_class else fn.name
        chunks.append(
            ChunkCandidate(
                repository_document_id=repository_document_id,
                file_path=file_path,
                language=language,
                chunk_type=chunk_type,
                symbol_name=symbol_name,
                start_line=fn.line,
                end_line=end_line,
                content=content,
                content_hash=_hash_content(content),
            )
        )

    if not chunks:
        # Fallback: no structural symbols were extracted for this file
        # (unsupported language, parse error, or a file with no top-level
        # classes/functions, e.g. a config file or a script with only
        # module-level statements). One whole-file chunk still makes the
        # file's content searchable.
        content = file_content[:max_chars]
        chunks.append(
            ChunkCandidate(
                repository_document_id=repository_document_id,
                file_path=file_path,
                language=language,
                chunk_type=ChunkType.FILE,
                symbol_name=None,
                start_line=1,
                end_line=max(len(source_lines), 1),
                content=content,
                content_hash=_hash_content(content),
            )
        )

    return chunks


def chunk_repository(
    analysis: RepositoryAnalysis,
    *,
    document_ids_by_path: dict[str, str],
    file_contents_by_path: dict[str, str],
) -> list[ChunkCandidate]:
    """
    Build chunks for every analyzed file in a `RepositoryAnalysis`.

    `document_ids_by_path` maps a file's repository-relative path to its
    persisted `RepositoryDocument.id` (as a string) — chunking needs this to
    link each chunk back to its document row. `file_contents_by_path` maps
    the same paths to their (already-read) file content, so this function
    never re-reads the filesystem itself.
    """
    classes_by_file: dict[str, list[ClassInfo]] = {}
    for cls in analysis.classes:
        classes_by_file.setdefault(cls.file, []).append(cls)

    functions_by_file: dict[str, list[FunctionInfo]] = {}
    for fn in analysis.functions:
        functions_by_file.setdefault(fn.file, []).append(fn)

    all_chunks: list[ChunkCandidate] = []
    for file_info in analysis.files:
        if file_info.path not in file_contents_by_path:
            continue  # skipped/unreadable/too-large files were never read — nothing to chunk
        document_id = document_ids_by_path.get(file_info.path)
        if document_id is None:
            continue  # should not happen if documents were persisted for every discovered file

        chunks = build_chunks_for_file(
            repository_document_id=document_id,
            file_path=file_info.path,
            language=file_info.language.value if file_info.language else None,
            file_content=file_contents_by_path[file_info.path],
            classes=classes_by_file.get(file_info.path, []),
            functions=functions_by_file.get(file_info.path, []),
        )
        all_chunks.extend(chunks)

    return all_chunks
