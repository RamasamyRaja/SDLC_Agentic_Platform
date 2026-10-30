"""
RetrievalService: the single entry point for semantic indexing and search.

index_repository(repository_id) -> chunk -> embed -> store in Milvus ->
persist CodeChunk/EmbeddingMetadata in PostgreSQL.

search(repository_id, query, top_k) -> embed query -> Milvus search
(repository-filtered) -> normalize into SearchResponse.

Nothing outside this module (routers, tests) should call chunking.py,
embeddings.py, or milvus_client.py directly for these operations.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.analysis.service import analyze_repository
from app.core.config import get_settings
from app.core.exceptions import NotFoundError, ValidationError, WorkflowStateError
from app.core.redaction import redact
from app.models.code_chunk import CodeChunk
from app.models.embedding_metadata import EmbeddingMetadata
from app.models.repository import IndexingStatus, Repository
from app.models.repository_document import DocumentAnalysisStatus, RepositoryDocument
from app.models.user import User
from app.retrieval.chunking import chunk_repository
from app.retrieval.embeddings import get_embedding_provider
from app.retrieval.milvus_client import MilvusVectorStore, VectorRecord
from app.retrieval import ranking
from app.retrieval.models import ChunkCandidate, IndexingSummary, SearchResponse, SearchResultItem
from app.services.repository_service import get_repository

logger = logging.getLogger(__name__)


def _get_vector_store() -> MilvusVectorStore:
    provider = get_embedding_provider()
    return MilvusVectorStore(dimension=provider.dimension)


def _is_interrupted(repository: Repository) -> bool:
    ts = repository.updated_at if repository.updated_at.tzinfo else repository.updated_at.replace(tzinfo=timezone.utc)
    return repository.indexing_status == IndexingStatus.INDEXING and \
        datetime.now(timezone.utc) - ts > timedelta(seconds=get_settings().REPO_STALE_AFTER_SECONDS)


def index_repository(db: Session, *, user: User, repository_id: uuid.UUID) -> IndexingSummary:
    """
    Incremental, resumable index of a repository.

    * Only documents whose content changed since they were last fully embedded (`indexed_content_hash`) are re-chunked;
      unchanged files keep their chunks and vectors untouched.
    * Chunks are embedded and stored in batches (INDEX_EMBED_BATCH_SIZE). Each batch commits PostgreSQL rows only after its
      vectors are stored, so after a crash every committed chunk has a vector; re-running resumes (already stored chunks are
      recognised by content hash) instead of starting over.
    * A concurrent request is refused (409) while a live run exists; a run with no progress for REPO_STALE_AFTER_SECONDS is
      treated as interrupted and may be restarted.
    * Orphan vectors (vector without a chunk row) are reconciled away at the end.
    """
    repository = get_repository(db, user=user, repository_id=repository_id)

    if repository.workspace_path is None:
        raise ValidationError(f"Repository {repository_id} has not been onboarded yet — POST /onboard first")
    workspace_path = Path(repository.workspace_path)
    if not workspace_path.exists():
        raise ValidationError(f"Repository {repository_id}'s workspace no longer exists on disk — re-run /onboard")
    if repository.indexing_status == IndexingStatus.INDEXING and not _is_interrupted(repository):
        raise WorkflowStateError(f"Repository {repository_id} is already being indexed; wait for it to finish.")

    repository.indexing_status = IndexingStatus.INDEXING
    repository.indexing_error = None
    repository.indexing_started_at = datetime.now(timezone.utc)
    repository.indexing_phase = "ANALYZING"
    repository.indexing_chunks_total = None
    repository.indexing_chunks_done = 0
    db.add(repository)
    db.commit()

    try:
        summary = _run_indexing(db, repository, workspace_path)
    except Exception as exc:  # noqa: BLE001 - any indexing failure must be recorded, not raised raw
        logger.exception("Indexing failed for repository %s", repository.id)
        db.rollback()
        repository = db.get(Repository, repository.id)
        repository.indexing_status = IndexingStatus.FAILED
        repository.indexing_error = redact(f"{exc.__class__.__name__}: {exc}")[:2000]
        repository.indexing_phase = "FAILED"
        db.add(repository)
        db.commit()
        raise

    repository.indexing_status = IndexingStatus.INDEXED
    repository.indexing_phase = "DONE"
    repository.indexed_chunk_count = summary.total_chunks
    repository.indexed_commit_sha = repository.commit_sha
    repository.last_indexed_at = datetime.now(timezone.utc)
    db.add(repository)
    db.commit()
    return summary


def _run_indexing(db: Session, repository: Repository, workspace_path: Path) -> IndexingSummary:
    settings = get_settings()
    analysis = analyze_repository(workspace_path, repository_id=str(repository.id), commit_sha=repository.commit_sha)

    documents = db.query(RepositoryDocument).filter(RepositoryDocument.repository_id == repository.id).all()
    document_ids_by_path = {d.file_path: str(d.id) for d in documents}
    path_by_document_id = {str(d.id): d.file_path for d in documents}
    indexable = {DocumentAnalysisStatus.ANALYZED, DocumentAnalysisStatus.PARSE_ERROR}
    # Documents that need work: content changed since last embedding, OR no longer indexable but still holding chunks.
    changed = {str(d.id) for d in documents if d.analysis_status in indexable and d.indexed_content_hash != d.content_hash}
    chunked_docs = {str(x) for (x,) in db.query(CodeChunk.repository_document_id).join(
        RepositoryDocument, CodeChunk.repository_document_id == RepositoryDocument.id).filter(RepositoryDocument.repository_id == repository.id).distinct().all()}
    stale_docs = {str(d.id) for d in documents if d.analysis_status not in indexable and str(d.id) in chunked_docs}
    # A document that is "up to date" but has lost its chunks (e.g. a manual cleanup) is also re-done.
    changed |= {str(d.id) for d in documents if d.analysis_status in indexable and str(d.id) not in chunked_docs}
    work_docs = changed | stale_docs

    file_contents_by_path: dict[str, str] = {}
    for fi in analysis.files:
        if document_ids_by_path.get(fi.path) not in changed:
            continue
        try:
            raw = (workspace_path / fi.path).read_bytes()
        except OSError:
            continue
        if b"\x00" in raw[:8192]:
            continue   # binary content behind a source extension: never embedded
        file_contents_by_path[fi.path] = raw.decode("utf-8", errors="replace")

    repository.indexing_phase = "CHUNKING"
    db.add(repository); db.commit()
    candidates = chunk_repository(analysis, document_ids_by_path=document_ids_by_path, file_contents_by_path=file_contents_by_path)

    existing_chunks = (db.query(CodeChunk).filter(CodeChunk.repository_document_id.in_([uuid.UUID(x) for x in work_docs])).all()) if work_docs else []
    existing_by_key = {(str(c.repository_document_id), c.content_hash): c for c in existing_chunks}
    total_all = (db.query(CodeChunk).join(RepositoryDocument, CodeChunk.repository_document_id == RepositoryDocument.id)
                 .filter(RepositoryDocument.repository_id == repository.id).count())

    unchanged = 0
    to_embed: list[tuple[ChunkCandidate, int]] = []
    for index, cand in enumerate(candidates):
        existing = existing_by_key.pop((cand.repository_document_id, cand.content_hash), None)
        if existing is not None:
            existing.chunk_index = index
            db.add(existing)
            unchanged += 1
        else:
            to_embed.append((cand, index))

    if total_all - len(existing_chunks) + len(candidates) > settings.INDEX_MAX_CHUNKS:
        raise ValidationError(f"The repository would hold more than INDEX_MAX_CHUNKS={settings.INDEX_MAX_CHUNKS} chunks; "
                              "raise the limit or exclude generated/vendored code. Nothing was indexed.")

    provider = get_embedding_provider()
    vector_store = _get_vector_store()
    repository.indexing_phase = "EMBEDDING"
    repository.indexing_chunks_total = len(to_embed)
    repository.indexing_chunks_done = 0
    db.add(repository); db.commit()

    created = embedded = 0
    size = max(1, settings.INDEX_EMBED_BATCH_SIZE)
    for start in range(0, len(to_embed), size):
        batch = to_embed[start:start + size]
        rows: list[CodeChunk] = []
        for cand, index in batch:
            row = CodeChunk(repository_document_id=uuid.UUID(cand.repository_document_id), chunk_index=index, chunk_type=cand.chunk_type,
                            symbol_name=cand.symbol_name, content_hash=cand.content_hash, start_line=cand.start_line, end_line=cand.end_line,
                            language=cand.language, content=cand.content)
            db.add(row)
            rows.append(row)
        db.flush()
        vectors = provider.embed([c.content for c, _ in batch])
        records = [VectorRecord(id=str(r.id), vector=v, repository_id=str(repository.id), code_chunk_id=str(r.id),
                                file_path=path_by_document_id.get(str(r.repository_document_id), ""), language=r.language or "",
                                chunk_type=r.chunk_type.value, symbol_name=r.symbol_name or "", content_hash=r.content_hash)
                   for r, v in zip(rows, vectors)]
        vector_store.upsert(records)          # vectors first ...
        for r in rows:
            db.add(EmbeddingMetadata(code_chunk_id=r.id, provider=provider.name, model_name=provider.model_name, dimension=provider.dimension,
                                     milvus_collection=vector_store.collection_name, milvus_id=str(r.id)))
        created += len(rows)
        embedded += len(vectors)
        repository.indexing_chunks_done = created
        db.add(repository)
        db.commit()                           # ... rows only after they have vectors

    removed_ids = [str(c.id) for c in existing_by_key.values()]
    for c in existing_by_key.values():
        db.delete(c)
    db.commit()
    if removed_ids:
        vector_store.delete_by_ids(removed_ids)

    repository.indexing_phase = "RECONCILING"
    db.add(repository); db.commit()
    pg_ids = {str(x) for (x,) in db.query(CodeChunk.id).join(RepositoryDocument, CodeChunk.repository_document_id == RepositoryDocument.id)
              .filter(RepositoryDocument.repository_id == repository.id).all()}
    orphans = list(vector_store.list_ids_for_repository(str(repository.id)) - pg_ids)
    for i in range(0, len(orphans), 500):
        vector_store.delete_by_ids(orphans[i:i + 500])
    if orphans:
        logger.warning("Removed %d orphan vectors for repository %s", len(orphans), repository.id)

    for d in documents:                       # only now are these documents "fully embedded"
        if str(d.id) in changed:
            d.indexed_content_hash = d.content_hash
            db.add(d)
    repository.indexed_files_count = len([d for d in documents if d.analysis_status in indexable])
    db.commit()

    return IndexingSummary(repository_id=str(repository.id), chunks_created=created, chunks_unchanged=unchanged + (total_all - len(existing_chunks)),
                           chunks_updated=0, chunks_removed=len(removed_ids), embeddings_generated=embedded, total_chunks=len(pg_ids))


def index_warnings(repository: Repository) -> list[str]:
    out = []
    if repository.indexed_commit_sha and repository.commit_sha and repository.indexed_commit_sha != repository.commit_sha:
        out.append(f"The index was built from commit {repository.indexed_commit_sha[:8]} but the repository is now at {repository.commit_sha[:8]}; "
                   "results may be stale - re-index.")
    return out


def search(db: Session, *, user: User, repository_id: uuid.UUID, query: str, top_k: int) -> SearchResponse:
    settings = get_settings()
    top_k = min(max(top_k, 1), settings.SEARCH_MAX_TOP_K)
    repository = get_repository(db, user=user, repository_id=repository_id)
    if repository.indexing_status != IndexingStatus.INDEXED:
        raise NotFoundError(f"Repository {repository_id} has not been indexed yet — POST /index first")

    provider = get_embedding_provider()
    vector_store = _get_vector_store()
    query_vector = provider.embed_one(query)
    fetch = top_k * max(1, settings.SEARCH_OVERFETCH_FACTOR) if settings.SEARCH_RERANK_ENABLED else top_k
    hits = vector_store.search(repository_id=str(repository.id), query_vector=query_vector, top_k=fetch)
    warnings = index_warnings(repository)
    if not hits:
        return SearchResponse(query=query, results=[], warnings=warnings)

    chunks_by_id = {str(c.id): c for c in db.query(CodeChunk).filter(CodeChunk.id.in_([uuid.UUID(h.code_chunk_id) for h in hits])).all()}
    cands = []
    for hit in hits:
        chunk = chunks_by_id.get(hit.code_chunk_id)
        if chunk is None:
            continue  # dangling vector: skip rather than fabricate content
        cands.append(ranking.Candidate(hit.code_chunk_id, hit.file_path, hit.symbol_name or None, chunk.content, chunk.content_hash, hit.score))
    if settings.SEARCH_RERANK_ENABLED:
        ranked = ranking.rerank(query, cands, top_k=top_k, lexical_weight=settings.SEARCH_LEXICAL_WEIGHT, max_per_file=settings.SEARCH_MAX_CHUNKS_PER_FILE)
    else:
        ranked = [(c, c.vector_score) for c in cands[:top_k]]
    hit_by_id = {h.code_chunk_id: h for h in hits}
    results = [SearchResultItem(chunk_id=c.chunk_id, file_path=c.file_path, symbol_name=c.symbol_name, chunk_type=chunks_by_id[c.chunk_id].chunk_type,
                                language=hit_by_id[c.chunk_id].language or None, score=score, content=c.content) for c, score in ranked]
    return SearchResponse(query=query, results=results, warnings=warnings)


def get_indexing_status(db: Session, *, user: User, repository_id: uuid.UUID) -> Repository:
    return get_repository(db, user=user, repository_id=repository_id)
