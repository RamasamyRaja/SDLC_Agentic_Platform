"""
Context builder: combines task info, Milestone 3 structural knowledge, and
Milestone 4 semantic retrieval results into a single, size-bounded
`ReasoningInput`.

STRUCTURAL CONTEXT SOURCE: Milestone 3's full per-symbol analysis
(RepositoryAnalysis) is deliberately NOT persisted (see README "Milestone
3" — avoiding an in-database code graph before it's needed). What IS
persisted from that analysis is the Milestone 4 `CodeChunk` table — each
row already carries `symbol_name`, `chunk_type`, `file_path`, and
`language`, extracted from Milestone 3's Tree-sitter analysis at indexing
time. This module reads CodeChunk rows as the structural-context source,
which means M5 consumes M3's *output* (via M4's persisted index of it)
without re-running Tree-sitter or rediscovering repository structure
itself — exactly the "M3 -> structural context, M4 -> semantic context, M5
-> reasoning" layering the spec calls for.

SEMANTIC CONTEXT SOURCE: calls `app.retrieval.retrieval_service.search()`
directly — never Milvus directly from this layer.

BOUNDING: every limit here is configurable (app.core.config) and applied
before anything is serialized into the prompt — never "send the whole
repository".
"""
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.llm.schemas import ReasoningInput, RepositoryContext, RetrievedChunk, StructuralSymbol, TaskContext
from app.models.code_chunk import CodeChunk
from app.models.repository import Repository
from app.models.repository_document import RepositoryDocument
from app.models.task import Task
from app.models.user import User
from app.retrieval import retrieval_service


def _load_structural_symbols(db: Session, repository: Repository, limit: int) -> list[StructuralSymbol]:
    rows = (
        db.query(CodeChunk)
        .join(RepositoryDocument, CodeChunk.repository_document_id == RepositoryDocument.id)
        .filter(RepositoryDocument.repository_id == repository.id)
        .filter(CodeChunk.symbol_name.isnot(None))
        .order_by(CodeChunk.chunk_index.asc())
        .limit(limit)
        .all()
    )
    return [
        StructuralSymbol(
            file_path=_document_path(db, row.repository_document_id),
            symbol_name=row.symbol_name,
            chunk_type=row.chunk_type.value,
            language=row.language,
        )
        for row in rows
    ]


def _document_path(db: Session, repository_document_id) -> str:
    document = db.get(RepositoryDocument, repository_document_id)
    return document.file_path if document else ""


def build_reasoning_input(db: Session, *, user: User, task: Task, repository: Repository) -> ReasoningInput:
    settings = get_settings()

    structural_symbols = _load_structural_symbols(
        db, repository, limit=settings.LLM_MAX_STRUCTURAL_SYMBOLS
    )

    retrieved_chunks: list[RetrievedChunk] = []
    if repository.indexing_status.value == "INDEXED":
        search_response = retrieval_service.search(
            db,
            user=user,
            repository_id=repository.id,
            query=task.description,
            top_k=settings.LLM_MAX_RETRIEVED_CHUNKS,
        )
        for item in search_response.results:
            retrieved_chunks.append(
                RetrievedChunk(
                    file_path=item.file_path,
                    symbol_name=item.symbol_name,
                    language=item.language,
                    content=item.content[: settings.LLM_MAX_CHARS_PER_CHUNK],
                    score=item.score,
                )
            )
    # If the repository hasn't been indexed yet, retrieved_context is simply
    # empty — reasoning still proceeds using structural context alone. The
    # model is instructed to note uncertainty where context is thin, rather
    # than the application refusing to reason at all.

    reasoning_input = ReasoningInput(
        task=TaskContext(id=str(task.id), title=task.title, description=task.description),
        repository=RepositoryContext(
            id=str(repository.id), languages=repository.detected_languages or []
        ),
        structural_context=structural_symbols,
        retrieved_context=retrieved_chunks,
    )

    return _enforce_total_size_limit(reasoning_input, settings.LLM_MAX_TOTAL_CONTEXT_CHARS)


def _enforce_total_size_limit(reasoning_input: ReasoningInput, max_chars: int) -> ReasoningInput:
    """
    Last-resort global cap: if structural + retrieved context together
    still exceed `max_chars` (as serialized), drop the lowest-priority
    retrieved chunks (lowest similarity score first) until it fits.
    Structural symbols are kept — they're already small (no content text)
    and are what grounding relies on.
    """
    def approx_size() -> int:
        return sum(len(s.file_path) + len(s.symbol_name or "") for s in reasoning_input.structural_context) + sum(
            len(c.content) + len(c.file_path) for c in reasoning_input.retrieved_context
        )

    chunks = sorted(reasoning_input.retrieved_context, key=lambda c: c.score, reverse=True)
    while approx_size() > max_chars and chunks:
        chunks.pop()
        reasoning_input = reasoning_input.model_copy(update={"retrieved_context": chunks})

    return reasoning_input
