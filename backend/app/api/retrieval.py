"""
Semantic indexing/search endpoints, nested under
/api/repositories/{repository_id}/... alongside onboarding.
"""
import uuid
from collections import Counter

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.rbac import Permission, require_permission
from app.db.session import get_db
from app.models.user import User
from app.retrieval import retrieval_service
from app.schemas.retrieval import (
    IndexingStatusResponse,
    IndexRepositoryResponse,
    SearchRequest,
    SearchResponseSchema,
)

router = APIRouter(prefix="/api/repositories/{repository_id}", tags=["repository-retrieval"])


@router.post("/index", response_model=IndexRepositoryResponse, status_code=201)
def index_repository(
    repository_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.REPOSITORY_WRITE)),
) -> IndexRepositoryResponse:
    summary = retrieval_service.index_repository(db, user=current_user, repository_id=repository_id)
    repository = retrieval_service.get_indexing_status(db, user=current_user, repository_id=repository_id)

    return IndexRepositoryResponse(
        repository_id=repository.id,
        status=repository.indexing_status,
        chunks_created=summary.chunks_created,
        chunks_unchanged=summary.chunks_unchanged,
        chunks_removed=summary.chunks_removed,
        embeddings_generated=summary.embeddings_generated,
        total_chunks=summary.total_chunks,
    )


@router.get("/index/status", response_model=IndexingStatusResponse)
def get_index_status(
    repository_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.REPOSITORY_READ)),
) -> IndexingStatusResponse:
    repository = retrieval_service.get_indexing_status(db, user=current_user, repository_id=repository_id)
    return IndexingStatusResponse.model_validate(repository)


@router.post("/search", response_model=SearchResponseSchema)
def search_repository(
    repository_id: uuid.UUID,
    payload: SearchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.REPOSITORY_READ)),
) -> SearchResponseSchema:
    result = retrieval_service.search(
        db, user=current_user, repository_id=repository_id, query=payload.query, top_k=payload.top_k
    )
    return SearchResponseSchema(query=result.query, results=result.results, warnings=result.warnings)


@router.get("/status")
def get_repository_readiness(
    repository_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.REPOSITORY_READ)),
) -> dict:
    """
    Real onboarding / indexing state for the repository page. Every number is read from the database; nothing is estimated.
    `chunks_done` / `chunks_total` describe only the current (or last) embedding run, which may cover only changed files.
    """
    from app.models.repository_document import RepositoryDocument
    from app.retrieval.retrieval_service import index_warnings
    from app.services import onboarding_service

    repo = retrieval_service.get_indexing_status(db, user=current_user, repository_id=repository_id)
    docs = db.query(RepositoryDocument.analysis_status, RepositoryDocument.language, RepositoryDocument.content_hash,
                    RepositoryDocument.indexed_content_hash).filter(RepositoryDocument.repository_id == repo.id).all()
    by_status = Counter(d[0].value if hasattr(d[0], "value") else str(d[0]) for d in docs)
    by_language = Counter(d[1] or "unknown" for d in docs)
    pending_files = sum(1 for d in docs if d[3] != d[2])
    onboarding_interrupted = onboarding_service.is_interrupted(repo)
    indexing_interrupted = retrieval_service._is_interrupted(repo)
    istatus = repo.indexing_status.value if hasattr(repo.indexing_status, "value") else str(repo.indexing_status)
    rstatus = repo.status.value if hasattr(repo.status, "value") else str(repo.status)
    warnings = index_warnings(repo)
    reasons: list[str] = []
    if rstatus in ("CLONING", "ANALYZING"):
        reasons.append("Onboarding interrupted - re-run onboard" if onboarding_interrupted else "Onboarding in progress")
    elif rstatus != "READY":
        reasons.append(f"Repository status is {rstatus}")
    if istatus == "INDEXING":
        reasons.append("Indexing interrupted - re-run index to resume" if indexing_interrupted else "Indexing in progress")
    elif istatus == "FAILED":
        reasons.append("Indexing failed: " + (repo.indexing_error or "unknown error"))
    elif istatus != "INDEXED":
        reasons.append("Repository has not been indexed yet")
    if istatus == "INDEXED" and pending_files:
        reasons.append(f"{pending_files} file(s) changed since they were last indexed")
    reasons += warnings
    ready = istatus == "INDEXED" and not warnings and not pending_files
    return {
        "repository_id": str(repo.id),
        "status": rstatus,
        "error": repo.onboarding_error,
        "onboarding": {"phase": repo.onboarding_phase, "started_at": repo.onboarding_started_at, "interrupted": onboarding_interrupted},
        "indexing": {"status": istatus, "phase": repo.indexing_phase, "started_at": repo.indexing_started_at,
                     "chunks_done": repo.indexing_chunks_done, "chunks_total": repo.indexing_chunks_total,
                     "indexed_chunk_count": repo.indexed_chunk_count, "last_indexed_at": repo.last_indexed_at,
                     "indexed_commit_sha": repo.indexed_commit_sha, "error": repo.indexing_error, "interrupted": indexing_interrupted},
        "commit_sha": repo.commit_sha,
        "documents": {"total": len(docs), "by_status": dict(by_status), "by_language": dict(by_language), "pending_index": pending_files},
        "stale": bool(warnings) or bool(pending_files),
        "ready_for_retrieval": ready,
        "reasons": reasons,
    }
