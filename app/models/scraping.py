from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


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
