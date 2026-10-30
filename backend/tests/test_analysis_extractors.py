from pathlib import Path

from app.analysis.models import SupportedLanguage
from app.analysis.tree_sitter.languages import java as java_extractor
from app.analysis.tree_sitter.languages import javascript as js_extractor
from app.analysis.tree_sitter.languages import python as py_extractor
from app.analysis.tree_sitter.languages import typescript as ts_extractor
from app.analysis.tree_sitter.parser import parse_source

FIXTURES = Path(__file__).parent / "fixtures"


def _read(relative_path: str) -> bytes:
    return (FIXTURES / relative_path).read_bytes()


def test_parse_python_fixture_has_no_error():
    source = _read("python_sample/investigation_service.py")
    parsed = parse_source(source, SupportedLanguage.PYTHON)
    assert parsed.has_error is False
    assert parsed.root_node is not None


def test_parse_java_fixture_has_no_error():
    source = _read("java_sample/InvestigationService.java")
    parsed = parse_source(source, SupportedLanguage.JAVA)
    assert parsed.has_error is False


def test_parse_typescript_fixture_has_no_error():
    source = _read("typescript_sample/investigation.ts")
    parsed = parse_source(source, SupportedLanguage.TYPESCRIPT)
    assert parsed.has_error is False


def test_parse_javascript_fixture_has_no_error():
    source = _read("javascript_sample/investigation.js")
    parsed = parse_source(source, SupportedLanguage.JAVASCRIPT)
    assert parsed.has_error is False


def test_parse_error_is_detected_for_malformed_python():
    source = b"class Foo:\n    def broken(:\n        pass"
    parsed = parse_source(source, SupportedLanguage.PYTHON)
    assert parsed.has_error is True
    assert parsed.error_message is not None


def test_python_extraction_finds_class_and_method():
    source = _read("python_sample/investigation_service.py")
    parsed = parse_source(source, SupportedLanguage.PYTHON)
    result = py_extractor.extract(parsed.root_node, source, "investigation_service.py")

    assert [c.name for c in result.classes] == ["InvestigationService"]
    assert result.classes[0].methods == ["delete_investigation"]
    assert [f.name for f in result.functions] == ["delete_investigation"]
    assert result.functions[0].enclosing_class == "InvestigationService"
    assert result.functions[0].parameters == ["self", "id"]
    assert [i.imported for i in result.imports] == ["os"]
    assert [c.callee for c in result.calls] == ["delete"]


def test_java_extraction_finds_class_and_method():
    source = _read("java_sample/InvestigationService.java")
    parsed = parse_source(source, SupportedLanguage.JAVA)
    result = java_extractor.extract(parsed.root_node, source, "InvestigationService.java")

    assert [c.name for c in result.classes] == ["InvestigationService"]
    assert result.classes[0].methods == ["deleteInvestigation"]
    assert result.functions[0].parameters == ["id"]
    assert [i.imported for i in result.imports] == ["java.util.List"]
    assert [c.callee for c in result.calls] == ["delete"]


def test_typescript_extraction_finds_exported_function():
    source = _read("typescript_sample/investigation.ts")
    parsed = parse_source(source, SupportedLanguage.TYPESCRIPT)
    result = ts_extractor.extract(parsed.root_node, source, "investigation.ts")

    assert [f.name for f in result.functions] == ["deleteInvestigation"]
    assert result.functions[0].parameters == ["id"]
    assert result.functions[0].enclosing_class is None
    assert [i.imported for i in result.imports] == ["./api"]
    assert [c.callee for c in result.calls] == ["delete"]


def test_javascript_extraction_finds_arrow_function():
    source = _read("javascript_sample/investigation.js")
    parsed = parse_source(source, SupportedLanguage.JAVASCRIPT)
    result = js_extractor.extract(parsed.root_node, source, "investigation.js")

    assert [f.name for f in result.functions] == ["deleteInvestigation"]
    assert result.functions[0].parameters == ["id"]
    assert [c.callee for c in result.calls] == ["delete"]
