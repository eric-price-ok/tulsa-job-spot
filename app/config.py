from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DOMAIN: str = "localhost"
    SECRET_KEY: str = "dev-secret-change-me"
    DATABASE_URL: str = "postgresql+asyncpg://tulsajobspot:tulsajobspot@db:5432/tulsajobspot"
    REDIS_URL: str = "redis://redis:6379"

    # OAuth providers — only those with both id+secret are enabled
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    LINKEDIN_CLIENT_ID: Optional[str] = None
    LINKEDIN_CLIENT_SECRET: Optional[str] = None
    GITHUB_CLIENT_ID: Optional[str] = None
    GITHUB_CLIENT_SECRET: Optional[str] = None
    MICROSOFT_CLIENT_ID: Optional[str] = None
    MICROSOFT_CLIENT_SECRET: Optional[str] = None
    FACEBOOK_CLIENT_ID: Optional[str] = None
    FACEBOOK_CLIENT_SECRET: Optional[str] = None

    # Email
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM: str = "noreply@localhost"
    SMTP_TLS: bool = True

    # Admin bootstrap
    ADMIN_EMAIL: Optional[str] = None

    # AI extraction
    ANTHROPIC_API_KEY: Optional[str] = None

    # Site branding (configurable for forks)
    SITE_NAME: str = "Tulsa Job Spot"
    SITE_TAGLINE: str = "Find your next job in Tulsa, Oklahoma"
    CONTACT_EMAIL: str = "hello@localhost"

    ITEMS_PER_PAGE: int = 25

    @property
    def enabled_providers(self) -> list[str]:
        pairs = [
            ("google", self.GOOGLE_CLIENT_ID, self.GOOGLE_CLIENT_SECRET),
            ("linkedin", self.LINKEDIN_CLIENT_ID, self.LINKEDIN_CLIENT_SECRET),
            ("github", self.GITHUB_CLIENT_ID, self.GITHUB_CLIENT_SECRET),
            ("microsoft", self.MICROSOFT_CLIENT_ID, self.MICROSOFT_CLIENT_SECRET),
            ("facebook", self.FACEBOOK_CLIENT_ID, self.FACEBOOK_CLIENT_SECRET),
        ]
        return [name for name, cid, csec in pairs if cid and csec]

    @property
    def is_production(self) -> bool:
        return self.DOMAIN not in ("localhost", "127.0.0.1")


settings = Settings()
