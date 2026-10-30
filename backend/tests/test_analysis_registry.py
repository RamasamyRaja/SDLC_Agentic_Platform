from app.analysis.models import SupportedLanguage
from app.analysis.tree_sitter.registry import detect_language, get_parser, supported_extensions


def test_detect_language_for_each_supported_extension():
    assert detect_language("Foo.py") == SupportedLanguage.PYTHON
    assert detect_language("Foo.js") == SupportedLanguage.JAVASCRIPT
    assert detect_language("Foo.jsx") == SupportedLanguage.JAVASCRIPT
    assert detect_language("Foo.ts") == SupportedLanguage.TYPESCRIPT
    assert detect_language("Foo.tsx") == SupportedLanguage.TYPESCRIPT
    assert detect_language("Foo.java") == SupportedLanguage.JAVA


def test_detect_language_returns_none_for_unsupported_extension():
    assert detect_language("README.md") is None
    assert detect_language("Makefile") is None
    assert detect_language("image.png") is None


def test_supported_extensions_matches_registry():
    exts = supported_extensions()
    assert {".py", ".js", ".ts", ".java"}.issubset(exts)


def test_get_parser_returns_working_parser_for_each_language():
    for language in SupportedLanguage:
        parser = get_parser(language)
        tree = parser.parse(b"")
        assert tree is not None
