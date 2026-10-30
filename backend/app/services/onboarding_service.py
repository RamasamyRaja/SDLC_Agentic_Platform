"""
Repository onboarding service.

Orchestrates: fetch repository record -> clone -> checkout branch -> record
commit SHA -> run structural analysis -> persist RepositoryDocument rows and
a summary on the Repository row. Does NOT execute any repository code, does
NOT call Mistral, does NOT start LangGraph — purely clone + static analysis.

One bad source file never aborts the whole run (see AnalysisService); a
*clone* failure, however, is fatal to onboarding by definition (there is no
repository to analyze) and is recorded on the Repository row as ERROR with
`onboarding_error` set, then re-raised so the API returns a clear error.
"""
import logging
from datetime import datetime, timezone

from datetime import timedelta

from sqlalchemy.orm import Session

from app.analysis.models import FileAnalysisStatus, RepositoryAnalysis
from app.analysis.service import analyze_repository
from app.core.config import get_settings
from app.core.exceptions import BranchNotFoundError, NotFoundError, RepositoryCloneError, WorkflowStateError
from app.models.repository import Repository, RepositoryStatus
from app.models.repository_document import DocumentAnalysisStatus, RepositoryDocument
from app.models.user import User
from app.services import git_service, workspace_service
from app.services.repository_service import get_repository

from app.core.redaction import redact

logger = logging.getLogger(__name__)

# Maps the in-memory analysis file status to the persisted document status.
# Kept as an explicit table (not a shared enum) because the two enums serve
# different layers (ephemeral analysis result vs. persisted row) and are
# allowed to diverge independently.
_FILE_STATUS_TO_DOCUMENT_STATUS = {
    FileAnalysisStatus.ANALYZED: DocumentAnalysisStatus.ANALYZED,
    FileAnalysisStatus.PARSE_ERROR: DocumentAnalysisStatus.PARSE_ERROR,
    FileAnalysisStatus.SKIPPED_UNSUPPORTED: DocumentAnalysisStatus.SKIPPED_UNSUPPORTED,
    FileAnalysisStatus.SKIPPED_TOO_LARGE: DocumentAnalysisStatus.SKIPPED_TOO_LARGE,
    FileAnalysisStatus.SKIPPED_UNREADABLE: DocumentAnalysisStatus.SKIPPED_UNREADABLE,
}


def _purge_vectors(chunk_ids: list[str], repository_id: str) -> None:
    """Remove vectors of chunks that no longer exist. Best effort: a failure is logged and later reconciled by indexing."""
    if not chunk_ids:
        return
    try:
        from app.retrieval.milvus_client import MilvusVectorStore
        MilvusVectorStore(dimension=get_settings().EMBEDDING_DIMENSION).delete_by_ids(chunk_ids)
    except Exception:  # noqa: BLE001
        logger.exception("Could not delete %d stale vectors for repository %s", len(chunk_ids), repository_id)


def _persist_documents(db: Session, repository: Repository, analysis: RepositoryAnalysis) -> None:
    """
    Upsert by path. Documents keep their id (and therefore their chunks and embeddings) while their path exists, so
    re-onboarding no longer wipes the semantic index; only files that disappeared are removed, together with their vectors.
    """
    from app.models.code_chunk import CodeChunk

    existing = {d.file_path: d for d in db.query(RepositoryDocument).filter(RepositoryDocument.repository_id == repository.id).all()}
    seen: set[str] = set()
    for fi in analysis.files:
        seen.add(fi.path)
        doc = existing.get(fi.path)
        status = _FILE_STATUS_TO_DOCUMENT_STATUS[fi.status]
        if doc is None:
            db.add(RepositoryDocument(repository_id=repository.id, file_path=fi.path, language=fi.language.value if fi.language else None,
                                      file_size=fi.size_bytes, content_hash=fi.content_hash, analysis_status=status))
        else:
            doc.language = fi.language.value if fi.language else None
            doc.file_size, doc.content_hash, doc.analysis_status = fi.size_bytes, fi.content_hash, status
            db.add(doc)
    gone = [d for path, d in existing.items() if path not in seen]
    gone_chunk_ids = [str(cid) for (cid,) in db.query(CodeChunk.id).filter(CodeChunk.repository_document_id.in_([d.id for d in gone])).all()] if gone else []
    for d in gone:
        db.delete(d)
    db.flush()
    _purge_vectors(gone_chunk_ids, str(repository.id))


def is_interrupted(repository: Repository) -> bool:
    """CLONING/ANALYZING with no progress for REPO_STALE_AFTER_SECONDS: the worker is gone."""
    from datetime import datetime, timezone
    if repository.status not in (RepositoryStatus.CLONING, RepositoryStatus.ANALYZING):
        return False
    ts = repository.updated_at if repository.updated_at.tzinfo else repository.updated_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - ts > timedelta(seconds=get_settings().REPO_STALE_AFTER_SECONDS)


def _phase(db: Session, repository: Repository, phase: str, status: RepositoryStatus | None = None) -> None:
    repository.onboarding_phase = phase
    if status is not None:
        repository.status = status
    db.add(repository)
    db.commit()


def onboard_repository(
    db: Session, *, user: User, repository_id, branch_override: str | None = None
) -> tuple[Repository, RepositoryAnalysis]:
    """
    Run the full onboarding pipeline for a repository the user owns.

    Returns the updated `Repository` row and the full in-memory
    `RepositoryAnalysis` (the latter is never persisted in full — see
    module docstring).
    """
    repository = get_repository(db, user=user, repository_id=repository_id)

    branch = branch_override or repository.default_branch
    if not branch_override and repository.default_branch_source == "fallback":
        # The branch recorded at registration was only a guess (remote was unreachable then). Ask the remote now.
        detected = git_service.resolve_remote_default_branch(repository.url)
        if detected:
            branch = repository.default_branch = detected
            repository.default_branch_source = "remote_head"

    if repository.status in (RepositoryStatus.CLONING, RepositoryStatus.ANALYZING) and not is_interrupted(repository):
        raise WorkflowStateError(f"Repository {repository.id} is already being onboarded ({repository.status.value}); wait for it to finish.")
    from datetime import datetime, timezone
    repository.status = RepositoryStatus.CLONING
    repository.onboarding_phase = "CLONING"
    repository.onboarding_started_at = datetime.now(timezone.utc)
    repository.onboarding_error = None
    db.add(repository)
    db.commit()

    try:
        workspace_path = workspace_service.ensure_clean_workspace(repository.id)
    except Exception as exc:  # noqa: BLE001 - any workspace failure is fatal to onboarding
        repository.status = RepositoryStatus.ERROR
        repository.onboarding_error = redact(f"Workspace setup failed: {exc}")[:2000]
        db.add(repository)
        db.commit()
        raise

    try:
        git_repo = git_service.clone_repository(repository.url, workspace_path, branch=branch)
    except BranchNotFoundError as first_error:
        # Existing records may have been created with the historical "main"
        # default. Resolve the remote's advertised HEAD and retry once rather
        # than requiring users to guess whether the repository uses main/master.
        detected_branch = git_service.resolve_remote_default_branch(repository.url)
        if not detected_branch or detected_branch == branch:
            repository.status = RepositoryStatus.ERROR
            repository.onboarding_error = str(first_error)[:2000]
            db.add(repository)
            db.commit()
            raise
        try:
            workspace_path = workspace_service.ensure_clean_workspace(repository.id)
            git_repo = git_service.clone_repository(
                repository.url, workspace_path, branch=detected_branch
            )
            branch = detected_branch
            repository.default_branch = detected_branch
            repository.default_branch_source = "remote_head"
        except (RepositoryCloneError, BranchNotFoundError) as retry_error:
            repository.status = RepositoryStatus.ERROR
            repository.onboarding_error = str(retry_error)[:2000]
            db.add(repository)
            db.commit()
            raise
    except RepositoryCloneError as exc:
        repository.status = RepositoryStatus.ERROR
        repository.onboarding_error = str(exc)[:2000]
        db.add(repository)
        db.commit()
        raise

    commit_sha = git_service.get_current_commit_sha(git_repo)
    actual_branch = git_service.get_default_branch_name(git_repo)   # what was really checked out
    if actual_branch and actual_branch != repository.default_branch and not branch_override:
        repository.default_branch = actual_branch
        repository.default_branch_source = "remote_head"

    repository.workspace_path = str(workspace_path)
    repository.commit_sha = commit_sha
    _phase(db, repository, "ANALYZING", RepositoryStatus.ANALYZING)

    try:
        analysis = analyze_repository(
            workspace_path, repository_id=str(repository.id), commit_sha=commit_sha
        )
    except Exception as exc:  # noqa: BLE001 - an unexpected analysis-layer failure is still fatal
        logger.exception("Structural analysis failed for repository %s", repository.id)
        repository.status = RepositoryStatus.ERROR
        repository.onboarding_error = redact(f"Analysis failed: {exc}")[:2000]
        db.add(repository)
        db.commit()
        raise

    repository.onboarding_phase = "PERSISTING"
    _persist_documents(db, repository, analysis)

    repository.onboarding_phase = "DONE"
    repository.status = RepositoryStatus.READY
    repository.detected_languages = [lang.value for lang in analysis.languages]
    repository.files_analyzed_count = analysis.files_analyzed_count
    repository.files_skipped_count = analysis.files_skipped_count
    repository.parse_error_count = len(analysis.parse_errors)
    repository.last_onboarded_at = datetime.now(timezone.utc)
    db.add(repository)
    db.commit()
    db.refresh(repository)

    return repository, analysis


def get_repository_documents(db: Session, *, user: User, repository_id) -> list[RepositoryDocument]:
    repository = get_repository(db, user=user, repository_id=repository_id)
    return (
        db.query(RepositoryDocument)
        .filter(RepositoryDocument.repository_id == repository.id)
        .order_by(RepositoryDocument.file_path.asc())
        .all()
    )


def get_repository_for_analysis(db: Session, *, user: User, repository_id) -> Repository:
    """Thin re-export used by the analysis-summary endpoint — kept here so the
    router only imports from onboarding_service, not repository_service too."""
    repository = get_repository(db, user=user, repository_id=repository_id)
    if repository.last_onboarded_at is None:
        raise NotFoundError(
            f"Repository {repository_id} has not been onboarded yet — POST /onboard first"
        )
    return repository
