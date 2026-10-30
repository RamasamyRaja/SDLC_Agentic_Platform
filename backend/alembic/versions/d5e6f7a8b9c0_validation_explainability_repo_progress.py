"""validation explainability, deployment evidence, repository progress + incremental indexing bookkeeping

Purely additive: every new column is nullable (or has a server default), so existing rows are preserved exactly as
they were. Historical validation verdicts are NOT rewritten; rows validated before this migration keep
`required` / `validation_summary` = NULL and are explained from their stored checks on read.

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-10-27 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, Sequence[str], None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- validation: explainable results -------------------------------------------------------------
    op.add_column("development_runs", sa.Column("validation_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("development_runs", sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("development_runs", sa.Column("validated_diff_sha", sa.String(length=64), nullable=True))
    op.add_column("validation_checks", sa.Column("required", sa.Boolean(), nullable=True))
    op.add_column("validation_checks", sa.Column("kind", sa.String(length=24), nullable=True))
    op.add_column("validation_checks", sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    # --- deployment: separate evidence ---------------------------------------------------------------
    op.add_column("deployments", sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("deployments", sa.Column("verification_level", sa.String(length=24), nullable=True))

    # --- repositories: real progress counters + index provenance -------------------------------------
    op.add_column("repositories", sa.Column("onboarding_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("repositories", sa.Column("onboarding_phase", sa.String(length=24), nullable=True))
    op.add_column("repositories", sa.Column("indexing_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("repositories", sa.Column("indexing_phase", sa.String(length=24), nullable=True))
    op.add_column("repositories", sa.Column("indexing_chunks_total", sa.Integer(), nullable=True))
    op.add_column("repositories", sa.Column("indexing_chunks_done", sa.Integer(), nullable=True))
    op.add_column("repositories", sa.Column("indexed_commit_sha", sa.String(length=40), nullable=True))
    op.add_column("repositories", sa.Column("indexed_files_count", sa.Integer(), nullable=True))

    # --- documents: incremental indexing -------------------------------------------------------------
    op.add_column("repository_documents", sa.Column("indexed_content_hash", sa.String(length=64), nullable=True))
    # Existing indexes were built from the documents' current content, so mark them as such. Without this the first
    # re-index after upgrading would needlessly re-chunk every file (chunk-level hashing would still avoid
    # re-embedding, but this keeps the first incremental run genuinely incremental).
    op.execute(
        "UPDATE repository_documents d SET indexed_content_hash = d.content_hash "
        "WHERE d.content_hash <> '' AND EXISTS (SELECT 1 FROM code_chunks c WHERE c.repository_document_id = d.id)"
    )
    op.execute(
        "UPDATE repositories SET indexed_commit_sha = commit_sha, indexed_files_count = files_analyzed_count "
        "WHERE indexing_status = 'INDEXED'"
    )


def downgrade() -> None:
    op.drop_column("repository_documents", "indexed_content_hash")
    for col in ("indexed_files_count", "indexed_commit_sha", "indexing_chunks_done", "indexing_chunks_total",
                "indexing_phase", "indexing_started_at", "onboarding_phase", "onboarding_started_at"):
        op.drop_column("repositories", col)
    op.drop_column("deployments", "verification_level")
    op.drop_column("deployments", "evidence")
    op.drop_column("validation_checks", "metrics")
    op.drop_column("validation_checks", "kind")
    op.drop_column("validation_checks", "required")
    op.drop_column("development_runs", "validated_diff_sha")
    op.drop_column("development_runs", "validated_at")
    op.drop_column("development_runs", "validation_summary")
