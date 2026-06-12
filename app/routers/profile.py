from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..dependencies import require_user
from ..models.user import User
from ..templates import templates

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    current_user: User = Depends(require_user),
):
    return templates.TemplateResponse(
        request,
        "profile/edit.html",
        {"title": "My Profile", "current_user": current_user},
    )


@router.post("", response_class=HTMLResponse)
async def profile_save(
    request: Request,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    form = await request.form()
    display_name = (form.get("display_name") or "").strip()
    headline = (form.get("headline") or "").strip()

    current_user.full_name = display_name or None
    current_user.headline = headline or None
    await db.commit()

    return RedirectResponse("/profile?success=profile_saved", status_code=303)
