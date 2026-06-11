import hashlib
import os
from datetime import datetime

from fastapi.templating import Jinja2Templates

from .config import settings
from .utils import job_url_slug

templates = Jinja2Templates(directory="app/templates")

# Globals available in every template without passing explicitly
templates.env.globals["settings"] = settings
templates.env.globals["enabled_providers"] = settings.enabled_providers
templates.env.globals["now"] = datetime.now

def _css_fingerprint() -> str:
    path = os.path.join(os.path.dirname(__file__), "static", "css", "main.css")
    try:
        with open(path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()[:8]
    except OSError:
        return "0"

templates.env.globals["css_v"] = _css_fingerprint()
templates.env.globals["job_url_slug"] = job_url_slug


def _format_phone(value: str | None) -> str:
    if not value:
        return ""
    digits = "".join(c for c in value if c.isdigit())
    if len(digits) == 11 and digits[0] == "1":
        digits = digits[1:]
    if len(digits) == 10:
        return f"{digits[:3]}.{digits[3:6]}.{digits[6:]}"
    return value


templates.env.filters["format_phone"] = _format_phone
