"""add password hashes and RBAC roles to users"""
from alembic import op
import sqlalchemy as sa

revision = "9b6e2c1f4a10"
down_revision = "ff72e96d6b3e"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("role", sa.String(length=20), nullable=False, server_default="DEVELOPER"))
    op.alter_column("users", "role", server_default=None)

def downgrade() -> None:
    op.drop_column("users", "role")
    op.drop_column("users", "password_hash")
