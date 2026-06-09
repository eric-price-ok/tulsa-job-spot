import math
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
from ..utils import sanitize_url
from ..models.company import Company, CompanyIndustry, CompanyInvite, CompanySite, CompanySocial, UserCompanyRole
from ..models.job import JobListing
from ..models.reference import City, CompanyType, Industry, JobStatus, SocialMediaType
from ..models.user import User
from ..templates import templates
from ..workers.email import enqueue_email

router = APIRouter(tags=["companies"])

ITEMS_PER_PAGE = settings.ITEMS_PER_PAGE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _require_company_admin(
    company_id: int,
    current_user: User,
    db: AsyncSession,
) -> Company:
    company = await db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404)
    if current_user.is_staff:
        return company
    role = await db.scalar(
        select(UserCompanyRole).where(
            UserCompanyRole.user_id == current_user.id,
            UserCompanyRole.company_id == company_id,
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

    company = Company(
        common_name=common_name,
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


@router.post("/companies/{company_id}/request-role")
async def request_company_role(
    company_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    company = await db.get(Company, company_id)
    if company is None or not company.approved or company.defunct:
        raise HTTPException(status_code=404)

    existing = await db.scalar(
        select(UserCompanyRole).where(
            UserCompanyRole.user_id == current_user.id,
            UserCompanyRole.company_id == company_id,
        )
    )
    if existing:
        return RedirectResponse("/companies/join?error=already_requested", status_code=303)

    role = UserCompanyRole(
        user_id=current_user.id,
        company_id=company_id,
        role="job_poster",
        approved=False,
    )
    db.add(role)
    await db.commit()

    await enqueue_email(
        "role_requested",
        {"company_name": company.common_name, "requested_by": current_user.email, "company_id": company_id},
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

@router.get("/companies/{company_id}/manage", response_class=HTMLResponse)
async def company_manage(
    company_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    company = await _require_company_admin(company_id, current_user, db)

    posters = (
        await db.execute(
            select(UserCompanyRole)
            .where(
                UserCompanyRole.company_id == company_id,
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
                CompanyInvite.company_id == company_id,
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


@router.post("/companies/{company_id}/invite")
async def send_company_invite(
    company_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
    invited_email: str = Form(...),
):
    company = await _require_company_admin(company_id, current_user, db)
    invited_email = invited_email.strip().lower()

    # Check if user already has an active role here
    existing_user = await db.scalar(select(User).where(User.email == invited_email))
    if existing_user:
        existing_role = await db.scalar(
            select(UserCompanyRole).where(
                UserCompanyRole.user_id == existing_user.id,
                UserCompanyRole.company_id == company_id,
                UserCompanyRole.approved == True,
            )
        )
        if existing_role:
            return RedirectResponse(
                f"/companies/{company_id}/manage?error=already_has_role", status_code=303
            )

    # Replace any existing pending invite for this email
    existing_invite = await db.scalar(
        select(CompanyInvite).where(
            CompanyInvite.company_id == company_id,
            CompanyInvite.invited_email == invited_email,
            CompanyInvite.accepted == False,
        )
    )
    if existing_invite:
        await db.delete(existing_invite)

    token = secrets.token_urlsafe(48)
    invite = CompanyInvite(
        company_id=company_id,
        invited_by=current_user.id,
        invited_email=invited_email,
        role="job_poster",
        token=token,
        expires_at=datetime.now() + timedelta(days=7),
    )
    db.add(invite)
    await db.commit()

    await enqueue_email(
        "invite_sent",
        {
            "invited_email": invited_email,
            "company_name": company.common_name,
            "invited_by_name": current_user.display_name,
            "token": token,
        },
    )

    return RedirectResponse(
        f"/companies/{company_id}/manage?success=invite_sent", status_code=303
    )


@router.post("/companies/{company_id}/invites/{invite_id}/revoke")
async def revoke_invite(
    company_id: int,
    invite_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    await _require_company_admin(company_id, current_user, db)

    invite = await db.get(CompanyInvite, invite_id)
    if invite and invite.company_id == company_id and not invite.accepted:
        await db.delete(invite)
        await db.commit()

    return RedirectResponse(f"/companies/{company_id}/manage", status_code=303)


@router.post("/companies/{company_id}/posters/{role_id}/remove")
async def remove_poster(
    company_id: int,
    role_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    await _require_company_admin(company_id, current_user, db)

    role = await db.get(UserCompanyRole, role_id)
    if role and role.company_id == company_id:
        if role.user_id == current_user.id and role.role == "company_admin":
            return RedirectResponse(
                f"/companies/{company_id}/manage?error=cannot_remove_self", status_code=303
            )
        await db.delete(role)
        await db.commit()

    return RedirectResponse(f"/companies/{company_id}/manage", status_code=303)


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

    existing = await db.scalar(
        select(UserCompanyRole).where(
            UserCompanyRole.user_id == current_user.id,
            UserCompanyRole.company_id == invite.company_id,
        )
    )
    if existing:
        if existing.approved:
            return RedirectResponse(f"/companies/{invite.company_id}/manage", status_code=303)
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

    return RedirectResponse(f"/companies/{invite.company_id}/manage", status_code=303)


# ---------------------------------------------------------------------------
# Employer job listings dashboard
# ---------------------------------------------------------------------------

@router.get("/companies/{company_id}/jobs", response_class=HTMLResponse)
async def company_jobs_dashboard(
    company_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    company = await _require_company_admin(company_id, current_user, db)

    jobs = (
        await db.execute(
            select(JobListing)
            .where(JobListing.company_id == company_id)
            .options(
                selectinload(JobListing.job_status),
                selectinload(JobListing.job_type),
                selectinload(JobListing.city),
                selectinload(JobListing.office_location),
            )
            .order_by(JobListing.created_at.desc())
        )
    ).scalars().all()

    return templates.TemplateResponse(
        request,
        "companies/employer_listings.html",
        {
            "title": f"Job Listings — {company.common_name}",
            "company": company,
            "jobs": jobs,
            "current_user": current_user,
        },
    )


# ---------------------------------------------------------------------------
# Browse companies (anonymous)
# ---------------------------------------------------------------------------

@router.get("/companies", response_class=HTMLResponse)
async def companies_index(
    request: Request,
    city_id: Optional[int] = None,
    industry_id: Optional[int] = None,
    page: int = 1,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
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

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = await db.scalar(count_stmt) or 0
    total_pages = max(1, math.ceil(total / ITEMS_PER_PAGE))
    page = max(1, min(page, total_pages))

    stmt = stmt.order_by(Company.common_name).offset((page - 1) * ITEMS_PER_PAGE).limit(ITEMS_PER_PAGE)
    companies = (await db.execute(stmt)).scalars().all()

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
            .order_by(Industry.sort_order.nullslast(), Industry.name)
        )
    ).scalars().all()

    filters = {"city_id": city_id, "industry_id": industry_id}

    ctx = {
        "title": "Browse Companies",
        "companies": companies,
        "total": total,
        "page": page,
        "total_pages": total_pages,
        "filters": filters,
        "city_options": city_options,
        "industries": industries,
        "current_user": current_user,
    }

    is_htmx = request.headers.get("HX-Request") == "true"
    template = "partials/company_list.html" if is_htmx else "companies/index.html"
    return templates.TemplateResponse(request, template, ctx)


# ---------------------------------------------------------------------------
# Edit company profile (company_admin only)
# ---------------------------------------------------------------------------

@router.get("/companies/{company_id}/edit", response_class=HTMLResponse)
async def company_edit_form(
    company_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    await _require_company_admin(company_id, current_user, db)

    result = await db.execute(
        select(Company)
        .where(Company.id == company_id)
        .options(
            selectinload(Company.company_type_obj),
            selectinload(Company.sites).selectinload(CompanySite.city),
            selectinload(Company.socials).selectinload(CompanySocial.social_type),
        )
    )
    company = result.scalar_one()

    current_industry_ids = set(
        (await db.execute(
            select(CompanyIndustry.industry_id).where(CompanyIndustry.company_id == company_id)
        )).scalars().all()
    )

    company_types = (await db.execute(
        select(CompanyType).where(CompanyType.is_active == True).order_by(CompanyType.name)
    )).scalars().all()

    industries = (await db.execute(
        select(Industry).where(Industry.is_active == True).order_by(Industry.name)
    )).scalars().all()

    social_types = (await db.execute(
        select(SocialMediaType).order_by(SocialMediaType.name)
    )).scalars().all()

    served_cities = (await db.execute(
        select(City)
        .where(City.is_served == True)
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
            "social_types": social_types,
            "served_cities": served_cities,
            "current_user": current_user,
        },
    )


@router.post("/companies/{company_id}/edit")
async def company_edit_submit(
    company_id: int,
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
):
    company = await _require_company_admin(company_id, current_user, db)

    company.common_name = common_name.strip()
    company.legal_name = legal_name.strip() if legal_name and legal_name.strip() else None
    company.description = description.strip() if description and description.strip() else None
    company.website = sanitize_url(website) if website and website.strip() else None
    company.jobboard = sanitize_url(jobboard) if jobboard and jobboard.strip() else None
    company.company_size = company_size.strip() if company_size and company_size.strip() else None
    company.company_type = company_type_id

    await db.execute(delete(CompanyIndustry).where(CompanyIndustry.company_id == company_id))
    for ind_id in (industry_ids or []):
        db.add(CompanyIndustry(company_id=company_id, industry_id=ind_id))

    await db.commit()
    return RedirectResponse(f"/companies/{company_id}/edit?success=saved", status_code=303)


@router.post("/companies/{company_id}/edit/socials/add")
async def company_edit_social_add(
    company_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
    social_type_id: int = Form(...),
    company_url: str = Form(...),
):
    await _require_company_admin(company_id, current_user, db)
    url = sanitize_url(company_url.strip())
    if url:
        db.add(CompanySocial(
            company_id=company_id,
            social_media_type_id=social_type_id,
            company_url=url,
            is_active=True,
        ))
        await db.commit()
    return RedirectResponse(f"/companies/{company_id}/edit", status_code=303)


@router.post("/companies/{company_id}/edit/socials/{social_id}/remove")
async def company_edit_social_remove(
    company_id: int,
    social_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    await _require_company_admin(company_id, current_user, db)
    social = await db.get(CompanySocial, social_id)
    if social and social.company_id == company_id:
        await db.delete(social)
        await db.commit()
    return RedirectResponse(f"/companies/{company_id}/edit", status_code=303)


@router.post("/companies/{company_id}/edit/sites/add")
async def company_edit_site_add(
    company_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
    city_id: Optional[int] = Form(None),
    phone: Optional[str] = Form(None),
    is_headquarters: Optional[str] = Form(None),
):
    await _require_company_admin(company_id, current_user, db)
    if city_id:
        db.add(CompanySite(
            company_id=company_id,
            city_id=city_id,
            phone=phone.strip() if phone and phone.strip() else None,
            is_headquarters=is_headquarters == "true",
            is_active=True,
        ))
        await db.commit()
    return RedirectResponse(f"/companies/{company_id}/edit", status_code=303)


@router.post("/companies/{company_id}/edit/sites/{site_id}/remove")
async def company_edit_site_remove(
    company_id: int,
    site_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    await _require_company_admin(company_id, current_user, db)
    site = await db.get(CompanySite, site_id)
    if site and site.company_id == company_id:
        await db.delete(site)
        await db.commit()
    return RedirectResponse(f"/companies/{company_id}/edit", status_code=303)


# ---------------------------------------------------------------------------
# Public company profile (keep last — parameterized route)
# ---------------------------------------------------------------------------

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
            selectinload(Company.socials).selectinload(CompanySocial.social_type),
        )
    )
    company = result.scalar_one_or_none()

    if company is None or (not company.approved and not (current_user and current_user.is_staff)):
        raise HTTPException(status_code=404)

    active_status = await db.scalar(select(JobStatus.id).where(JobStatus.name == "active"))
    jobs = (
        await db.execute(
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
    ).scalars().all()

    return templates.TemplateResponse(
        request,
        "companies/profile.html",
        {
            "title": company.common_name,
            "company": company,
            "jobs": jobs,
            "current_user": current_user,
        },
    )
