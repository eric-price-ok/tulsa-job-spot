"""Add degree_types reference table and user_education

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-12
"""
import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "degree_types",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    op.create_table(
        "user_education",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("degree_type_id", sa.Integer(), sa.ForeignKey("degree_types.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("school_name", sa.String(255), nullable=False),
        sa.Column("subject_of_study", sa.String(255), nullable=True),
        sa.Column("completion_date", sa.Date(), nullable=True),
        sa.Column("is_in_progress", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("idx_user_education_user", "user_education", ["user_id"])
    op.create_index("idx_user_education_degree", "user_education", ["degree_type_id"])

    op.execute(sa.text("""
        CREATE TRIGGER update_user_education_updated_at
            BEFORE UPDATE ON user_education
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP TRIGGER IF EXISTS update_user_education_updated_at ON user_education"))
    op.drop_table("user_education")
    op.drop_table("degree_types")
