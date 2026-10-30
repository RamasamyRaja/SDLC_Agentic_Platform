from app.analysis.models import ClassInfo
from app.analysis.tree_sitter.languages.base import LanguageExtractionResult


def aggregate_classes(results: list[LanguageExtractionResult]) -> list[ClassInfo]:
    return [c for r in results for c in r.classes]
