import base64
import csv
import io
import json
from datetime import datetime
from typing import Optional, Type

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...database import get_db
from ...dependencies import require_admin
from ...models.company import Company, CompanySite, CompanySocial, UserCompanyRole
from ...models.job import JobListing
from ...models.reference import (
    City,
    CompanyType,
    Experience,
    Function,
    FunctionSpecialty,
    Industry,
    JobType,
    OfficeLocation,
    Skill,
    SocialMediaType,
    State,
)
from ...models.scraping import ScraperSource, ScrapingLog
from ...models.user import User
from ...templates import templates
from ...utils import generate_slug, sanitize_url

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Reference table registry  (slug → model, display label)
# ---------------------------------------------------------------------------

_REFERENCE_REGISTRY: dict[str, tuple[type, str]] = {
    "company-types":    (CompanyType,     "Company Types"),
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


# ---------------------------------------------------------------------------
# Import companies from CSV  (issue #26)
# ---------------------------------------------------------------------------

_IMPORT_REQUIRED_COLS = {"common_name", "company_type"}


@router.get("/import-companies", response_class=HTMLResponse)
async def import_companies_get(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    company_types = (
        await db.execute(select(CompanyType).where(CompanyType.is_active == True).order_by(CompanyType.name))
    ).scalars().all()

    return templates.TemplateResponse(
        request,
        "admin/import_companies.html",
        {
            "title": "Import Companies",
            "current_user": current_user,
            "step": "upload",
            "company_types": company_types,
        },
    )


@router.post("/import-companies/preview", response_class=HTMLResponse)
async def import_companies_preview(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    company_types = (
        await db.execute(select(CompanyType).where(CompanyType.is_active == True).order_by(CompanyType.name))
    ).scalars().all()

    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    fieldnames = [f.strip().lower() for f in (reader.fieldnames or [])]

    if not _IMPORT_REQUIRED_COLS.issubset(set(fieldnames)):
        missing = _IMPORT_REQUIRED_COLS - set(fieldnames)
        return templates.TemplateResponse(
            request,
            "admin/import_companies.html",
            {
                "title": "Import Companies",
                "current_user": current_user,
                "step": "upload",
                "company_types": company_types,
                "error": f"Missing required column(s): {', '.join(sorted(missing))}. "
                         f"Got: {', '.join(fieldnames) or '(no columns found)'}",
            },
        )

    company_type_map = {ct.name.lower(): ct.id for ct in company_types}

    existing_names = {
        n.lower()
        for n in (await db.execute(select(Company.common_name))).scalars().all()
    }

    rows_to_import: list[dict] = []
    rows_skipped: list[dict] = []
    rows_errors: list[dict] = []

    for line_num, raw_row in enumerate(reader, start=2):
        row = {k.strip().lower(): (v.strip() if v else "") for k, v in raw_row.items()}

        common_name = row.get("common_name", "").strip()
        if not common_name:
            rows_errors.append({"row": line_num, "common_name": "—", "reason": "common_name is blank"})
            continue

        if common_name.lower() in existing_names:
            rows_skipped.append({"row": line_num, "common_name": common_name, "reason": "already exists"})
            continue

        ct_name = row.get("company_type", "").strip()
        ct_id = company_type_map.get(ct_name.lower())
        if ct_id is None:
            rows_errors.append({
                "row": line_num,
                "common_name": common_name,
                "reason": f"unknown company_type \"{ct_name}\"",
            })
            continue

        date_founded = None
        if row.get("date_founded"):
            try:
                date_founded = datetime.strptime(row["date_founded"], "%Y-%m-%d").isoformat()
            except ValueError:
                rows_errors.append({
                    "row": line_num,
                    "common_name": common_name,
                    "reason": f"invalid date_founded \"{row['date_founded']}\" — use YYYY-MM-DD",
                })
                continue

        date_closed = None
        if row.get("date_closed"):
            try:
                date_closed = datetime.strptime(row["date_closed"], "%Y-%m-%d").isoformat()
            except ValueError:
                rows_errors.append({
                    "row": line_num,
                    "common_name": common_name,
                    "reason": f"invalid date_closed \"{row['date_closed']}\" — use YYYY-MM-DD",
                })
                continue

        rows_to_import.append({
            "common_name": common_name,
            "legal_name": row.get("legal_name") or None,
            "company_type_id": ct_id,
            "website": sanitize_url(row.get("website")),
            "jobboard": sanitize_url(row.get("jobboard")),
            "description": row.get("description") or None,
            "company_size": row.get("company_size") or None,
            "date_founded": date_founded,
            "date_closed": date_closed,
            # Social media
            "linkedin":  sanitize_url(row.get("linkedin")),
            "github":    sanitize_url(row.get("github")),
            "facebook":  sanitize_url(row.get("facebook")),
            "instagram": sanitize_url(row.get("instagram")),
            "twitter":   sanitize_url(row.get("twitter")),
            # Location
            "street":     row.get("street") or None,
            "city_name":  row.get("city") or None,
            "state_abbr": row.get("state") or None,
            "zip":        row.get("zip") or None,
            "phone":      row.get("phone") or None,
        })
        existing_names.add(common_name.lower())

    encoded = base64.b64encode(json.dumps(rows_to_import).encode()).decode()

    return templates.TemplateResponse(
        request,
        "admin/import_companies.html",
        {
            "title": "Import Companies — Preview",
            "current_user": current_user,
            "step": "preview",
            "company_types": company_types,
            "import_count": len(rows_to_import),
            "skip_count": len(rows_skipped),
            "error_count": len(rows_errors),
            "preview_rows": rows_to_import[:20],
            "rows_skipped": rows_skipped[:10],
            "rows_errors": rows_errors[:10],
            "encoded_rows": encoded,
        },
    )


@router.post("/import-companies/confirm")
async def import_companies_confirm(
    encoded_rows: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        rows: list[dict] = json.loads(base64.b64decode(encoded_rows.encode()).decode())
    except Exception:
        return RedirectResponse("/admin/import-companies?error=invalid_data", status_code=303)

    now = datetime.now()
    imported = 0

    smt_rows = (await db.execute(select(SocialMediaType))).scalars().all()
    smt_id_map = {s.name.lower(): s.id for s in smt_rows}
    _SOCIAL_COLS = {
        "linkedin":  "linkedin",
        "github":    "github",
        "facebook":  "facebook",
        "instagram": "instagram",
        "twitter":   "twitter/x",
    }

    state_cache: dict = {}
    city_cache: dict = {}

    for row in rows:
        base = generate_slug(row["common_name"])
        slug = base
        counter = 2
        while await db.scalar(select(Company.id).where(Company.slug == slug)):
            slug = f"{base}-{counter}"
            counter += 1

        date_founded = datetime.fromisoformat(row["date_founded"]) if row.get("date_founded") else None
        date_closed = datetime.fromisoformat(row["date_closed"]) if row.get("date_closed") else None

        company = Company(
            slug=slug,
            common_name=row["common_name"],
            legal_name=row.get("legal_name"),
            company_type=row["company_type_id"],
            website=row.get("website"),
            jobboard=row.get("jobboard"),
            description=row.get("description"),
            company_size=row.get("company_size"),
            date_founded=date_founded,
            date_closed=date_closed,
            approved=True,
            approved_by=current_user.id,
            approved_at=now,
            is_scraped=False,
        )
        db.add(company)
        await db.flush()

        for col, smt_key in _SOCIAL_COLS.items():
            url = row.get(col)
            if url:
                smt_id = smt_id_map.get(smt_key)
                if smt_id:
                    db.add(CompanySocial(
                        company_id=company.id,
                        social_media_type_id=smt_id,
                        company_url=url,
                    ))

        street     = row.get("street") or None
        city_name  = row.get("city_name") or None
        state_abbr = row.get("state_abbr") or None
        postcode   = row.get("zip") or None
        phone      = row.get("phone") or None

        if any([street, city_name, state_abbr, postcode, phone]):
            state_id = None
            if state_abbr:
                key = state_abbr.upper()
                if key not in state_cache:
                    state_cache[key] = await db.scalar(
                        select(State.id).where(State.abbreviation == key)
                    )
                state_id = state_cache[key]

            city_id = None
            if city_name:
                cache_key = (city_name.lower(), state_id)
                if cache_key not in city_cache:
                    stmt = select(City.id).where(City.city_name.ilike(city_name))
                    if state_id:
                        stmt = stmt.where(City.state_id == state_id)
                    city_cache[cache_key] = await db.scalar(stmt)
                city_id = city_cache[cache_key]

            db.add(CompanySite(
                company_id=company.id,
                address1=street,
                city_id=city_id,
                state_id=state_id,
                postcode=postcode,
                phone=phone,
                is_headquarters=True,
            ))

        imported += 1

    await db.commit()
    return RedirectResponse(f"/admin/import-companies?success={imported}", status_code=303)
