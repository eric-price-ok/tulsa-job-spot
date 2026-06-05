from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import get_db
from ..dependencies import get_current_user
from ..models.company import Company
from ..models.job import JobListing
from ..models.reference import JobStatus
from ..models.user import User
from ..templates import templates

router = APIRouter(tags=["companies"])


@router.get("/companies/{company_id}", response_class=HTMLResponse)
async def company_profile(
    company_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    result = await db.execute(
        select(Company)
        .where(Company.id == company_id)
        .options(
            selectinload(Company.sites),
            selectinload(Company.socials).selectinload(
                Company.socials.property.mapper.class_.social_type
            ),
        )
    )
    company = result.scalar_one_or_none()

    if company is None or (not company.approved and not (current_user and current_user.is_staff)):
        raise HTTPException(status_code=404)

    # Active job listings for this company
    active_status = await db.scalar(select(JobStatus.id).where(JobStatus.name == "active"))
    jobs_result = await db.execute(
        select(JobListing)
        .where(
            JobListing.company_id == company_id,
            JobListing.approved == True,
            JobListing.job_status_id == active_status,
        )
        .options(
            selectinload(JobListing.city),
            selectinload(JobListing.job_type),
            selectinload(JobListing.office_location),
        )
        .order_by(JobListing.date_posted.desc().nullslast())
    )
    jobs = jobs_result.scalars().all()

    return templates.TemplateResponse(
        request,
        "companies/profile.html",
        {"title": company.common_name, "company": company, "jobs": jobs, "current_user": current_user},
    )
