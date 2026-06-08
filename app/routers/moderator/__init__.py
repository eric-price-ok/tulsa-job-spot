from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...database import get_db
from ...dependencies import require_moderator
from ...models.company import Company, UserCompanyRole
from ...models.job import JobListing
from ...models.user import User
from ...templates import templates
from ...workers.email import enqueue_email

router = APIRouter(prefix="/moderator", tags=["moderator"])


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@router.get("", response_class=HTMLResponse)
async def moderator_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_moderator),
):
    pending_companies = await db.scalar(
        select(func.count(Company.id)).where(
            Company.approved == False, Company.defunct == False
        )
    ) or 0

    pending_roles = await db.scalar(
        select(func.count(UserCompanyRole.id))
        .join(Company, UserCompanyRole.company_id == Company.id)
        .where(
            UserCompanyRole.approved == False,
            Company.approved == True,
            Company.defunct == False,
        )
    ) or 0

    from ...models.reference import JobStatus as _JS
    active_status_id = await db.scalar(select(_JS.id).where(_JS.name == "active"))
    pending_jobs = await db.scalar(
        select(func.count(JobListing.id)).where(
            JobListing.approved == False,
            JobListing.job_status_id == active_status_id,
        )
    ) or 0

    return templates.TemplateResponse(
        request,
        "moderator/dashboard.html",
        {
            "title": "Moderator Dashboard",
            "pending_companies": pending_companies,
            "pending_roles": pending_roles,
            "pending_jobs": pending_jobs,
            "current_user": current_user,
        },
    )


# ---------------------------------------------------------------------------
# Company approval queue
# ---------------------------------------------------------------------------

@router.get("/companies", response_class=HTMLResponse)
async def company_queue(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_moderator),
):
    companies = (
        await db.execute(
            select(Company)
            .where(Company.approved == False, Company.defunct == False)
            .options(selectinload(Company.user_roles).selectinload(UserCompanyRole.user))
            .order_by(Company.created_at.asc())
        )
    ).scalars().all()

    return templates.TemplateResponse(
        request,
        "moderator/companies.html",
        {
            "title": "Pending Companies",
            "companies": companies,
            "current_user": current_user,
        },
    )


@router.post("/companies/{company_id}/approve")
async def approve_company(
    company_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_moderator),
    role: str = Form("company_admin"),
):
    company = (
        await db.execute(
            select(Company)
            .where(Company.id == company_id)
            .options(selectinload(Company.user_roles).selectinload(UserCompanyRole.user))
        )
    ).scalar_one_or_none()

    if company is None:
        return RedirectResponse("/moderator/companies", status_code=303)

    company.approved = True
    company.approved_by = current_user.id
    company.approved_at = datetime.now()

    for ucr in company.user_roles:
        if not ucr.approved:
            ucr.role = role
            ucr.approved = True
            ucr.approved_by = current_user.id
            ucr.approved_at = datetime.now()
            await enqueue_email(
                "company_approved",
                {
                    "to_email": ucr.user.email,
                    "company_name": company.common_name,
                    "role": role,
                },
            )

    await db.commit()
    return RedirectResponse("/moderator/companies?success=approved", status_code=303)


@router.post("/companies/{company_id}/reject")
async def reject_company(
    company_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_moderator),
    reason: str = Form(""),
):
    company = (
        await db.execute(
            select(Company)
            .where(Company.id == company_id)
            .options(selectinload(Company.user_roles).selectinload(UserCompanyRole.user))
        )
    ).scalar_one_or_none()

    if company is None:
        return RedirectResponse("/moderator/companies", status_code=303)

    for ucr in company.user_roles:
        await enqueue_email(
            "company_rejected",
            {
                "to_email": ucr.user.email,
                "company_name": company.common_name,
                "reason": reason or "No reason provided.",
            },
        )
        await db.delete(ucr)

    company.defunct = True
    await db.commit()
    return RedirectResponse("/moderator/companies?success=rejected", status_code=303)


# ---------------------------------------------------------------------------
# User role approval queue
# ---------------------------------------------------------------------------

@router.get("/roles", response_class=HTMLResponse)
async def role_queue(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_moderator),
):
    pending = (
        await db.execute(
            select(UserCompanyRole)
            .join(Company, UserCompanyRole.company_id == Company.id)
            .where(
                UserCompanyRole.approved == False,
                Company.approved == True,
                Company.defunct == False,
            )
            .options(
                selectinload(UserCompanyRole.user),
                selectinload(UserCompanyRole.company),
            )
            .order_by(UserCompanyRole.created_at.asc())
        )
    ).scalars().all()

    return templates.TemplateResponse(
        request,
        "moderator/roles.html",
        {
            "title": "Pending Role Requests",
            "pending": pending,
            "current_user": current_user,
        },
    )


@router.post("/roles/{role_id}/approve")
async def approve_role(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_moderator),
    role: str = Form("job_poster"),
):
    ucr = (
        await db.execute(
            select(UserCompanyRole)
            .where(UserCompanyRole.id == role_id)
            .options(
                selectinload(UserCompanyRole.user),
                selectinload(UserCompanyRole.company),
            )
        )
    ).scalar_one_or_none()

    if ucr is None:
        return RedirectResponse("/moderator/roles", status_code=303)

    ucr.role = role
    ucr.approved = True
    ucr.approved_by = current_user.id
    ucr.approved_at = datetime.now()
    await db.commit()

    await enqueue_email(
        "role_approved",
        {
            "to_email": ucr.user.email,
            "company_name": ucr.company.common_name,
            "role": role,
        },
    )

    return RedirectResponse("/moderator/roles?success=approved", status_code=303)


@router.post("/roles/{role_id}/reject")
async def reject_role(
    role_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_moderator),
    reason: str = Form(""),
):
    ucr = (
        await db.execute(
            select(UserCompanyRole)
            .where(UserCompanyRole.id == role_id)
            .options(
                selectinload(UserCompanyRole.user),
                selectinload(UserCompanyRole.company),
            )
        )
    ).scalar_one_or_none()

    if ucr is None:
        return RedirectResponse("/moderator/roles", status_code=303)

    await enqueue_email(
        "role_rejected",
        {
            "to_email": ucr.user.email,
            "company_name": ucr.company.common_name,
            "reason": reason or "No reason provided.",
        },
    )

    await db.delete(ucr)
    await db.commit()
    return RedirectResponse("/moderator/roles?success=rejected", status_code=303)


# ---------------------------------------------------------------------------
# Job listing approval queue
# ---------------------------------------------------------------------------

@router.get("/jobs", response_class=HTMLResponse)
async def job_queue(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_moderator),
):
    from ...models.reference import JobStatus as _JobStatus
    active_status_id = await db.scalar(
        select(_JobStatus.id).where(_JobStatus.name == "active")
    )

    pending = (
        await db.execute(
            select(JobListing)
            .where(
                JobListing.approved == False,
                JobListing.job_status_id == active_status_id,
            )
            .options(
                selectinload(JobListing.company),
                selectinload(JobListing.poster),
            )
            .order_by(JobListing.created_at.asc())
        )
    ).scalars().all()

    return templates.TemplateResponse(
        request,
        "moderator/jobs.html",
        {
            "title": "Pending Job Listings",
            "pending": pending,
            "current_user": current_user,
        },
    )


@router.post("/jobs/{job_id}/approve")
async def approve_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_moderator),
):
    job = (
        await db.execute(
            select(JobListing)
            .where(JobListing.id == job_id)
            .options(selectinload(JobListing.poster))
        )
    ).scalar_one_or_none()

    if job is None:
        return RedirectResponse("/moderator/jobs", status_code=303)

    job.approved = True
    job.approved_by = current_user.id
    job.approved_at = datetime.now()
    await db.commit()

    await enqueue_email(
        "job_approved",
        {
            "to_email": job.poster.email,
            "job_title": job.job_title,
            "job_id": job.id,
        },
    )

    return RedirectResponse("/moderator/jobs?success=approved", status_code=303)


@router.post("/jobs/{job_id}/reject")
async def reject_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_moderator),
    reason: str = Form(""),
):
    job = (
        await db.execute(
            select(JobListing)
            .where(JobListing.id == job_id)
            .options(selectinload(JobListing.poster))
        )
    ).scalar_one_or_none()

    if job is None:
        return RedirectResponse("/moderator/jobs", status_code=303)

    await enqueue_email(
        "job_rejected",
        {
            "to_email": job.poster.email,
            "job_title": job.job_title,
            "reason": reason or "No reason provided.",
        },
    )

    from ...models.reference import JobStatus as _JS2
    closed_status_id = await db.scalar(
        select(_JS2.id).where(_JS2.name == "closed")
    )
    job.job_status_id = closed_status_id
    await db.commit()

    return RedirectResponse("/moderator/jobs?success=rejected", status_code=303)
