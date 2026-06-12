from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import get_db
from ..dependencies import require_user
from ..models.reference import Skill
from ..models.user import User, UserSkill
from ..templates import templates

router = APIRouter(prefix="/profile", tags=["profile"])

PROFICIENCY_LEVELS = ["beginner", "intermediate", "advanced", "expert", "unknown"]


async def _load_profile_context(user: User, db: AsyncSession) -> dict:
    user_skills = (
        await db.execute(
            select(UserSkill)
            .where(UserSkill.user_id == user.id)
            .options(selectinload(UserSkill.skill))
            .order_by(UserSkill.is_featured.desc(), UserSkill.created_at)
        )
    ).scalars().all()

    all_skills = (
        await db.execute(
            select(Skill).where(Skill.is_active == True).order_by(Skill.name)
        )
    ).scalars().all()

    return {
        "user_skills": user_skills,
        "all_skills": all_skills,
        "proficiency_levels": PROFICIENCY_LEVELS,
    }


@router.get("", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    ctx = await _load_profile_context(current_user, db)
    return templates.TemplateResponse(
        request,
        "profile/edit.html",
        {"title": "My Profile", "current_user": current_user, **ctx},
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


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------

@router.post("/skills/add")
async def profile_skills_add(
    request: Request,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    form = await request.form()
    raw_skill_id = form.get("skill_id")
    proficiency = (form.get("proficiency_level") or "unknown").strip()
    raw_years = form.get("years_experience")

    if not raw_skill_id:
        return RedirectResponse("/profile?error=invalid_skill", status_code=303)
    try:
        skill_id = int(raw_skill_id)
    except ValueError:
        return RedirectResponse("/profile?error=invalid_skill", status_code=303)

    skill = await db.scalar(
        select(Skill).where(Skill.id == skill_id, Skill.is_active == True)
    )
    if not skill:
        return RedirectResponse("/profile?error=invalid_skill", status_code=303)

    existing = await db.scalar(
        select(UserSkill).where(
            UserSkill.user_id == current_user.id,
            UserSkill.skill_id == skill_id,
        )
    )
    if existing:
        return RedirectResponse("/profile?error=skill_already_added", status_code=303)

    if proficiency not in PROFICIENCY_LEVELS:
        proficiency = "unknown"

    years = None
    if raw_years:
        try:
            years = max(0, int(raw_years))
        except ValueError:
            pass

    db.add(UserSkill(
        user_id=current_user.id,
        skill_id=skill_id,
        proficiency_level=proficiency,
        years_experience=years,
    ))
    await db.commit()
    return RedirectResponse("/profile?success=skill_added", status_code=303)


@router.post("/skills/{user_skill_id}/remove")
async def profile_skills_remove(
    user_skill_id: int,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    user_skill = await db.scalar(
        select(UserSkill).where(
            UserSkill.id == user_skill_id,
            UserSkill.user_id == current_user.id,
        )
    )
    if user_skill:
        await db.delete(user_skill)
        await db.commit()
    return RedirectResponse("/profile?success=skill_removed", status_code=303)


@router.post("/skills/{user_skill_id}/feature")
async def profile_skills_feature(
    user_skill_id: int,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    user_skill = await db.scalar(
        select(UserSkill).where(
            UserSkill.id == user_skill_id,
            UserSkill.user_id == current_user.id,
        )
    )
    if not user_skill:
        return RedirectResponse("/profile", status_code=303)

    if user_skill.is_featured:
        user_skill.is_featured = False
    else:
        featured_count = await db.scalar(
            select(func.count(UserSkill.id)).where(
                UserSkill.user_id == current_user.id,
                UserSkill.is_featured == True,
            )
        )
        if featured_count >= 3:
            return RedirectResponse("/profile?error=featured_limit", status_code=303)
        user_skill.is_featured = True

    await db.commit()
    return RedirectResponse("/profile", status_code=303)
