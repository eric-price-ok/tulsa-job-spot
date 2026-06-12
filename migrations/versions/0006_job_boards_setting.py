"""Add job_boards_section_enabled to site_settings

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-11
"""
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "site_settings",
        sa.Column("job_boards_section_enabled", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("site_settings", "job_boards_section_enabled")
