from datetime import datetime
from typing import Optional, Type

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...database import get_db
from ...dependencies import require_admin
from ...models.company import Company, UserCompanyRole
from ...models.job import JobListing
from ...models.reference import (
    City,
    Experience,
    Function,
    FunctionSpecialty,
    Industry,
    JobType,
    OfficeLocation,
    Skill,
    State,
)
from ...models.scraping import ScraperSource, ScrapingLog
from ...models.user import User
from ...templates import templates

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Reference table registry  (slug → model, display label)
# ---------------------------------------------------------------------------

_REFERENCE_REGISTRY: dict[str, tuple[type, str]] = {
    "skills":           (Skill,           "Skills"),
    "job-types":        (JobType,         "Job Types"),
    "industries":       (Industry,        "Industries"),
    "office-locations": (OfficeLocation,  "Office Locations"),
    "experience":       (Experience,      "Experience Levels"),
}


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@router.get("", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    from ...models.reference import JobStatus as _JS
    active_status_id = await db.scalar(select(_JS.id).where(_JS.name == "active"))

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
    pending_jobs = await db.scalar(
        select(func.count(JobListing.id)).where(
            JobListing.approved == False,
            JobListing.job_status_id == active_status_id,
        )
    ) or 0
    served_cities = await db.scalar(
        select(func.count(City.id)).where(City.is_served == True)
    ) or 0
    active_scrapers = await db.scalar(
        select(func.count(ScraperSource.id)).where(ScraperSource.is_active == True)
    ) or 0

    recent_logs = (
        await db.execute(
            select(ScrapingLog)
            .order_by(ScrapingLog.started_at.desc())
            .limit(5)
        )
    ).scalars().all()

    return templates.TemplateResponse(
        request,
        "admin/dashboard.html",
        {
            "title": "Admin",
            "pending_companies": pending_companies,
            "pending_roles": pending_roles,
            "pending_jobs": pending_jobs,
            "served_cities": served_cities,
            "active_scrapers": active_scrapers,
            "recent_logs": recent_logs,
            "current_user": current_user,
        },
    )


# ---------------------------------------------------------------------------
# Cities management
# ---------------------------------------------------------------------------

@router.get("/cities", response_class=HTMLResponse)
async def cities_list(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    cities = (
        await db.execute(
            select(City)
            .options(selectinload(City.state))
            .order_by(City.is_served.desc(), City.sort_order.nullslast(), City.city_name)
        )
    ).scalars().all()

    states = (
        await db.execute(select(State).where(State.is_active == True).order_by(State.name))
    ).scalars().all()

    return templates.TemplateResponse(
        request,
        "admin/cities.html",
        {
            "title": "Manage Cities",
            "cities": cities,
            "states": states,
            "current_user": current_user,
        },
    )


@router.post("/cities/{city_id}/toggle-served")
async def toggle_city_served(
    city_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    city = await db.get(City, city_id)
    if city is None:
        raise HTTPException(status_code=404)
    city.is_served = not city.is_served
    await db.commit()
    return RedirectResponse("/admin/cities", status_code=303)


@router.post("/cities/{city_id}/sort")
async def update_city_sort(
    city_id: int,
    sort_order: Optional[int] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    city = await db.get(City, city_id)
    if city is None:
        raise HTTPException(status_code=404)
    city.sort_order = sort_order
    await db.commit()
    return RedirectResponse("/admin/cities", status_code=303)


@router.post("/cities/add")
async def add_city(
    city_name: str = Form(...),
    state_id: Optional[int] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    city_name = city_name.strip()
    if not city_name:
        return RedirectResponse("/admin/cities?error=name_required", status_code=303)
    db.add(City(city_name=city_name, state_id=state_id or None, is_served=True))
    await db.commit()
    return RedirectResponse("/admin/cities?success=added", status_code=303)


# ---------------------------------------------------------------------------
# Functions + specialties (separate page due to hierarchy)
# ---------------------------------------------------------------------------

@router.get("/reference/functions", response_class=HTMLResponse)
async def functions_list(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    functions = (
        await db.execute(
            select(Function)
            .options(selectinload(Function.specialties))
            .order_by(Function.name)
        )
    ).scalars().all()

    return templates.TemplateResponse(
        request,
        "admin/functions.html",
        {
            "title": "Job Functions",
            "functions": functions,
            "current_user": current_user,
        },
    )


@router.post("/reference/functions/add")
async def add_function(
    name: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    name = name.strip()
    if name:
        db.add(Function(name=name))
        await db.commit()
    return RedirectResponse("/admin/reference/functions?success=added", status_code=303)


@router.post("/reference/functions/{fn_id}/toggle")
async def toggle_function(
    fn_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    fn = await db.get(Function, fn_id)
    if fn:
        fn.is_active = not fn.is_active
        await db.commit()
    return RedirectResponse("/admin/reference/functions", status_code=303)


@router.post("/reference/functions/{fn_id}/specialties/add")
async def add_specialty(
    fn_id: int,
    name: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    name = name.strip()
    if name:
        db.add(FunctionSpecialty(function_id=fn_id, specialty=name))
        await db.commit()
    return RedirectResponse("/admin/reference/functions?success=added", status_code=303)


@router.post("/reference/specialties/{spec_id}/toggle")
async def toggle_specialty(
    spec_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    spec = await db.get(FunctionSpecialty, spec_id)
    if spec:
        spec.is_active = not spec.is_active
        await db.commit()
    return RedirectResponse("/admin/reference/functions", status_code=303)


# ---------------------------------------------------------------------------
# Generic reference table management
# ---------------------------------------------------------------------------

@router.get("/reference/{table}", response_class=HTMLResponse)
async def reference_table_list(
    table: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if table not in _REFERENCE_REGISTRY:
        raise HTTPException(status_code=404)

    model_cls, label = _REFERENCE_REGISTRY[table]
    entries = (
        await db.execute(select(model_cls).order_by(model_cls.name))
    ).scalars().all()

    return templates.TemplateResponse(
        request,
        "admin/reference_table.html",
        {
            "title": label,
            "table": table,
            "label": label,
            "entries": entries,
            "current_user": current_user,
        },
    )


@router.post("/reference/{table}/add")
async def reference_table_add(
    table: str,
    name: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if table not in _REFERENCE_REGISTRY:
        raise HTTPException(status_code=404)

    model_cls, _ = _REFERENCE_REGISTRY[table]
    name = name.strip()
    if name:
        db.add(model_cls(name=name))
        await db.commit()
    return RedirectResponse(f"/admin/reference/{table}?success=added", status_code=303)


@router.post("/reference/{table}/{entry_id}/toggle")
async def reference_table_toggle(
    table: str,
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if table not in _REFERENCE_REGISTRY:
        raise HTTPException(status_code=404)

    model_cls, _ = _REFERENCE_REGISTRY[table]
    entry = await db.get(model_cls, entry_id)
    if entry:
        entry.is_active = not entry.is_active
        await db.commit()
    return RedirectResponse(f"/admin/reference/{table}", status_code=303)


# ---------------------------------------------------------------------------
# Scraper sources
# ---------------------------------------------------------------------------

@router.get("/scrapers", response_class=HTMLResponse)
async def scrapers_list(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    sources = (
        await db.execute(
            select(ScraperSource)
            .options(selectinload(ScraperSource.company))
            .order_by(ScraperSource.name)
        )
    ).scalars().all()

    companies = (
        await db.execute(
            select(Company)
            .where(Company.approved == True, Company.defunct == False)
            .order_by(Company.common_name)
        )
    ).scalars().all()

    return templates.TemplateResponse(
        request,
        "admin/scrapers.html",
        {
            "title": "Scraper Sources",
            "sources": sources,
            "companies": companies,
            "current_user": current_user,
        },
    )


@router.post("/scrapers/add")
async def add_scraper(
    name: str = Form(...),
    scraper_class: str = Form(...),
    url: str = Form(...),
    company_id: Optional[int] = Form(None),
    cron_schedule: str = Form("0 3 * * *"),
    selenium_required: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    db.add(ScraperSource(
        name=name.strip(),
        scraper_class=scraper_class.strip(),
        url=url.strip(),
        company_id=company_id or None,
        cron_schedule=cron_schedule.strip() or "0 3 * * *",
        selenium_required=selenium_required,
    ))
    await db.commit()
    return RedirectResponse("/admin/scrapers?success=added", status_code=303)


@router.post("/scrapers/{source_id}/toggle")
async def toggle_scraper(
    source_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    source = await db.get(ScraperSource, source_id)
    if source:
        source.is_active = not source.is_active
        await db.commit()
    return RedirectResponse("/admin/scrapers", status_code=303)


@router.post("/scrapers/{source_id}/run")
async def trigger_scraper_run(
    source_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    source = await db.get(ScraperSource, source_id)
    if source is None:
        raise HTTPException(status_code=404)

    from ...workers.email import enqueue_email  # reuse pool helper pattern
    try:
        import arq
        from arq.connections import RedisSettings
        from ...config import settings as _settings

        pool = await arq.create_pool(RedisSettings.from_dsn(_settings.REDIS_URL))
        await pool.enqueue_job("run_scraper", source_id)
        await pool.aclose()
        return RedirectResponse(f"/admin/scrapers?success=queued", status_code=303)
    except Exception:
        return RedirectResponse(f"/admin/scrapers?error=queue_failed", status_code=303)


# ---------------------------------------------------------------------------
# Scraping log
# ---------------------------------------------------------------------------

@router.get("/scraping-log", response_class=HTMLResponse)
async def scraping_log(
    request: Request,
    source: Optional[str] = None,
    page: int = 1,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    stmt = select(ScrapingLog).order_by(ScrapingLog.started_at.desc())
    if source:
        stmt = stmt.where(ScrapingLog.job_board == source)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = await db.scalar(count_stmt) or 0
    per_page = 50
    import math
    total_pages = max(1, math.ceil(total / per_page))
    page = max(1, min(page, total_pages))

    logs = (
        await db.execute(stmt.offset((page - 1) * per_page).limit(per_page))
    ).scalars().all()

    sources = (
        await db.execute(
            select(ScrapingLog.job_board).distinct().order_by(ScrapingLog.job_board)
        )
    ).scalars().all()

    return templates.TemplateResponse(
        request,
        "admin/scraping_log.html",
        {
            "title": "Scraping Log",
            "logs": logs,
            "sources": sources,
            "source_filter": source,
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "current_user": current_user,
        },
    )


# ---------------------------------------------------------------------------
# User management  (7.4)
# ---------------------------------------------------------------------------

@router.get("/users", response_class=HTMLResponse)
async def users_list(
    request: Request,
    q: Optional[str] = None,
    page: int = 1,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    import math

    stmt = select(User).order_by(User.created_at.desc())
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(User.email.ilike(like), User.full_name.ilike(like)))

    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    per_page = 50
    total_pages = max(1, math.ceil(total / per_page))
    page = max(1, min(page, total_pages))

    users = (
        await db.execute(stmt.offset((page - 1) * per_page).limit(per_page))
    ).scalars().all()

    return templates.TemplateResponse(
        request,
        "admin/users.html",
        {
            "title": "Manage Users",
            "users": users,
            "q": q or "",
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "current_user": current_user,
        },
    )


@router.post("/users/{user_id}/toggle-active")
async def toggle_user_active(
    user_id: int,
    q: Optional[str] = Form(None),
    page: int = Form(1),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404)
    if user.id == current_user.id:
        return RedirectResponse("/admin/users?error=cannot_deactivate_self", status_code=303)
    user.is_active = not user.is_active
    await db.commit()
    qs = f"?page={page}" + (f"&q={q}" if q else "")
    return RedirectResponse(f"/admin/users{qs}", status_code=303)


# ---------------------------------------------------------------------------
# Moderator management  (7.5)
# ---------------------------------------------------------------------------

@router.get("/moderators", response_class=HTMLResponse)
async def moderators_list(
    request: Request,
    q: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    staff = (
        await db.execute(
            select(User)
            .where(or_(User.is_admin == True, User.is_moderator == True))
            .order_by(User.is_admin.desc(), User.full_name, User.email)
        )
    ).scalars().all()

    search_results: list[User] = []
    if q:
        like = f"%{q.strip()}%"
        search_results = (
            await db.execute(
                select(User)
                .where(
                    or_(User.email.ilike(like), User.full_name.ilike(like)),
                    User.is_active == True,
                    User.is_moderator == False,
                    User.is_admin == False,
                )
                .order_by(User.full_name, User.email)
                .limit(10)
            )
        ).scalars().all()

    return templates.TemplateResponse(
        request,
        "admin/moderators.html",
        {
            "title": "Manage Moderators",
            "staff": staff,
            "search_results": search_results,
            "q": q or "",
            "current_user": current_user,
        },
    )


@router.post("/moderators/{user_id}/promote")
async def promote_moderator(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404)
    user.is_moderator = True
    await db.commit()
    return RedirectResponse("/admin/moderators?success=promoted", status_code=303)


@router.post("/moderators/{user_id}/demote")
async def demote_moderator(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404)
    if user.id == current_user.id:
        return RedirectResponse("/admin/moderators?error=cannot_remove_self", status_code=303)
    if user.is_admin:
        return RedirectResponse("/admin/moderators?error=cannot_demote_admin", status_code=303)
    user.is_moderator = False
    await db.commit()
    return RedirectResponse("/admin/moderators?success=demoted", status_code=303)
