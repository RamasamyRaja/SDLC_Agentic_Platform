"""
Deterministic structural code analysis.

Pipeline: file_discovery -> tree_sitter (parse) -> language extractors
(app/analysis/tree_sitter/languages/*.py) -> analyzers (aggregation) ->
`RepositoryAnalysis` (app/analysis/models.py).

`analyze_repository()` in service.py is the single entry point other code
should use. See README "Milestone 3" for the supported-language list and
known limitations (no cross-file/import resolution, no dynamic-language
support beyond Python/JS/TS/Java).
"""
