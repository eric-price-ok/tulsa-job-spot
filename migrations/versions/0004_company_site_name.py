"""Add site_name column to companysite

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-11
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "companysite",
        sa.Column("site_name", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("companysite", "site_name")
