from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class JobListing(Base):
    __tablename__ = "joblistings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("company.id", ondelete="CASCADE"), nullable=False)
    company_site_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("companysite.id", ondelete="SET NULL"))
    posted_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    job_title: Mapped[str] = mapped_column(String(500), nullable=False)
    job_description: Mapped[Optional[str]] = mapped_column(Text)
    posting_id: Mapped[Optional[str]] = mapped_column(String(255))
    posting_url: Mapped[Optional[str]] = mapped_column(String(1000))
    application_method: Mapped[str] = mapped_column(String(20), default="external_url", nullable=False)
    application_email: Mapped[Optional[str]] = mapped_column(String(255))
    date_posted: Mapped[Optional[date]] = mapped_column(Date)
    date_closed: Mapped[Optional[date]] = mapped_column(Date)
    perpetual: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    approved_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    job_status_id: Mapped[int] = mapped_column(Integer, ForeignKey("jobstatus.id"), nullable=False)
    # DB column is named "function" — aliased to avoid confusion with builtins
    function: Mapped[Optional[int]] = mapped_column("function", Integer, ForeignKey("functions.id", ondelete="SET NULL"))
    specialty: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("functionspecialties.id", ondelete="SET NULL"))
    job_type_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("jobtype.id"))
    experience_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("experience.id"))
    office_location_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("officelocations.id"))
    city_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("cities.id"))
    minimum_salary: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    maximum_salary: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    pay_frequency: Mapped[Optional[str]] = mapped_column(String(50))
    experience_years_min: Mapped[Optional[int]] = mapped_column(Integer)
    experience_years_max: Mapped[Optional[int]] = mapped_column(Integer)
    associate_degree: Mapped[Optional[str]] = mapped_column(String(20), default="not_mentioned")
    bachelors_degree: Mapped[Optional[str]] = mapped_column(String(20), default="not_mentioned")
    masters_degree: Mapped[Optional[str]] = mapped_column(String(20), default="not_mentioned")
    doctorate_degree: Mapped[Optional[str]] = mapped_column(String(20), default="not_mentioned")
    first_shift: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)
    second_shift: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)
    third_shift: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)
    rotating_shift: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)
    flexible_schedule: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)
    weekends_required: Mapped[Optional[str]] = mapped_column(String(20), default="not_mentioned")
    evenings_required: Mapped[Optional[str]] = mapped_column(String(20), default="not_mentioned")
    holidays_required: Mapped[Optional[str]] = mapped_column(String(20), default="not_mentioned")
    travel_requirements: Mapped[Optional[str]] = mapped_column(String(20), default="not_mentioned")
    travel_percentage: Mapped[Optional[int]] = mapped_column(Integer)
    is_temporary: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)
    is_seasonal: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)
    is_volunteer: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)
    is_individual_contributor: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)
    is_people_manager: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)
    source_job_board: Mapped[Optional[str]] = mapped_column(String(100))
    external_job_id: Mapped[Optional[str]] = mapped_column(String(255))
    scraping_hash: Mapped[Optional[str]] = mapped_column(String(64))
    last_scraped: Mapped[Optional[datetime]] = mapped_column(DateTime, server_default=func.now())
    extraction_confidence: Mapped[Optional[Decimal]] = mapped_column(Numeric(3, 2), default=Decimal("1.0"))
    extraction_model: Mapped[Optional[str]] = mapped_column(String(50), default="claude-sonnet")
    extraction_timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    extraction_version: Mapped[Optional[str]] = mapped_column(String(10), default="2.0")
    raw_text_length: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    company: Mapped["Company"] = relationship("Company")  # type: ignore[name-defined]
    poster: Mapped[Optional["User"]] = relationship("User", foreign_keys=[posted_by])  # type: ignore[name-defined]
    job_status: Mapped["JobStatus"] = relationship("JobStatus")  # type: ignore[name-defined]
    job_type: Mapped[Optional["JobType"]] = relationship("JobType")  # type: ignore[name-defined]
    office_location: Mapped[Optional["OfficeLocation"]] = relationship("OfficeLocation")  # type: ignore[name-defined]
    city: Mapped[Optional["City"]] = relationship("City")  # type: ignore[name-defined]
    function_obj: Mapped[Optional["Function"]] = relationship("Function", foreign_keys=[function])  # type: ignore[name-defined]
    experience: Mapped[Optional["Experience"]] = relationship("Experience")  # type: ignore[name-defined]
    skills: Mapped[list["JobListingSkill"]] = relationship("JobListingSkill", back_populates="job_listing")
    certifications: Mapped[list["JobListingCertification"]] = relationship(
        "JobListingCertification", back_populates="job_listing"
    )


class JobListingSkill(Base):
    __tablename__ = "joblistingskills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_listing_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("joblistings.id", ondelete="CASCADE"), nullable=False
    )
    skill_id: Mapped[int] = mapped_column(Integer, ForeignKey("skills.id", ondelete="CASCADE"), nullable=False)
    required_skill: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    preferred_skill: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    years_required: Mapped[Optional[int]] = mapped_column(Integer)
    proficiency_level: Mapped[Optional[str]] = mapped_column(String(20), default="unknown")
    extraction_method: Mapped[Optional[str]] = mapped_column(String(20), default="manual")
    confidence_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(3, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    job_listing: Mapped["JobListing"] = relationship("JobListing", back_populates="skills")
    skill: Mapped["Skill"] = relationship("Skill")  # type: ignore[name-defined]


class JobListingCertification(Base):
    __tablename__ = "joblistingcertifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_listing_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("joblistings.id", ondelete="CASCADE"), nullable=False
    )
    certification_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("certifications.id", ondelete="CASCADE"), nullable=False
    )
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_preferred: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    extraction_method: Mapped[Optional[str]] = mapped_column(String(20), default="manual")
    confidence_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(3, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    job_listing: Mapped["JobListing"] = relationship("JobListing", back_populates="certifications")
    certification: Mapped["Certification"] = relationship("Certification")  # type: ignore[name-defined]
