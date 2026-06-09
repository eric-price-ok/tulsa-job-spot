"""Add slug column to company

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-09
"""
import re

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

_LEGAL_SUFFIX_RE = re.compile(
    r",?\s*\b(?:P\.?L\.?L\.?C|L\.?L\.?C|L\.?L\.?P|P\.?L\.?C|PLLC|LLP|LLC|PLC|L\.?P|LP|Inc|Ltd|Corp|Co|P\.?A|P\.?C)\.?\s*$",
    re.IGNORECASE,
)


def _slug(name: str) -> str:
    text = _LEGAL_SUFFIX_RE.sub("", name).strip()
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "company"


def upgrade() -> None:
    op.add_column("company", sa.Column("slug", sa.String(255), nullable=True))

    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, common_name FROM company ORDER BY id")).fetchall()

    used: set[str] = set()
    for row in rows:
        base = _slug(row[1])
        slug = base
        n = 2
        while slug in used:
            slug = f"{base}-{n}"
            n += 1
        used.add(slug)
        conn.execute(sa.text("UPDATE company SET slug = :s WHERE id = :i"), {"s": slug, "i": row[0]})

    op.alter_column("company", "slug", existing_type=sa.String(255), nullable=False)
    op.create_unique_constraint("uq_company_slug", "company", ["slug"])


def downgrade() -> None:
    op.drop_constraint("uq_company_slug", "company", type_="unique")
    op.drop_column("company", "slug")
