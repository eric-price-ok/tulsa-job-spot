from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_listing_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("joblistings.id", ondelete="CASCADE"), nullable=False
    )
    applicant_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL")
    )
    applicant_name: Mapped[str] = mapped_column(String(255), nullable=False)
    applicant_email: Mapped[str] = mapped_column(String(255), nullable=False)
    applicant_phone: Mapped[Optional[str]] = mapped_column(String(50))
    cover_letter: Mapped[Optional[str]] = mapped_column(Text)
    resume_filename: Mapped[Optional[str]] = mapped_column(String(500))
    resume_uploaded_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(30), default="submitted", nullable=False)
    status_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    status_updated_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    job_listing: Mapped["JobListing"] = relationship("JobListing")  # type: ignore[name-defined]
    applicant: Mapped[Optional["User"]] = relationship("User", foreign_keys=[applicant_user_id])  # type: ignore[name-defined]


class SavedJob(Base):
    __tablename__ = "saved_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    job_listing_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("joblistings.id", ondelete="CASCADE"), nullable=False
    )
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    user: Mapped["User"] = relationship("User")  # type: ignore[name-defined]
    job_listing: Mapped["JobListing"] = relationship("JobListing")  # type: ignore[name-defined]


class SavedSearch(Base):
    __tablename__ = "saved_searches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    filters: Mapped[dict] = mapped_column(JSONB, nullable=False)
    notify_on_match: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    user: Mapped["User"] = relationship("User")  # type: ignore[name-defined]


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[Optional[str]] = mapped_column(Text)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    related_job_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("joblistings.id", ondelete="SET NULL"))
    related_company_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("company.id", ondelete="SET NULL"))
    related_application_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("applications.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    user: Mapped["User"] = relationship("User")  # type: ignore[name-defined]
