from arq.connections import RedisSettings

from ..config import settings


class WorkerSettings:
    # Background job functions registered here as they're implemented.
    functions = []
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    max_jobs = 10
