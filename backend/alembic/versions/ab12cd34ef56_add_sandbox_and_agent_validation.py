"""add sandbox runs and engineering execution telemetry

Revision ID: ab12cd34ef56
Revises: 9b6e2c1f4a10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = "ab12cd34ef56"
down_revision = "9b6e2c1f4a10"
branch_labels = None
depends_on = None

def upgrade() -> None:
    # create_type=False: the type is created explicitly (checkfirst) below; without this,
    # op.create_table() would emit a second CREATE TYPE and fail on fresh databases.
    sandbox_status = postgresql.ENUM("QUEUED", "RUNNING", "PASSED", "FAILED", "TIMED_OUT", "BLOCKED", name="sandbox_run_status", create_type=False)
    sandbox_status.create(op.get_bind(), checkfirst=True)
    op.create_table("sandbox_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("repository_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("command", sa.String(length=100), nullable=False),
        sa.Column("status", sandbox_status, nullable=False),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("stdout", sa.Text(), nullable=True),
        sa.Column("stderr", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index("ix_sandbox_runs_task_id", "sandbox_runs", ["task_id"])
    op.create_index("ix_sandbox_runs_repository_id", "sandbox_runs", ["repository_id"])
    op.add_column("agent_executions", sa.Column("validation", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("agent_executions", sa.Column("changed_files", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("agent_executions", sa.Column("repair_attempts", sa.Integer(), nullable=True))
    op.add_column("agent_executions", sa.Column("final_diff", sa.Text(), nullable=True))

def downgrade() -> None:
    op.drop_column("agent_executions", "final_diff")
    op.drop_column("agent_executions", "repair_attempts")
    op.drop_column("agent_executions", "changed_files")
    op.drop_column("agent_executions", "validation")
    op.drop_index("ix_sandbox_runs_repository_id", table_name="sandbox_runs")
    op.drop_index("ix_sandbox_runs_task_id", table_name="sandbox_runs")
    op.drop_table("sandbox_runs")
    sa.Enum(name="sandbox_run_status").drop(op.get_bind(), checkfirst=True)
