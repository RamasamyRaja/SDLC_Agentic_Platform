"""
Derives file-to-module dependency edges directly from extracted imports.

This is intentionally NOT a resolved dependency graph: `DependencyEdge.target`
is the raw imported name as written in source (e.g. "./api", "java.util.List",
"os"). Whether that resolves to another file in this repository, a
third-party package, or the standard library is left unresolved — see
`DependencyEdge`'s docstring in app/analysis/models.py. Resolving imports to
concrete repository files is future work (likely alongside Milestone 4
repository indexing), not something this milestone claims to do.
"""
from app.analysis.models import DependencyEdge, ImportInfo


def build_dependencies(imports: list[ImportInfo]) -> list[DependencyEdge]:
    return [DependencyEdge(from_file=i.file, target=i.imported) for i in imports]
