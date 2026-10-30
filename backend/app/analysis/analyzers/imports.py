from app.analysis.models import ImportInfo
from app.analysis.tree_sitter.languages.base import LanguageExtractionResult


def aggregate_imports(results: list[LanguageExtractionResult]) -> list[ImportInfo]:
    return [i for r in results for i in r.imports]
