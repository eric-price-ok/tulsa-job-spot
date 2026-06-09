from datetime import datetime
from typing import Optional

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..models.user import User
from ..templates import templates
from ..utils import is_safe_redirect

router = APIRouter(prefix="/auth", tags=["auth"])

# ---------------------------------------------------------------------------
# OAuth client setup — only registers providers that have credentials set
# ---------------------------------------------------------------------------

oauth = OAuth()

_PROVIDER_CONFIG = {
    "google": {
        "server_metadata_url": "https://accounts.google.com/.well-known/openid-configuration",
        "client_kwargs": {"scope": "openid email profile"},
    },
    "github": {
        "access_token_url": "https://github.com/login/oauth/access_token",
        "authorize_url": "https://github.com/login/oauth/authorize",
        "api_base_url": "https://api.github.com/",
        "client_kwargs": {"scope": "user:email"},
    },
    "linkedin": {
        "server_metadata_url": "https://www.linkedin.com/oauth/.well-known/openid-configuration",
        "client_kwargs": {"scope": "openid profile email"},
    },
    "microsoft": {
        "server_metadata_url": "https://login.microsoftonline.com/common/v2.0/.well-known/openid-configuration",
        "client_kwargs": {"scope": "openid email profile"},
    },
    "facebook": {
        "access_token_url": "https://graph.facebook.com/oauth/access_token",
        "authorize_url": "https://www.facebook.com/dialog/oauth",
        "api_base_url": "https://graph.facebook.com/",
        "client_kwargs": {"scope": "email,public_profile"},
    },
}

_PROVIDER_CREDENTIALS = {
    "google":    (settings.GOOGLE_CLIENT_ID,    settings.GOOGLE_CLIENT_SECRET),
    "github":    (settings.GITHUB_CLIENT_ID,    settings.GITHUB_CLIENT_SECRET),
    "linkedin":  (settings.LINKEDIN_CLIENT_ID,  settings.LINKEDIN_CLIENT_SECRET),
    "microsoft": (settings.MICROSOFT_CLIENT_ID, settings.MICROSOFT_CLIENT_SECRET),
    "facebook":  (settings.FACEBOOK_CLIENT_ID,  settings.FACEBOOK_CLIENT_SECRET),
}

for provider, (cid, csec) in _PROVIDER_CREDENTIALS.items():
    if cid and csec:
        oauth.register(
            name=provider,
            client_id=cid,
            client_secret=csec,
            **_PROVIDER_CONFIG[provider],
        )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if request.session.get("user_id"):
        next_url = request.query_params.get("next", "/")
        if not is_safe_redirect(next_url):
            next_url = "/"
        return RedirectResponse(next_url)
    if next_url := request.query_params.get("next"):
        if is_safe_redirect(next_url):
            request.session["next"] = next_url
    return templates.TemplateResponse(
        request,
        "auth/login.html",
        {"title": "Sign In", "enabled_providers": settings.enabled_providers},
    )


@router.get("/login/{provider}")
async def oauth_login(provider: str, request: Request):
    if provider not in settings.enabled_providers:
        return RedirectResponse("/auth/login")
    if next_url := request.query_params.get("next"):
        if is_safe_redirect(next_url):
            request.session["next"] = next_url
    client = oauth.create_client(provider)
    redirect_uri = str(request.url_for("oauth_callback", provider=provider))
    return await client.authorize_redirect(request, redirect_uri)


@router.get("/callback/{provider}", name="oauth_callback")
async def oauth_callback(provider: str, request: Request, db: AsyncSession = Depends(get_db)):
    if provider not in settings.enabled_providers:
        return RedirectResponse("/auth/login")

    client = oauth.create_client(provider)

    try:
        token = await client.authorize_access_token(request)
    except OAuthError:
        return RedirectResponse("/auth/login?error=oauth_failed")

    try:
        user_info = await _extract_user_info(provider, token, client)
    except Exception:
        return RedirectResponse("/auth/login?error=profile_fetch_failed")

    if not user_info.get("email"):
        return RedirectResponse("/auth/login?error=no_email")

    user = await _get_or_create_user(db, provider, user_info)
    if user is None:
        return RedirectResponse("/auth/login?error=email_conflict")

    user.last_login_at = datetime.now()
    await db.commit()

    request.session["user_id"] = user.id
    next_url = request.session.pop("next", "/")
    if not is_safe_redirect(next_url):
        next_url = "/"
    return RedirectResponse(next_url, status_code=303)


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=303)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _extract_user_info(provider: str, token: dict, client) -> dict:
    if provider == "google":
        info = token.get("userinfo") or {}
        return {
            "email": info.get("email"),
            "full_name": info.get("name"),
            "avatar_url": info.get("picture"),
            "subject": info.get("sub"),
        }

    if provider == "github":
        resp = await client.get("user", token=token)
        data = resp.json()
        email = data.get("email")
        if not email:
            emails_resp = await client.get("user/emails", token=token)
            for e in emails_resp.json():
                if e.get("primary") and e.get("verified"):
                    email = e["email"]
                    break
        return {
            "email": email,
            "full_name": data.get("name") or data.get("login"),
            "avatar_url": data.get("avatar_url"),
            "subject": str(data["id"]),
        }

    if provider == "linkedin":
        info = token.get("userinfo") or {}
        if not info:
            resp = await client.get("userinfo", token=token)
            info = resp.json()
        return {
            "email": info.get("email"),
            "full_name": info.get("name"),
            "avatar_url": info.get("picture"),
            "subject": info.get("sub"),
        }

    if provider == "microsoft":
        info = token.get("userinfo") or {}
        return {
            "email": info.get("email") or info.get("preferred_username"),
            "full_name": info.get("name"),
            "avatar_url": None,
            "subject": info.get("sub"),
        }

    if provider == "facebook":
        resp = await client.get("me?fields=id,name,email,picture.type(large)", token=token)
        data = resp.json()
        pic = data.get("picture", {})
        if isinstance(pic, dict):
            avatar = pic.get("data", {}).get("url")
        else:
            avatar = None
        return {
            "email": data.get("email"),
            "full_name": data.get("name"),
            "avatar_url": avatar,
            "subject": str(data["id"]),
        }

    return {}


async def _get_or_create_user(
    db: AsyncSession, provider: str, info: dict
) -> Optional[User]:
    email = info["email"]
    subject = info["subject"]

    # Look up by OAuth identity first
    result = await db.execute(
        select(User).where(User.oauth_provider == provider, User.oauth_subject == subject)
    )
    user = result.scalar_one_or_none()
    if user:
        if info.get("avatar_url"):
            user.avatar_url = info["avatar_url"]
        if info.get("full_name") and not user.full_name:
            user.full_name = info["full_name"]
        await db.commit()
        await db.refresh(user)
        return user

    # Check if email already registered
    result = await db.execute(select(User).where(User.email == email))
    existing = result.scalar_one_or_none()
    if existing:
        if existing.oauth_provider == "seed":
            # Seed-bootstrapped admin account — claim it with the real OAuth identity
            existing.oauth_provider = provider
            existing.oauth_subject = subject
            if info.get("avatar_url"):
                existing.avatar_url = info["avatar_url"]
            if info.get("full_name") and not existing.full_name:
                existing.full_name = info["full_name"]
            await db.commit()
            await db.refresh(existing)
            return existing
        # Genuine email conflict — user must sign in with their original provider
        return None

    # New user
    user = User(
        email=email,
        full_name=info.get("full_name"),
        avatar_url=info.get("avatar_url"),
        oauth_provider=provider,
        oauth_subject=subject,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
