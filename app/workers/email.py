import asyncio
import logging
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from ..config import settings

logger = logging.getLogger(__name__)


def _build_message(notification_type: str, ctx: dict) -> tuple[str, str, str]:
    """Return (subject, plain_text, html)."""
    site = settings.SITE_NAME
    domain = settings.DOMAIN

    if notification_type == "company_submitted":
        subject = f"[{site}] New company pending approval"
        body = (
            f"A new company has been submitted for approval.\n\n"
            f"Company: {ctx['company_name']}\n"
            f"Submitted by: {ctx['submitted_by']}\n\n"
            f"Review: https://{domain}/moderator/companies\n"
        )
    elif notification_type == "company_approved":
        subject = f"[{site}] Your company has been approved"
        body = (
            f"Your company \"{ctx['company_name']}\" has been approved on {site}.\n\n"
            f"You have been granted the {ctx['role'].replace('_', ' ')} role.\n\n"
            f"Post your first job: https://{domain}/jobs/create\n"
        )
    elif notification_type == "company_rejected":
        subject = f"[{site}] Company registration not approved"
        body = (
            f"Your company registration for \"{ctx['company_name']}\" was not approved.\n\n"
            f"Reason: {ctx['reason']}\n\n"
            f"Questions? Reach us at https://{domain}\n"
        )
    elif notification_type == "role_requested":
        subject = f"[{site}] New role request for {ctx['company_name']}"
        body = (
            f"{ctx['requested_by']} has requested to join {ctx['company_name']}.\n\n"
            f"Review: https://{domain}/moderator/roles\n"
        )
    elif notification_type == "role_approved":
        subject = f"[{site}] Your role request was approved"
        body = (
            f"Your request to join {ctx['company_name']} as "
            f"{ctx['role'].replace('_', ' ')} has been approved.\n\n"
            f"Post a job: https://{domain}/jobs/create\n"
        )
    elif notification_type == "role_rejected":
        subject = f"[{site}] Role request not approved"
        body = (
            f"Your request to join {ctx['company_name']} was not approved.\n\n"
            f"Reason: {ctx['reason']}\n"
        )
    elif notification_type == "invite_sent":
        subject = f"You've been invited to post jobs on {site}"
        body = (
            f"{ctx['invited_by_name']} has invited you to post jobs for "
            f"{ctx['company_name']} on {site}.\n\n"
            f"Accept your invite (expires in 7 days):\n"
            f"https://{domain}/invites/{ctx['token']}\n"
        )
    elif notification_type == "job_submitted":
        subject = f"[{site}] New job listing pending approval"
        body = (
            f"A new job listing has been submitted for approval.\n\n"
            f"Job: {ctx['job_title']}\n"
            f"Company: {ctx['company_name']}\n"
            f"Posted by: {ctx['posted_by']}\n\n"
            f"Review: https://{domain}/moderator/jobs\n"
        )
    elif notification_type == "job_approved":
        subject = f"[{site}] Your job listing is live"
        body = (
            f"Your job listing \"{ctx['job_title']}\" has been approved and is now live.\n\n"
            f"View: https://{domain}/jobs/{ctx['job_id']}\n"
        )
    elif notification_type == "job_rejected":
        subject = f"[{site}] Job listing not approved"
        body = (
            f"Your job listing \"{ctx['job_title']}\" was not approved.\n\n"
            f"Reason: {ctx['reason']}\n"
        )
    else:
        subject = f"[{site}] Notification"
        body = str(ctx)

    html = (
        "<div style='font-family:sans-serif;font-size:14px;line-height:1.6;"
        "max-width:600px;margin:0 auto;padding:24px'>"
        f"<pre style='white-space:pre-wrap;font-family:inherit'>{body}</pre>"
        "</div>"
    )
    return subject, body, html


def _send_smtp(to_email: str, subject: str, text_body: str, html_body: str) -> None:
    if not settings.SMTP_HOST:
        logger.info("SMTP not configured — skipping email to %s: %s", to_email, subject)
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM
    msg["To"] = to_email
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        if settings.SMTP_TLS:
            context = ssl.create_default_context()
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as smtp:
                smtp.starttls(context=context)
                if settings.SMTP_USER:
                    smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                smtp.sendmail(settings.SMTP_FROM, to_email, msg.as_string())
        else:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as smtp:
                if settings.SMTP_USER:
                    smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                smtp.sendmail(settings.SMTP_FROM, to_email, msg.as_string())
        logger.info("Email sent to %s: %s", to_email, subject)
    except Exception as exc:
        logger.error("Failed to send email to %s: %s", to_email, exc)


async def send_notification_email(
    ctx: dict[str, Any], notification_type: str, context: dict
) -> None:
    """ARQ task: send a transactional notification email."""
    to_email = context.get("to_email")

    # Moderator-broadcast notifications — fan out to all staff
    if not to_email and notification_type in ("company_submitted", "role_requested", "job_submitted"):
        from sqlalchemy import or_, select

        from ..database import AsyncSessionLocal
        from ..models.user import User

        async with AsyncSessionLocal() as db:
            emails = (
                await db.execute(
                    select(User.email).where(
                        or_(User.is_moderator == True, User.is_admin == True),
                        User.is_active == True,
                    )
                )
            ).scalars().all()

        subject, text_body, html_body = _build_message(notification_type, context)
        for email in emails:
            await asyncio.to_thread(_send_smtp, email, subject, text_body, html_body)
        return

    if not to_email:
        logger.warning(
            "send_notification_email missing to_email — type=%s", notification_type
        )
        return

    subject, text_body, html_body = _build_message(notification_type, context)
    await asyncio.to_thread(_send_smtp, to_email, subject, text_body, html_body)


async def enqueue_email(notification_type: str, context: dict) -> None:
    """Enqueue a notification email via ARQ. Silently degrades if Redis is unavailable."""
    try:
        import arq

        pool = await arq.create_pool(
            arq.connections.RedisSettings.from_dsn(settings.REDIS_URL)
        )
        await pool.enqueue_job("send_notification_email", notification_type, context)
        await pool.aclose()
    except Exception as exc:
        logger.warning("Could not enqueue email (type=%s): %s", notification_type, exc)
