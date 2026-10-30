"""
RepositoryDocument model.

One row per source file discovered during onboarding, recording only
lightweight file-level metadata (path, language, size, content hash,
analysis outcome) — never the file's content or its raw AST. This is
deliberately the only per-file persistence this milestone introduces; the
detailed symbol/class/function/import/call breakdown produced by
`AnalysisService` stays in-memory and is returned directly from the
onboarding API response rather than persisted (see README "Milestone 3" for
the rationale — avoiding a large graph structure inside PostgreSQL this
early, before Milestone 4 repository indexing needs it for real).
"""
import enum
import uuid

from sqlalchemy import Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DocumentAnalysisStatus(str, enum.Enum):
    ANALYZED = "ANALYZED"
    PARSE_ERROR = "PARSE_ERROR"
    SKIPPED_UNSUPPORTED = "SKIPPED_UNSUPPORTED"
    SKIPPED_TOO_LARGE = "SKIPPED_TOO_LARGE"
    SKIPPED_UNREADABLE = "SKIPPED_UNREADABLE"


class RepositoryDocument(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "repository_documents"

    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    language: Mapped[str | None] = mapped_column(String(50), nullable=True)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # sha256 hex digest
    # content_hash the file had when its chunks were last fully embedded + stored. A document whose content_hash
    # equals this needs no re-chunking/re-embedding (incremental indexing); NULL = never indexed.
    indexed_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    analysis_status: Mapped[DocumentAnalysisStatus] = mapped_column(
        Enum(DocumentAnalysisStatus, name="repository_document_analysis_status"),
        nullable=False,
    )

    repository: Mapped["Repository"] = relationship("Repository", back_populates="documents")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<RepositoryDocument id={self.id} file_path={self.file_path!r}>"
