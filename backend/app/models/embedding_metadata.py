"""
EmbeddingMetadata model.

Relational pointer from a CodeChunk to its vector in Milvus — PostgreSQL
holds the metadata (which provider/model produced it, its dimension, which
Milvus collection and ID it lives at); Milvus holds the actual vector. This
separation is deliberate: PostgreSQL is the relational source of truth,
Milvus is the vector-search engine, and neither duplicates the other's data.
"""
import uuid

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class EmbeddingMetadata(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "embedding_metadata"

    code_chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("code_chunks.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # one embedding per chunk at a time — re-embedding replaces, not adds
        index=True,
    )

    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    milvus_collection: Mapped[str] = mapped_column(String(255), nullable=False)
    milvus_id: Mapped[str] = mapped_column(String(64), nullable=False)

    code_chunk: Mapped["CodeChunk"] = relationship("CodeChunk", back_populates="embedding_metadata")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<EmbeddingMetadata id={self.id} milvus_id={self.milvus_id!r}>"
