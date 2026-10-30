"""
Dispatch table from `SupportedLanguage` to its extractor module's
`extract(root, source, file_path) -> LanguageExtractionResult` function.

This is the registry/factory pattern applied to extraction, mirroring
`app.analysis.tree_sitter.registry` for grammar selection. Adding a new
language means adding one entry here plus its extractor module — no
if/else chains elsewhere.
"""
from collections.abc import Callable

from tree_sitter import Node

from app.analysis.models import SupportedLanguage
from app.analysis.tree_sitter.languages import java, javascript, python, typescript
from app.analysis.tree_sitter.languages.base import LanguageExtractionResult

_EXTRACTORS: dict[SupportedLanguage, Callable[[Node, bytes, str], LanguageExtractionResult]] = {
    SupportedLanguage.PYTHON: python.extract,
    SupportedLanguage.JAVASCRIPT: javascript.extract,
    SupportedLanguage.TYPESCRIPT: typescript.extract,
    SupportedLanguage.JAVA: java.extract,
}


def extract_for_language(
    language: SupportedLanguage, root: Node, source: bytes, file_path: str
) -> LanguageExtractionResult:
    extractor = _EXTRACTORS.get(language)
    if extractor is None:
        raise ValueError(f"No structural extractor registered for language: {language}")
    return extractor(root, source, file_path)
