from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ScraperSource(Base):
    __tablename__ = "scraper_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    scraper_class: Mapped[str] = mapped_column(String(100), nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    company_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("company.id", ondelete="SET NULL")
    )
    config: Mapped[Optional[dict]] = mapped_column(JSON)
    cron_schedule: Mapped[str] = mapped_column(String(50), default="0 3 * * *", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    selenium_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    last_status: Mapped[Optional[str]] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    company: Mapped[Optional["Company"]] = relationship("Company")  # type: ignore[name-defined]


class ScrapingLog(Base):
    __tablename__ = "scrapinglog"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_board: Mapped[str] = mapped_column(String(100), nullable=False)
    company_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("company.id", ondelete="SET NULL"))
    jobs_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    jobs_added: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    jobs_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    jobs_skipped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    errors: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="running", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer)
    scraper_version: Mapped[Optional[str]] = mapped_column(String(50))
    ai_model_used: Mapped[Optional[str]] = mapped_column(String(50))
    notes: Mapped[Optional[str]] = mapped_column(Text)
