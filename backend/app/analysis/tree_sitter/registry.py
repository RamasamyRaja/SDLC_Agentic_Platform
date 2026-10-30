"""
Language registry: maps file extensions to `SupportedLanguage`, and
`SupportedLanguage` to a compiled Tree-sitter `Language` grammar + `Parser`.

This is the one place new languages get wired in — everything else in the
analysis layer (file discovery, analyzers) is written against
`SupportedLanguage`, never against raw file extensions or grammar modules.
Adding a language means adding one entry to `_EXTENSION_TO_LANGUAGE` and one
factory function to `_LANGUAGE_FACTORIES` — no other module needs to change.
"""
from functools import lru_cache

from tree_sitter import Language, Parser

from app.analysis.models import SupportedLanguage

_EXTENSION_TO_LANGUAGE: dict[str, SupportedLanguage] = {
    ".py": SupportedLanguage.PYTHON,
    ".js": SupportedLanguage.JAVASCRIPT,
    ".jsx": SupportedLanguage.JAVASCRIPT,
    ".mjs": SupportedLanguage.JAVASCRIPT,
    ".ts": SupportedLanguage.TYPESCRIPT,
    ".tsx": SupportedLanguage.TYPESCRIPT,
    ".java": SupportedLanguage.JAVA,
}


def _load_python_language() -> Language:
    import tree_sitter_python as ts_mod

    return Language(ts_mod.language())


def _load_javascript_language() -> Language:
    import tree_sitter_javascript as ts_mod

    return Language(ts_mod.language())


def _load_typescript_language() -> Language:
    import tree_sitter_typescript as ts_mod

    # tree-sitter-typescript ships two grammars: plain TypeScript and TSX.
    # We standardize on the TypeScript grammar; .tsx files are close enough
    # syntactically for the structural extraction this milestone performs
    # (classes/functions/imports/calls). A dedicated TSX grammar can be
    # added later without changing this registry's public interface.
    return Language(ts_mod.language_typescript())


def _load_java_language() -> Language:
    import tree_sitter_java as ts_mod

    return Language(ts_mod.language())


_LANGUAGE_FACTORIES = {
    SupportedLanguage.PYTHON: _load_python_language,
    SupportedLanguage.JAVASCRIPT: _load_javascript_language,
    SupportedLanguage.TYPESCRIPT: _load_typescript_language,
    SupportedLanguage.JAVA: _load_java_language,
}


def detect_language(file_path: str) -> SupportedLanguage | None:
    """Detect language from a file path's extension. Returns None if unsupported."""
    for ext, language in _EXTENSION_TO_LANGUAGE.items():
        if file_path.endswith(ext):
            return language
    return None


def supported_extensions() -> set[str]:
    return set(_EXTENSION_TO_LANGUAGE.keys())


@lru_cache(maxsize=None)
def get_language(language: SupportedLanguage) -> Language:
    """Return the compiled Tree-sitter grammar for a language (cached — grammars are immutable)."""
    factory = _LANGUAGE_FACTORIES.get(language)
    if factory is None:
        raise ValueError(f"No Tree-sitter grammar registered for language: {language}")
    return factory()


def get_parser(language: SupportedLanguage) -> Parser:
    """
    Return a fresh Parser bound to the given language's grammar.

    A new Parser instance is returned each call (Parsers are cheap and not
    guaranteed thread-safe to share), while the underlying compiled Language
    grammar is cached via `get_language`.
    """
    return Parser(get_language(language))
