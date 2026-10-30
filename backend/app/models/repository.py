"""
Repository model.

Represents a Git repository the agent is asked to work with. This model
tracks both *registration* metadata (Milestone 2: url, branch) and
*onboarding* summary metadata (Milestone 3: commit SHA, detected languages,
last onboarding counts). The full per-symbol analysis result is NOT stored
here or anywhere in PostgreSQL — see app/analysis/models.py and the
"Milestone 3" section of the README for why.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import ARRAY, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base, TimestampMixin, UUIDPrimaryKeyMixin


class RepositoryStatus(str, enum.Enum):
    """
    Repository *preparation* status — deliberately separate from Task
    status (which describes the requested software change, not the
    repository's own readiness).
    """

    PENDING = "PENDING"      # registered, not yet onboarded
    CLONING = "CLONING"      # onboarding in progress: cloning the repository
    ANALYZING = "ANALYZING"  # onboarding in progress: running structural analysis
    READY = "READY"          # onboarded and available (possibly with parse-error warnings)
    ERROR = "ERROR"          # onboarding failed (clone failure, workspace failure, etc.)


class IndexingStatus(str, enum.Enum):
    """
    Semantic-indexing status (Milestone 4) — deliberately separate from
    both `RepositoryStatus` (onboarding/cloning) and `TaskStatus` (the
    requested change). A repository can be READY (onboarded) but still
    NOT_INDEXED; indexing requires onboarding to have completed first.
    """

    NOT_INDEXED = "NOT_INDEXED"
    INDEXING = "INDEXING"
    INDEXED = "INDEXED"
    FAILED = "FAILED"


class Repository(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "repositories"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    default_branch: Mapped[str] = mapped_column(String(255), nullable=False, default="main")

    # Where `default_branch` came from: "remote_head" (the remote's advertised
    # HEAD symref, verified), "user_specified" (the caller asked for this
    # branch) or "fallback" (could not be resolved; "main" is only a guess
    # and gets re-resolved at onboarding).
    default_branch_source: Mapped[str] = mapped_column(String(24), nullable=False, default="fallback", server_default="fallback")

    # Set once the repository has actually been cloned onto disk.
    workspace_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    status: Mapped[RepositoryStatus] = mapped_column(
        Enum(RepositoryStatus, name="repository_status"),
        nullable=False,
        default=RepositoryStatus.PENDING,
    )

    # --- Onboarding summary (Milestone 3) ---
    # A summary only — counts and the detected language list — not the full
    # per-file/per-symbol analysis result. See module docstring.
    commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    detected_languages: Mapped[list[str] | None] = mapped_column(ARRAY(String(50)), nullable=True)
    files_analyzed_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    files_skipped_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parse_error_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_onboarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    onboarding_error: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    # --- Semantic indexing summary (Milestone 4) ---
    indexing_status: Mapped[IndexingStatus] = mapped_column(
        Enum(IndexingStatus, name="repository_indexing_status"),
        nullable=False,
        default=IndexingStatus.NOT_INDEXED,
    )
    indexed_chunk_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    indexing_error: Mapped[str | None] = mapped_column(String(2000), nullable=True)

    # --- Live progress + consistency bookkeeping (real counters written by the pipeline, never estimated) ---
    onboarding_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    onboarding_phase: Mapped[str | None] = mapped_column(String(24), nullable=True)   # CLONING | ANALYZING | PERSISTING | DONE
    indexing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    indexing_phase: Mapped[str | None] = mapped_column(String(24), nullable=True)     # ANALYZING | CHUNKING | EMBEDDING | RECONCILING | DONE
    indexing_chunks_total: Mapped[int | None] = mapped_column(Integer, nullable=True)  # chunks that need embedding in this run
    indexing_chunks_done: Mapped[int | None] = mapped_column(Integer, nullable=True)
    indexed_commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)  # commit the current index was built from
    indexed_files_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="repositories")
    tasks: Mapped[list["Task"]] = relationship(
        "Task",
        back_populates="repository",
        cascade="all, delete-orphan",
    )
    documents: Mapped[list["RepositoryDocument"]] = relationship(
        "RepositoryDocument",
        back_populates="repository",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<Repository id={self.id} url={self.url!r}>"
