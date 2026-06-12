from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from .config import settings
from .routers.admin import router as admin_router
from .routers.auth import router as auth_router
from .routers.companies import router as companies_router
from .routers.jobs import router as jobs_router
from .routers.moderator import router as moderator_router
from .routers.profile import router as profile_router
from .templates import templates


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        for deprecated in ("X-XSS-Protection", "Expires"):
            try:
                del response.headers[deprecated]
            except KeyError:
                pass
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif "cache-control" not in response.headers:
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
        ct = response.headers.get("content-type", "")
        if ct.startswith("text/") and "charset" not in ct:
            response.headers["content-type"] = ct + "; charset=utf-8"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    from .database import AsyncSessionLocal
    from .models.settings import SiteSettings
    from .templates import set_recruiters_enabled, set_job_boards_enabled
    from sqlalchemy import select as _select
    async with AsyncSessionLocal() as db:
        row = await db.scalar(_select(SiteSettings))
        if row:
            set_recruiters_enabled(row.recruiters_page_enabled)
            set_job_boards_enabled(row.job_boards_section_enabled)
    yield


app = FastAPI(
    title=settings.SITE_NAME,
    description=settings.SITE_TAGLINE,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    max_age=60 * 60 * 24 * 30,
    https_only=settings.is_production,
    same_site="lax",
)
# Must be outermost — tells FastAPI to trust X-Forwarded-Proto from Caddy
# so request.url_for() generates https:// URLs
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")
# Added after ProxyHeadersMiddleware so it wraps all responses including static files
app.add_middleware(SecurityHeadersMiddleware)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth_router)
app.include_router(jobs_router)
app.include_router(companies_router)
app.include_router(moderator_router)
app.include_router(admin_router)
app.include_router(profile_router)


@app.get("/")
async def home():
    return RedirectResponse("/jobs")


@app.exception_handler(404)
async def not_found(request: Request, exc):
    return templates.TemplateResponse(
        request, "errors/404.html", {"title": "Page Not Found"}, status_code=404
    )


@app.exception_handler(500)
async def server_error(request: Request, exc):
    return templates.TemplateResponse(
        request, "errors/500.html", {"title": "Server Error"}, status_code=500
    )
