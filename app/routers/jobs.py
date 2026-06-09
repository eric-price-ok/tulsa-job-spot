import math
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import List, Optional

import nh3
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..config import settings
from ..utils import sanitize_url
from ..database import get_db
from ..dependencies import get_current_user, require_user
from ..models.company import Company, UserCompanyRole
from ..models.job import JobListing, JobListingCertification, JobListingSkill
from ..models.reference import (
    City,
    Experience,
    Function,
    FunctionSpecialty,
    JobStatus,
    JobType,
    OfficeLocation,
    Skill,
)
from ..models.user import User
from ..templates import templates
from ..workers.email import enqueue_email

router = APIRouter(tags=["jobs"])

ITEMS_PER_PAGE = settings.ITEMS_PER_PAGE

PAY_FREQUENCIES = ["hourly", "daily", "weekly", "biweekly", "monthly", "annually"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_active_status_id(db: AsyncSession) -> int:
    return await db.scalar(select(JobStatus.id).where(JobStatus.name == "active"))


async def _get_closed_status_id(db: AsyncSession) -> int:
    return await db.scalar(select(JobStatus.id).where(JobStatus.name == "closed"))


async def _get_user_company_role(
    db: AsyncSession, user_id: int, company_id: int
) -> Optional[UserCompanyRole]:
    return await db.scalar(
        select(UserCompanyRole).where(
            UserCompanyRole.user_id == user_id,
            UserCompanyRole.company_id == company_id,
            UserCompanyRole.approved == True,
        )
    )


async def _require_poster_role(
    company_id: int, current_user: User, db: AsyncSession
) -> Company:
    company = await db.get(Company, company_id)
    if company is None or not company.approved:
        raise HTTPException(status_code=404)
    if current_user.is_staff:
        return company
    role = await _get_user_company_role(db, current_user.id, company_id)
    if role is None:
        raise HTTPException(status_code=403)
    return company


async def _load_form_data(db: AsyncSession) -> dict:
    """Load all reference data needed to render the job form."""
    served_cities = (
        await db.execute(
            select(City)
            .where(City.is_served == True)
            .options(selectinload(City.state))
            .order_by(City.sort_order.nullslast(), City.city_name)
        )
    ).scalars().all()
    functions = (
        await db.execute(
            select(Function).where(Function.is_active == True).order_by(Function.name)
        )
    ).scalars().all()
    job_types = (
        await db.execute(
            select(JobType).where(JobType.is_active == True).order_by(JobType.name)
        )
    ).scalars().all()
    office_locations = (
        await db.execute(
            select(OfficeLocation)
            .where(OfficeLocation.is_active == True)
            .order_by(OfficeLocation.name)
        )
    ).scalars().all()
    experience_levels = (
        await db.execute(select(Experience).where(Experience.is_active == True))
    ).scalars().all()
    skills = (
        await db.execute(
            select(Skill).where(Skill.is_active == True).order_by(Skill.name)
        )
    ).scalars().all()

    return {
        "served_cities": served_cities,
        "functions": functions,
        "job_types": job_types,
        "office_locations": office_locations,
        "experience_levels": experience_levels,
        "skills": skills,
        "pay_frequencies": PAY_FREQUENCIES,
    }


async def _load_specialties(db: AsyncSession, function_id: int) -> list:
    return (
        await db.execute(
            select(FunctionSpecialty)
            .where(
                FunctionSpecialty.function_id == function_id,
                FunctionSpecialty.is_active == True,
            )
            .order_by(FunctionSpecialty.specialty)
        )
    ).scalars().all()


# ---------------------------------------------------------------------------
# HTMX: specialty options for a function
# ---------------------------------------------------------------------------

@router.get("/jobs/specialties", response_class=HTMLResponse)
async def specialty_options(
    request: Request,
    function_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    specialties = []
    if function_id:
        specialties = await _load_specialties(db, function_id)
    return templates.TemplateResponse(
        request,
        "partials/specialty_options.html",
        {"specialties": specialties},
    )


# ---------------------------------------------------------------------------
# Create job listing
# ---------------------------------------------------------------------------

@router.get("/jobs/create", response_class=HTMLResponse)
async def job_create_form(
    request: Request,
    company_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    # Determine which companies this user can post for
    if current_user.is_staff:
        user_companies = (
            await db.execute(
                select(Company)
                .where(Company.approved == True, Company.defunct == False)
                .order_by(Company.common_name)
            )
        ).scalars().all()
    else:
        roles = (
            await db.execute(
                select(UserCompanyRole)
                .where(
                    UserCompanyRole.user_id == current_user.id,
                    UserCompanyRole.approved == True,
                )
                .options(selectinload(UserCompanyRole.company))
            )
        ).scalars().all()
        user_companies = [r.company for r in roles if r.company.approved]

    if not user_companies:
        return RedirectResponse("/companies/join", status_code=303)

    # Validate pre-selected company
    selected_company = None
    if company_id:
        selected_company = next((c for c in user_companies if c.id == company_id), None)
        if selected_company is None:
            raise HTTPException(status_code=403)

    form_data = await _load_form_data(db)

    return templates.TemplateResponse(
        request,
        "jobs/create.html",
        {
            "title": "Post a Job",
            "user_companies": user_companies,
            "selected_company": selected_company,
            "job": None,
            **form_data,
            "current_user": current_user,
        },
    )


@router.post("/jobs/create")
async def job_create_submit(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
    company_id: int = Form(...),
    job_title: str = Form(...),
    job_description: str = Form(...),
    application_method: str = Form(...),
    posting_url: Optional[str] = Form(None),
    application_email: Optional[str] = Form(None),
    city_id: Optional[int] = Form(None),
    office_location_id: Optional[int] = Form(None),
    job_type_id: Optional[int] = Form(None),
    function_id: Optional[int] = Form(None),
    specialty_id: Optional[int] = Form(None),
    experience_id: Optional[int] = Form(None),
    minimum_salary: Optional[str] = Form(None),
    maximum_salary: Optional[str] = Form(None),
    pay_frequency: Optional[str] = Form(None),
    date_closed: Optional[str] = Form(None),
    skill_ids: List[int] = Form(default=[]),
):
    company = await _require_poster_role(company_id, current_user, db)

    job_title = job_title.strip()
    if not job_title:
        raise HTTPException(status_code=400, detail="Job title is required")
    if application_method not in ("external_url", "email", "in_platform"):
        raise HTTPException(status_code=400, detail="Invalid application method")

    active_status_id = await _get_active_status_id(db)

    def parse_salary(val: Optional[str]) -> Optional[Decimal]:
        if not val or not val.strip():
            return None
        try:
            return Decimal(val.strip())
        except InvalidOperation:
            return None

    def parse_date(val: Optional[str]) -> Optional[date]:
        if not val or not val.strip():
            return None
        try:
            return date.fromisoformat(val.strip())
        except ValueError:
            return None

    job = JobListing(
        company_id=company_id,
        posted_by=current_user.id,
        job_title=job_title,
        job_description=nh3.clean(job_description.strip()),
        application_method=application_method,
        posting_url=sanitize_url(posting_url),
        application_email=application_email.strip() if application_email else None,
        city_id=city_id or None,
        office_location_id=office_location_id or None,
        job_type_id=job_type_id or None,
        function=function_id or None,
        specialty=specialty_id or None,
        experience_id=experience_id or None,
        minimum_salary=parse_salary(minimum_salary),
        maximum_salary=parse_salary(maximum_salary),
        pay_frequency=pay_frequency if pay_frequency in PAY_FREQUENCIES else None,
        date_closed=parse_date(date_closed),
        date_posted=date.today(),
        approved=False,
        job_status_id=active_status_id,
    )
    db.add(job)
    await db.flush()

    for skill_id in set(skill_ids):
        db.add(JobListingSkill(
            job_listing_id=job.id,
            skill_id=skill_id,
            required_skill=True,
            extraction_method="manual",
        ))

    await db.commit()

    await enqueue_email(
        "job_submitted",
        {
            "job_title": job.job_title,
            "company_name": company.common_name,
            "posted_by": current_user.email,
            "job_id": job.id,
        },
    )

    return RedirectResponse(
        f"/companies/{company_id}/jobs?success=job_submitted", status_code=303
    )


# ---------------------------------------------------------------------------
# Edit job listing
# ---------------------------------------------------------------------------

@router.get("/jobs/{job_id}/edit", response_class=HTMLResponse)
async def job_edit_form(
    job_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    job = (
        await db.execute(
            select(JobListing)
            .where(JobListing.id == job_id)
            .options(
                selectinload(JobListing.skills).selectinload(JobListingSkill.skill),
            )
        )
    ).scalar_one_or_none()

    if job is None:
        raise HTTPException(status_code=404)

    company = await _require_poster_role(job.company_id, current_user, db)

    specialties = []
    if job.function:
        specialties = await _load_specialties(db, job.function)

    form_data = await _load_form_data(db)

    return templates.TemplateResponse(
        request,
        "jobs/edit.html",
        {
            "title": f"Edit — {job.job_title}",
            "job": job,
            "company": company,
            "specialties": specialties,
            **form_data,
            "current_user": current_user,
        },
    )


@router.post("/jobs/{job_id}/edit")
async def job_edit_submit(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
    job_title: str = Form(...),
    job_description: str = Form(...),
    application_method: str = Form(...),
    posting_url: Optional[str] = Form(None),
    application_email: Optional[str] = Form(None),
    city_id: Optional[int] = Form(None),
    office_location_id: Optional[int] = Form(None),
    job_type_id: Optional[int] = Form(None),
    function_id: Optional[int] = Form(None),
    specialty_id: Optional[int] = Form(None),
    experience_id: Optional[int] = Form(None),
    minimum_salary: Optional[str] = Form(None),
    maximum_salary: Optional[str] = Form(None),
    pay_frequency: Optional[str] = Form(None),
    date_closed: Optional[str] = Form(None),
    skill_ids: List[int] = Form(default=[]),
):
    job = await db.get(JobListing, job_id)
    if job is None:
        raise HTTPException(status_code=404)

    await _require_poster_role(job.company_id, current_user, db)

    def parse_salary(val: Optional[str]) -> Optional[Decimal]:
        if not val or not val.strip():
            return None
        try:
            return Decimal(val.strip())
        except InvalidOperation:
            return None

    def parse_date(val: Optional[str]) -> Optional[date]:
        if not val or not val.strip():
            return None
        try:
            return date.fromisoformat(val.strip())
        except ValueError:
            return None

    job.job_title = job_title.strip()
    job.job_description = nh3.clean(job_description.strip())
    job.application_method = application_method
    job.posting_url = sanitize_url(posting_url)
    job.application_email = application_email.strip() if application_email else None
    job.city_id = city_id or None
    job.office_location_id = office_location_id or None
    job.job_type_id = job_type_id or None
    job.function = function_id or None
    job.specialty = specialty_id or None
    job.experience_id = experience_id or None
    job.minimum_salary = parse_salary(minimum_salary)
    job.maximum_salary = parse_salary(maximum_salary)
    job.pay_frequency = pay_frequency if pay_frequency in PAY_FREQUENCIES else None
    job.date_closed = parse_date(date_closed)

    # Replace skills
    for skill in (
        await db.execute(
            select(JobListingSkill).where(JobListingSkill.job_listing_id == job_id)
        )
    ).scalars().all():
        await db.delete(skill)

    for skill_id in set(skill_ids):
        db.add(JobListingSkill(
            job_listing_id=job.id,
            skill_id=skill_id,
            required_skill=True,
            extraction_method="manual",
        ))

    await db.commit()

    return RedirectResponse(
        f"/companies/{job.company_id}/jobs?success=job_saved", status_code=303
    )


# ---------------------------------------------------------------------------
# Close job listing
# ---------------------------------------------------------------------------

@router.post("/jobs/{job_id}/close")
async def job_close(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    job = await db.get(JobListing, job_id)
    if job is None:
        raise HTTPException(status_code=404)

    await _require_poster_role(job.company_id, current_user, db)

    closed_status_id = await _get_closed_status_id(db)
    job.job_status_id = closed_status_id
    await db.commit()

    return RedirectResponse(
        f"/companies/{job.company_id}/jobs", status_code=303
    )


# ---------------------------------------------------------------------------
# Browse (anonymous)
# ---------------------------------------------------------------------------

@router.get("/jobs", response_class=HTMLResponse)
async def jobs_index(
    request: Request,
    q: str = "",
    city_id: Optional[int] = None,
    function_id: Optional[int] = None,
    job_type_id: Optional[int] = None,
    office_location_id: Optional[int] = None,
    salary_min: Optional[int] = None,
    experience_id: Optional[int] = None,
    date_posted: Optional[str] = None,
    page: int = 1,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    active_status = await _get_active_status_id(db)

    stmt = (
        select(JobListing)
        .where(JobListing.approved == True, JobListing.job_status_id == active_status)
        .options(
            selectinload(JobListing.company),
            selectinload(JobListing.city),
            selectinload(JobListing.job_type),
            selectinload(JobListing.office_location),
        )
    )

    if q.strip():
        search_vec = func.to_tsvector(
            "english",
            func.concat(
                func.coalesce(JobListing.job_title, ""),
                " ",
                func.coalesce(JobListing.job_description, ""),
            ),
        )
        stmt = stmt.where(search_vec.op("@@")(func.websearch_to_tsquery("english", q.strip())))

    if city_id:
        stmt = stmt.where(JobListing.city_id == city_id)
    if function_id:
        stmt = stmt.where(JobListing.function == function_id)
    if job_type_id:
        stmt = stmt.where(JobListing.job_type_id == job_type_id)
    if office_location_id:
        stmt = stmt.where(JobListing.office_location_id == office_location_id)
    if salary_min:
        stmt = stmt.where(JobListing.minimum_salary >= salary_min)
    if experience_id:
        stmt = stmt.where(JobListing.experience_id == experience_id)
    if date_posted:
        cutoffs = {"1d": 1, "7d": 7, "30d": 30}
        days = cutoffs.get(date_posted)
        if days:
            cutoff = date.today() - timedelta(days=days)
            stmt = stmt.where(JobListing.date_posted >= cutoff)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = await db.scalar(count_stmt) or 0
    total_pages = max(1, math.ceil(total / ITEMS_PER_PAGE))
    page = max(1, min(page, total_pages))

    stmt = stmt.order_by(JobListing.date_posted.desc().nullslast(), JobListing.created_at.desc())
    stmt = stmt.offset((page - 1) * ITEMS_PER_PAGE).limit(ITEMS_PER_PAGE)
    jobs = (await db.execute(stmt)).scalars().all()

    served_cities = (
        await db.execute(
            select(City)
            .where(City.is_served == True)
            .order_by(City.sort_order.nullslast(), City.city_name)
        )
    ).scalars().all()
    functions = (
        await db.execute(
            select(Function).where(Function.is_active == True).order_by(Function.name)
        )
    ).scalars().all()
    job_types = (
        await db.execute(
            select(JobType).where(JobType.is_active == True).order_by(JobType.name)
        )
    ).scalars().all()
    office_locations = (
        await db.execute(
            select(OfficeLocation)
            .where(OfficeLocation.is_active == True)
            .order_by(OfficeLocation.name)
        )
    ).scalars().all()

    filters = {
        "q": q,
        "city_id": city_id,
        "function_id": function_id,
        "job_type_id": job_type_id,
        "office_location_id": office_location_id,
        "salary_min": salary_min,
        "experience_id": experience_id,
        "date_posted": date_posted,
    }

    ctx = {
        "title": "Browse Jobs",
        "jobs": jobs,
        "total": total,
        "page": page,
        "total_pages": total_pages,
        "filters": filters,
        "served_cities": served_cities,
        "functions": functions,
        "job_types": job_types,
        "office_locations": office_locations,
        "current_user": current_user,
    }

    is_htmx = request.headers.get("HX-Request") == "true"
    template = "partials/job_list.html" if is_htmx else "jobs/index.html"
    return templates.TemplateResponse(request, template, ctx)


# ---------------------------------------------------------------------------
# Job detail (anonymous)
# ---------------------------------------------------------------------------

@router.get("/jobs/{job_id}", response_class=HTMLResponse)
async def job_detail(
    job_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    job = (
        await db.execute(
            select(JobListing)
            .where(JobListing.id == job_id)
            .options(
                selectinload(JobListing.company),
                selectinload(JobListing.city),
                selectinload(JobListing.job_type),
                selectinload(JobListing.office_location),
                selectinload(JobListing.function_obj),
                selectinload(JobListing.experience),
                selectinload(JobListing.job_status),
                selectinload(JobListing.skills).selectinload(JobListingSkill.skill),
                selectinload(JobListing.certifications).selectinload(
                    JobListingCertification.certification
                ),
            )
        )
    ).scalar_one_or_none()

    if job is None or (not job.approved and not (current_user and current_user.is_staff)):
        raise HTTPException(status_code=404)

    return templates.TemplateResponse(
        request,
        "jobs/detail.html",
        {"title": job.job_title, "job": job, "current_user": current_user},
    )
