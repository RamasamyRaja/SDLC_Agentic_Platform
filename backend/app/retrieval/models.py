"""
Typed models for the retrieval layer — chunk boundaries, search results, and
the indexing summary. These are the "clean, structured, LLM-context-ready"
shapes referenced in the Milestone 4 spec for future Mistral integration
(not implemented here — see README).
"""
import enum

from pydantic import BaseModel, Field


class ChunkType(str, enum.Enum):
    CLASS = "CLASS"
    FUNCTION = "FUNCTION"
    METHOD = "METHOD"
    FILE = "FILE"  # fallback: whole-file chunk, used when structural chunking isn't available


class ChunkCandidate(BaseModel):
    """A chunk boundary + content, produced by chunking.py before it is
    persisted (as CodeChunk) or embedded. Not a DB model — an intermediate,
    in-memory shape."""

    repository_document_id: str
    file_path: str
    language: str | None
    chunk_type: ChunkType
    symbol_name: str | None
    start_line: int
    end_line: int
    content: str
    content_hash: str


class SearchResultItem(BaseModel):
    chunk_id: str
    file_path: str
    symbol_name: str | None
    chunk_type: ChunkType
    language: str | None
    score: float
    content: str


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)   # e.g. the index is older than the checked-out commit


class IndexingSummary(BaseModel):
    repository_id: str
    chunks_created: int
    chunks_unchanged: int
    chunks_updated: int
    chunks_removed: int
    embeddings_generated: int
    total_chunks: int
