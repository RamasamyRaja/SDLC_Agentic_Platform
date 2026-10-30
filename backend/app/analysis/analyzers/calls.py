from app.analysis.models import CallInfo
from app.analysis.tree_sitter.languages.base import LanguageExtractionResult


def aggregate_calls(results: list[LanguageExtractionResult]) -> list[CallInfo]:
    return [c for r in results for c in r.calls]
