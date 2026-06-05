import math
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..config import settings
from ..database import get_db
from ..dependencies import get_current_user
from ..models.job import JobListing, JobListingCertification, JobListingSkill
from ..models.reference import City, Function, JobStatus, JobType, OfficeLocation
from ..models.user import User
from ..templates import templates

router = APIRouter(tags=["jobs"])

ITEMS_PER_PAGE = settings.ITEMS_PER_PAGE


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
    date_posted: Optional[str] = None,  # "1d", "7d", "30d"
    page: int = 1,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    # Resolve active job status ID
    active_status = await db.scalar(select(JobStatus.id).where(JobStatus.name == "active"))

    # Base query — approved active jobs only
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

    # Full-text search
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

    # Filters
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

    # Count before pagination
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = await db.scalar(count_stmt) or 0
    total_pages = max(1, math.ceil(total / ITEMS_PER_PAGE))
    page = max(1, min(page, total_pages))

    stmt = stmt.order_by(JobListing.date_posted.desc().nullslast(), JobListing.created_at.desc())
    stmt = stmt.offset((page - 1) * ITEMS_PER_PAGE).limit(ITEMS_PER_PAGE)
    result = await db.execute(stmt)
    jobs = result.scalars().all()

    # Filter options for sidebar
    served_cities = (await db.execute(
        select(City).where(City.is_served == True).order_by(City.sort_order.nullslast(), City.city_name)
    )).scalars().all()
    functions = (await db.execute(
        select(Function).where(Function.is_active == True).order_by(Function.name)
    )).scalars().all()
    job_types = (await db.execute(
        select(JobType).where(JobType.is_active == True).order_by(JobType.name)
    )).scalars().all()
    office_locations = (await db.execute(
        select(OfficeLocation).where(OfficeLocation.is_active == True).order_by(OfficeLocation.name)
    )).scalars().all()

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


@router.get("/jobs/{job_id}", response_class=HTMLResponse)
async def job_detail(
    job_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    result = await db.execute(
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
            selectinload(JobListing.certifications).selectinload(JobListingCertification.certification),
        )
    )
    job = result.scalar_one_or_none()

    if job is None or (not job.approved and not (current_user and current_user.is_staff)):
        from fastapi import HTTPException
        raise HTTPException(status_code=404)

    return templates.TemplateResponse(
        request,
        "jobs/detail.html",
        {"title": job.job_title, "job": job, "current_user": current_user},
    )
