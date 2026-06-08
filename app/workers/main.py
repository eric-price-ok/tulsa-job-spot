from datetime import datetime

from arq import cron
from arq.connections import RedisSettings
from sqlalchemy import delete

from ..config import settings
from ..database import AsyncSessionLocal
from ..models.company import CompanyInvite
from .email import send_notification_email


async def expire_invites(ctx: dict) -> None:
    """Daily: delete un-accepted invites that are past their expires_at."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            delete(CompanyInvite).where(
                CompanyInvite.expires_at < datetime.now(),
                CompanyInvite.accepted == False,
            )
        )
        await db.commit()
    print(f"[expire_invites] Deleted {result.rowcount} expired invites")


class WorkerSettings:
    functions = [send_notification_email]
    cron_jobs = [cron(expire_invites, hour=2, minute=0)]
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    max_jobs = 10
