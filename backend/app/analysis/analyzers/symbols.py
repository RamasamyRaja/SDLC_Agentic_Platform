"""
Derives a unified `Symbol` table from already-extracted classes and
functions. This is a convenience index (e.g. "give me every named thing in
the repository") rather than a new extraction step — classes/functions
remain the source of truth for their own detail (methods, parameters, etc).

Variable/declaration-level symbols are explicitly out of scope for this
milestone (see class/function docstrings) — tracked here as a documented
limitation rather than silently pretended to be complete.
"""
from app.analysis.models import ClassInfo, FunctionInfo, Symbol, SymbolKind


def build_symbols(classes: list[ClassInfo], functions: list[FunctionInfo]) -> list[Symbol]:
    symbols: list[Symbol] = []

    for cls in classes:
        symbols.append(Symbol(name=cls.name, kind=SymbolKind.CLASS, file=cls.file, line=cls.line))

    for fn in functions:
        kind = SymbolKind.METHOD if fn.enclosing_class else SymbolKind.FUNCTION
        symbols.append(Symbol(name=fn.name, kind=kind, file=fn.file, line=fn.line))

    return symbols
