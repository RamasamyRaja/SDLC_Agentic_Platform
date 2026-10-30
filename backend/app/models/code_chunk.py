"""
CodeChunk model.

One row per chunk produced by the chunking layer (app/retrieval/chunking.py)
— a class body, a function/method body, or (fallback) a whole file. Stores
the chunk's boundaries, identifying metadata, and its actual text content
(justified here, unlike the full Milestone 3 analysis result: a chunk's
content IS the retrieval unit — search results need to return it, and a
chunk is capped at CHUNK_MAX_CHARS, so this stays bounded, unlike storing
entire files or a full AST).

The embedding vector itself is NEVER stored here — only in Milvus. See
EmbeddingMetadata for the PostgreSQL-side pointer to it.
"""
import uuid

from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.retrieval.models import ChunkType


class CodeChunk(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "code_chunks"

    repository_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repository_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_type: Mapped[ChunkType] = mapped_column(Enum(ChunkType, name="code_chunk_type"), nullable=False)
    symbol_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    language: Mapped[str | None] = mapped_column(String(50), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    repository_document: Mapped["RepositoryDocument"] = relationship("RepositoryDocument")
    embedding_metadata: Mapped["EmbeddingMetadata | None"] = relationship(
        "EmbeddingMetadata",
        back_populates="code_chunk",
        cascade="all, delete-orphan",
        uselist=False,
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<CodeChunk id={self.id} symbol_name={self.symbol_name!r}>"
