from sqlalchemy import Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SiteSettings(Base):
    __tablename__ = "site_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recruiters_page_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    job_boards_section_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
