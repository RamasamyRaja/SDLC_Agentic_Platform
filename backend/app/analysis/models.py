"""
Typed output models for the structural analysis layer.

These are plain Pydantic models (not DB models / not API schemas) — they
represent the deterministic analysis result in memory and are what
`AnalysisService.analyze_repository` returns. Only a summary of this is
persisted to PostgreSQL (see app/models/repository_document.py and the
`Repository` summary columns); the full per-symbol breakdown is intentionally
not stored, to avoid building a large graph structure inside PostgreSQL this
early (see README "Milestone 3" for the rationale).
"""
import enum

from pydantic import BaseModel, Field


class SupportedLanguage(str, enum.Enum):
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    JAVA = "java"


class FileAnalysisStatus(str, enum.Enum):
    ANALYZED = "ANALYZED"
    PARSE_ERROR = "PARSE_ERROR"
    SKIPPED_UNSUPPORTED = "SKIPPED_UNSUPPORTED"
    SKIPPED_TOO_LARGE = "SKIPPED_TOO_LARGE"
    SKIPPED_UNREADABLE = "SKIPPED_UNREADABLE"


class FileInfo(BaseModel):
    path: str = Field(..., description="Repository-relative file path")
    language: SupportedLanguage | None = None
    size_bytes: int
    content_hash: str
    status: FileAnalysisStatus


class SymbolKind(str, enum.Enum):
    CLASS = "CLASS"
    FUNCTION = "FUNCTION"
    METHOD = "METHOD"
    VARIABLE = "VARIABLE"


class Symbol(BaseModel):
    name: str
    kind: SymbolKind
    file: str
    line: int  # 1-indexed


class ClassInfo(BaseModel):
    name: str
    file: str
    line: int
    # Added in Milestone 4 (additive — every existing field/behavior from
    # Milestone 3 is unchanged): the class body's last line, needed to
    # extract exact source text for chunking. Falls back to `line` itself
    # if the extractor couldn't determine an end position.
    end_line: int = 0
    methods: list[str] = Field(default_factory=list)


class FunctionInfo(BaseModel):
    name: str
    file: str
    line: int
    end_line: int = 0  # see ClassInfo.end_line
    enclosing_class: str | None = None
    parameters: list[str] = Field(default_factory=list)


class ImportInfo(BaseModel):
    file: str
    imported: str  # module/package name, as written in source — not resolved to a filesystem path
    line: int


class CallInfo(BaseModel):
    file: str
    caller: str | None = Field(
        default=None, description="Enclosing function/method name, if known, else None (module-level call)"
    )
    callee: str = Field(..., description="Called function/method name, as written — not resolved to a definition")
    line: int


class DependencyEdge(BaseModel):
    """
    A deterministically-inferable file-to-module relationship, derived
    directly from an ImportInfo entry. This is NOT a resolved import graph —
    `target` is the raw imported name, and whether it maps to another file
    in this repository, a third-party package, or the standard library is
    left unresolved at this milestone.
    """

    from_file: str
    target: str


class ParseErrorInfo(BaseModel):
    file: str
    message: str


class RepositoryAnalysis(BaseModel):
    repository_id: str
    commit_sha: str | None
    languages: list[SupportedLanguage] = Field(default_factory=list)
    files: list[FileInfo] = Field(default_factory=list)
    symbols: list[Symbol] = Field(default_factory=list)
    classes: list[ClassInfo] = Field(default_factory=list)
    functions: list[FunctionInfo] = Field(default_factory=list)
    imports: list[ImportInfo] = Field(default_factory=list)
    calls: list[CallInfo] = Field(default_factory=list)
    dependencies: list[DependencyEdge] = Field(default_factory=list)
    parse_errors: list[ParseErrorInfo] = Field(default_factory=list)

    @property
    def files_analyzed_count(self) -> int:
        return sum(1 for f in self.files if f.status == FileAnalysisStatus.ANALYZED)

    @property
    def files_skipped_count(self) -> int:
        return sum(1 for f in self.files if f.status != FileAnalysisStatus.ANALYZED)
