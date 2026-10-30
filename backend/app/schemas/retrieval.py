"""
Pydantic schemas for the indexing/search API.
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.repository import IndexingStatus
from app.retrieval.models import SearchResultItem


class IndexRepositoryResponse(BaseModel):
    repository_id: uuid.UUID
    status: IndexingStatus
    chunks_created: int
    chunks_unchanged: int
    chunks_removed: int
    embeddings_generated: int
    total_chunks: int


class IndexingStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    repository_id: uuid.UUID = Field(validation_alias="id")
    indexing_status: IndexingStatus
    indexed_chunk_count: int | None
    last_indexed_at: datetime | None
    indexing_error: str | None


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)


class SearchResponseSchema(BaseModel):
    query: str
    results: list[SearchResultItem]
    warnings: list[str] = []
