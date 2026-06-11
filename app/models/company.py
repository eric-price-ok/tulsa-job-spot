from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Company(Base):
    __tablename__ = "company"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    common_name: Mapped[str] = mapped_column(String(255), nullable=False)
    legal_name: Mapped[Optional[str]] = mapped_column(String(255))
    website: Mapped[Optional[str]] = mapped_column(String(500))
    jobboard: Mapped[Optional[str]] = mapped_column(String(500))
    date_founded: Mapped[Optional[datetime]] = mapped_column(DateTime)
    date_closed: Mapped[Optional[datetime]] = mapped_column(DateTime)
    defunct: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    approved_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    company_type: Mapped[int] = mapped_column(Integer, ForeignKey("company_type.id", ondelete="SET NULL"), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    company_size: Mapped[Optional[str]] = mapped_column(String(50))
    is_scraped: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    last_full_scrape_completed: Mapped[Optional[datetime]] = mapped_column(DateTime)

    company_type_obj: Mapped[Optional["CompanyType"]] = relationship(  # type: ignore[name-defined]
        "CompanyType", foreign_keys=[company_type]
    )
    sites: Mapped[list["CompanySite"]] = relationship("CompanySite", back_populates="company")
    socials: Mapped[list["CompanySocial"]] = relationship("CompanySocial", back_populates="company")
    user_roles: Mapped[list["UserCompanyRole"]] = relationship("UserCompanyRole", back_populates="company")


class UserCompanyRole(Base):
    __tablename__ = "user_company_roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("company.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    approved_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])  # type: ignore[name-defined]
    company: Mapped["Company"] = relationship("Company", back_populates="user_roles")


class CompanyInvite(Base):
    __tablename__ = "company_invites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("company.id", ondelete="CASCADE"), nullable=False)
    invited_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    invited_email: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="job_poster", nullable=False)
    token: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    accepted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    accepted_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    company: Mapped["Company"] = relationship("Company")
    inviter: Mapped["User"] = relationship("User", foreign_keys=[invited_by])  # type: ignore[name-defined]


class CompanySite(Base):
    __tablename__ = "companysite"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("company.id", ondelete="CASCADE"), nullable=False)
    site_type: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("companysitetype.id", ondelete="SET NULL"))
    address1: Mapped[Optional[str]] = mapped_column(String(255))
    address2: Mapped[Optional[str]] = mapped_column(String(255))
    country_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("country.id", ondelete="SET NULL"))
    state_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("state.id", ondelete="SET NULL"))
    city_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("cities.id", ondelete="SET NULL"))
    postcode: Mapped[Optional[str]] = mapped_column(String(10))
    phone: Mapped[Optional[str]] = mapped_column(String(50))
    site_name: Mapped[Optional[str]] = mapped_column(String(255))
    site_web: Mapped[Optional[str]] = mapped_column(String(500))
    site_job_board: Mapped[Optional[str]] = mapped_column(String(500))
    shortname: Mapped[Optional[str]] = mapped_column(String)
    is_headquarters: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    employee_count: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    company: Mapped["Company"] = relationship("Company", back_populates="sites")
    city: Mapped[Optional["City"]] = relationship("City")  # type: ignore[name-defined]
    state: Mapped[Optional["State"]] = relationship("State")  # type: ignore[name-defined]


class CompanySocial(Base):
    __tablename__ = "company_socials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("company.id", ondelete="CASCADE"), nullable=False)
    social_media_type_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("social_media_types.id", ondelete="CASCADE"), nullable=False
    )
    company_url: Mapped[str] = mapped_column(String(500), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    company: Mapped["Company"] = relationship("Company", back_populates="socials")
    social_type: Mapped["SocialMediaType"] = relationship("SocialMediaType")  # type: ignore[name-defined]


class CompanyBenefit(Base):
    __tablename__ = "companybenefits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("company.id", ondelete="CASCADE"), nullable=False)
    benefit_id: Mapped[int] = mapped_column(Integer, ForeignKey("benefits.id", ondelete="CASCADE"), nullable=False)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    last_updated: Mapped[Optional[datetime]] = mapped_column(DateTime)


class CompanyFunction(Base):
    __tablename__ = "companyfunctions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("company.id", ondelete="CASCADE"), nullable=False)
    function_id: Mapped[int] = mapped_column(Integer, ForeignKey("functions.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class CompanyIndustry(Base):
    __tablename__ = "companyindustries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("company.id", ondelete="CASCADE"), nullable=False)
    industry_id: Mapped[int] = mapped_column(Integer, ForeignKey("industries.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class CompanyTechnology(Base):
    __tablename__ = "companytechnologies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("company.id", ondelete="CASCADE"), nullable=False)
    skill_id: Mapped[int] = mapped_column(Integer, ForeignKey("skills.id", ondelete="CASCADE"), nullable=False)
    proficiency_level: Mapped[Optional[str]] = mapped_column(String(20), default="unknown")
    years_experience: Mapped[Optional[int]] = mapped_column(Integer)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(Integer, ForeignKey("company.id", ondelete="CASCADE"), nullable=False)
    shortname: Mapped[Optional[str]] = mapped_column(String(100))
    fullnote: Mapped[Optional[str]] = mapped_column(Text)
    date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    note_type: Mapped[Optional[str]] = mapped_column(String(50), default="general")
    is_private: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
