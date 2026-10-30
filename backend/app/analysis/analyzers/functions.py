from app.analysis.models import FunctionInfo
from app.analysis.tree_sitter.languages.base import LanguageExtractionResult


def aggregate_functions(results: list[LanguageExtractionResult]) -> list[FunctionInfo]:
    return [f for r in results for f in r.functions]
