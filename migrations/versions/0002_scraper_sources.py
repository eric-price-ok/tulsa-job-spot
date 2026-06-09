"""Add scraper_sources table

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-08

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE scraper_sources (
            id              SERIAL PRIMARY KEY,
            name            VARCHAR(100) NOT NULL,
            scraper_class   VARCHAR(100) NOT NULL,
            url             VARCHAR(1000) NOT NULL,
            company_id      INT REFERENCES company(id) ON DELETE SET NULL,
            config          JSONB,
            cron_schedule   VARCHAR(50) NOT NULL DEFAULT '0 3 * * *',
            is_active       BOOLEAN NOT NULL DEFAULT TRUE,
            selenium_required BOOLEAN NOT NULL DEFAULT FALSE,
            last_run_at     TIMESTAMP,
            last_status     VARCHAR(20),
            created_at      TIMESTAMP NOT NULL DEFAULT NOW()
        );

        CREATE INDEX idx_scraper_sources_active ON scraper_sources (is_active);
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS scraper_sources;"))
