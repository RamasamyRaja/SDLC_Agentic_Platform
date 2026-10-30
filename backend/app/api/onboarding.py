"""
Repository onboarding endpoints: clone + structural analysis only.

Nested under /api/repositories/{repository_id}/... alongside the Milestone
2 repository CRUD router. Onboarding is synchronous in this milestone (no
LangGraph/background task infra exists yet) — the request blocks until
clone + analysis complete, and returns the full result directly.
"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.rbac import Permission, require_permission
from app.db.session import get_db
from app.models.user import User
from app.schemas.onboarding import (
    OnboardRepositoryRequest,
    OnboardRepositoryResponse,
    RepositoryAnalysisSummaryResponse,
)
from app.schemas.repository_document import RepositoryDocumentResponse
from app.schemas.file_content import FileContentResponse
from app.core.config import get_settings
from app.tools.base import get_onboarded_workspace
from app.tools.path_safety import resolve_safe_relative_path
from app.tools.exceptions import FileTooLargeError, ToolFileNotFoundError, PathSecurityError
from app.services import onboarding_service

router = APIRouter(prefix="/api/repositories/{repository_id}", tags=["repository-onboarding"])


@router.post("/onboard", response_model=OnboardRepositoryResponse, status_code=201)
def onboard_repository(
    repository_id: uuid.UUID,
    payload: OnboardRepositoryRequest = OnboardRepositoryRequest(),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.REPOSITORY_WRITE)),
) -> OnboardRepositoryResponse:
    repository, analysis = onboarding_service.onboard_repository(
        db, user=current_user, repository_id=repository_id, branch_override=payload.branch
    )

    return OnboardRepositoryResponse(
        repository_id=repository.id,
        status=repository.status,
        workspace_path=repository.workspace_path,
        commit_sha=repository.commit_sha,
        languages=[lang.value for lang in analysis.languages],
        files_analyzed=analysis.files_analyzed_count,
        files_skipped=analysis.files_skipped_count,
        parse_error_count=len(analysis.parse_errors),
        parse_errors=analysis.parse_errors,
        symbols=analysis.symbols,
        classes=analysis.classes,
        functions=analysis.functions,
        imports=analysis.imports,
        calls=analysis.calls,
        dependencies=analysis.dependencies,
        files=analysis.files,
    )


@router.get("/analysis", response_model=RepositoryAnalysisSummaryResponse)
def get_analysis_summary(
    repository_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.REPOSITORY_READ)),
) -> RepositoryAnalysisSummaryResponse:
    repository = onboarding_service.get_repository_for_analysis(
        db, user=current_user, repository_id=repository_id
    )
    response = RepositoryAnalysisSummaryResponse.model_validate(repository)
    langs = ", ".join(repository.detected_languages or []) or "none detected"
    response.summary = f"Analyzed {repository.files_analyzed_count or 0} source files; skipped {repository.files_skipped_count or 0}; parse errors {repository.parse_error_count or 0}; languages: {langs}."
    return response


@router.get("/documents", response_model=list[RepositoryDocumentResponse])
def list_repository_documents(
    repository_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.REPOSITORY_READ)),
) -> list[RepositoryDocumentResponse]:
    documents = onboarding_service.get_repository_documents(
        db, user=current_user, repository_id=repository_id
    )
    return [RepositoryDocumentResponse.model_validate(d) for d in documents]


@router.get("/files/content", response_model=FileContentResponse)
def get_file_content(repository_id: uuid.UUID, path: str, start_line: int | None = None, end_line: int | None = None, db: Session = Depends(get_db), current_user: User = Depends(require_permission(Permission.REPOSITORY_READ))) -> FileContentResponse:
    settings = get_settings()
    workspace = get_onboarded_workspace(db, user=current_user, repository_id=repository_id)
    try:
        target = resolve_safe_relative_path(workspace, path)
    except Exception as exc:
        raise PathSecurityError(str(exc)) from exc
    if not target.exists() or not target.is_file():
        raise ToolFileNotFoundError(f"File not found: {path}")
    size = target.stat().st_size
    if size > settings.TOOL_MAX_FILE_SIZE_BYTES:
        raise FileTooLargeError(f"File exceeds configured read limit: {size} bytes")
    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise PathSecurityError("File is not valid UTF-8 text") from exc
    lines = content.splitlines()
    start = max(1, start_line or 1)
    end = min(len(lines), end_line or len(lines))
    rendered = "\n".join(lines[start-1:end])
    truncated = len(rendered) > settings.TOOL_MAX_FILE_SIZE_BYTES
    if truncated: rendered = rendered[:settings.TOOL_MAX_FILE_SIZE_BYTES]
    language_map = {".py":"python",".js":"javascript",".ts":"typescript",".tsx":"typescript",".jsx":"javascript",".java":"java",".html":"html",".css":"css",".scss":"scss",".json":"json",".md":"markdown",".yml":"yaml",".yaml":"yaml"}
    return FileContentResponse(path=path, language=language_map.get(target.suffix.lower(), "text"), content=rendered, lines=len(lines), size=size, truncated=truncated)
