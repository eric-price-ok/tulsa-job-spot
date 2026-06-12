"""Add site_settings table

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-11
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "site_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("recruiters_page_enabled", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.execute("INSERT INTO site_settings (recruiters_page_enabled) VALUES (false)")


def downgrade() -> None:
    op.drop_table("site_settings")
