"""
AnalysisService: orchestrates file discovery, language detection,
Tree-sitter parsing, and per-language structural extraction into a single
`RepositoryAnalysis` result.

This is the only entry point other code (the onboarding service, tests)
should call for structural analysis — it hides the discovery/parse/extract
pipeline behind one function.
"""
import hashlib
import logging
from pathlib import Path

from app.analysis.analyzers.calls import aggregate_calls
from app.analysis.analyzers.classes import aggregate_classes
from app.analysis.analyzers.dependencies import build_dependencies
from app.analysis.analyzers.functions import aggregate_functions
from app.analysis.analyzers.imports import aggregate_imports
from app.analysis.analyzers.symbols import build_symbols
from app.analysis.file_discovery import discover_files
from app.analysis.models import (
    FileAnalysisStatus,
    FileInfo,
    ParseErrorInfo,
    RepositoryAnalysis,
)
from app.analysis.tree_sitter.languages.base import LanguageExtractionResult
from app.analysis.tree_sitter.languages.dispatch import extract_for_language
from app.analysis.tree_sitter.parser import parse_source
from app.analysis.tree_sitter.registry import detect_language
from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def analyze_repository(
    workspace_root: Path, *, repository_id: str, commit_sha: str | None
) -> RepositoryAnalysis:
    """
    Discover, parse, and structurally analyze every supported source file
    under `workspace_root`. One bad file (parse error, unreadable, too
    large) is recorded and skipped — it never aborts analysis of the rest
    of the repository.
    """
    settings = get_settings()
    max_size = settings.ANALYSIS_MAX_FILE_SIZE_BYTES

    files: list[FileInfo] = []
    parse_errors: list[ParseErrorInfo] = []
    extraction_results: list[LanguageExtractionResult] = []
    languages_seen: set = set()

    for discovered in discover_files(workspace_root):
        language = detect_language(discovered.relative_path)

        if language is None:
            files.append(
                FileInfo(
                    path=discovered.relative_path,
                    language=None,
                    size_bytes=discovered.size_bytes,
                    content_hash="",
                    status=FileAnalysisStatus.SKIPPED_UNSUPPORTED,
                )
            )
            continue

        if discovered.size_bytes > max_size:
            files.append(
                FileInfo(
                    path=discovered.relative_path,
                    language=language,
                    size_bytes=discovered.size_bytes,
                    content_hash="",
                    status=FileAnalysisStatus.SKIPPED_TOO_LARGE,
                )
            )
            continue

        try:
            source_bytes = discovered.absolute_path.read_bytes()
        except OSError as exc:
            logger.warning("Could not read %s: %s", discovered.relative_path, exc)
            files.append(
                FileInfo(
                    path=discovered.relative_path,
                    language=language,
                    size_bytes=discovered.size_bytes,
                    content_hash="",
                    status=FileAnalysisStatus.SKIPPED_UNREADABLE,
                )
            )
            continue

        content_hash = _content_hash(source_bytes)
        parsed = parse_source(source_bytes, language)

        if parsed.tree is None or parsed.root_node is None:
            parse_errors.append(
                ParseErrorInfo(file=discovered.relative_path, message=parsed.error_message or "unknown parse failure")
            )
            files.append(
                FileInfo(
                    path=discovered.relative_path,
                    language=language,
                    size_bytes=discovered.size_bytes,
                    content_hash=content_hash,
                    status=FileAnalysisStatus.PARSE_ERROR,
                )
            )
            continue

        languages_seen.add(language)

        if parsed.has_error:
            # Tree-sitter still produces a (partial) tree even with syntax
            # errors — we extract what we can AND record the parse error,
            # rather than throwing the whole file away.
            parse_errors.append(
                ParseErrorInfo(file=discovered.relative_path, message=parsed.error_message or "syntax error")
            )

        try:
            extraction = extract_for_language(language, parsed.root_node, source_bytes, discovered.relative_path)
            extraction_results.append(extraction)
        except Exception as exc:  # noqa: BLE001 - one file's extractor bug must not abort the run
            logger.exception("Structural extraction failed for %s", discovered.relative_path)
            parse_errors.append(ParseErrorInfo(file=discovered.relative_path, message=f"extraction error: {exc}"))
            files.append(
                FileInfo(
                    path=discovered.relative_path,
                    language=language,
                    size_bytes=discovered.size_bytes,
                    content_hash=content_hash,
                    status=FileAnalysisStatus.PARSE_ERROR,
                )
            )
            continue

        files.append(
            FileInfo(
                path=discovered.relative_path,
                language=language,
                size_bytes=discovered.size_bytes,
                content_hash=content_hash,
                status=FileAnalysisStatus.PARSE_ERROR if parsed.has_error else FileAnalysisStatus.ANALYZED,
            )
        )

    classes = aggregate_classes(extraction_results)
    functions = aggregate_functions(extraction_results)
    imports = aggregate_imports(extraction_results)
    calls = aggregate_calls(extraction_results)
    symbols = build_symbols(classes, functions)
    dependencies = build_dependencies(imports)

    return RepositoryAnalysis(
        repository_id=repository_id,
        commit_sha=commit_sha,
        languages=sorted(languages_seen, key=lambda l: l.value),
        files=files,
        symbols=symbols,
        classes=classes,
        functions=functions,
        imports=imports,
        calls=calls,
        dependencies=dependencies,
        parse_errors=parse_errors,
    )
