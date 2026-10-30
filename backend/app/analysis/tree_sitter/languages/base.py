"""
Shared result type produced by each per-language extractor
(app/analysis/tree_sitter/languages/*.py).

Each language module walks its own Tree-sitter AST and returns one of these
— the analyzers package (app/analysis/analyzers/) then just aggregates
these across files. This keeps language-specific AST-node-type knowledge
confined to one file per language, while everything downstream works with
the same plain shape regardless of language.
"""
from dataclasses import dataclass, field

from app.analysis.models import CallInfo, ClassInfo, FunctionInfo, ImportInfo


@dataclass
class LanguageExtractionResult:
    classes: list[ClassInfo] = field(default_factory=list)
    functions: list[FunctionInfo] = field(default_factory=list)
    imports: list[ImportInfo] = field(default_factory=list)
    calls: list[CallInfo] = field(default_factory=list)
