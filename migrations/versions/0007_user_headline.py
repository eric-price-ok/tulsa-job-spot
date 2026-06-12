"""Add headline to users

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-12
"""
import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("headline", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "headline")
