import math
import re
import secrets
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..config import settings
from ..database import get_db
from ..dependencies import get_current_user, require_user
from ..utils import generate_slug, sanitize_url
from ..models.company import Company, CompanyFunction, CompanyIndustry, CompanyInvite, CompanySite, CompanySocial, UserCompanyRole
from ..models.job import JobListing
from ..models.reference import City, CompanySiteType, CompanyType, Function, Industry, JobStatus, SocialMediaType
from ..models.user import User
from ..templates import templates, is_recruiters_enabled, is_job_boards_enabled
from ..workers.email import enqueue_email

router = APIRouter(tags=["companies"])

ITEMS_PER_PAGE = settings.ITEMS_PER_PAGE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _require_company_admin(
    company_slug: str,
    current_user: User,
    db: AsyncSession,
) -> Company:
    company = await db.scalar(select(Company).where(Company.slug == company_slug))
    if company is None:
        raise HTTPException(status_code=404)
    if current_user.is_staff:
        return company
    role = await db.scalar(
        select(UserCompanyRole).where(
            UserCompanyRole.user_id == current_user.id,
            UserCompanyRole.company_id == company.id,
            UserCompanyRole.role == "company_admin",
            UserCompanyRole.approved == True,
        )
    )
    if role is None:
        raise HTTPException(status_code=403)
    return company


# ---------------------------------------------------------------------------
# Create company
# ---------------------------------------------------------------------------

@router.get("/companies/create", response_class=HTMLResponse)
async def company_create_form(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    company_types = (
        await db.execute(
            select(CompanyType)
            .where(CompanyType.is_active == True)
            .order_by(CompanyType.name)
        )
    ).scalars().all()
    industries = (
        await db.execute(
            select(Industry)
            .where(Industry.is_active == True)
            .order_by(Industry.sort_order, Industry.name)
        )
    ).scalars().all()

    return templates.TemplateResponse(
        request,
        "companies/create.html",
        {
            "title": "Register Your Company",
            "company_types": company_types,
            "industries": industries,
            "current_user": current_user,
        },
    )


@router.post("/companies/create")
async def company_create_submit(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
    common_name: str = Form(...),
    company_type_id: int = Form(...),
    website: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
):
    common_name = common_name.strip()
    if not common_name:
        raise HTTPException(status_code=400, detail="Company name is required")

    base_slug = generate_slug(common_name)
    slug = base_slug
    counter = 2
    while await db.scalar(select(Company.id).where(Company.slug == slug)):
        slug = f"{base_slug}-{counter}"
        counter += 1

    company = Company(
        common_name=common_name,
        slug=slug,
        company_type=company_type_id,
        website=sanitize_url(website),
        description=description.strip() if description else None,
        approved=False,
    )
    db.add(company)
    await db.flush()

    role = UserCompanyRole(
        user_id=current_user.id,
        company_id=company.id,
        role="company_admin",
        approved=False,
    )
    db.add(role)
    await db.commit()

    await enqueue_email(
        "company_submitted",
        {"company_name": company.common_name, "submitted_by": current_user.email, "company_id": company.id},
    )

    return RedirectResponse("/companies/pending?success=company_submitted", status_code=303)


# ---------------------------------------------------------------------------
# Join existing company
# ---------------------------------------------------------------------------

@router.get("/companies/join", response_class=HTMLResponse)
async def company_join_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    existing_roles = (
        await db.execute(
            select(UserCompanyRole)
            .where(
                UserCompanyRole.user_id == current_user.id,
                UserCompanyRole.approved == True,
            )
            .options(selectinload(UserCompanyRole.company))
        )
    ).scalars().all()

    return templates.TemplateResponse(
        request,
        "companies/join.html",
        {
            "title": "Post a Job",
            "existing_roles": existing_roles,
            "current_user": current_user,
        },
    )


@router.get("/companies/search", response_class=HTMLResponse)
async def company_search_partial(
    request: Request,
    q: str = "",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    companies = []
    user_role_map: dict = {}

    if q.strip():
        companies = (
            await db.execute(
                select(Company)
                .where(
                    Company.common_name.ilike(f"%{q.strip()}%"),
                    Company.approved == True,
                    Company.defunct == False,
                )
                .order_by(Company.common_name)
                .limit(10)
            )
        ).scalars().all()

        if companies:
            roles = (
                await db.execute(
                    select(UserCompanyRole).where(
                        UserCompanyRole.user_id == current_user.id,
                        UserCompanyRole.company_id.in_([c.id for c in companies]),
                    )
                )
            ).scalars().all()
            user_role_map = {r.company_id: r for r in roles}

    return templates.TemplateResponse(
        request,
        "partials/company_search_results.html",
        {"companies": companies, "user_role_map": user_role_map},
    )


@router.post("/companies/{company_slug}/request-role")
async def request_company_role(
    company_slug: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    company = await db.scalar(select(Company).where(Company.slug == company_slug))
    if company is None or not company.approved or company.defunct:
        raise HTTPException(status_code=404)

    existing = await db.scalar(
        select(UserCompanyRole).where(
            UserCompanyRole.user_id == current_user.id,
            UserCompanyRole.company_id == company.id,
        )
    )
    if existing:
        return RedirectResponse("/companies/join?error=already_requested", status_code=303)

    role = UserCompanyRole(
        user_id=current_user.id,
        company_id=company.id,
        role="job_poster",
        approved=False,
    )
    db.add(role)
    await db.commit()

    await enqueue_email(
        "role_requested",
        {"company_name": company.common_name, "requested_by": current_user.email, "company_id": company.id},
    )

    return RedirectResponse("/companies/pending?success=role_requested", status_code=303)


# ---------------------------------------------------------------------------
# Pending confirmation page
# ---------------------------------------------------------------------------

@router.get("/companies/pending", response_class=HTMLResponse)
async def company_pending(
    request: Request,
    current_user: User = Depends(require_user),
):
    return templates.TemplateResponse(
        request,
        "companies/pending.html",
        {"title": "Pending Approval", "current_user": current_user},
    )


# ---------------------------------------------------------------------------
# Company management (company_admin view)
# ---------------------------------------------------------------------------

@router.get("/companies/{company_slug}/manage", response_class=HTMLResponse)
async def company_manage(
    company_slug: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    company = await _require_company_admin(company_slug, current_user, db)

    posters = (
        await db.execute(
            select(UserCompanyRole)
            .where(
                UserCompanyRole.company_id == company.id,
                UserCompanyRole.approved == True,
            )
            .options(selectinload(UserCompanyRole.user))
            .order_by(UserCompanyRole.role, UserCompanyRole.created_at)
        )
    ).scalars().all()

    invites = (
        await db.execute(
            select(CompanyInvite)
            .where(
                CompanyInvite.company_id == company.id,
                CompanyInvite.accepted == False,
                CompanyInvite.expires_at > datetime.now(),
            )
            .order_by(CompanyInvite.created_at.desc())
        )
    ).scalars().all()

    return templates.TemplateResponse(
        request,
        "companies/manage.html",
        {
            "title": f"Manage — {company.common_name}",
            "company": company,
            "posters": posters,
            "invites": invites,
            "current_user": current_user,
        },
    )


@router.post("/companies/{company_slug}/invite")
async def send_company_invite(
    company_slug: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
    invited_email: str = Form(...),
):
    company = await _require_company_admin(company_slug, current_user, db)
    invited_email = invited_email.strip().lower()

    existing_user = await db.scalar(select(User).where(User.email == invited_email))
    if existing_user:
        existing_role = await db.scalar(
            select(UserCompanyRole).where(
                UserCompanyRole.user_id == existing_user.id,
                UserCompanyRole.company_id == company.id,
                UserCompanyRole.approved == True,
            )
        )
        if existing_role:
            return RedirectResponse(
                f"/companies/{company.slug}/manage?error=already_has_role", status_code=303
            )

    existing_invite = await db.scalar(
        select(CompanyInvite).where(
            CompanyInvite.company_id == company.id,
            CompanyInvite.invited_email == invited_email,
            CompanyInvite.accepted == False,
        )
    )
    if existing_invite:
        await db.delete(existing_invite)

    token = secrets.token_urlsafe(48)
    invite = CompanyInvite(
        company_id=company.id,
        invited_by=current_user.id,
        invited_email=invited_email,
        role="job_poster",
        token=token,
        expires_at=datetime.now() + timedelta(days=7),
    )
    db.add(invite)
    company_name = company.common_name  # save before commit
    await db.commit()

    await enqueue_email(
        "invite_sent",
        {
            "invited_email": invited_email,
            "company_name": company_name,
            "invited_by_name": current_user.display_name,
            "token": token,
        },
    )

    return RedirectResponse(
        f"/companies/{company_slug}/manage?success=invite_sent", status_code=303
    )


@router.post("/companies/{company_slug}/invites/{invite_id}/revoke")
async def revoke_invite(
    company_slug: str,
    invite_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    company = await _require_company_admin(company_slug, current_user, db)

    invite = await db.get(CompanyInvite, invite_id)
    if invite and invite.company_id == company.id and not invite.accepted:
        await db.delete(invite)
        await db.commit()

    return RedirectResponse(f"/companies/{company_slug}/manage", status_code=303)


@router.post("/companies/{company_slug}/posters/{role_id}/remove")
async def remove_poster(
    company_slug: str,
    role_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    company = await _require_company_admin(company_slug, current_user, db)

    role = await db.get(UserCompanyRole, role_id)
    if role and role.company_id == company.id:
        if role.user_id == current_user.id and role.role == "company_admin":
            return RedirectResponse(
                f"/companies/{company_slug}/manage?error=cannot_remove_self", status_code=303
            )
        await db.delete(role)
        await db.commit()

    return RedirectResponse(f"/companies/{company_slug}/manage", status_code=303)


# ---------------------------------------------------------------------------
# Accept invite
# ---------------------------------------------------------------------------

@router.get("/invites/{token}", response_class=HTMLResponse)
async def invite_accept_page(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    invite = await db.scalar(
        select(CompanyInvite)
        .where(CompanyInvite.token == token)
        .options(selectinload(CompanyInvite.company))
    )

    if invite is None or invite.accepted or invite.expires_at < datetime.now():
        return templates.TemplateResponse(
            request,
            "companies/invite_invalid.html",
            {"title": "Invite Expired", "current_user": current_user},
            status_code=410,
        )

    return templates.TemplateResponse(
        request,
        "companies/invite_accept.html",
        {
            "title": f"Join {invite.company.common_name}",
            "invite": invite,
            "current_user": current_user,
        },
    )


@router.post("/invites/{token}/accept")
async def invite_accept_submit(
    token: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    invite = await db.scalar(
        select(CompanyInvite)
        .where(CompanyInvite.token == token)
        .options(selectinload(CompanyInvite.company))
    )

    if invite is None or invite.accepted or invite.expires_at < datetime.now():
        raise HTTPException(status_code=410, detail="Invite expired or already used")

    company_slug = invite.company.slug  # save before commit

    existing = await db.scalar(
        select(UserCompanyRole).where(
            UserCompanyRole.user_id == current_user.id,
            UserCompanyRole.company_id == invite.company_id,
        )
    )
    if existing:
        if existing.approved:
            return RedirectResponse(f"/companies/{company_slug}/manage", status_code=303)
        existing.role = invite.role
        existing.approved = True
        existing.approved_by = invite.invited_by
        existing.approved_at = datetime.now()
    else:
        db.add(UserCompanyRole(
            user_id=current_user.id,
            company_id=invite.company_id,
            role=invite.role,
            approved=True,
            approved_by=invite.invited_by,
            approved_at=datetime.now(),
        ))

    invite.accepted = True
    invite.accepted_at = datetime.now()
    invite.accepted_by = current_user.id
    await db.commit()

    return RedirectResponse(f"/companies/{company_slug}/manage", status_code=303)


# ---------------------------------------------------------------------------
# Employer job listings dashboard
# ---------------------------------------------------------------------------

@router.get("/companies/{company_slug}/jobs", response_class=HTMLResponse)
async def company_jobs_dashboard(
    company_slug: str,
    request: Request,
    q: str = "",
    status: str = "",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    company = await _require_company_admin(company_slug, current_user, db)

    stmt = (
        select(JobListing)
        .where(JobListing.company_id == company.id)
        .options(
            selectinload(JobListing.job_status),
            selectinload(JobListing.job_type),
            selectinload(JobListing.city),
            selectinload(JobListing.office_location),
        )
        .order_by(JobListing.created_at.desc())
    )

    if q.strip():
        stmt = stmt.where(JobListing.job_title.ilike(f"%{q.strip()}%"))

    if status == "active":
        active_id = await db.scalar(select(JobStatus.id).where(JobStatus.name == "active"))
        stmt = stmt.where(JobListing.job_status_id == active_id)
    elif status == "closed":
        closed_ids = (
            await db.execute(select(JobStatus.id).where(JobStatus.name.in_(["closed", "expired"])))
        ).scalars().all()
        stmt = stmt.where(JobListing.job_status_id.in_(closed_ids))

    jobs = (await db.execute(stmt)).scalars().all()

    return templates.TemplateResponse(
        request,
        "companies/employer_listings.html",
        {
            "title": f"Job Listings — {company.common_name}",
            "company": company,
            "jobs": jobs,
            "q": q,
            "status_filter": status,
            "current_user": current_user,
        },
    )


# ---------------------------------------------------------------------------
# Browse companies (anonymous)
# ---------------------------------------------------------------------------

@router.get("/companies", response_class=HTMLResponse)
async def companies_index(
    request: Request,
    city_id: Optional[str] = None,
    industry_id: Optional[str] = None,
    function_id: Optional[str] = None,
    page: int = 1,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    authenticated = current_user is not None

    # Filters are only honoured for authenticated users
    city_id = int(city_id) if city_id and authenticated else None
    industry_id = int(industry_id) if industry_id and authenticated else None
    function_id = int(function_id) if function_id and authenticated else None

    stmt = (
        select(Company)
        .where(Company.approved == True, Company.defunct == False)
        .options(
            selectinload(Company.sites).selectinload(CompanySite.city),
            selectinload(Company.socials).selectinload(CompanySocial.social_type),
        )
    )

    if city_id:
        stmt = stmt.where(
            select(CompanySite.id)
            .where(
                CompanySite.company_id == Company.id,
                CompanySite.city_id == city_id,
                CompanySite.is_active == True,
            )
            .correlate(Company)
            .exists()
        )

    if industry_id:
        stmt = stmt.where(
            select(CompanyIndustry.id)
            .where(
                CompanyIndustry.company_id == Company.id,
                CompanyIndustry.industry_id == industry_id,
            )
            .correlate(Company)
            .exists()
        )

    if function_id:
        stmt = stmt.where(
            select(CompanyFunction.id)
            .where(
                CompanyFunction.company_id == Company.id,
                CompanyFunction.function_id == function_id,
            )
            .correlate(Company)
            .exists()
        )

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = await db.scalar(count_stmt) or 0
    total_pages = max(1, math.ceil(total / ITEMS_PER_PAGE))
    page = max(1, min(page, total_pages))

    stmt = stmt.order_by(Company.common_name).offset((page - 1) * ITEMS_PER_PAGE).limit(ITEMS_PER_PAGE)
    companies = (await db.execute(stmt)).scalars().all()

    city_options = []
    industries = []
    functions = []
    if authenticated:
        city_options = (
            await db.execute(
                select(City)
                .join(CompanySite, CompanySite.city_id == City.id)
                .join(Company, Company.id == CompanySite.company_id)
                .where(
                    Company.approved == True,
                    Company.defunct == False,
                    CompanySite.is_active == True,
                    CompanySite.city_id.isnot(None),
                )
                .distinct()
                .order_by(City.city_name)
            )
        ).scalars().all()

        industries = (
            await db.execute(
                select(Industry)
                .where(Industry.is_active == True)
                .order_by(Industry.name)
            )
        ).scalars().all()

        functions = (
            await db.execute(
                select(Function)
                .where(Function.is_active == True)
                .order_by(Function.name)
            )
        ).scalars().all()

    filters = {"city_id": city_id, "industry_id": industry_id, "function_id": function_id}

    ctx = {
        "title": "Browse Companies",
        "companies": companies,
        "total": total,
        "page": page,
        "total_pages": total_pages,
        "filters": filters,
        "city_options": city_options,
        "industries": industries,
        "functions": functions,
        "authenticated": authenticated,
        "current_user": current_user,
    }

    is_htmx = request.headers.get("HX-Request") == "true"
    template = "partials/company_list.html" if is_htmx else "companies/index.html"
    return templates.TemplateResponse(request, template, ctx)


# ---------------------------------------------------------------------------
# Recruiters page (industry = Recruiting, feature-toggled)
# ---------------------------------------------------------------------------

@router.get("/recruiters", response_class=HTMLResponse)
async def recruiters_index(
    request: Request,
    page: int = 1,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    if not is_recruiters_enabled():
        raise HTTPException(status_code=404)

    _opts = [
        selectinload(Company.sites).selectinload(CompanySite.city),
        selectinload(Company.socials).selectinload(CompanySocial.social_type),
    ]
    _base = select(Company).where(Company.approved == True, Company.defunct == False)

    def _industry_filter(stmt, industry_id):
        if industry_id:
            return stmt.where(
                select(CompanyIndustry.id)
                .where(
                    CompanyIndustry.company_id == Company.id,
                    CompanyIndustry.industry_id == industry_id,
                )
                .correlate(Company)
                .exists()
            )
        return stmt.where(False)

    # Recruiters
    recruiting_industry_id = await db.scalar(
        select(Industry.id).where(Industry.name == "Recruiting")
    )
    rec_stmt = _industry_filter(_base.options(*_opts), recruiting_industry_id)
    total = await db.scalar(select(func.count()).select_from(rec_stmt.subquery())) or 0
    total_pages = max(1, math.ceil(total / ITEMS_PER_PAGE))
    page = max(1, min(page, total_pages))
    recruiters = (await db.execute(
        rec_stmt.order_by(Company.common_name).offset((page - 1) * ITEMS_PER_PAGE).limit(ITEMS_PER_PAGE)
    )).scalars().all()

    # Job boards (only fetched if section is enabled)
    job_board_companies = []
    if is_job_boards_enabled():
        jb_industry_id = await db.scalar(
            select(Industry.id).where(Industry.name == "Job Board")
        )
        jb_stmt = _industry_filter(_base.options(*_opts), jb_industry_id)
        job_board_companies = (await db.execute(
            jb_stmt.order_by(Company.common_name)
        )).scalars().all()

    return templates.TemplateResponse(
        request,
        "recruiters/index.html",
        {
            "title": "Recruiters",
            "recruiters": recruiters,
            "total": total,
            "page": page,
            "total_pages": total_pages,
            "job_board_companies": job_board_companies,
            "job_boards_enabled": is_job_boards_enabled(),
            "current_user": current_user,
        },
    )


# ---------------------------------------------------------------------------
# Edit company profile (company_admin only)
# ---------------------------------------------------------------------------

@router.get("/companies/{company_slug}/edit", response_class=HTMLResponse)
async def company_edit_form(
    company_slug: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    await _require_company_admin(company_slug, current_user, db)

    company = (await db.execute(
        select(Company)
        .where(Company.slug == company_slug)
        .options(
            selectinload(Company.company_type_obj),
            selectinload(Company.sites).selectinload(CompanySite.city),
            selectinload(Company.socials).selectinload(CompanySocial.social_type),
        )
    )).scalar_one()

    current_industry_ids = set(
        (await db.execute(
            select(CompanyIndustry.industry_id).where(CompanyIndustry.company_id == company.id)
        )).scalars().all()
    )

    current_function_ids = set(
        (await db.execute(
            select(CompanyFunction.function_id).where(CompanyFunction.company_id == company.id)
        )).scalars().all()
    )

    company_types = (await db.execute(
        select(CompanyType).where(CompanyType.is_active == True).order_by(CompanyType.name)
    )).scalars().all()

    industries = (await db.execute(
        select(Industry).where(Industry.is_active == True).order_by(Industry.name)
    )).scalars().all()

    functions = (await db.execute(
        select(Function).where(Function.is_active == True).order_by(Function.name)
    )).scalars().all()

    social_types = (await db.execute(
        select(SocialMediaType).order_by(SocialMediaType.name)
    )).scalars().all()

    served_cities = (await db.execute(
        select(City)
        .where(City.is_served == True)
        .order_by(City.sort_order.nullslast(), City.city_name)
    )).scalars().all()

    site_types = (await db.execute(
        select(CompanySiteType).where(CompanySiteType.is_active == True).order_by(CompanySiteType.name)
    )).scalars().all()

    return templates.TemplateResponse(
        request,
        "companies/edit.html",
        {
            "title": f"Edit — {company.common_name}",
            "company": company,
            "company_types": company_types,
            "industries": industries,
            "current_industry_ids": current_industry_ids,
            "functions": functions,
            "current_function_ids": current_function_ids,
            "social_types": social_types,
            "served_cities": served_cities,
            "site_types": site_types,
            "current_user": current_user,
        },
    )


@router.post("/companies/{company_slug}/edit")
async def company_edit_submit(
    company_slug: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
    common_name: str = Form(...),
    legal_name: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    website: Optional[str] = Form(None),
    jobboard: Optional[str] = Form(None),
    company_size: Optional[str] = Form(None),
    company_type_id: int = Form(...),
    industry_ids: Optional[List[int]] = Form(None),
    function_ids: Optional[List[int]] = Form(None),
    custom_slug: Optional[str] = Form(None),
):
    await _require_company_admin(company_slug, current_user, db)

    company = (await db.execute(
        select(Company)
        .where(Company.slug == company_slug)
        .options(
            selectinload(Company.company_type_obj),
            selectinload(Company.sites).selectinload(CompanySite.city),
            selectinload(Company.socials).selectinload(CompanySocial.social_type),
        )
    )).scalar_one()

    common_name = common_name.strip()
    new_slug = generate_slug(common_name)

    if custom_slug and custom_slug.strip():
        new_slug = re.sub(r"[^a-z0-9-]+", "-", custom_slug.strip().lower()).strip("-") or new_slug

    if new_slug != company.slug:
        collision = await db.scalar(
            select(Company.id).where(Company.slug == new_slug, Company.id != company.id)
        )
        if collision:
            current_industry_ids = set(
                (await db.execute(
                    select(CompanyIndustry.industry_id).where(CompanyIndustry.company_id == company.id)
                )).scalars().all()
            )
            current_function_ids = set(
                (await db.execute(
                    select(CompanyFunction.function_id).where(CompanyFunction.company_id == company.id)
                )).scalars().all()
            )
            company_types = (await db.execute(
                select(CompanyType).where(CompanyType.is_active == True).order_by(CompanyType.name)
            )).scalars().all()
            industries = (await db.execute(
                select(Industry).where(Industry.is_active == True).order_by(Industry.name)
            )).scalars().all()
            functions = (await db.execute(
                select(Function).where(Function.is_active == True).order_by(Function.name)
            )).scalars().all()
            social_types = (await db.execute(
                select(SocialMediaType).order_by(SocialMediaType.name)
            )).scalars().all()
            served_cities = (await db.execute(
                select(City).where(City.is_served == True)
                .order_by(City.sort_order.nullslast(), City.city_name)
            )).scalars().all()

            return templates.TemplateResponse(
                request,
                "companies/edit.html",
                {
                    "title": f"Edit — {company.common_name}",
                    "company": company,
                    "company_types": company_types,
                    "industries": industries,
                    "current_industry_ids": current_industry_ids,
                    "functions": functions,
                    "current_function_ids": current_function_ids,
                    "social_types": social_types,
                    "served_cities": served_cities,
                    "current_user": current_user,
                    "slug_collision": True,
                    "pending_name": common_name,
                    "suggested_slug": f"{new_slug}-2",
                },
                status_code=422,
            )

    company.slug = new_slug
    company.common_name = common_name
    company.legal_name = legal_name.strip() if legal_name and legal_name.strip() else None
    company.description = description.strip() if description and description.strip() else None
    company.website = sanitize_url(website) if website and website.strip() else None
    company.jobboard = sanitize_url(jobboard) if jobboard and jobboard.strip() else None
    company.company_size = company_size.strip() if company_size and company_size.strip() else None
    company.company_type = company_type_id

    await db.execute(delete(CompanyIndustry).where(CompanyIndustry.company_id == company.id))
    for ind_id in (industry_ids or []):
        db.add(CompanyIndustry(company_id=company.id, industry_id=ind_id))

    await db.execute(delete(CompanyFunction).where(CompanyFunction.company_id == company.id))
    for fn_id in (function_ids or []):
        db.add(CompanyFunction(company_id=company.id, function_id=fn_id))

    await db.commit()
    return RedirectResponse(f"/companies/{new_slug}/edit?success=saved", status_code=303)


@router.post("/companies/{company_slug}/edit/socials/add")
async def company_edit_social_add(
    company_slug: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
    social_type_id: int = Form(...),
    company_url: str = Form(...),
):
    company = await _require_company_admin(company_slug, current_user, db)
    url = sanitize_url(company_url.strip())
    if url:
        db.add(CompanySocial(
            company_id=company.id,
            social_media_type_id=social_type_id,
            company_url=url,
            is_active=True,
        ))
        await db.commit()
    return RedirectResponse(f"/companies/{company_slug}/edit", status_code=303)


@router.post("/companies/{company_slug}/edit/socials/{social_id}/remove")
async def company_edit_social_remove(
    company_slug: str,
    social_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    company = await _require_company_admin(company_slug, current_user, db)
    social = await db.get(CompanySocial, social_id)
    if social and social.company_id == company.id:
        await db.delete(social)
        await db.commit()
    return RedirectResponse(f"/companies/{company_slug}/edit", status_code=303)


@router.post("/companies/{company_slug}/edit/sites/add")
async def company_edit_site_add(
    company_slug: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
    site_name: Optional[str] = Form(None),
    site_type_id: Optional[int] = Form(None),
    city_id: Optional[int] = Form(None),
    address1: Optional[str] = Form(None),
    address2: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    is_headquarters: Optional[str] = Form(None),
):
    company = await _require_company_admin(company_slug, current_user, db)
    if city_id:
        db.add(CompanySite(
            company_id=company.id,
            site_name=site_name.strip() if site_name and site_name.strip() else None,
            site_type=site_type_id or None,
            city_id=city_id,
            address1=address1.strip() if address1 and address1.strip() else None,
            address2=address2.strip() if address2 and address2.strip() else None,
            phone=phone.strip() if phone and phone.strip() else None,
            is_headquarters=is_headquarters == "true",
            is_active=True,
        ))
        await db.commit()
    return RedirectResponse(f"/companies/{company_slug}/edit", status_code=303)


@router.post("/companies/{company_slug}/edit/sites/{site_id}/remove")
async def company_edit_site_remove(
    company_slug: str,
    site_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    company = await _require_company_admin(company_slug, current_user, db)
    site = await db.get(CompanySite, site_id)
    if site and site.company_id == company.id:
        await db.delete(site)
        await db.commit()
    return RedirectResponse(f"/companies/{company_slug}/edit", status_code=303)


# ---------------------------------------------------------------------------
# Public company profile (keep last — parameterized route)
# ---------------------------------------------------------------------------

@router.get("/companies/{company_slug}", response_class=HTMLResponse)
async def company_profile(
    company_slug: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    company = (await db.execute(
        select(Company)
        .where(Company.slug == company_slug)
        .options(
            selectinload(Company.company_type_obj),
            selectinload(Company.sites).selectinload(CompanySite.city),
            selectinload(Company.sites).selectinload(CompanySite.site_type_obj),
            selectinload(Company.socials).selectinload(CompanySocial.social_type),
        )
    )).scalar_one_or_none()

    if company is None:
        raise HTTPException(status_code=404)
    is_staff = current_user and current_user.is_staff
    if not is_staff and (not company.approved or company.defunct):
        raise HTTPException(status_code=404)

    is_company_admin = False
    site_types = []
    served_cities = []
    if current_user:
        if current_user.is_staff:
            is_company_admin = True
        else:
            admin_role = await db.scalar(
                select(UserCompanyRole).where(
                    UserCompanyRole.user_id == current_user.id,
                    UserCompanyRole.company_id == company.id,
                    UserCompanyRole.role == "company_admin",
                    UserCompanyRole.approved == True,
                )
            )
            is_company_admin = admin_role is not None

    if is_company_admin:
        site_types = (await db.execute(
            select(CompanySiteType).where(CompanySiteType.is_active == True).order_by(CompanySiteType.name)
        )).scalars().all()
        served_cities = (await db.execute(
            select(City).where(City.is_served == True).order_by(City.sort_order.nullslast(), City.city_name)
        )).scalars().all()

    company_functions = (await db.execute(
        select(Function)
        .join(CompanyFunction, CompanyFunction.function_id == Function.id)
        .where(CompanyFunction.company_id == company.id, Function.is_active == True)
        .order_by(Function.name)
    )).scalars().all()

    active_status = await db.scalar(select(JobStatus.id).where(JobStatus.name == "active"))
    jobs = (
        await db.execute(
            select(JobListing)
            .where(
                JobListing.company_id == company.id,
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
    ).scalars().all()

    return templates.TemplateResponse(
        request,
        "companies/profile.html",
        {
            "title": company.common_name,
            "company": company,
            "jobs": jobs,
            "company_functions": company_functions,
            "is_company_admin": is_company_admin,
            "site_types": site_types,
            "served_cities": served_cities,
            "current_user": current_user,
        },
    )


@router.post("/companies/{company_slug}/sites/add")
async def company_site_add(
    company_slug: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
    site_name: Optional[str] = Form(None),
    site_type_id: Optional[int] = Form(None),
    city_id: Optional[int] = Form(None),
    address1: Optional[str] = Form(None),
    address2: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    is_headquarters: Optional[str] = Form(None),
):
    company = await _require_company_admin(company_slug, current_user, db)
    db.add(CompanySite(
        company_id=company.id,
        site_name=site_name.strip() if site_name and site_name.strip() else None,
        site_type=site_type_id or None,
        city_id=city_id or None,
        address1=address1.strip() if address1 and address1.strip() else None,
        address2=address2.strip() if address2 and address2.strip() else None,
        phone=phone.strip() if phone and phone.strip() else None,
        is_headquarters=is_headquarters == "true",
        is_active=True,
    ))
    await db.commit()
    return RedirectResponse(f"/companies/{company_slug}", status_code=303)


@router.post("/companies/{company_slug}/sites/{site_id}/edit")
async def company_site_edit(
    company_slug: str,
    site_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
    site_name: Optional[str] = Form(None),
    site_type_id: Optional[str] = Form(None),
    city_id: Optional[str] = Form(None),
    address1: Optional[str] = Form(None),
    address2: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    is_headquarters: Optional[str] = Form(None),
):
    company = await _require_company_admin(company_slug, current_user, db)
    site = await db.get(CompanySite, site_id)
    if site is None or site.company_id != company.id:
        raise HTTPException(status_code=404)

    site.site_name = site_name.strip() if site_name and site_name.strip() else None
    site.site_type = int(site_type_id) if site_type_id and site_type_id.strip() else None
    site.city_id = int(city_id) if city_id and city_id.strip() else None
    site.address1 = address1.strip() if address1 and address1.strip() else None
    site.address2 = address2.strip() if address2 and address2.strip() else None
    site.phone = phone.strip() if phone and phone.strip() else None
    site.is_headquarters = is_headquarters == "true"

    await db.commit()
    return RedirectResponse(f"/companies/{company_slug}", status_code=303)


@router.post("/companies/{company_slug}/sites/{site_id}/toggle")
async def company_site_toggle(
    company_slug: str,
    site_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    company = await _require_company_admin(company_slug, current_user, db)
    site = await db.get(CompanySite, site_id)
    if site and site.company_id == company.id:
        site.is_active = not site.is_active
        await db.commit()
    return RedirectResponse(f"/companies/{company_slug}", status_code=303)


# ---------------------------------------------------------------------------
# Admin: disable / re-enable a company
# ---------------------------------------------------------------------------

@router.post("/companies/{company_slug}/disable", response_class=HTMLResponse)
async def company_disable(
    company_slug: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    if not current_user.is_staff:
        raise HTTPException(status_code=403)
    company = await db.scalar(select(Company).where(Company.slug == company_slug))
    if company is None:
        raise HTTPException(status_code=404)
    company.defunct = True
    await db.commit()
    return RedirectResponse(f"/companies/{company_slug}", status_code=303)


@router.post("/companies/{company_slug}/enable", response_class=HTMLResponse)
async def company_enable(
    company_slug: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    if not current_user.is_staff:
        raise HTTPException(status_code=403)
    company = await db.scalar(select(Company).where(Company.slug == company_slug))
    if company is None:
        raise HTTPException(status_code=404)
    company.defunct = False
    await db.commit()
    return RedirectResponse(f"/companies/{company_slug}", status_code=303)
