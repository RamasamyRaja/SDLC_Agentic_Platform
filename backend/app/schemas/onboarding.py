"""
Pydantic schemas for the repository onboarding operation and its persisted
summary. The full per-symbol analysis result (classes/functions/imports/
calls/dependencies) is included in the onboarding response ONLY — it is not
persisted, so it cannot be reconstructed later from GET /analysis. See
app/models/repository.py's module docstring for why.
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.analysis.models import (
    CallInfo,
    ClassInfo,
    DependencyEdge,
    FileInfo,
    FunctionInfo,
    ImportInfo,
    ParseErrorInfo,
    Symbol,
)
from app.models.repository import RepositoryStatus


class OnboardRepositoryRequest(BaseModel):
    # Optional override of the repository's stored default_branch for this
    # onboarding run only (does not persist a new default_branch).
    branch: str | None = Field(default=None, max_length=255)


class OnboardRepositoryResponse(BaseModel):
    repository_id: uuid.UUID
    status: RepositoryStatus
    workspace_path: str
    commit_sha: str | None
    languages: list[str]
    files_analyzed: int
    files_skipped: int
    parse_error_count: int
    parse_errors: list[ParseErrorInfo]

    # Full in-memory analysis detail — returned here only, not persisted.
    symbols: list[Symbol]
    classes: list[ClassInfo]
    functions: list[FunctionInfo]
    imports: list[ImportInfo]
    calls: list[CallInfo]
    dependencies: list[DependencyEdge]
    files: list[FileInfo]


class RepositoryAnalysisSummaryResponse(BaseModel):
    """Persisted onboarding summary only (see module docstring) — GET /analysis."""

    model_config = ConfigDict(from_attributes=True)

    repository_id: uuid.UUID = Field(validation_alias="id")
    status: RepositoryStatus
    commit_sha: str | None
    detected_languages: list[str] | None
    files_analyzed_count: int | None
    files_skipped_count: int | None
    parse_error_count: int | None
    last_onboarded_at: datetime | None
    onboarding_error: str | None
    summary: str | None = None
