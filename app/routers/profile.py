from datetime import date
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import get_db
from ..dependencies import require_user
from ..models.reference import Certification, Skill
from ..models.user import User, UserCertification, UserSkill
from ..templates import templates

router = APIRouter(prefix="/profile", tags=["profile"])

PROFICIENCY_LEVELS = ["beginner", "intermediate", "advanced", "expert", "unknown"]


def _parse_date(val: str | None) -> date | None:
    if not val:
        return None
    try:
        return date.fromisoformat(val.strip())
    except ValueError:
        return None


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

    user_certs = (
        await db.execute(
            select(UserCertification)
            .where(UserCertification.user_id == user.id)
            .options(
                selectinload(UserCertification.certification)
                .selectinload(Certification.provider)
            )
            .order_by(UserCertification.created_at)
        )
    ).scalars().all()

    all_certs = (
        await db.execute(
            select(Certification)
            .where(Certification.is_active == True)
            .options(selectinload(Certification.provider))
            .order_by(Certification.name)
        )
    ).scalars().all()

    return {
        "user_skills": user_skills,
        "all_skills": all_skills,
        "proficiency_levels": PROFICIENCY_LEVELS,
        "user_certs": user_certs,
        "all_certs": all_certs,
        "today": date.today(),
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


# ---------------------------------------------------------------------------
# Certifications
# ---------------------------------------------------------------------------

@router.post("/certifications/add")
async def profile_certs_add(
    request: Request,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    form = await request.form()
    raw_cert_id = form.get("certification_id")

    if not raw_cert_id:
        return RedirectResponse("/profile?error=invalid_cert", status_code=303)
    try:
        cert_id = int(raw_cert_id)
    except ValueError:
        return RedirectResponse("/profile?error=invalid_cert", status_code=303)

    cert = await db.scalar(
        select(Certification).where(Certification.id == cert_id, Certification.is_active == True)
    )
    if not cert:
        return RedirectResponse("/profile?error=invalid_cert", status_code=303)

    existing = await db.scalar(
        select(UserCertification).where(
            UserCertification.user_id == current_user.id,
            UserCertification.certification_id == cert_id,
        )
    )
    if existing:
        return RedirectResponse("/profile?error=cert_already_added", status_code=303)

    obtained = _parse_date(form.get("obtained_date"))
    expiry = _parse_date(form.get("expiry_date"))

    if obtained and expiry and expiry <= obtained:
        return RedirectResponse("/profile?error=cert_date_invalid", status_code=303)

    credential_id = (form.get("credential_id") or "").strip() or None
    raw_url = (form.get("credential_url") or "").strip()
    credential_url = raw_url if raw_url.startswith(("http://", "https://")) else None

    db.add(UserCertification(
        user_id=current_user.id,
        certification_id=cert_id,
        obtained_date=datetime(obtained.year, obtained.month, obtained.day) if obtained else None,
        expiry_date=datetime(expiry.year, expiry.month, expiry.day) if expiry else None,
        credential_id=credential_id,
        credential_url=credential_url,
    ))
    await db.commit()
    return RedirectResponse("/profile?success=cert_added", status_code=303)


@router.post("/certifications/{user_cert_id}/remove")
async def profile_certs_remove(
    user_cert_id: int,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    user_cert = await db.scalar(
        select(UserCertification).where(
            UserCertification.id == user_cert_id,
            UserCertification.user_id == current_user.id,
        )
    )
    if user_cert:
        await db.delete(user_cert)
        await db.commit()
    return RedirectResponse("/profile?success=cert_removed", status_code=303)
